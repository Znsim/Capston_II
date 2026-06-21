param([string]$OutputDirectory = "portable")

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot
$OutputRoot = Join-Path $ProjectRoot $OutputDirectory

$GestureHash = (Get-FileHash -Algorithm SHA256 "app\ai\models\gesture_model.pkl").Hash.ToLowerInvariant()
$EncoderHash = (Get-FileHash -Algorithm SHA256 "app\ai\models\label_encoder.pkl").Hash.ToLowerInvariant()
if ($GestureHash -ne "75a8bf05864297676048f50963a0a5aaff036cabe4ab31c9cf56fe2a732b6067") {
    throw "gesture_model_hash_mismatch"
}
if ($EncoderHash -ne "9bf71b1c50c14fb0691b81e23408517a936d404b6fd2e8825764009ea5361ab5") {
    throw "label_encoder_hash_mismatch"
}

$previousAssetBase = $env:REACT_APP_MEDIAPIPE_ASSET_BASE
$env:REACT_APP_MEDIAPIPE_ASSET_BASE = "/mediapipe"
try {
    npm.cmd run build
} finally {
    if ($null -eq $previousAssetBase) {
        Remove-Item Env:REACT_APP_MEDIAPIPE_ASSET_BASE -ErrorAction SilentlyContinue
    } else {
        $env:REACT_APP_MEDIAPIPE_ASSET_BASE = $previousAssetBase
    }
}

New-Item -ItemType Directory -Force "build\mediapipe\hands", "build\mediapipe\pose" | Out-Null
Copy-Item "node_modules\@mediapipe\hands\*" "build\mediapipe\hands" -Recurse -Force
Copy-Item "node_modules\@mediapipe\pose\*" "build\mediapipe\pose" -Recurse -Force

venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name SignKiosk `
    --distpath $OutputRoot `
    --workpath (Join-Path $OutputRoot "work") `
    --specpath (Join-Path $OutputRoot "spec") `
    --add-data "$ProjectRoot\build;build" `
    --add-data "$ProjectRoot\app\ai\models;app\ai\models" `
    --add-data "$ProjectRoot\migrations;migrations" `
    --add-data "$ProjectRoot\alembic.ini;." `
    --hidden-import sklearn.neural_network._multilayer_perceptron `
    --hidden-import sklearn.preprocessing._label `
    --hidden-import sklearn.utils._cython_blas `
    --hidden-import sklearn.utils._weight_vector `
    --hidden-import sklearn._loss._loss `
    --exclude-module jax `
    --exclude-module jaxlib `
    --exclude-module matplotlib `
    --exclude-module PIL `
    --exclude-module mediapipe `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    "$ProjectRoot\scripts\deploy\portable_launcher.py"
if ($LASTEXITCODE -ne 0) { throw "pyinstaller_build_failed" }

$Package = Join-Path $OutputRoot "SignKiosk"
Copy-Item "docs\portable_windows_test_guide.md" (Join-Path $Package "README.md") -Force
$Manifest = @(
    "gesture_model.pkl  $GestureHash",
    "label_encoder.pkl  $EncoderHash"
)
$Manifest | Set-Content -Encoding UTF8 (Join-Path $Package "MODEL_SHA256.txt")

$ZipPath = Join-Path $OutputRoot "SignKiosk-windows-x64.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$Package\*" -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash.ToLowerInvariant()
"$ZipHash  SignKiosk-windows-x64.zip" | Set-Content -Encoding ASCII "$ZipPath.sha256"
Write-Host "Portable ZIP: $ZipPath"
Write-Host "SHA-256: $ZipHash"
