param(
    [string]$Site = "https://kiosk.example.com",
    [string]$CaddyExe = "deployment\bin\caddy.exe",
    [string]$Config = "deployment\Caddyfile.example"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
if (-not (Test-Path -LiteralPath $CaddyExe)) { throw "Caddy 실행 파일이 없습니다: $CaddyExe" }

$env:KIOSK_SITE = $Site
$env:KIOSK_ROOT = $ProjectRoot.Replace('\', '/')
& $CaddyExe run --config $Config --adapter caddyfile
