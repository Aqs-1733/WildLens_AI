param(
  [int]$MaxSpecies = 8,
  [int]$StartIndex = 0,
  [int]$ImagesPerSpecies = 2,
  [string]$Taxonomy = "",
  [string]$MediaSource = "auto",
  [string[]]$Category = @(),
  [string[]]$Priority = @(),
  [switch]$SkipSpeciesNet,
  [switch]$KeepImages,
  [switch]$StoreEmbeddings,
  [switch]$AppendOutput,
  [switch]$AllowUnlicensedInat,
  [switch]$SkipExisting
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
& (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")
if (-not $SkipSpeciesNet) {
  & (Join-Path $PSScriptRoot "start_speciesnet_cpu.ps1")
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

$ArgsList = @(
  (Join-Path $Root "scripts\active_learning_stream.py"),
  "--max-species", "$MaxSpecies",
  "--start-index", "$StartIndex",
  "--images-per-species", "$ImagesPerSpecies",
  "--media-source", "$MediaSource"
)

if ($Taxonomy) {
  $ArgsList += @("--taxonomy", $Taxonomy)
}

foreach ($item in $Category) {
  $ArgsList += @("--category", $item)
}
foreach ($item in $Priority) {
  $ArgsList += @("--priority", $item)
}
if ($SkipSpeciesNet) {
  $ArgsList += "--skip-speciesnet"
}
if ($KeepImages) {
  $ArgsList += "--keep-images"
}
if ($StoreEmbeddings) {
  $ArgsList += "--store-embeddings"
}
if ($AppendOutput) {
  $ArgsList += "--append-output"
}
if ($AllowUnlicensedInat) {
  $ArgsList += "--allow-unlicensed-inat"
}
if ($SkipExisting) {
  $ArgsList += "--skip-existing"
}

& $Python @ArgsList
