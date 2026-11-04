"""Cloud tables. The configured database is the only source of truth."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Prescription(Base):
    __tablename__ = "cloud_prescriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    legacy_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    ref_no: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    card_date: Mapped[date] = mapped_column(Date, nullable=False)
    patient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    lens: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    re_sph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    re_cyl: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    re_axis: Mapped[Decimal | None] = mapped_column(Numeric(6, 0))
    re_add: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    le_sph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    le_cyl: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    le_axis: Mapped[Decimal | None] = mapped_column(Numeric(6, 0))
    le_add: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    retailer: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    jobs: Mapped[list["PrintJob"]] = relationship(back_populates="prescription")


class PrinterDevice(Base):
    __tablename__ = "printer_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    printer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    agent_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="registered", nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_print_job_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prescription_id: Mapped[str] = mapped_column(ForeignKey("cloud_prescriptions.id"), nullable=False)
    target_device_id: Mapped[str | None] = mapped_column(ForeignKey("printer_devices.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("printer_devices.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    spooler_job_id: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    prescription: Mapped[Prescription] = relationship(back_populates="jobs")
    events: Mapped[list["PrintJobEvent"]] = relationship(back_populates="job")


class PrintJobEvent(Base):
    __tablename__ = "print_job_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    print_job_id: Mapped[str] = mapped_column(ForeignKey("print_jobs.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    job: Mapped[PrintJob] = relationship(back_populates="events")
