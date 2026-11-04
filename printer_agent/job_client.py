"""Talk to the central API. The agent only makes outbound requests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail or f"API returned {status}")
        self.status = status


class JobClient:
    def __init__(self, base_url: str, device_token: str, timeout: float = 20):
        self.base_url = base_url.rstrip("/")
        self.device_token = device_token
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Device-Token": self.device_token},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            raise ApiError(error.code, raw) from error
        except urllib.error.URLError as error:
            raise ConnectionError(str(error.reason)) from error

    def heartbeat(self, printer_name: str, printer_ready: bool, agent_version: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/agent/heartbeat/",
            {"printer_name": printer_name, "printer_ready": printer_ready, "agent_version": agent_version},
        )

    def claim(self) -> dict:
        return self._request("POST", "/api/v1/agent/jobs/claim/")

    def started(self, job_id: str) -> dict:
        return self._request("POST", f"/api/v1/agent/jobs/{job_id}/started/")

    def rendered(self, job_id: str) -> dict:
        return self._request("POST", f"/api/v1/agent/jobs/{job_id}/rendered/")

    def submitting(self, job_id: str) -> dict:
        return self._request("POST", f"/api/v1/agent/jobs/{job_id}/submitting/")

    def submitted(self, job_id: str, spooler_job_id: str) -> dict:
        return self._request("POST", f"/api/v1/agent/jobs/{job_id}/submitted/", {"spooler_job_id": spooler_job_id})

    def failed(self, job_id: str, error_code: str, message: str, *, retryable: bool, reached_spooler: bool) -> dict:
        return self._request(
            "POST",
            f"/api/v1/agent/jobs/{job_id}/failed/",
            {
                "error_code": error_code,
                "message": message,
                "retryable": retryable,
                "reached_spooler": reached_spooler,
            },
        )
