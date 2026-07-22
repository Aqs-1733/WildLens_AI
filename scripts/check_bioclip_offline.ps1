$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:BIOCLIP_PYTHON) { $env:BIOCLIP_PYTHON } else { Join-Path $ProjectRoot ".venv-speciesnet-cpu\Scripts\python.exe" }

if (-not (Test-Path $Python)) {
  throw "Python not found: $Python"
}

& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")
& $Python (Join-Path $PSScriptRoot "verify_bioclip_offline.py") --check-only
