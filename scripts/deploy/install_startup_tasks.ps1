#Requires -RunAsAdministrator
param(
    [string]$EnvironmentFile = ".env.production",
    [string]$Site = "https://kiosk.example.com",
    [string]$CaddyConfig = "deployment\Caddyfile.example",
    [ValidateSet("SQLite", "MySQL")][string]$DatabaseMode = "SQLite"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$TaskSettings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable
$SystemPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$BackendAction = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\deploy\run_backend.ps1`" -EnvironmentFile `"$EnvironmentFile`"" `
    -WorkingDirectory $ProjectRoot
$BackendTask = New-ScheduledTask `
    -Action $BackendAction `
    -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Settings $TaskSettings `
    -Principal $SystemPrincipal
Register-ScheduledTask -TaskName "SignKiosk-Backend" -InputObject $BackendTask -Force | Out-Null

$CaddyAction = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\deploy\run_caddy.ps1`" -Site `"$Site`" -Config `"$CaddyConfig`"" `
    -WorkingDirectory $ProjectRoot
$CaddyTask = New-ScheduledTask `
    -Action $CaddyAction `
    -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Settings $TaskSettings `
    -Principal $SystemPrincipal
Register-ScheduledTask -TaskName "SignKiosk-Caddy" -InputObject $CaddyTask -Force | Out-Null

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$InteractivePrincipal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Highest
$KioskAction = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\deploy\start_kiosk.ps1`" -Url `"$Site/`"" `
    -WorkingDirectory $ProjectRoot
$KioskTask = New-ScheduledTask `
    -Action $KioskAction `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser) `
    -Settings $TaskSettings `
    -Principal $InteractivePrincipal
Register-ScheduledTask -TaskName "SignKiosk-Browser" -InputObject $KioskTask -Force | Out-Null

if ($DatabaseMode -eq "SQLite") {
    $BackupAction = New-ScheduledTaskAction `
        -Execute "$ProjectRoot\venv\Scripts\python.exe" `
        -Argument "scripts\deploy\backup_sqlite.py --database data\kiosk.db --output backups --retention-days 30" `
        -WorkingDirectory $ProjectRoot
    $BackupTask = New-ScheduledTask `
        -Action $BackupAction `
        -Trigger (New-ScheduledTaskTrigger -Daily -At "02:00") `
        -Settings $TaskSettings `
        -Principal $SystemPrincipal
    Register-ScheduledTask -TaskName "SignKiosk-DatabaseBackup" -InputObject $BackupTask -Force | Out-Null
}

Write-Host "자동 시작 작업을 등록했습니다. 작업 스케줄러에서 실행 계정과 최근 결과를 확인하세요."
