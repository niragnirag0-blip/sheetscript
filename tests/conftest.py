from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("MAGNUS_JWT_SECRET", "test-secret")
    monkeypatch.setenv("MAGNUS_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("MAGNUS_ADMIN_PASSWORD", "change-me-please")
    monkeypatch.setenv("MAGNUS_ENV", "development")
    monkeypatch.setenv("MAGNUS_RATE_LIMIT_PER_MINUTE", "10000")
    from config.settings import load_settings

    return load_settings()


@pytest.fixture
def api(settings):
    from backend.main import create_app

    application = create_app(settings)
    client = TestClient(application)
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text
    return client, response.json()["access_token"], application


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sample(**overrides) -> dict:
    payload = {
        "ref_no": "J4429",
        "date": "2026-11-02",
        "patient_name": "Keshav Gupta",
        "lens": "MAGNUS BR 1.67",
        "retailer": "Space Optics",
        "re_sph": "-10",
        "re_cyl": "-1",
        "re_axis": "150",
        "re_add": "",
        "le_sph": "-11",
        "le_cyl": "-1",
        "le_axis": "140",
        "le_add": "",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def saved(api):
    client, token, application = api
    response = client.post("/api/v1/prescriptions/", json=sample(), headers=auth(token))
    assert response.status_code == 200, response.text
    return client, token, application, response.json()
