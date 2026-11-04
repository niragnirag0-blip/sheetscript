from pathlib import Path

from printer_agent.printer_detector import validate_printer_name
from printer_agent.windows_printer import PrinterError
from printer_agent.worker import Worker
from validation import InputError


class FakeClient:
    def __init__(self, prescription):
        self.prescription = prescription
        self.calls = []

    def heartbeat(self, printer_name, printer_ready, agent_version):
        self.calls.append(("heartbeat", printer_ready))

    def claim(self):
        return {"job": {"id": "job-1"}, "prescription": self.prescription}

    def started(self, job_id):
        self.calls.append(("started", job_id))

    def rendered(self, job_id):
        self.calls.append(("rendered", job_id))

    def submitting(self, job_id):
        self.calls.append(("submitting", job_id))

    def submitted(self, job_id, spooler_job_id):
        self.calls.append(("submitted", spooler_job_id))
        return {"status": "submitted_to_spooler"}

    def failed(self, job_id, error_code, message, *, retryable, reached_spooler):
        self.calls.append(("failed", error_code, retryable, reached_spooler))
        return {"status": "failed"}


def prescription():
    return {
        "id": "card-1",
        "date": "2026-11-02",
        "patient_name": "Keshav Gupta",
        "lens": "MAGNUS BR 1.67",
        "retailer": "Space Optics",
        "ref_no": "J4429",
        "re_sph": "-10.00",
        "re_cyl": "-1.00",
        "re_axis": "150",
        "re_add": None,
        "le_sph": "-11.00",
        "le_cyl": "-1.00",
        "le_axis": "140",
        "le_add": None,
    }


def test_usb_port_is_not_a_printer_name():
    try:
        validate_printer_name("USB002")
    except InputError as error:
        assert "USB002" in str(error)
    else:
        raise AssertionError("USB002 was accepted as a printer name")


def test_worker_reports_spooler_acceptance_without_calling_windows(tmp_path):
    client = FakeClient(prescription())

    class Ready(Worker):
        def printer_ready(self):
            return True

        def submit(self, image_path: Path) -> str:
            assert image_path.suffix == ".png"
            assert image_path.stat().st_size > 1000
            return "WIN-9"

    worker = Ready(client, "Zebra ZC300 USB Card Printer", tmp_path)
    assert worker.process_once() is True
    assert ("submitted", "WIN-9") in client.calls
    assert not any(call[0] == "failed" for call in client.calls)


def test_missing_printer_is_retried_and_not_discarded(tmp_path):
    client = FakeClient(prescription())

    class Missing(Worker):
        def printer_ready(self):
            return False

        def submit(self, image_path: Path) -> str:
            raise AssertionError("The missing printer must not receive a card")

    worker = Missing(client, "Zebra ZC300 USB Card Printer", tmp_path)
    assert worker.process_once() is True
    failed = [call for call in client.calls if call[0] == "failed"]
    assert failed == [("failed", "printer_unavailable", True, False)]


def test_unknown_spooler_result_is_not_retried_automatically(tmp_path):
    client = FakeClient(prescription())

    class Uncertain(Worker):
        def printer_ready(self):
            return True

        def submit(self, image_path: Path) -> str:
            raise PrinterError("spooler", "EndDoc result is unknown", reached_spooler=True)

    worker = Uncertain(client, "Zebra ZC300 USB Card Printer", tmp_path)
    worker.process_once()
    failed = [call for call in client.calls if call[0] == "failed"][0]
    assert failed[1] == "spooler"
    assert failed[2] is False
    assert failed[3] is True
