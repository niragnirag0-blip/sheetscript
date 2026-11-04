"""Shop print agent command line."""

from __future__ import annotations

import argparse
import os

from printer_agent.logging_config import configure_logging
from printer_agent.printer_detector import installed_printers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Magnus Lens Windows print agent")
    parser.add_argument("command", choices=("run", "once", "printers", "install-service"))
    args = parser.parse_args(argv)
    logger = configure_logging()
    if args.command == "printers":
        names = installed_printers()
        if not names:
            print("No Windows printers were found. On Linux this list is empty.")
        for name in names:
            print(name)
        return 0
    if args.command == "install-service":
        from printer_agent.service import install_service

        install_service()
        print("Service MagnusLensPrintAgent installed.")
        return 0
    from printer_agent.config import load_config
    from printer_agent.job_client import JobClient
    from printer_agent.worker import Worker

    config = load_config()
    worker = Worker(
        JobClient(config.api_url, config.device_token),
        config.printer_name,
        config.output_dir,
        config.poll_seconds,
    )
    if args.command == "once":
        try:
            worked = worker.process_once()
        except ConnectionError as error:
            logger.error("api unavailable error=%s", error)
            return 1
        print("claimed" if worked else "idle")
        return 0
    if os.name != "nt":
        logger.warning("This process is not Windows. It can claim jobs, but it cannot see USB002.")
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
