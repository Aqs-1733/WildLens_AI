$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HostName = if ($env:SPECIESNET_API_HOST) { $env:SPECIESNET_API_HOST } else { "127.0.0.1" }
$Port = if ($env:SPECIESNET_API_PORT) { [int]$env:SPECIESNET_API_PORT } else { 8101 }
$Image = if ($env:SPECIESNET_TEST_IMAGE) { $env:SPECIESNET_TEST_IMAGE } else { Join-Path $ProjectRoot "models\speciesnet_offline\test\images\tiger.jpg" }
$BaseUrl = "http://$HostName`:$Port"

Write-Host "Checking SpeciesNet CPU service at $BaseUrl"
$Health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 10
$Health | ConvertTo-Json -Depth 8
if ($Health.status -ne "ready" -or $Health.model_loaded -ne $true) {
  throw "SpeciesNet CPU service is not ready"
}
if (-not (Test-Path $Image)) {
  throw "Test image not found: $Image"
}

Add-Type -AssemblyName System.Net.Http
$Client = [System.Net.Http.HttpClient]::new()
$Client.Timeout = [TimeSpan]::FromSeconds(180)
$Content = [System.Net.Http.MultipartFormDataContent]::new()
$Bytes = [System.Net.Http.ByteArrayContent]::new([System.IO.File]::ReadAllBytes($Image))
$Bytes.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("image/jpeg")
$Content.Add($Bytes, "file", [System.IO.Path]::GetFileName($Image))
$Content.Add([System.Net.Http.StringContent]::new("5"), "top_k")

$Response = $Client.PostAsync("$BaseUrl/predict/upload", $Content).GetAwaiter().GetResult()
$Body = $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
if (-not $Response.IsSuccessStatusCode) {
  throw "Prediction failed: $($Response.StatusCode) $Body"
}
$Json = $Body | ConvertFrom-Json
$Json | ConvertTo-Json -Depth 12
if ($Json.result.scientific_name -ne "Panthera tigris") {
  throw "Expected Panthera tigris, got $($Json.result.scientific_name)"
}
if ([double]$Json.result.score -lt 0.99) {
  throw "Expected tiger score close to 0.9992, got $($Json.result.score)"
}
if (-not ($Json.result.detections | Where-Object { $_.label -eq "animal" })) {
  throw "Expected an animal detection"
}
Write-Host "SpeciesNet CPU tiger check passed"

