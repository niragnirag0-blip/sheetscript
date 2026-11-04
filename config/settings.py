"""Environment configuration. Secrets come from the process environment, never from source."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    jwt_secret: str
    jwt_ttl_seconds: int
    admin_username: str
    admin_password: str
    cors_origins: tuple[str, ...]
    rate_limit_per_minute: int
    job_lease_seconds: int
    job_max_attempts: int
    agent_poll_seconds: int
    qr_base_url: str


def load_settings() -> Settings:
    load_dotenv()
    env = os.environ.get("MAGNUS_ENV", "development").strip() or "development"
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/magnus.db").strip()
    jwt_secret = os.environ.get("MAGNUS_JWT_SECRET", "").strip()
    if not jwt_secret and env != "production":
        jwt_secret = "dev-only-change-me"
    if env == "production" and database_url.startswith("sqlite"):
        raise RuntimeError("Production requires PostgreSQL. Set DATABASE_URL to a postgresql+psycopg URL.")
    origins = tuple(
        item.strip()
        for item in os.environ.get(
            "MAGNUS_CORS_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if item.strip()
    )
    return Settings(
        env=env,
        database_url=database_url,
        jwt_secret=jwt_secret,
        jwt_ttl_seconds=int(os.environ.get("MAGNUS_JWT_TTL_SECONDS", "43200")),
        admin_username=os.environ.get("MAGNUS_ADMIN_USERNAME", "admin").strip(),
        admin_password=os.environ.get("MAGNUS_ADMIN_PASSWORD", "").strip(),
        cors_origins=origins,
        rate_limit_per_minute=int(os.environ.get("MAGNUS_RATE_LIMIT_PER_MINUTE", "120")),
        job_lease_seconds=int(os.environ.get("MAGNUS_JOB_LEASE_SECONDS", "120")),
        job_max_attempts=int(os.environ.get("MAGNUS_JOB_MAX_ATTEMPTS", "3")),
        agent_poll_seconds=int(os.environ.get("MAGNUS_AGENT_POLL_SECONDS", "5")),
        qr_base_url=os.environ.get("MAGNUS_QR_BASE_URL", "").strip().rstrip("/"),
    )
