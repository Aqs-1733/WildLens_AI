param()

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$SummaryPath = Join-Path $Root "storage\active_learning\stream_eval_summary.json"
$OutputPath = Join-Path $Root "storage\active_learning\stream_eval.jsonl"
$TmpDir = Join-Path $Root "storage\tmp_active_learning"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

function Get-JsonlProgress {
  param([string]$Path)

  $Progress = [ordered]@{
    rows = 0
    unique_species = 0
    max_catalog_rank = -1
    next_start_index = 0
    last_expected = $null
    last_common_name = $null
    last_created_at = $null
  }
  if (-not (Test-Path $Path)) {
    return $Progress
  }

  $Species = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($Line in [System.IO.File]::ReadLines($Path)) {
    if ([string]::IsNullOrWhiteSpace($Line)) {
      continue
    }
    try {
      $Row = $Line | ConvertFrom-Json
    } catch {
      continue
    }

    $Progress.rows += 1
    if ($null -ne $Row.catalog_rank) {
      $Rank = [int]$Row.catalog_rank
      if ($Rank -gt $Progress.max_catalog_rank) {
        $Progress.max_catalog_rank = $Rank
      }
    }
    $Expected = $Row.expected
    if (-not $Expected) {
      $Expected = $Row.scientific_name
    }
    if ($Expected) {
      [void]$Species.Add([string]$Expected)
    }
    $Progress.last_expected = $Row.expected
    $Progress.last_common_name = $Row.common_name
    $Progress.last_created_at = $Row.created_at
    if (-not $Progress.last_created_at) {
      $Progress.last_created_at = $Row.timestamp
    }
  }

  $Progress.unique_species = $Species.Count
  $Progress.next_start_index = [Math]::Max(0, $Progress.max_catalog_rank)
  return $Progress
}

Write-Host "Summary:"
if (Test-Path $SummaryPath) {
  Get-Content $SummaryPath
} else {
  Write-Host "No summary yet: $SummaryPath"
}

Write-Host ""
Write-Host "JSONL progress:"
$Progress = Get-JsonlProgress -Path $OutputPath
($Progress | ConvertTo-Json -Depth 4)

Write-Host ""
Write-Host "Learning memory:"
& $Python -c "from backend.vision.active_learning_memory import active_learning_memory; import json; print(json.dumps(active_learning_memory.status(), ensure_ascii=False, indent=2))"

Write-Host ""
Write-Host "Temporary image files:"
Get-ChildItem $TmpDir -ErrorAction SilentlyContinue | Measure-Object | Select-Object Count

Write-Host ""
Write-Host "Running training processes:"
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object { $_.CommandLine -like "*active_learning_stream.py*" } |
  Select-Object ProcessId, CommandLine |
  Format-List
