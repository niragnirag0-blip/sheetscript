$ErrorActionPreference = "Stop"
schtasks /Delete /TN "MagnusLensPrintAgent" /F
python -m pip show pywin32 *> $null
if ($LASTEXITCODE -eq 0) {
    python -c "import win32serviceutil; win32serviceutil.RemoveService('MagnusLensPrintAgent')"
}
Write-Host "The agent task was removed. C:\ProgramData\MagnusLens was left in place, including printer-agent.json."
