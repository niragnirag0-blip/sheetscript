"""Windows service wrapper. USB card printers are often visible only in the signed-in user session."""

from __future__ import annotations

import os
import sys
import threading


def serve() -> None:
    from printer_agent.config import load_config
    from printer_agent.job_client import JobClient
    from printer_agent.worker import Worker

    config = load_config()
    client = JobClient(config.api_url, config.device_token)
    Worker(client, config.printer_name, config.output_dir, config.poll_seconds).run()


def install_service() -> None:
    if os.name != "nt":
        raise RuntimeError("The Windows service can only be installed on the shop PC.")
    import win32serviceutil

    win32serviceutil.InstallService(
        "printer_agent.service.MagnusPrintService",
        "MagnusLensPrintAgent",
        "Magnus Lens Print Agent",
        startType=2,
        exeName=sys.executable,
    )


if os.name == "nt":
    try:
        import servicemanager
        import win32event
        import win32service
        import win32serviceutil

        class MagnusPrintService(win32serviceutil.ServiceFramework):
            _svc_name_ = "MagnusLensPrintAgent"
            _svc_display_name_ = "Magnus Lens Print Agent"
            _svc_description_ = "Pulls Magnus warranty cards and sends them to the local Zebra printer."

            def __init__(self, args):
                super().__init__(args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.worker = None

            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                if self.worker is not None:
                    self.worker.stop()
                win32event.SetEvent(self.stop_event)

            def SvcDoRun(self):
                servicemanager.LogInfoMsg("Magnus Lens Print Agent is starting.")
                thread = threading.Thread(target=self._run, daemon=True)
                thread.start()
                win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

            def _run(self):
                from printer_agent.config import load_config
                from printer_agent.job_client import JobClient
                from printer_agent.worker import Worker

                config = load_config()
                self.worker = Worker(
                    JobClient(config.api_url, config.device_token),
                    config.printer_name,
                    config.output_dir,
                    config.poll_seconds,
                )
                self.worker.run()

    except ImportError:
        MagnusPrintService = None  # type: ignore
else:
    MagnusPrintService = None
