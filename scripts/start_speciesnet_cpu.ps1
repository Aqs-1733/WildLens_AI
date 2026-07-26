$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:SPECIESNET_API_PYTHON) { $env:SPECIESNET_API_PYTHON } else { Join-Path $ProjectRoot ".venv-speciesnet-cpu\Scripts\python.exe" }
$HostName = if ($env:SPECIESNET_API_HOST) { $env:SPECIESNET_API_HOST } else { "127.0.0.1" }
$Port = if ($env:SPECIESNET_API_PORT) { [int]$env:SPECIESNET_API_PORT } else { 8101 }
$Cache = if ($env:KAGGLEHUB_CACHE) { $env:KAGGLEHUB_CACHE } else { Join-Path $ProjectRoot "models\speciesnet_offline" }
$PidDir = Join-Path $ProjectRoot "storage\pids"
$LogDir = Join-Path $ProjectRoot "storage\logs"
$PidFile = Join-Path $PidDir "speciesnet_cpu.pid"
$LogFile = Join-Path $LogDir "speciesnet_cpu.log"
$ErrFile = Join-Path $LogDir "speciesnet_cpu.error.log"
$AlreadyRunning = $false

New-Item -ItemType Directory -Force -Path $PidDir, $LogDir, (Join-Path $ProjectRoot "storage\speciesnet_cache") | Out-Null

if (-not (Test-Path $Python)) {
  throw "SpeciesNet CPU Python not found: $Python"
}
if (-not (Test-Path $Cache)) {
  throw "SpeciesNet offline cache not found: $Cache"
}

if (Test-Path $PidFile) {
  $OldPid = (Get-Content $PidFile -Raw).Trim()
  if ($OldPid) {
    $Existing = Get-Process -Id ([int]$OldPid) -ErrorAction SilentlyContinue
    if ($Existing) {
      $ExistingCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$OldPid").CommandLine
      if ($ExistingCommand -like "*services\speciesnet_api\app.py*" -or $ExistingCommand -like "*services/speciesnet_api/app.py*") {
        Write-Host "SpeciesNet CPU service already running with PID $OldPid"
        $AlreadyRunning = $true
      } else {
        Write-Host "Ignoring stale SpeciesNet PID file; PID $OldPid belongs to another process"
      }
    }
  }
  if (-not $AlreadyRunning) {
    Remove-Item $PidFile -Force
  }
}

$env:KAGGLEHUB_CACHE = $Cache
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:SPECIESNET_MODEL_NAME = if ($env:SPECIESNET_MODEL_NAME) { $env:SPECIESNET_MODEL_NAME } else { "kaggle:google/speciesnet/pyTorch/v4.0.3a/1" }
$env:SPECIESNET_MODEL_VERSION = if ($env:SPECIESNET_MODEL_VERSION) { $env:SPECIESNET_MODEL_VERSION } else { "4.0.3a" }
$env:SPECIESNET_CACHE_DIR = if ($env:SPECIESNET_CACHE_DIR) { $env:SPECIESNET_CACHE_DIR } else { Join-Path $ProjectRoot "storage\speciesnet_cache" }
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$ProjectRoot;$env:PYTHONPATH" } else { $ProjectRoot }

if (-not $AlreadyRunning) {
  $Args = @("services\speciesnet_api\app.py", "--host", $HostName, "--port", [string]$Port)
  $Process = Start-Process -FilePath $Python `
    -ArgumentList $Args `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrFile `
    -WindowStyle Hidden `
    -PassThru

  Set-Content -Path $PidFile -Value $Process.Id -Encoding ASCII
  Write-Host "Started SpeciesNet CPU service PID $($Process.Id) at http://$HostName`:$Port"
}

$HealthUrl = "http://$HostName`:$Port/health"
for ($i = 0; $i -lt 120; $i++) {
  Start-Sleep -Seconds 2
  try {
    $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5
    if ($Health.status -eq "ready" -and $Health.model_loaded -eq $true) {
      Write-Host "SpeciesNet CPU health ready"
      $Health | ConvertTo-Json -Depth 6
      exit 0
    }
  } catch {
    if ($i -eq 119) { throw }
  }
}

throw "SpeciesNet CPU service did not become ready. See $LogFile and $ErrFile"
