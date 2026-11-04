"""Database engine and session factory for the API process."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.models import Base, User
from backend.security import hash_password
from config.settings import Settings


def make_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
            Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def prepare_database(engine, settings: Settings, session_factory) -> None:
    if settings.env != "production":
        Base.metadata.create_all(engine)
    else:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    if not settings.admin_username or not settings.admin_password:
        return
    with session_factory() as session:
        existing = session.query(User).filter(User.username == settings.admin_username).one_or_none()
        if existing is None:
            password_hash, salt = hash_password(settings.admin_password)
            session.add(
                User(
                    username=settings.admin_username,
                    password_hash=password_hash,
                    password_salt=salt,
                    role="admin",
                )
            )
            session.commit()
