# PowerShell script to schedule daily AIFS data download
# Run this script as Administrator to set up the scheduled task

# Configuration
$TaskName = "ECMWF_AIFS_Daily_Download"
$ScriptPath = "$PSScriptRoot\download_aifs_daily.py"
$PythonPath = (Get-Command python).Source  # Automatically finds Python
$WorkingDir = $PSScriptRoot

# Schedule time (runs every day at 11:00 PM)
$ScheduleTime = "23:00"

# Check if script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Script not found: $ScriptPath"
    exit 1
}

# Create the scheduled task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $ScriptPath `
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
    -Description "Downloads ECMWF AIFS forecast data daily at $ScheduleTime" `
    -User $env:USERNAME

Write-Host ""
Write-Host "Scheduled task created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Name: $TaskName"
Write-Host "  Schedule: Daily at $ScheduleTime"
Write-Host "  Script: $ScriptPath"
Write-Host "  Python: $PythonPath"
Write-Host ""
Write-Host "Management Commands:" -ForegroundColor Cyan
$cmd1 = "Get-ScheduledTask -TaskName '$TaskName'"
$cmd2 = "Start-ScheduledTask -TaskName '$TaskName'"
$cmd3 = "Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host "  View task: $cmd1"
Write-Host "  Run now:   $cmd2"
Write-Host "  Remove:    $cmd3"
