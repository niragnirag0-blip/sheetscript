"""Prescription, device, and print-job operations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Prescription, PrinterDevice, PrintJob, PrintJobEvent, utcnow
from backend.security import hash_token, new_device_token
import store
from validation import InputError, normalize_prescription, reject_usb_port

ACTIVE_BEFORE_SPOOLER = ("claimed", "downloading", "rendering")
POWER_FIELDS = ("re_sph", "re_cyl", "re_add", "le_sph", "le_cyl", "le_add")
AXIS_FIELDS = ("re_axis", "le_axis")


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def _format_power(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def _format_axis(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(int(Decimal(value)))


def prescription_dict(row: Prescription, latest: PrintJob | None = None) -> dict:
    payload = {
        "id": row.id,
        "legacy_id": row.legacy_id,
        "ref_no": row.ref_no,
        "date": row.card_date.isoformat(),
        "patient_name": row.patient_name,
        "lens": row.lens,
        "retailer": row.retailer,
        "created_at": row.created_at.isoformat(sep=" "),
        "updated_at": row.updated_at.isoformat(sep=" "),
        "created_by": row.created_by,
        "print_status": latest.status if latest else None,
        "print_job_id": latest.id if latest else None,
    }
    for field in POWER_FIELDS:
        payload[field] = _format_power(getattr(row, field))
    for field in AXIS_FIELDS:
        payload[field] = _format_axis(getattr(row, field))
    return payload


def job_dict(job: PrintJob) -> dict:
    return {
        "id": job.id,
        "prescription_id": job.prescription_id,
        "target_device_id": job.target_device_id,
        "device_id": job.device_id,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "spooler_job_id": job.spooler_job_id,
        "lease_expires_at": job.lease_expires_at.isoformat(sep=" ") if job.lease_expires_at else None,
        "created_at": job.created_at.isoformat(sep=" "),
        "assigned_at": job.assigned_at.isoformat(sep=" ") if job.assigned_at else None,
        "started_at": job.started_at.isoformat(sep=" ") if job.started_at else None,
        "submitted_at": job.submitted_at.isoformat(sep=" ") if job.submitted_at else None,
        "completed_at": job.completed_at.isoformat(sep=" ") if job.completed_at else None,
        "physically_printed": False,
    }


def device_dict(device: PrinterDevice) -> dict:
    return {
        "id": device.id,
        "device_name": device.device_name,
        "location": device.location,
        "printer_name": device.printer_name,
        "operating_system": device.operating_system,
        "agent_version": device.agent_version,
        "status": device.status,
        "last_heartbeat_at": device.last_heartbeat_at.isoformat(sep=" ") if device.last_heartbeat_at else None,
        "registered_at": device.registered_at.isoformat(sep=" "),
        "revoked": device.revoked_at is not None,
    }


def event_dict(event: PrintJobEvent) -> dict:
    return {
        "id": event.id,
        "print_job_id": event.print_job_id,
        "event_type": event.event_type,
        "message": event.message,
        "details": event.details,
        "created_at": event.created_at.isoformat(sep=" "),
    }


def add_event(session: Session, job: PrintJob, event_type: str, message: str, details: dict | None = None) -> None:
    session.add(
        PrintJobEvent(
            print_job_id=job.id,
            event_type=event_type,
            message=message[:500],
            details=json.dumps(details or {}, default=str),
        )
    )


def _apply(row: Prescription, data: dict) -> None:
    row.ref_no = data["ref_no"]
    row.card_date = data["date"]
    row.patient_name = data["patient_name"]
    row.lens = data["lens"]
    row.retailer = data["retailer"]
    for field in (*POWER_FIELDS, *AXIS_FIELDS):
        setattr(row, field, data[field])
    row.updated_at = utcnow()


def create_prescription(session: Session, payload: dict, user_id: str | None) -> Prescription:
    data = normalize_prescription(payload)
    row = Prescription(created_by=user_id, created_at=utcnow(), updated_at=utcnow())
    _apply(row, data)
    session.add(row)
    session.commit()
    return row


def list_prescriptions(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    newest_first: bool = True,
) -> tuple[list[dict], int]:
    query = select(Prescription).where(Prescription.deleted_at.is_(None))
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Prescription.patient_name.ilike(term),
                Prescription.ref_no.ilike(term),
                Prescription.retailer.ilike(term),
                Prescription.lens.ilike(term),
            )
        )
    order = (Prescription.card_date.desc(), Prescription.created_at.desc()) if newest_first else (
        Prescription.card_date.asc(),
        Prescription.created_at.asc(),
    )
    total = len(session.scalars(query).all())
    rows = session.scalars(query.order_by(*order).limit(limit).offset(offset)).all()
    return [prescription_dict(row, latest_job(session, row.id)) for row in rows], total


def get_prescription(session: Session, prescription_id: str) -> Prescription:
    row = session.get(Prescription, prescription_id)
    if row is None or row.deleted_at is not None:
        raise NotFound("Prescription was not found.")
    return row


def update_prescription(session: Session, prescription_id: str, payload: dict) -> Prescription:
    row = get_prescription(session, prescription_id)
    _apply(row, normalize_prescription(payload))
    session.commit()
    return row


def delete_prescription(session: Session, prescription_id: str) -> None:
    row = get_prescription(session, prescription_id)
    row.deleted_at = utcnow()
    row.updated_at = row.deleted_at
    session.commit()


def latest_job(session: Session, prescription_id: str) -> PrintJob | None:
    return session.scalar(
        select(PrintJob)
        .where(PrintJob.prescription_id == prescription_id)
        .order_by(PrintJob.created_at.desc())
    )


def sheet_row(row: Prescription) -> dict:
    """Shape expected by the existing Excel renderer."""
    created = datetime.combine(row.card_date, datetime.min.time())
    payload = {
        "wsl_id": row.ref_no,
        "timestamp": created,
        "entry_date": row.card_date.isoformat(),
        "patient_name": row.patient_name,
        "lens": row.lens,
        "optician_name": row.retailer,
    }
    for field in (*POWER_FIELDS, *AXIS_FIELDS):
        payload[field] = getattr(row, field)
    return payload


def export_rows(session: Session) -> list[dict]:
    rows = session.scalars(
        select(Prescription)
        .where(Prescription.deleted_at.is_(None))
        .order_by(Prescription.card_date.asc(), Prescription.created_at.asc())
    ).all()
    return [sheet_row(row) for row in rows]


def import_sheet_rows(session: Session, content: bytes) -> dict:
    """Add every valid sheet row. The same patient, ref, and date is not added twice."""
    rows = store.read_workbook(content)
    inserted = 0
    skipped = 0
    errors = []
    for row in rows:
        payload = {
            "ref_no": row.get("wsl_id") or "",
            "date": row.get("timestamp") or "",
            "patient_name": row.get("patient_name") or "",
            "lens": row.get("lens") or "",
            "retailer": row.get("optician_name") or "",
        }
        for field in (*POWER_FIELDS, *AXIS_FIELDS):
            payload[field] = row.get(field) or ""
        try:
            data = normalize_prescription(payload)
        except InputError as error:
            errors.append({"row": row["excel_row"], "error": str(error)})
            continue
        existing = session.scalar(
            select(Prescription).where(
                Prescription.deleted_at.is_(None),
                Prescription.ref_no == data["ref_no"],
                Prescription.patient_name == data["patient_name"],
                Prescription.card_date == data["date"],
            )
        )
        if existing is not None:
            skipped += 1
            continue
        record = Prescription(created_at=utcnow(), updated_at=utcnow())
        _apply(record, data)
        session.add(record)
        inserted += 1
    session.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def register_device(session: Session, payload: dict) -> tuple[PrinterDevice, str]:
    printer_name = str(payload.get("printer_name") or "").strip()
    reject_usb_port(printer_name)
    if not printer_name:
        raise InputError("Enter the Windows printer name.")
    device_name = str(payload.get("device_name") or "").strip()
    if not device_name:
        raise InputError("Enter a name for this shop computer.")
    token, token_hash = new_device_token()
    device = PrinterDevice(
        device_name=device_name[:120],
        token_hash=token_hash,
        location=str(payload.get("location") or "")[:120],
        printer_name=printer_name[:200],
        operating_system=str(payload.get("operating_system") or "")[:80],
        agent_version=str(payload.get("agent_version") or "")[:40],
        status="registered",
    )
    session.add(device)
    session.commit()
    return device, token


def device_from_token(session: Session, token: str) -> PrinterDevice | None:
    if not token:
        return None
    device = session.scalar(select(PrinterDevice).where(PrinterDevice.token_hash == hash_token(token)))
    if device is None or device.revoked_at is not None:
        return None
    return device


def rotate_device_token(session: Session, device: PrinterDevice) -> str:
    token, token_hash = new_device_token()
    device.token_hash = token_hash
    device.updated_at = utcnow()
    session.commit()
    return token


def revoke_device(session: Session, device_id: str) -> PrinterDevice:
    device = session.get(PrinterDevice, device_id)
    if device is None:
        raise NotFound("Device was not found.")
    device.revoked_at = utcnow()
    device.status = "revoked"
    device.updated_at = device.revoked_at
    session.commit()
    return device


def record_heartbeat(session: Session, device: PrinterDevice, payload: dict) -> PrinterDevice:
    printer_name = str(payload.get("printer_name") or device.printer_name).strip()
    reject_usb_port(printer_name)
    device.printer_name = printer_name[:200]
    device.agent_version = str(payload.get("agent_version") or device.agent_version)[:40]
    device.status = "printer_ready" if payload.get("printer_ready") else "printer_unavailable"
    device.last_heartbeat_at = utcnow()
    device.updated_at = device.last_heartbeat_at
    session.commit()
    return device


def create_print_job(
    session: Session,
    prescription_id: str,
    *,
    idempotency_key: str,
    target_device_id: str | None,
    max_attempts: int,
) -> PrintJob:
    get_prescription(session, prescription_id)
    key = idempotency_key.strip()
    if not key:
        raise InputError("A print request needs an idempotency key.")
    existing = session.scalar(select(PrintJob).where(PrintJob.idempotency_key == key))
    if existing is not None:
        if existing.prescription_id != prescription_id:
            raise Conflict("That idempotency key already belongs to another prescription.")
        return existing
    if target_device_id:
        device = session.get(PrinterDevice, target_device_id)
        if device is None or device.revoked_at is not None:
            raise NotFound("That shop computer is not registered.")
    job = PrintJob(
        prescription_id=prescription_id,
        target_device_id=target_device_id,
        status="pending",
        idempotency_key=key[:120],
        max_attempts=max_attempts,
    )
    session.add(job)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        existing = session.scalar(select(PrintJob).where(PrintJob.idempotency_key == key))
        if existing is not None:
            return existing
        raise Conflict("The print job could not be created.") from error
    add_event(session, job, "created", "Print job created. Waiting for the shop computer.")
    session.commit()
    return job


def list_jobs(session: Session, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[PrintJob], int]:
    query = select(PrintJob)
    if status:
        query = query.where(PrintJob.status == status)
    total = len(session.scalars(query).all())
    rows = session.scalars(query.order_by(PrintJob.created_at.desc()).limit(limit).offset(offset)).all()
    return rows, total


def get_job(session: Session, job_id: str) -> PrintJob:
    job = session.get(PrintJob, job_id)
    if job is None:
        raise NotFound("Print job was not found.")
    return job


def cancel_job(session: Session, job_id: str) -> PrintJob:
    job = get_job(session, job_id)
    if job.status not in {"pending", "claimed"}:
        raise Conflict("This job can no longer be cancelled. Check whether it already reached the printer.")
    job.status = "cancelled"
    job.completed_at = utcnow()
    job.updated_at = job.completed_at
    add_event(session, job, "cancelled", "Print job cancelled before it reached the spooler.")
    session.commit()
    return job


def requeue_job(session: Session, job_id: str, *, confirm_not_printed: bool, max_attempts: int) -> PrintJob:
    job = get_job(session, job_id)
    if job.status in {"submitting", "submitted_to_spooler"}:
        raise Conflict("This job may already have reached the printer. It was not requeued.")
    if job.status == "requires_manual_review" and not confirm_not_printed:
        raise Conflict("Confirm that the card did not print before sending it again.")
    if job.status not in {"failed", "cancelled", "requires_manual_review"}:
        raise Conflict("Only a failed or reviewed job can be sent again.")
    replacement = PrintJob(
        prescription_id=job.prescription_id,
        target_device_id=job.target_device_id,
        status="pending",
        idempotency_key=f"requeue:{job.id}:{utcnow().isoformat()}",
        max_attempts=max_attempts,
    )
    session.add(replacement)
    session.flush()
    add_event(session, replacement, "created", f"Requeued from {job.id} after it was confirmed not printed.")
    add_event(session, job, "requeued", f"A new job {replacement.id} was created.")
    session.commit()
    return replacement


def recover_expired_leases(session: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    recovered = 0
    stale = session.scalars(
        select(PrintJob).where(
            PrintJob.status.in_(ACTIVE_BEFORE_SPOOLER),
            PrintJob.lease_expires_at.is_not(None),
            PrintJob.lease_expires_at < now,
        )
    ).all()
    for job in stale:
        job.status = "pending"
        job.device_id = None
        job.lease_expires_at = None
        job.updated_at = now
        add_event(session, job, "lease_expired", "The shop computer stopped before sending the card. The job is pending again.")
        recovered += 1
    uncertain = session.scalars(
        select(PrintJob).where(
            PrintJob.status == "submitting",
            PrintJob.lease_expires_at.is_not(None),
            PrintJob.lease_expires_at < now,
        )
    ).all()
    for job in uncertain:
        job.status = "requires_manual_review"
        job.error_code = "lease_expired_during_submit"
        job.error_message = "The agent stopped while sending the card to Windows. Do not print it again until the queue is checked."
        job.updated_at = now
        add_event(session, job, "manual_review", job.error_message)
        recovered += 1
    if recovered:
        session.commit()
    return recovered


def claim_job(session: Session, device: PrinterDevice, lease_seconds: int) -> PrintJob | None:
    now = utcnow()
    recover_expired_leases(session, now)
    statement = (
        select(PrintJob)
        .where(PrintJob.status == "pending")
        .where(or_(PrintJob.target_device_id.is_(None), PrintJob.target_device_id == device.id))
        .order_by(PrintJob.created_at.asc())
        .limit(1)
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    job = session.scalar(statement)
    if job is None:
        return None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.error_code = "max_attempts"
        job.error_message = "The shop computer could not print this card within the retry limit."
        job.completed_at = now
        add_event(session, job, "failed", job.error_message)
        session.commit()
        return None
    lease = now + timedelta(seconds=lease_seconds)
    result = session.execute(
        update(PrintJob)
        .where(PrintJob.id == job.id, PrintJob.status == "pending")
        .values(
            status="claimed",
            device_id=device.id,
            attempts=PrintJob.attempts + 1,
            assigned_at=now,
            lease_expires_at=lease,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        return None
    session.refresh(job)
    add_event(session, job, "claimed", f"Claimed by {device.device_name}.")
    session.commit()
    return job


def _touch(job: PrintJob, lease_seconds: int) -> datetime:
    now = utcnow()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.updated_at = now
    return now


def _owned(job: PrintJob, device: PrinterDevice) -> None:
    if job.device_id != device.id:
        raise PermissionError("This job belongs to another shop computer.")


def mark_started(session: Session, job_id: str, device: PrinterDevice, lease_seconds: int) -> PrintJob:
    job = get_job(session, job_id)
    _owned(job, device)
    if job.status != "claimed":
        raise Conflict("The job is not waiting to start.")
    now = _touch(job, lease_seconds)
    job.status = "downloading"
    job.started_at = now
    add_event(session, job, "started", "The shop computer started the job.")
    session.commit()
    return job


def mark_rendered(session: Session, job_id: str, device: PrinterDevice, lease_seconds: int) -> PrintJob:
    job = get_job(session, job_id)
    _owned(job, device)
    if job.status not in {"downloading", "claimed"}:
        raise Conflict("The job is not ready to render.")
    _touch(job, lease_seconds)
    job.status = "rendering"
    add_event(session, job, "rendered", "Warranty card file was created on the shop computer.")
    session.commit()
    return job


def mark_submitting(session: Session, job_id: str, device: PrinterDevice, lease_seconds: int) -> PrintJob:
    job = get_job(session, job_id)
    _owned(job, device)
    if job.status != "rendering":
        raise Conflict("The job is not ready to send to the printer.")
    _touch(job, lease_seconds)
    job.status = "submitting"
    add_event(session, job, "submitting", "Sending the card to the Windows print spooler.")
    session.commit()
    return job


def mark_submitted(session: Session, job_id: str, device: PrinterDevice, spooler_job_id: str) -> PrintJob:
    job = get_job(session, job_id)
    _owned(job, device)
    if job.status != "submitting":
        raise Conflict("The spooler result does not match the job state.")
    now = utcnow()
    job.status = "submitted_to_spooler"
    job.spooler_job_id = (spooler_job_id or "")[:80]
    job.submitted_at = now
    job.completed_at = now
    job.updated_at = now
    job.lease_expires_at = None
    job.error_code = None
    job.error_message = None
    add_event(
        session,
        job,
        "submitted_to_spooler",
        "Windows accepted the card. This does not confirm that a plastic card came out of the printer.",
        {"spooler_job_id": job.spooler_job_id},
    )
    session.commit()
    return job


def mark_failed(
    session: Session,
    job_id: str,
    device: PrinterDevice,
    *,
    error_code: str,
    message: str,
    retryable: bool,
    reached_spooler: bool,
) -> PrintJob:
    job = get_job(session, job_id)
    _owned(job, device)
    now = utcnow()
    job.error_code = (error_code or "agent_error")[:80]
    job.error_message = message[:500]
    job.updated_at = now
    if reached_spooler:
        job.status = "requires_manual_review"
        job.completed_at = now
        add_event(session, job, "manual_review", message)
    elif retryable and job.attempts < job.max_attempts:
        job.status = "pending"
        job.device_id = None
        job.lease_expires_at = None
        add_event(session, job, "retry", message)
    else:
        job.status = "failed"
        job.completed_at = now
        add_event(session, job, "failed", message)
    session.commit()
    return job


def job_events(session: Session, job_id: str) -> list[PrintJobEvent]:
    get_job(session, job_id)
    return session.scalars(
        select(PrintJobEvent).where(PrintJobEvent.print_job_id == job_id).order_by(PrintJobEvent.created_at.asc())
    ).all()


def summary(session: Session) -> dict:
    prescriptions = session.scalars(select(Prescription).where(Prescription.deleted_at.is_(None))).all()
    jobs = session.scalars(select(PrintJob)).all()
    devices = session.scalars(select(PrinterDevice).order_by(PrinterDevice.created_at.desc())).all()

    def count(status: str) -> int:
        return sum(1 for job in jobs if job.status == status)

    recent = sorted(jobs, key=lambda job: job.created_at, reverse=True)[:10]
    return {
        "prescriptions": len(prescriptions),
        "print_jobs": len(jobs),
        "pending": count("pending"),
        "submitted_to_spooler": count("submitted_to_spooler"),
        "failed": count("failed"),
        "requires_manual_review": count("requires_manual_review"),
        "devices": [device_dict(device) for device in devices],
        "recent_jobs": [job_dict(job) for job in recent],
    }
