param(
  [string]$DatasetRoot = "D:\WildLens_Datasets\inat2021",
  [int]$BatchSize = 8,
  [int]$Accumulation = 8,
  [int]$Workers = 0,
  [int]$Epochs = 12,
  [ValidateSet("mobilenet_v3_small", "efficientnet_b0", "convnext_tiny")][string]$Architecture = "mobilenet_v3_small"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
$ResumeArgs = @()
if (Test-Path "models\trained\inat10k\last.pt") {
  $ResumeArgs = @("--resume", "models/trained/inat10k/last.pt")
  Write-Host "检测到断点，将继续训练 inat10k。" -ForegroundColor Yellow
} elseif (Test-Path "models\trained\inat1000\best.pt") {
  $ResumeArgs = @("--init-backbone", "models/trained/inat1000/best.pt")
  Write-Host "使用1000类最佳权重初始化一万类主干。" -ForegroundColor Green
}
uv run python scripts/datasets/import_inat_taxonomy.py "$DatasetRoot\train_mini.json"
uv run python ml/training/train_inat10k.py `
  --dataset-root $DatasetRoot `
  --profile mini `
  --max-classes 10000 `
  --samples-per-class 50 `
  --epochs $Epochs `
  --freeze-backbone-epochs 2 `
  --batch-size $BatchSize `
  --accumulation $Accumulation `
  --workers $Workers `
  --architecture $Architecture `
  --output-dir models/trained/inat10k `
  @ResumeArgs
