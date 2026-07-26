$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PackRoot = Join-Path $ProjectRoot "storage\cloud_migration\wildlens_compact_prototype_pack"
$HfHome = Join-Path $PackRoot "models\hf_cache"
$PrototypeDb = Join-Path $PackRoot "storage\species_prototypes_inference.sqlite"
$ModelBin = Join-Path $HfHome "hub\models--imageomics--bioclip\snapshots\ce901ab3c6a913f9e9ef94ce6d27761069f4f01c\open_clip_pytorch_model.bin"

if (-not (Test-Path $PackRoot)) { throw "BioCLIP compact pack not found: $PackRoot" }
if (-not (Test-Path $HfHome)) { throw "BioCLIP HF cache not found: $HfHome" }
if (-not (Test-Path $PrototypeDb)) { throw "BioCLIP prototype database not found: $PrototypeDb" }
if (-not (Test-Path $ModelBin)) { throw "BioCLIP model weight not found: $ModelBin" }

$env:BIOCLIP_ENABLED = "true"
$env:BIOCLIP_MODEL_ID = "hf-hub:imageomics/bioclip"
$env:BIOCLIP_EMBEDDING_DIM = "512"
$env:BIOCLIP_HF_HOME = $HfHome
$env:BIOCLIP_PROTOTYPE_DB_PATH = $PrototypeDb
$env:BIOCLIP_DEVICE = if ($env:BIOCLIP_DEVICE) { $env:BIOCLIP_DEVICE } else { "cpu" }
$env:BIOCLIP_TOP_K = if ($env:BIOCLIP_TOP_K) { $env:BIOCLIP_TOP_K } else { "10" }
$env:BIOCLIP_BATCH_SIZE = if ($env:BIOCLIP_BATCH_SIZE) { $env:BIOCLIP_BATCH_SIZE } else { "4096" }
$env:HF_HOME = $HfHome
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"

Write-Host "BioCLIP offline environment configured for this PowerShell session."
Write-Host "Project: $ProjectRoot"
Write-Host "HF_HOME: $env:HF_HOME"
Write-Host "Prototype DB: $env:BIOCLIP_PROTOTYPE_DB_PATH"
Write-Host "Model: $env:BIOCLIP_MODEL_ID"
Write-Host "Embedding dim: $env:BIOCLIP_EMBEDDING_DIM"
Write-Host "No model or database files were copied."
