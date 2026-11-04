param(
    [Parameter(Mandatory = $true)][string]$ApiUrl,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$Password,
    [string]$PrinterName = "Zebra ZC300 USB Card Printer",
    [string]$DeviceName = $env:COMPUTERNAME,
    [string]$InstallDir = "C:\ProgramData\MagnusLens"
)

$ErrorActionPreference = "Stop"

if ($PrinterName -match "^USB\d+$") {
    throw "USB002 is a Windows port, not the printer name. Use Zebra ZC300 USB Card Printer."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Install Python 3.11 or newer and make sure python is on PATH."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$source = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $source "printer_agent"))) {
    $source = (Get-Location).Path
}
Copy-Item -Recurse -Force (Join-Path $source "*") $InstallDir
Set-Location $InstallDir

& python -m pip install --upgrade pip
& python -m pip install -r requirements-windows.txt

$loginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body $loginBody
$registerBody = @{
    device_name = $DeviceName
    printer_name = $PrinterName
    location = "Jagadamba Optics"
    operating_system = "Windows"
    agent_version = "1.0.0"
} | ConvertTo-Json
$registered = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/devices/register" -ContentType "application/json" -Headers @{ Authorization = "Bearer $($login.access_token)" } -Body $registerBody

$config = @{
    api_url = $ApiUrl
    device_token = $registered.device_token
    printer_name = $PrinterName
    poll_seconds = 5
    output_dir = (Join-Path $InstallDir "out")
} | ConvertTo-Json
$configPath = Join-Path $InstallDir "printer-agent.json"
Set-Content -Path $configPath -Value $config -Encoding utf8

$env:MAGNUS_AGENT_CONFIG = $configPath
& python -c "from printer_agent.printer_detector import installed_printers; print('\n'.join(installed_printers()))"

$task = "MagnusLensPrintAgent"
$action = "python -m printer_agent run"
schtasks /Create /TN $task /SC ONLOGON /RL LIMITED /TR $action /F | Out-Null
Write-Host "Registered logon task $task. This USB printer is used from the signed-in Windows session."
Write-Host "Device id: $($registered.device.id)"
Write-Host "The device token was saved in $configPath. It is not shown again."
Write-Host "To also install the Windows service, run: python -m printer_agent install-service"
Write-Host "A service in session 0 may not see a USB printer. Prefer the logon task until a test card reaches the spooler."
