param(
  [string]$DatasetRoot = "D:\WildLens_Datasets\inat2021",
  [ValidateSet("mini", "full")][string]$Profile = "mini",
  [switch]$SkipExtract
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $DatasetRoot | Out-Null
$free = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($DatasetRoot).TrimEnd(':','\'))).Free
if ($Profile -eq "mini" -and $free -lt 120GB) {
  Write-Warning "剩余空间少于120GB。mini压缩包约50GB，解压和训练产物还需要额外空间。"
}
if ($Profile -eq "full" -and $free -lt 500GB) {
  Write-Warning "完整iNaturalist 2021数据非常大，建议至少准备500GB可用空间。"
}

$base = "https://ml-inat-competition-datasets.s3.amazonaws.com/2021"
$files = @(
  @{ Name = "val.tar.gz"; Url = "$base/val.tar.gz"; Md5 = "f6f6e0e242e3d4c9569ba56400938afc" },
  @{ Name = "val.json.tar.gz"; Url = "$base/val.json.tar.gz"; Md5 = "4d761e0f6a86cc63e8f7afc91f6a8f0b" }
)
if ($Profile -eq "mini") {
  $files += @{ Name = "train_mini.tar.gz"; Url = "$base/train_mini.tar.gz"; Md5 = "db6ed8330e634445efc8fec83ae81442" }
  $files += @{ Name = "train_mini.json.tar.gz"; Url = "$base/train_mini.json.tar.gz"; Md5 = "395a35be3651d86dc3b0d365b8ea5f92" }
} else {
  $files += @{ Name = "train.tar.gz"; Url = "$base/train.tar.gz"; Md5 = "e0526d53c7f7b2e3167b2b43bb2690ed" }
  $files += @{ Name = "train.json.tar.gz"; Url = "$base/train.json.tar.gz"; Md5 = "38a7bb733f7a09214d44293460ec0021" }
}

foreach ($item in $files) {
  $target = Join-Path $DatasetRoot $item.Name
  Write-Host "\n下载 $($item.Name)" -ForegroundColor Cyan
  & curl.exe -L --fail --retry 8 --retry-delay 5 -C - -o $target $item.Url
  if ($LASTEXITCODE -ne 0) { throw "下载失败：$($item.Url)" }
  $actual = (Get-FileHash -Path $target -Algorithm MD5).Hash.ToLower()
  if ($actual -ne $item.Md5.ToLower()) {
    throw "MD5校验失败：$target`n期望 $($item.Md5)`n实际 $actual"
  }
  Write-Host "MD5通过：$actual" -ForegroundColor Green
}

if (-not $SkipExtract) {
  foreach ($item in $files) {
    $target = Join-Path $DatasetRoot $item.Name
    Write-Host "解压 $target" -ForegroundColor Cyan
    & tar.exe -xzf $target -C $DatasetRoot
    if ($LASTEXITCODE -ne 0) { throw "解压失败：$target" }
  }
}

Write-Host "\niNaturalist 2021 $Profile 数据准备完成：$DatasetRoot" -ForegroundColor Green
Write-Host "数据仅限遵守原始许可的研究与教育用途；不要重新分发原始图片。" -ForegroundColor Yellow
