param([string]$DatasetRoot = "D:\WildLens_Datasets\inat2021")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
uv run python ml/training/train_inat10k.py `
  --dataset-root $DatasetRoot `
  --profile mini `
  --max-classes 100 `
  --samples-per-class 50 `
  --epochs 2 `
  --freeze-backbone-epochs 1 `
  --batch-size 8 `
  --accumulation 4 `
  --workers 0 `
  --limit-train-batches 5 `
  --limit-val-batches 2 `
  --architecture mobilenet_v3_small `
  --output-dir models/trained/inat100_smoke
