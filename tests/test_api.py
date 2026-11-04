from datetime import timedelta
from io import BytesIO

import openpyxl

from backend.models import PrintJob, utcnow
from tests.conftest import auth, sample


def test_health(api):
    client, _token, _application = api
    assert client.get("/health").json()["status"] == "ok"


def test_login_rejects_a_wrong_password(api):
    client, _token, _application = api
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope"})
    assert response.status_code == 401


def test_save_requires_a_patient_name(api):
    client, token, _application = api
    response = client.post("/api/v1/prescriptions/", json=sample(patient_name="  "), headers=auth(token))
    assert response.status_code == 422


def test_save_rejects_text_in_a_power(api):
    client, token, _application = api
    response = client.post("/api/v1/prescriptions/", json=sample(re_sph="abc"), headers=auth(token))
    assert response.status_code == 422


def test_save_keeps_two_decimals_and_the_ref_exactly(saved):
    _client, _token, _application, row = saved
    assert row["re_sph"] == "-10.00"
    assert row["re_cyl"] == "-1.00"
    assert row["re_axis"] == "150"
    assert row["le_sph"] == "-11.00"
    assert row["ref_no"] == "J4429"
    assert row["patient_name"] == "Keshav Gupta"


def test_ref_case_is_not_changed(api):
    client, token, _application = api
    response = client.post("/api/v1/prescriptions/", json=sample(ref_no="j4429"), headers=auth(token))
    assert response.status_code == 200
    assert response.json()["ref_no"] == "j4429"


def test_newest_card_is_first(api):
    client, token, _application = api
    client.post("/api/v1/prescriptions/", json=sample(date="2026-11-01", patient_name="Older Person"), headers=auth(token))
    client.post("/api/v1/prescriptions/", json=sample(date="2026-11-04", patient_name="Newer Person"), headers=auth(token))
    listed = client.get("/api/v1/prescriptions/", headers=auth(token)).json()
    assert listed["items"][0]["patient_name"] == "Newer Person"
    assert listed["total"] == 2


def test_excel_is_not_written_on_save_and_columns_match(saved, tmp_path):
    client, token, _application, row = saved
    assert not list(tmp_path.glob("*.xlsx"))
    response = client.get("/api/v1/exports/prescriptions.xlsx", headers=auth(token))
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(BytesIO(response.content))
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    assert headers == [
        "Ref No",
        "Date",
        "Patient Name",
        "Lens",
        "RE Sph",
        "RE Cyl",
        "RE Axis",
        "RE Add",
        "LE Sph",
        "LE Cyl",
        "LE Axis",
        "LE Add",
        "Retailer",
    ]
    assert sheet["A2"].value == "J4429"
    assert sheet["C2"].value == "Keshav Gupta"
    assert sheet["E2"].value == -10
    assert row["id"]


def test_device_token_is_not_the_stored_value(api):
    client, token, application = api
    response = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Jagadamba", "printer_name": "Zebra ZC300 USB Card Printer", "location": "Shop"},
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    secret = response.json()["device_token"]
    from backend.models import PrinterDevice

    with application.state.session_factory() as session:
        device = session.get(PrinterDevice, response.json()["device"]["id"])
        assert device.token_hash != secret
        assert secret not in device.token_hash


def test_usb_port_is_rejected_as_a_printer_name(api):
    client, token, _application = api
    response = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Shop", "printer_name": "USB002"},
        headers=auth(token),
    )
    assert response.status_code == 422


def test_duplicate_print_request_returns_the_same_job(saved):
    client, token, _application, row = saved
    first = client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "same-key"},
        headers=auth(token),
    )
    second = client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "same-key"},
        headers=auth(token),
    )
    assert first.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["physically_printed"] is False


