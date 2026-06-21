param([string]$Url = "https://kiosk.example.com/")

$candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)
$browser = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browser) { throw "Chrome 또는 Edge를 찾을 수 없습니다." }

Start-Process -FilePath $browser -ArgumentList @(
    "--kiosk", $Url,
    "--no-first-run",
    "--disable-session-crashed-bubble",
    "--autoplay-policy=no-user-gesture-required"
)
