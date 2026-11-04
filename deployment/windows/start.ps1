$ErrorActionPreference = "Stop"
$InstallDir = "C:\ProgramData\MagnusLens"
Set-Location $InstallDir
$env:MAGNUS_AGENT_CONFIG = Join-Path $InstallDir "printer-agent.json"
python -m printer_agent run
