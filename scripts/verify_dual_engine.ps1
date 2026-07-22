$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:BIOCLIP_PYTHON) { $env:BIOCLIP_PYTHON } else { Join-Path $ProjectRoot ".venv-speciesnet-cpu\Scripts\python.exe" }
$Image = if ($env:BIOCLIP_TEST_IMAGE) { $env:BIOCLIP_TEST_IMAGE } else { Join-Path $ProjectRoot "storage\cloud_migration\wildlens_compact_prototype_pack\test\images\tiger.jpg" }
$HostName = if ($env:SPECIESNET_API_HOST) { $env:SPECIESNET_API_HOST } else { "127.0.0.1" }
$Port = if ($env:SPECIESNET_API_PORT) { [int]$env:SPECIESNET_API_PORT } else { 8101 }
$SpeciesNetUrl = "http://$HostName`:$Port"

if (-not (Test-Path $Python)) {
  throw "Python not found: $Python"
}
if (-not (Test-Path $Image)) {
  throw "Dual-engine test image not found: $Image"
}

& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")
& (Join-Path $PSScriptRoot "start_speciesnet_cpu.ps1")

$env:SPECIESNET_ENABLED = "true"
$env:SPECIESNET_API_URL = $SpeciesNetUrl
$env:BIOCLIP_ENABLED = "true"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$ProjectRoot;$env:PYTHONPATH" } else { $ProjectRoot }

& $Python (Join-Path $PSScriptRoot "verify_dual_engine.py") --image $Image --speciesnet-url $SpeciesNetUrl --device $env:BIOCLIP_DEVICE --top-k ([int]$env:BIOCLIP_TOP_K) --batch-size ([int]$env:BIOCLIP_BATCH_SIZE)
