"""Claim one job, draw the card, and hand it to the Windows spooler."""

from __future__ import annotations

import time
from pathlib import Path

from printer_agent.card_renderer import render_prescription
from printer_agent.job_client import JobClient
from printer_agent.logging_config import configure_logging
from printer_agent.printer_detector import installed_printers, printer_is_ready
from printer_agent.windows_printer import PrinterError, submit_raster

logger = configure_logging()


class Worker:
    def __init__(self, client: JobClient, printer_name: str, output_dir: Path, poll_seconds: float = 5):
        self.client = client
        self.printer_name = printer_name
        self.output_dir = output_dir
        self.poll_seconds = poll_seconds
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def printer_ready(self) -> bool:
        if self.printer_name not in installed_printers():
            return False
        return printer_is_ready(self.printer_name)

    def submit(self, image_path: Path) -> str:
        return submit_raster(image_path, self.printer_name)

    def process_once(self) -> bool:
        """Handle at most one job. Return True when a job was claimed."""
        ready = False
        try:
            ready = self.printer_ready()
        except Exception as error:
            logger.warning("printer check failed error=%s", error)
        try:
            self.client.heartbeat(self.printer_name, ready, "1.0.0")
        except ConnectionError:
            raise
        payload = self.client.claim()
        job = payload.get("job")
        if not job:
            return False
        job_id = job["id"]
        logger.info("job claimed job_id=%s", job_id)
        try:
            self.client.started(job_id)
            png_path, _pdf_path = render_prescription(payload["prescription"], self.output_dir)
            self.client.rendered(job_id)
        except Exception as error:
            logger.exception("render failed job_id=%s", job_id)
            self.client.failed(job_id, "render_failed", str(error), retryable=True, reached_spooler=False)
            return True
        if not ready:
            message = f"{self.printer_name} is not available on this PC."
            logger.warning("printer unavailable job_id=%s", job_id)
            self.client.failed(job_id, "printer_unavailable", message, retryable=True, reached_spooler=False)
            return True
        self.client.submitting(job_id)
        try:
            spooler_job_id = self.submit(png_path)
        except PrinterError as error:
            logger.error("spooler failed job_id=%s code=%s", job_id, error.code)
            self.client.failed(
                job_id,
                error.code,
                str(error),
                retryable=not error.reached_spooler,
                reached_spooler=error.reached_spooler,
            )
            return True
        except Exception as error:
            logger.exception("spooler result unknown job_id=%s", job_id)
            self.client.failed(job_id, "spooler_unknown", str(error), retryable=False, reached_spooler=True)
            return True
        result = self.client.submitted(job_id, spooler_job_id)
        logger.info("job submitted_to_spooler job_id=%s status=%s", job_id, result.get("status"))
        return True

    def run(self) -> None:
        delay = self.poll_seconds
        while not self._stop:
            try:
                worked = self.process_once()
                delay = self.poll_seconds
                if not worked:
                    time.sleep(delay)
            except ConnectionError as error:
                logger.warning("api unavailable error=%s", error)
                delay = min(delay * 2, 60)
                time.sleep(delay)
