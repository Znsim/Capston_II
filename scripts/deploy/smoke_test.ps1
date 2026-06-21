param([string]$BaseUrl = "https://kiosk.example.com")

$ErrorActionPreference = "Stop"
$health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 15
if (-not $health.all_systems_ready) { throw "헬스 체크 실패: $($health | ConvertTo-Json -Compress)" }
$page = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 15
if ($page.StatusCode -ne 200 -or $page.Content -notmatch "수어 안내 키오스크") {
    throw "React 배포 페이지 확인 실패"
}
Write-Host "배포 스모크 테스트 통과: $BaseUrl"
