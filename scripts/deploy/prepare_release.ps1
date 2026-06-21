param(
    [string]$EnvironmentFile = ".env.production",
    [string]$ModelSource = "deployment\models"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
    throw "운영 환경 파일이 없습니다: $EnvironmentFile (.env.production.example을 복사해 작성하세요.)"
}

$env:ENV_FILE = $EnvironmentFile
try {
    venv\Scripts\python.exe -m pip install -r requirements.txt
    npm.cmd ci
    venv\Scripts\python.exe -m scripts.deploy.validate_release
    New-Item -ItemType Directory -Path "data" -Force | Out-Null
    venv\Scripts\python.exe -m scripts.deploy.relocate_sqlite
    venv\Scripts\python.exe scripts\deploy\place_models.py --source $ModelSource
    npm.cmd run lint
    npm.cmd run test:all
    npm.cmd run build
    venv\Scripts\python.exe -m app.core.migrate
} finally {
    Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
}

Write-Host "배포 준비 완료: build/, app/ai/models/, DB migration"
