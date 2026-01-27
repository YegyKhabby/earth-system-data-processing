# PowerShell script to schedule daily AIFS data download using Conda environment
# Run this script as Administrator to set up the scheduled task

# Configuration
$TaskName = "ECMWF_AIFS_Daily_Download"
$ScriptPath = Join-Path $PSScriptRoot "..\download_aifs_daily.py"
$Era5ScriptPath = Join-Path $PSScriptRoot "..\era5_download_only.py"
$CondaPath = "C:\Users\90542\miniconda3\Scripts\conda.exe"
$CondaEnv = "aifs_clean"
$WorkingDir = (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

# Schedule time (runs every day at 11:00 PM)
$ScheduleTime = "23:00"

# Check if script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Script not found: $ScriptPath"
    exit 1
}

# Check if conda exists
if (-not (Test-Path $CondaPath)) {
    Write-Error "Conda not found at: $CondaPath"
    Write-Host "Please update the CondaPath variable in this script with your conda location"
    exit 1
}

# Create the scheduled task action to run via conda environment
$ConfigPath = Join-Path $PSScriptRoot "..\..\aifs_config.yaml"
$ArgumentList = "run -n $CondaEnv python `"$ScriptPath`" --config `"$ConfigPath`"; run -n $CondaEnv python `"$Era5ScriptPath`""
$Action = New-ScheduledTaskAction `
    -Execute $CondaPath `
    -Argument $ArgumentList `
    -WorkingDirectory $WorkingDir

# Create the trigger (daily at specified time)
$Trigger = New-ScheduledTaskTrigger -Daily -At $ScheduleTime

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Task '$TaskName' already exists. Updating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Register the scheduled task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Downloads ECMWF AIFS forecast data daily at $ScheduleTime using conda environment $CondaEnv" `
    -User $env:USERNAME

Write-Host ""
Write-Host "Scheduled task created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Name: $TaskName"
Write-Host "  Schedule: Daily at $ScheduleTime"
Write-Host "  Script: $ScriptPath"
Write-Host "  Conda: $CondaPath"
Write-Host "  Environment: $CondaEnv"
Write-Host ""
Write-Host "Management Commands:" -ForegroundColor Cyan
$cmd1 = "Get-ScheduledTask -TaskName '$TaskName'"
$cmd2 = "Start-ScheduledTask -TaskName '$TaskName'"
$cmd3 = "Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host "  View task: $cmd1"
Write-Host "  Run now:   $cmd2"
Write-Host "  Remove:    $cmd3"
