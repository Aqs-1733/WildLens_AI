$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
uv run python ml/export/export_inat10k_onnx.py models/trained/inat10k/best.pt --output models/onnx/wildlife_species.onnx
Write-Host "导出完成。请重启后端，模型会自动加载。" -ForegroundColor Green
