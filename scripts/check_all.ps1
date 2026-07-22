$ErrorActionPreference = "Continue"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PidDir = Join-Path $Root "storage\pids"

function Check-Tool($Name) {
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if ($cmd) { Write-Host "[ok] $Name -> $($cmd.Source)" } else { Write-Host "[missing] $Name" }
}

function Check-Pid($Name) {
  $pidFile = Join-Path $PidDir "$Name.pid"
  if (-not (Test-Path $pidFile)) { Write-Host "[idle] $Name has no PID file"; return }
  $pidValue = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  $process = if ($pidValue) { Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue } else { $null }
  if ($process) { Write-Host "[ok] $Name running PID $pidValue" } else { Write-Host "[stale] $Name PID $pidValue not running" }
}

Push-Location $Root
try {
  foreach ($tool in @("uv", "python", "node", "pnpm", "ffmpeg", "ffprobe")) { Check-Tool $tool }
  foreach ($name in @("backend", "worker", "frontend")) { Check-Pid $name }
  if (Test-Path ".env") { Write-Host "[ok] .env present" } else { Write-Host "[info] .env absent; defaults and .env.example are used" }
  foreach ($path in @("storage\uploads", "storage\results", "storage\reports", "storage\logs", "models\registry", "models\checkpoints")) {
    if (Test-Path $path) { Write-Host "[ok] $path" } else { Write-Host "[missing] $path" }
  }
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8010/api/health" -TimeoutSec 3
    Write-Host "[ok] backend health: $($health.status)"
  } catch {
    Write-Host "[warn] backend health unavailable: $($_.Exception.Message)"
  }
  try {
    $frontend = Invoke-WebRequest -Uri "http://127.0.0.1:5174" -UseBasicParsing -TimeoutSec 3
    if ($frontend -and $frontend.StatusCode) {
      Write-Host "[ok] frontend status: $($frontend.StatusCode)"
    } else {
      Write-Host "[warn] frontend response did not include a status code"
    }
  } catch {
    Write-Host "[warn] frontend unavailable: $($_.Exception.Message)"
  }
} finally {
  Pop-Location
}
