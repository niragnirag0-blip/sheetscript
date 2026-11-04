"""Agent settings from the environment or a JSON file on the shop PC. The token is never logged."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from printer_agent.printer_detector import DEFAULT_PRINTER, validate_printer_name


@dataclass(frozen=True)
class AgentConfig:
    api_url: str
    device_token: str
    printer_name: str
    poll_seconds: float
    output_dir: Path
    agent_version: str = "1.0.0"


def load_config(path: Path | None = None) -> AgentConfig:
    file_values = {}
    config_path = path or Path(os.environ.get("MAGNUS_AGENT_CONFIG", "printer-agent.json"))
    if config_path.is_file():
        file_values = json.loads(config_path.read_text(encoding="utf-8"))
    api_url = os.environ.get("MAGNUS_API_URL", file_values.get("api_url", "")).strip()
    token = os.environ.get("MAGNUS_DEVICE_TOKEN", file_values.get("device_token", "")).strip()
    printer = os.environ.get("MAGNUS_PRINTER_NAME", file_values.get("printer_name", DEFAULT_PRINTER))
    poll = float(os.environ.get("MAGNUS_AGENT_POLL_SECONDS", file_values.get("poll_seconds", 5)))
    output = Path(os.environ.get("MAGNUS_AGENT_OUTPUT", file_values.get("output_dir", "out/agent")))
    if not api_url:
        raise RuntimeError("Set MAGNUS_API_URL to the central API, for example http://127.0.0.1:8000")
    if not token:
        raise RuntimeError("Set MAGNUS_DEVICE_TOKEN to the credential returned when this PC was registered.")
    return AgentConfig(
        api_url=api_url,
        device_token=token,
        printer_name=validate_printer_name(printer),
        poll_seconds=max(1.0, poll),
        output_dir=output,
    )
