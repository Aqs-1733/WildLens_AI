param(
  [int]$StartIndex = -1,
  [int]$TargetCount = 10000,
  [int]$ImagesPerSpecies = 3,
  [string]$Taxonomy = "",
  [string[]]$Category = @(),
  [switch]$SkipSpeciesNet,
  [switch]$AllowUnlicensedInat,
  [switch]$NoSkipExisting,
  [switch]$NoTranscript
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$SummaryPath = Join-Path $Root "storage\active_learning\stream_eval_summary.json"
$OutputPath = Join-Path $Root "storage\active_learning\stream_eval.jsonl"
$TmpDir = Join-Path $Root "storage\tmp_active_learning"
$LogDir = Join-Path $Root "storage\logs"
$PidDir = Join-Path $Root "storage\pids"
$LockPath = Join-Path $PidDir "train_common_species_10k.lock"

function Assert-NoTrainingProcess {
  $Existing = Get-CimInstance Win32_Process |
    Where-Object {
      $_.ProcessId -ne $PID -and
      $_.CommandLine -and
      ($_.CommandLine -like "*active_learning_stream.py*" -or $_.CommandLine -like "*train_common_species_10k.ps1*")
    }
  if ($Existing) {
    $List = ($Existing | ForEach-Object { "PID $($_.ProcessId): $($_.CommandLine)" }) -join "`n"
    throw "Another common-species training process is already running. Stop it first or wait for it to finish.`n$List"
  }
}

function Enter-TrainingLock {
  param([string]$Path)

  New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
  if (Test-Path $Path) {
    $OldPidText = (Get-Content $Path -Raw).Trim()
    if ($OldPidText) {
      $OldProcess = Get-Process -Id ([int]$OldPidText) -ErrorAction SilentlyContinue
      if ($OldProcess) {
        $OldCommand = (Get-CimInstance Win32_Process -Filter "ProcessId=$OldPidText").CommandLine
        if ($OldCommand -like "*train_common_species_10k.ps1*" -or $OldCommand -like "*active_learning_stream.py*") {
          throw "Training is already running with PID $OldPidText."
        }
      }
    }
    Remove-Item $Path -Force
  }
  Set-Content -Path $Path -Value $PID -Encoding ASCII
}

function Exit-TrainingLock {
  param([string]$Path)

  if (Test-Path $Path) {
    $PidText = (Get-Content $Path -Raw).Trim()
    if ($PidText -eq [string]$PID) {
      Remove-Item $Path -Force
    }
  }
}

function Get-JsonlResumeIndex {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return -1
  }

  $MaxRank = -1
  foreach ($Line in [System.IO.File]::ReadLines($Path)) {
    if ([string]::IsNullOrWhiteSpace($Line)) {
      continue
    }
    try {
      $Row = $Line | ConvertFrom-Json
      if ($null -ne $Row.catalog_rank) {
        $Rank = [int]$Row.catalog_rank
        if ($Rank -gt $MaxRank) {
          $MaxRank = $Rank
        }
      }
    } catch {
      continue
    }
  }

  if ($MaxRank -ge 0) {
    return $MaxRank
  }
  return -1
}

if (-not $Taxonomy) {
  $Taxonomy = Join-Path $Root "data\taxonomy\common_species_10k.csv"
}
if (-not (Test-Path $Taxonomy)) {
  & (Join-Path $PSScriptRoot "build_common_species_catalog.ps1") -TargetCount $TargetCount -Output $Taxonomy
}

if ($StartIndex -lt 0) {
  $StartIndex = 0
  $SummaryResumeIndex = -1
  if (Test-Path $SummaryPath) {
    try {
      $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
      if ($null -ne $Summary.next_start_index) {
        $SummaryResumeIndex = [int]$Summary.next_start_index
      }
    } catch {
      Write-Warning "Could not read previous summary; checking JSONL progress."
    }
  }
  $JsonlResumeIndex = Get-JsonlResumeIndex -Path $OutputPath
  $StartIndex = [Math]::Max(0, [Math]::Max($SummaryResumeIndex, $JsonlResumeIndex))
  if ($SummaryResumeIndex -ge 0 -or $JsonlResumeIndex -ge 0) {
    Write-Host "Resume index: $StartIndex (summary=$SummaryResumeIndex, jsonl=$JsonlResumeIndex)"
  }
}

$Remaining = [Math]::Max(0, $TargetCount - $StartIndex)
if ($Remaining -le 0) {
  Write-Host "All requested species are already past TargetCount=$TargetCount. Nothing to run."
  exit 0
}

New-Item -ItemType Directory -Force -Path $LogDir, $PidDir | Out-Null
Assert-NoTrainingProcess
Enter-TrainingLock -Path $LockPath
if (Test-Path $TmpDir) {
  Get-ChildItem -LiteralPath $TmpDir -File -ErrorAction SilentlyContinue | Remove-Item -Force
}

$TranscriptStarted = $false
if (-not $NoTranscript) {
  $LogPath = Join-Path $LogDir ("train_common_species_10k_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
  Start-Transcript -Path $LogPath -Append | Out-Null
  $TranscriptStarted = $true
  Write-Host "Log: $LogPath"
}

try {
  & (Join-Path $PSScriptRoot "setup_bioclip_offline.ps1")
  if (-not $SkipSpeciesNet) {
    & (Join-Path $PSScriptRoot "start_speciesnet_cpu.ps1")
  }

  $Python = Join-Path $Root ".venv\Scripts\python.exe"
  if (-not (Test-Path $Python)) {
    $Python = "python"
  }

  Write-Host "Starting continuous 10k common-species training"
  Write-Host "StartIndex: $StartIndex"
  Write-Host "Remaining species this run: $Remaining"
  Write-Host "ImagesPerSpecies: $ImagesPerSpecies"
  Write-Host "Taxonomy: $Taxonomy"
  Write-Host "Output: $OutputPath"
  Write-Host "Summary: $SummaryPath"
  Write-Host "Press Ctrl+C to stop; next run will resume from the saved next_start_index."

  $ArgsList = @(
    (Join-Path $Root "scripts\active_learning_stream.py"),
    "--taxonomy", $Taxonomy,
    "--start-index", "$StartIndex",
    "--max-species", "$Remaining",
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
  $ExitCode = $LASTEXITCODE

  if (Test-Path $SummaryPath) {
    Write-Host ""
    Write-Host "Latest summary:"
    Get-Content $SummaryPath
  }

  Write-Host ""
  Write-Host "Learning memory status:"
  & $Python -c "from backend.vision.active_learning_memory import active_learning_memory; import json; print(json.dumps(active_learning_memory.status(), ensure_ascii=False, indent=2))"

  Write-Host ""
  Write-Host "Temporary image files:"
  Get-ChildItem $TmpDir -ErrorAction SilentlyContinue | Measure-Object | Select-Object Count

  exit $ExitCode
} finally {
  Exit-TrainingLock -Path $LockPath
  if ($TranscriptStarted) {
    Stop-Transcript | Out-Null
  }
}
