"""Initial cloud tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("password_salt", sa.String(64), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "cloud_prescriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legacy_id", sa.Integer(), unique=True),
        sa.Column("ref_no", sa.String(64), nullable=False),
        sa.Column("card_date", sa.Date(), nullable=False),
        sa.Column("patient_name", sa.String(200), nullable=False),
        sa.Column("lens", sa.String(200), nullable=False),
        sa.Column("re_sph", sa.Numeric(6, 2)),
        sa.Column("re_cyl", sa.Numeric(6, 2)),
        sa.Column("re_axis", sa.Numeric(6, 0)),
        sa.Column("re_add", sa.Numeric(6, 2)),
        sa.Column("le_sph", sa.Numeric(6, 2)),
        sa.Column("le_cyl", sa.Numeric(6, 2)),
        sa.Column("le_axis", sa.Numeric(6, 0)),
        sa.Column("le_add", sa.Numeric(6, 2)),
        sa.Column("retailer", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("deleted_at", sa.DateTime()),
    )
    op.create_table(
        "printer_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("location", sa.String(120), nullable=False),
        sa.Column("printer_name", sa.String(200), nullable=False),
        sa.Column("operating_system", sa.String(80), nullable=False),
        sa.Column("agent_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime()),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("prescription_id", sa.String(36), sa.ForeignKey("cloud_prescriptions.id"), nullable=False),
        sa.Column("target_device_id", sa.String(36), sa.ForeignKey("printer_devices.id")),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("printer_devices.id")),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("spooler_job_id", sa.String(80)),
        sa.Column("lease_expires_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_at", sa.DateTime()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_print_jobs_status", "print_jobs", ["status"])
    op.create_table(
        "print_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("print_job_id", sa.String(36), sa.ForeignKey("print_jobs.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_print_job_events_print_job_id", "print_job_events", ["print_job_id"])


def downgrade():
    op.drop_table("print_job_events")
    op.drop_table("print_jobs")
    op.drop_table("printer_devices")
    op.drop_table("cloud_prescriptions")
    op.drop_table("users")
