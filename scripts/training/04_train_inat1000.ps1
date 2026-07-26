param(
  [string]$DatasetRoot = "D:\WildLens_Datasets\inat2021",
  [int]$BatchSize = 8,
  [int]$Accumulation = 8,
  [int]$Workers = 0,
  [int]$Epochs = 6,
  [ValidateSet("mobilenet_v3_small", "efficientnet_b0", "convnext_tiny")][string]$Architecture = "mobilenet_v3_small"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
$ResumeArgs = @()
if (Test-Path "models\trained\inat1000\last.pt") {
  $ResumeArgs = @("--resume", "models/trained/inat1000/last.pt")
  Write-Host "检测到断点，将继续训练 inat1000。" -ForegroundColor Yellow
}
uv run python ml/training/train_inat10k.py `
  --dataset-root $DatasetRoot `
  --profile mini `
  --max-classes 1000 `
  --samples-per-class 50 `
  --epochs $Epochs `
  --freeze-backbone-epochs 2 `
  --batch-size $BatchSize `
  --accumulation $Accumulation `
  --workers $Workers `
  --architecture $Architecture `
  --output-dir models/trained/inat1000 `
  @ResumeArgs
