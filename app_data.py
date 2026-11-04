"""Streamlit uses these functions directly. The page does not store prescriptions in session state."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path

import store
from backend.database import make_engine, make_session_factory, prepare_database
from backend.migrate_sqlite import migrate
from backend import services
from config.settings import ROOT, load_settings

_factory = None
_status = {"ready": False, "detail": ""}


class DatabaseNotConfigured(RuntimeError):
    pass


def reset() -> None:
    global _factory
    _factory = None
    _status["ready"] = False
    _status["detail"] = ""


def on_streamlit_cloud() -> bool:
    return Path("/mount/src").is_dir()


def apply_streamlit_secrets() -> None:
    try:
        import streamlit as st

        secret = str(st.secrets.get("DATABASE_URL", "") or "").strip()
    except Exception:
        return
    if secret:
        os.environ["DATABASE_URL"] = secret


def _sqlite_file(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    text = database_url.removeprefix("sqlite:///")
    if text.endswith(":memory:"):
        return None
    return Path(text).resolve()


def connect():
    """Open the shared database once per process."""
    global _factory
    if _factory is not None:
        return _factory
    apply_streamlit_secrets()
    settings = load_settings()
    if on_streamlit_cloud() and settings.database_url.startswith("sqlite"):
        _status["ready"] = False
        _status["detail"] = (
            "This public page is open. Add DATABASE_URL in the Streamlit secrets, "
            "using a PostgreSQL address. Cards are not saved on the Streamlit server disk."
        )
        return None
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    prepare_database(engine, settings, factory)
    source = ROOT / "prescriptions.db"
    target = _sqlite_file(settings.database_url)
    default_target = (ROOT / "data" / "magnus.db").resolve()
    if source.is_file() and target == default_target:
        with factory() as session:
            migrate(source, session, dry_run=False)
    _factory = factory
    _status["ready"] = True
    _status["detail"] = "" if settings.database_url.startswith("postgresql") else (
        "This computer is using a local database. Set DATABASE_URL to PostgreSQL to share cards with the shop."
    )
    return factory


def status() -> dict:
    connect()
    return dict(_status)


def _require():
    factory = connect()
    if factory is None:
        raise DatabaseNotConfigured(_status["detail"])
    return factory


def save_prescription(payload: dict) -> dict:
    with _require()() as session:
        row = services.create_prescription(session, payload, None)
        return services.prescription_dict(row)


def list_prescriptions(limit: int, offset: int) -> tuple[list[dict], int]:
    with _require()() as session:
        return services.list_prescriptions(session, limit=limit, offset=offset)


def request_print(prescription_id: str, idempotency_key: str) -> dict:
    with _require()() as session:
        job = services.create_print_job(
            session,
            prescription_id,
            idempotency_key=idempotency_key,
            target_device_id=None,
            max_attempts=load_settings().job_max_attempts,
        )
        return services.job_dict(job)


def card_files(entry: dict) -> tuple[str, bytes, bytes]:
    from printer_agent.card_renderer import render_bytes

    return render_bytes(entry)


def cards_archive() -> bytes:
    """Zip every saved card as PNG and PDF."""
    rows, _total = list_prescriptions(500, 0)
    if not rows:
        raise DatabaseNotConfigured("No cards saved yet.")
    buffer = BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in rows:
            stem, png, pdf = card_files(entry)
            name = stem if stem not in used else f"{stem}-{str(entry['id'])[:8]}"
            used.add(name)
            archive.writestr(f"{name}.png", png)
            archive.writestr(f"{name}.pdf", pdf)
    return buffer.getvalue()


def export_workbook() -> bytes:
    with _require()() as session:
        return store.workbook_bytes(services.export_rows(session))


def blank_sheet() -> bytes:
    return store.workbook_bytes([])


def import_workbook(content: bytes) -> dict:
    with _require()() as session:
        return services.import_sheet_rows(session, content)


def shop_summary() -> dict:
    with _require()() as session:
        return services.summary(session)


def register_shop_pc(device_name: str, printer_name: str) -> tuple[dict, str]:
    with _require()() as session:
        device, token = services.register_device(
            session,
            {
                "device_name": device_name,
                "printer_name": printer_name,
                "location": "Jagadamba Optics",
                "operating_system": "Windows",
                "agent_version": "1.0.0",
            },
        )
        return services.device_dict(device), token


def send_again(job_id: str, confirm_not_printed: bool) -> dict:
    with _require()() as session:
        job = services.requeue_job(
            session,
            job_id,
            confirm_not_printed=confirm_not_printed,
            max_attempts=load_settings().job_max_attempts,
        )
        return services.job_dict(job)
