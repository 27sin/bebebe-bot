param(
    [string]$ServerHost = "85.208.86.166",
    [string]$User = "iziashnyi",
    [string]$Key = "D:\VibeCode\SSH\bebebe-bot\id_rsa",
    [string]$RemoteDir = "/opt/telegram-parody-bot"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Key)) {
    Write-Error "SSH key not found: $Key`nPass -Key path to your private key."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$baseDir = Join-Path $PSScriptRoot "..\downloaded-logs"
New-Item -ItemType Directory -Force -Path $baseDir | Out-Null
$target = Join-Path (Resolve-Path $baseDir).Path $timestamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

Write-Host "Downloading file logs to $target ..."

scp -i $Key -r "${User}@${ServerHost}:${RemoteDir}/logs/*" $target 2>$null

Write-Host "Downloading last 500 systemd lines ..."
ssh -i $Key "${User}@${ServerHost}" "journalctl -u telegram-parody-bot --no-pager -n 500" `
    | Out-File -FilePath (Join-Path $target "systemd-last-500.log") -Encoding utf8

Write-Host "Done. Files:"
Get-ChildItem $target | Format-Table Name, Length

Write-Host "Tip: full archive on server: bash $RemoteDir/scripts/export-logs.sh"
