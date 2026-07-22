param([string]$DatasetRoot = "D:\WildLens_Datasets\inat2021")
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\download_inat2021.ps1" -DatasetRoot $DatasetRoot -Profile mini
