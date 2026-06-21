param([string]$EnvironmentFile = ".env.production")

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
$env:ENV_FILE = $EnvironmentFile
venv\Scripts\python.exe -m scripts.deploy.run_backend
