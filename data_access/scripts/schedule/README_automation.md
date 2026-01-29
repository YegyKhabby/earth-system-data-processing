# AIFS & ERA5 Data Download Automation Guide

This guide explains how to automate daily AIFS downloads and where to find AIFS/ERA5 logs.

## Overview

The automation consists of:
- **`scripts/download_aifs_daily.py`**: Python script driven by `aifs_config.yaml`
- **`aifs_config.yaml`**: Configuration for dates, steps, variables, output paths, and retries
- **`scripts/schedule/schedule_daily_download.ps1`**: PowerShell script to set up Windows Task Scheduler
- **`scripts/schedule/schedule_daily_download_macos.sh`**: macOS LaunchAgent helper
- **`logs/aifs_log/`**: AIFS download logs (created automatically)
- **`logs/era5_log/`**: ERA5 download logs (created automatically)

## Quick Start

### Option 1: Windows Task Scheduler

1. **Open PowerShell as Administrator**
   - Right-click Start menu → "Windows PowerShell (Admin)" or "Terminal (Admin)"

2. **Navigate to the project directory**
   ```powershell
   cd d:\earth-system-data-processing\data_access
   ```

3. **Run the scheduling script**
   ```powershell
   .\scripts/schedule/schedule_daily_download.ps1
   ```

4. **Verify the task was created**
   ```powershell
   Get-ScheduledTask -TaskName "ECMWF_AIFS_Daily_Download"
   ```

The script will now run automatically every day at **11:00 PM** (23:00).

### Option 2: macOS LaunchAgent

This does not affect Windows users. It installs a per-user LaunchAgent on macOS only.

1. **Create the LaunchAgent (macOS)**
   ```bash
   chmod +x scripts/schedule/schedule_daily_download_macos.sh
   scripts/schedule/schedule_daily_download_macos.sh
   ```

2. **Load the agent**
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.yeg.aifs-download.plist 2>/dev/null
   launchctl load ~/Library/LaunchAgents/com.yeg.aifs-download.plist
   ```

3. **Verify**
   ```bash
   launchctl list | grep com.yeg.aifs-download
   ```

The macOS script lives at:
- **`scripts/schedule/schedule_daily_download_macos.sh`**

The script is portable: it auto-detects the project root based on its own location.
You only need to set:
- `USE_CONDA` ("auto", "yes", "no")
- `CONDA_ENV` (your env name)
- `SCHEDULE_HOUR` / `SCHEDULE_MINUTE`

### Option 3: Manual Execution

You can run the download script manually anytime:

```bash
python data_access/scripts/download_aifs_daily.py --config data_access/aifs_config.yaml
```

## Configuration

### Change Schedule Time

Edit line 12 in [scripts/schedule/schedule_daily_download.ps1](scripts/schedule/schedule_daily_download.ps1):

```powershell
$ScheduleTime = "23:00"
```

Then re-run the script to update the schedule.

### Change Download Parameters

Edit [aifs_config.yaml](aifs_config.yaml):

Available parameters:
- **Temperature**: `2t` (2m temp), `skt` (skin temp)
- **Wind**: `10u`, `10v` (10m wind components), `100u`, `100v` (100m wind)
- **Pressure**: `msl` (mean sea level), `sp` (surface pressure)
- **Precipitation**: `tp` (total precipitation)
- **Humidity**: `2d` (2m dewpoint)
- See [ECMWF Parameter Database](https://codes.ecmwf.int/grib/param-db/) for complete list

## Task Management

### View task status (Windows)
```powershell
Get-ScheduledTask -TaskName "ECMWF_AIFS_Daily_Download" | Format-List
```

### Run task immediately (for testing, Windows)
```powershell
Start-ScheduledTask -TaskName "ECMWF_AIFS_Daily_Download"
```

### View task history (Windows)
```powershell
Get-ScheduledTaskInfo -TaskName "ECMWF_AIFS_Daily_Download"
```

### Remove the scheduled task (Windows)
```powershell
Unregister-ScheduledTask -TaskName "ECMWF_AIFS_Daily_Download" -Confirm:$false
```

## Monitoring

### Log Files

Every run creates a log file in `logs/aifs_log/aifs_download_YYYYMMDD.log`:

```
2026-01-08 23:00:01 - INFO - Starting AIFS data download
2026-01-08 23:00:02 - INFO - Output directory: d:\earth-system-data-processing\data_access\data\aifs
2026-01-08 23:00:02 - INFO - Dates to download: ['2026-01-05', '2026-01-06', '2026-01-07']
2026-01-08 23:00:15 - INFO - ✓ Saved: aifs-single_20260105_12_sfc_step006_0p25.grib2 (2.41 MB)
...
```

### Check Recent Logs (Windows)

```powershell
# View today's log
Get-Content logs\aifs_log\aifs_download_$(Get-Date -Format "yyyyMMdd").log

