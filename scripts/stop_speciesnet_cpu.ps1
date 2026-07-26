$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $ProjectRoot "storage\pids\speciesnet_cpu.pid"

if (-not (Test-Path $PidFile)) {
  Write-Host "SpeciesNet CPU PID file not found; nothing to stop"
  exit 0
}

$PidText = (Get-Content $PidFile -Raw).Trim()
if (-not $PidText) {
  Remove-Item $PidFile -Force
  Write-Host "SpeciesNet CPU PID file was empty"
  exit 0
}

$PidValue = [int]$PidText
$Process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
if (-not $Process) {
  Remove-Item $PidFile -Force
  Write-Host "SpeciesNet CPU process $PidValue is not running"
  exit 0
}

$Command = (Get-CimInstance Win32_Process -Filter "ProcessId=$PidValue").CommandLine
if ($Command -notlike "*services\speciesnet_api\app.py*" -and $Command -notlike "*services/speciesnet_api/app.py*") {
  throw "Refusing to stop PID $PidValue because it is not the SpeciesNet CPU service: $Command"
}

Stop-Process -Id $PidValue
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  if (-not (Get-Process -Id $PidValue -ErrorAction SilentlyContinue)) {
    Remove-Item $PidFile -Force
    Write-Host "Stopped SpeciesNet CPU service PID $PidValue"
    exit 0
  }
}

Stop-Process -Id $PidValue -Force -ErrorAction SilentlyContinue
Remove-Item $PidFile -Force
Write-Host "Force-stopped SpeciesNet CPU service PID $PidValue"

