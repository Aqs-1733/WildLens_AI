$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:BIOCLIP_PYTHON) { $env:BIOCLIP_PYTHON } else { Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
$Image = if ($env:BIOCLIP_TEST_IMAGE) { $env:BIOCLIP_TEST_IMAGE } else { Join-Path $ProjectRoot "storage\cloud_migration\wildlens_compact_prototype_pack\test\images\tiger.jpg" }

if (-not (Test-Path $Python)) {
  throw "Python not found: $Python"
}
if (-not (Test-Path $Image)) {
  throw "BioCLIP test image not found: $Image"
}

& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")
& $Python (Join-Path $PSScriptRoot "verify_bioclip_offline.py") --image $Image --device $env:BIOCLIP_DEVICE --top-k ([int]$env:BIOCLIP_TOP_K) --batch-size ([int]$env:BIOCLIP_BATCH_SIZE)

