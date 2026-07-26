param(
  [int]$StartIndex = 0,
  [int]$MaxSpecies = 100,
  [int]$ImagesPerSpecies = 1,
  [string]$Taxonomy = "",
  [string[]]$Category = @(),
  [switch]$SkipSpeciesNet,
  [switch]$AllowUnlicensedInat,
  [switch]$NoSkipExisting
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $Taxonomy) {
  $Taxonomy = Join-Path $Root "data\taxonomy\common_species_10k.csv"
}
if (-not (Test-Path $Taxonomy)) {
  & (Join-Path $PSScriptRoot "build_common_species_catalog.ps1") -TargetCount 10000 -Output $Taxonomy
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")

$ArgsList = @(
  (Join-Path $Root "scripts\active_learning_stream.py"),
  "--taxonomy", $Taxonomy,
  "--start-index", "$StartIndex",
  "--max-species", "$MaxSpecies",
  "--images-per-species", "$ImagesPerSpecies",
  "--media-source", "inat",
  "--store-embeddings",
  "--append-output"
)

if (-not $NoSkipExisting) {
  $ArgsList += "--skip-existing"
}

foreach ($item in $Category) {
  $ArgsList += @("--category", $item)
}
if ($SkipSpeciesNet) {
  $ArgsList += "--skip-speciesnet"
}
if ($AllowUnlicensedInat) {
  $ArgsList += "--allow-unlicensed-inat"
}

& $Python @ArgsList
