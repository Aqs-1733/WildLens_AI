$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "storage\logs"
$PidDir = Join-Path $Root "storage\pids"
New-Item -ItemType Directory -Force -Path $LogDir, $PidDir, (Join-Path $Root "storage\uploads"), (Join-Path $Root "storage\results"), (Join-Path $Root "storage\reports"), (Join-Path $Root "storage\annotated"), (Join-Path $Root "storage\playback"), (Join-Path $Root "storage\outputs"), (Join-Path $Root "models\registry"), (Join-Path $Root "models\checkpoints") | Out-Null

function Test-Tool($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name"
  }
}

function Test-LivePid($Path) {
  if (-not (Test-Path $Path)) { return $false }
  $pidValue = (Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $pidValue) { return $false }
  return [bool](Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue)
}

function Start-Managed($Name, $FilePath, [string[]]$Arguments, $WorkingDirectory) {
  $pidFile = Join-Path $PidDir "$Name.pid"
  if (Test-LivePid $pidFile) {
    Write-Host "$Name already running with PID $(Get-Content $pidFile)"
    return
  }
  $stdout = Join-Path $LogDir "$Name.console.log"
  $stderr = Join-Path $LogDir "$Name.error.log"
  $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
  Set-Content -Path $pidFile -Value $process.Id
  Write-Host "$Name started with PID $($process.Id)"
}

Push-Location $Root
try {
  Test-Tool "uv"
  Test-Tool "node"
  Test-Tool "pnpm"
  Test-Tool "ffmpeg"
  Test-Tool "ffprobe"

  uv sync --extra bioclip
  uv run python scripts/migrate_db.py

  $uv = (Get-Command uv).Source
  $pnpm = (Get-Command pnpm).Source
  Start-Managed "backend" $uv @("run", "python", "backend/main.py") $Root
  Start-Managed "worker" $uv @("run", "python", "scripts/worker.py") $Root
  Start-Managed "frontend" "cmd.exe" @("/c", "pnpm", "dev") (Join-Path $Root "frontend")

  Write-Host ""
  Write-Host "识境 is starting."
  Write-Host "Frontend: http://127.0.0.1:5174"
  Write-Host "API docs: http://127.0.0.1:8010/docs"
  Write-Host "Health: http://127.0.0.1:8010/api/health"
  Write-Host "Logs: $LogDir"
} finally {
  Pop-Location
}
