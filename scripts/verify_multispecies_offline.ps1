param(
  [switch]$DownloadSamples,
  [switch]$UseAiCorrection,
  [int]$TopK = 10,
  [int]$BatchSize = 4096
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

$ArgsList = @(
  (Join-Path $Root "scripts\verify_multispecies_offline.py"),
  "--top-k", "$TopK",
  "--batch-size", "$BatchSize"
)

if ($DownloadSamples) {
  $ArgsList += "--download-samples"
}

if ($UseAiCorrection) {
  $ArgsList += "--use-ai-correction"
}

& $Python @ArgsList
