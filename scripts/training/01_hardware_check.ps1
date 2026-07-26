$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
uv sync --extra training --extra vision
uv run python scripts/training/check_hardware.py
