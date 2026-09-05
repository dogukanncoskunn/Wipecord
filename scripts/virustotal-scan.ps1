# Submit the built Wipecord.exe to VirusTotal and save the result in the repo.
#
#   $env:VT_API_KEY = "<your free virustotal api key>"
#   powershell -ExecutionPolicy Bypass -File scripts\virustotal-scan.ps1
#
# Writes security\virustotal-result.json (full report) and prints a summary.
#
# NOTE: uploading makes the binary PUBLIC on VirusTotal. That is fine for an
# open-source release, but it is a deliberate choice — do not run this on a
# build you do not intend to publish.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe  = Join-Path $root "dist\Wipecord.exe"
$outDir = Join-Path $root "security"
$out  = Join-Path $outDir "virustotal-result.json"

if (-not $env:VT_API_KEY) { throw "Set VT_API_KEY first:  `$env:VT_API_KEY = '<key>'" }
if (-not (Test-Path $exe)) { throw "Build the exe first:  scripts\build-exe.ps1" }
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

$sha = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower()
Write-Host "SHA256: $sha"
Write-Host "Uploading $((Get-Item $exe).Length) bytes to VirusTotal..."

# curl.exe (bundled with Windows 10+) handles the multipart upload cleanly on
# both Windows PowerShell 5.1 and PowerShell 7.
$uploadJson = & curl.exe --silent --show-error --request POST `
    --url "https://www.virustotal.com/api/v3/files" `
    --header "x-apikey: $env:VT_API_KEY" `
    --form "file=@$exe"
$analysisId = ($uploadJson | ConvertFrom-Json).data.id
if (-not $analysisId) { throw "Upload failed: $uploadJson" }
Write-Host "Analysis id: $analysisId"

$headers = @{ "x-apikey" = $env:VT_API_KEY }
$uri = "https://www.virustotal.com/api/v3/analyses/$analysisId"
do {
    Start-Sleep -Seconds 15
    $report = Invoke-RestMethod -Uri $uri -Headers $headers
    $status = $report.data.attributes.status
    Write-Host "  status: $status"
} while ($status -ne "completed")

$report | ConvertTo-Json -Depth 12 | Out-File -FilePath $out -Encoding utf8
$stats = $report.data.attributes.stats
Write-Host ""
Write-Host "=== VirusTotal summary ==="
Write-Host "  malicious:  $($stats.malicious)"
Write-Host "  suspicious: $($stats.suspicious)"
Write-Host "  harmless:   $($stats.harmless)"
Write-Host "  undetected: $($stats.undetected)"
Write-Host ""
Write-Host "Full report written to $out"
Write-Host "Public page: https://www.virustotal.com/gui/file/$sha"