def test_only_the_assigned_device_can_update_a_job(saved):
    client, token, _application, row = saved
    shop_a = client.post(
        "/api/v1/devices/register",
        json={"device_name": "A", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    shop_b = client.post(
        "/api/v1/devices/register",
        json={"device_name": "B", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    created = client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "for-a", "device_id": shop_a["device"]["id"]},
        headers=auth(token),
    )
    assert created.status_code == 200
    missed = client.post("/api/v1/agent/jobs/claim/", headers={"X-Device-Token": shop_b["device_token"]})
    assert missed.json()["job"] is None
    claimed = client.post("/api/v1/agent/jobs/claim/", headers={"X-Device-Token": shop_a["device_token"]})
    job_id = claimed.json()["job"]["id"]
    blocked = client.post(
        f"/api/v1/agent/jobs/{job_id}/started/",
        headers={"X-Device-Token": shop_b["device_token"]},
    )
    assert blocked.status_code == 403


def test_expired_lease_before_the_spooler_returns_the_job_to_pending(saved):
    client, token, application, row = saved
    shop = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Shop", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "lease"},
        headers=auth(token),
    )
    claimed = client.post("/api/v1/agent/jobs/claim/", headers={"X-Device-Token": shop["device_token"]}).json()["job"]
    with application.state.session_factory() as session:
        job = session.get(PrintJob, claimed["id"])
        job.lease_expires_at = utcnow() - timedelta(minutes=5)
        session.commit()
    again = client.post("/api/v1/agent/jobs/claim/", headers={"X-Device-Token": shop["device_token"]}).json()["job"]
    assert again["id"] == claimed["id"]
    assert again["attempts"] == 2
    assert again["status"] == "claimed"


def test_expired_lease_while_submitting_needs_a_person(saved):
    client, token, application, row = saved
    shop = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Shop", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "uncertain"},
        headers=auth(token),
    )
    header = {"X-Device-Token": shop["device_token"]}
    job_id = client.post("/api/v1/agent/jobs/claim/", headers=header).json()["job"]["id"]
    assert client.post(f"/api/v1/agent/jobs/{job_id}/started/", headers=header).status_code == 200
    assert client.post(f"/api/v1/agent/jobs/{job_id}/rendered/", headers=header).status_code == 200
    assert client.post(f"/api/v1/agent/jobs/{job_id}/submitting/", headers=header).status_code == 200
    with application.state.session_factory() as session:
        job = session.get(PrintJob, job_id)
        job.lease_expires_at = utcnow() - timedelta(minutes=5)
        session.commit()
    client.post("/api/v1/agent/jobs/claim/", headers=header)
    with application.state.session_factory() as session:
        job = session.get(PrintJob, job_id)
        assert job.status == "requires_manual_review"


def test_retry_stops_at_the_attempt_limit(saved):
    client, token, _application, row = saved
    shop = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Shop", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    created = client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "retries"},
        headers=auth(token),
    ).json()
    with saved[2].state.session_factory() as session:
        job = session.get(PrintJob, created["id"])
        job.max_attempts = 1
        session.commit()
    header = {"X-Device-Token": shop["device_token"]}
    job_id = client.post("/api/v1/agent/jobs/claim/", headers=header).json()["job"]["id"]
    failed = client.post(
        f"/api/v1/agent/jobs/{job_id}/failed/",
        json={"error_code": "printer_unavailable", "message": "USB cable is out", "retryable": True, "reached_spooler": False},
        headers=header,
    )
    assert failed.json()["status"] == "failed"


def test_requeue_is_refused_after_the_spooler_accepted_the_card(saved):
    client, token, application, row = saved
    shop = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Shop", "printer_name": "Zebra ZC300 USB Card Printer"},
        headers=auth(token),
    ).json()
    client.post(
        "/api/v1/print-jobs/",
        json={"prescription_id": row["id"], "idempotency_key": "spooled"},
        headers=auth(token),
    )
    header = {"X-Device-Token": shop["device_token"]}
    job_id = client.post("/api/v1/agent/jobs/claim/", headers=header).json()["job"]["id"]
    client.post(f"/api/v1/agent/jobs/{job_id}/started/", headers=header)
    client.post(f"/api/v1/agent/jobs/{job_id}/rendered/", headers=header)
    client.post(f"/api/v1/agent/jobs/{job_id}/submitting/", headers=header)
    submitted = client.post(
        f"/api/v1/agent/jobs/{job_id}/submitted/",
        json={"spooler_job_id": "WIN-1"},
        headers=header,
    )
    assert submitted.json()["status"] == "submitted_to_spooler"
    assert submitted.json()["physically_printed"] is False
    refused = client.post(
        f"/api/v1/print-jobs/{job_id}/requeue/",
        json={"confirm_not_printed": True},
        headers=auth(token),
    )
    assert refused.status_code == 409
    events = client.get(f"/api/v1/print-jobs/{job_id}/events/", headers=auth(token)).json()
    assert any(event["event_type"] == "submitted_to_spooler" for event in events)
    assert application is not None
