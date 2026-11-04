# Windows print agent

The agent runs on the Jagadamba Optics PC. That PC has the Zebra on port USB002. The Windows printer name is **Zebra ZC300 USB Card Printer**.

## Install

On the shop PC, in PowerShell, from a copy of this repository:

```powershell
powershell -ExecutionPolicy Bypass -File deployment\windows\install.ps1 -ApiUrl https://api.example.com -Username admin -Password "the-shop-password"
```

The script installs `requirements-windows.txt`, registers the PC, writes `C:\ProgramData\MagnusLens\printer-agent.json`, and creates a logon task named `MagnusLensPrintAgent`.

The device token is written into that JSON file once. Do not copy it into chat or into source control.

## Commands

From `C:\ProgramData\MagnusLens`, with `MAGNUS_AGENT_CONFIG` pointing at `printer-agent.json`:

```powershell
python -m printer_agent printers
python -m printer_agent once
python -m printer_agent run
python -m printer_agent install-service
```

`deployment\windows\start.ps1` starts the console worker.

`deployment\windows\uninstall.ps1` removes the logon task and the service. It leaves the program folder and the token file in place.

Service control, after `install-service`:

```powershell
sc start MagnusLensPrintAgent
sc stop MagnusLensPrintAgent
sc query MagnusLensPrintAgent
```

Logs go to the console of the process that owns the task. The log line includes the job id and the event. It does not include the device token or the full prescription.

## Why the logon task is the default

The Zebra is a USB printer. Windows services run in session 0 and often cannot see a USB queue that was installed for the signed-in user. The installer therefore starts the agent when that user logs on. `install-service` is available when the driver is known to work from a service account. Until a card reaches the spooler from the service, use the logon task.

## Polling and recovery

The default poll is 5 seconds. If the API cannot be reached, the wait doubles up to 60 seconds. Jobs that were claimed but not yet sent to the spooler return to `pending` after the lease (default 120 seconds). A job already marked `submitting` becomes `requires_manual_review` instead of being sent again.

## Printer missing

If the queue is absent or offline, the agent reports `printer_unavailable`, leaves the card files on disk, and asks the API to retry. It does not drop the job.
