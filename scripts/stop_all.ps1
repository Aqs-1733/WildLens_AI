$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PidDir = Join-Path $Root "storage\pids"

function Stop-ProcessTree([int]$ProcessId) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId }
  foreach ($child in $children) {
    Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
  }
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path $PidDir)) {
  Write-Host "No PID directory found."
}

foreach ($name in @("frontend", "worker", "backend", "speciesnet_cpu")) {
  $pidFile = Join-Path $PidDir "$name.pid"
  if (-not (Test-Path $pidFile)) {
    Write-Host "$name is not managed."
    continue
  }
  $pidValue = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($pidValue) {
    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    if ($process) {
      Stop-ProcessTree -ProcessId $process.Id
      Write-Host "$name stopped (PID $pidValue)."
    } else {
      Write-Host "$name PID $pidValue is not running."
    }
  }
  Remove-Item -LiteralPath $pidFile -Force
}

$rootPattern = [regex]::Escape($Root.Path)
$leftovers = Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match $rootPattern -and
  ($_.CommandLine -match 'backend[/\\]main.py' -or
   $_.CommandLine -match 'scripts[/\\]worker.py' -or
   $_.CommandLine -match 'services[/\\]speciesnet_api[/\\]app.py' -or
   ($_.CommandLine -match 'vite' -and $_.CommandLine -match '5174'))
}
foreach ($item in $leftovers) {
  Stop-ProcessTree -ProcessId ([int]$item.ProcessId)
  Write-Host "stopped leftover $($item.Name) PID $($item.ProcessId)"
}
