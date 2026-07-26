param(
  [int]$TargetCount = 10000,
  [string]$Output = "",
  [string[]]$IconicTaxon = @()
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

if (-not $Output) {
  $Output = Join-Path $Root "data\taxonomy\common_species_10k.csv"
}

$ArgsList = @(
  (Join-Path $Root "scripts\build_common_species_catalog.py"),
  "--target-count", "$TargetCount",
  "--output", $Output
)

foreach ($item in $IconicTaxon) {
  $ArgsList += @("--iconic-taxon", $item)
}

& $Python @ArgsList