# View last 20 lines
Get-Content logs\aifs_log\aifs_download_$(Get-Date -Format "yyyyMMdd").log -Tail 20

# List all logs
Get-ChildItem logs\aifs_log\*.log | Sort-Object LastWriteTime -Descending
```

### ERA5 Logs (Windows)

ERA5 logs are written to `logs\era5_log\era5_download_YYYYMMDD.log`:

```powershell
Get-Content logs\era5_log\era5_download_$(Get-Date -Format "yyyyMMdd").log -Tail 20
```

## Troubleshooting

### Issue: "Execution policy" error when running PowerShell script (Windows)

**Solution**: Temporarily allow script execution:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: Python not found (Windows)

**Solution**: Specify full path to Python in the scheduling script:
```powershell
$PythonPath = "C:\Users\YourName\anaconda3\envs\aifs\python.exe"
```

### Issue: Task runs but doesn't download data (Windows)

**Possible causes**:
1. **Conda environment not activated**: Modify the schedule script to use the conda environment:
   ```powershell
   $Action = New-ScheduledTaskAction `
       -Execute "C:\Users\YourName\anaconda3\Scripts\conda.exe" `
       -Argument "run -n aifs python $ScriptPath" `
       -WorkingDirectory $WorkingDir
   ```

2. **Network not available**: The task settings already include `-RunOnlyIfNetworkAvailable`, but check your connection

3. **Data not available yet**: ECMWF releases data with some delay. Run the script later in the day (after 14:00 UTC)

### Issue: Want to use Conda environment (Windows)

**Solution**: Create an alternative scheduling script:

```powershell
# In scripts/schedule/schedule_daily_download.ps1, replace the Action creation with:
$CondaPath = "C:\Users\YourName\anaconda3\Scripts\conda.exe"
$Action = New-ScheduledTaskAction `
    -Execute $CondaPath `
    -Argument "run -n aifs python `"$ScriptPath`"" `
    -WorkingDirectory $WorkingDir
```

## Data Management

### Automatic Cleanup (Optional)

The script downloads the last 3 days each time it runs. Old files accumulate over time. To automatically delete files older than 7 days, add this to the end of `download_aifs_data()` function:

```python
# Clean up old files (keep only last 7 days)
logger.info("Cleaning up old files...")
cutoff_date = datetime.now() - timedelta(days=7)
for file in OUT.glob("*.grib2"):
    file_date_str = file.stem.split("_")[1]  # Extract date from filename
    try:
        file_date = datetime.strptime(file_date_str, "%Y%m%d")
        if file_date < cutoff_date:
            file.unlink()
            logger.info(f"Deleted old file: {file.name}")
    except Exception as e:
        logger.warning(f"Could not process {file.name}: {e}")
```

### Manual Cleanup (Windows example)

```powershell
# Delete files older than 7 days
Get-ChildItem data\aifs\*.grib2 | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | Remove-Item
```

## Best Practices

1. **Schedule Time**: Run after 14:00 UTC (when 12 UTC forecasts are likely available). If your local time is not UTC, adjust accordingly.
2. **Monitor Logs**: Check logs weekly to ensure downloads are successful
3. **Disk Space**: Each day generates ~7-8 MB. Plan accordingly if keeping historical data
4. **Backup**: Consider backing up downloaded data to external storage periodically

## Additional Resources

- [ECMWF Open Data Documentation](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [earthkit-data Documentation](https://earthkit-data.readthedocs.io/)
- [Windows Task Scheduler Documentation](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page)
