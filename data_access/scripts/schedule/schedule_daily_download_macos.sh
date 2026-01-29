#!/usr/bin/env bash
set -euo pipefail

# macOS helper: create/update LaunchAgent for daily AIFS downloads.
# Edit the variables below for your setup, then run this script.

PLIST_NAME="com.yeg.aifs-download.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

# Project paths
PROJECT_DIR="/Users/yeganehkhabbazian/Projects/Earth_System/earth-system-data-processing"
DATA_ACCESS_DIR="${PROJECT_DIR}/data_access"
SCRIPT_AIFS="${DATA_ACCESS_DIR}/scripts/download_aifs_daily.py"
SCRIPT_ERA5="${DATA_ACCESS_DIR}/scripts/era5_download_only.py"
CONFIG_PATH="${DATA_ACCESS_DIR}/aifs_config.yaml"

# Conda settings (optional). If you prefer system python, set USE_CONDA="no".
USE_CONDA="yes"
CONDA_BASE="/Users/yeganehkhabbazian/miniconda3"
CONDA_ENV="aifs_clean"

# Schedule time (24h)
SCHEDULE_HOUR=23
SCHEDULE_MINUTE=0

# Logs
LOG_DIR="${DATA_ACCESS_DIR}/logs"
STDOUT_LOG="${LOG_DIR}/aifs_download_stdout.log"
STDERR_LOG="${LOG_DIR}/aifs_download_stderr.log"

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"

if [[ "${USE_CONDA}" == "yes" ]]; then
  PY_CMD="${CONDA_BASE}/envs/${CONDA_ENV}/bin/python"
  if [[ ! -x "${PY_CMD}" ]]; then
    echo "Conda python not found at: ${PY_CMD}"
    echo "Update CONDA_BASE or CONDA_ENV in this script."
    exit 1
  fi
else
  PY_CMD="$(command -v python3)"
  if [[ -z "${PY_CMD}" ]]; then
    echo "python3 not found on PATH."
    exit 1
  fi
fi

PLIST_PATH="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"
CMD="${PY_CMD} ${SCRIPT_AIFS} --config ${CONFIG_PATH} && ${PY_CMD} ${SCRIPT_ERA5}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.yeg.aifs-download</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>-lc</string>
      <string>${CMD}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>${SCHEDULE_HOUR}</integer>
      <key>Minute</key><integer>${SCHEDULE_MINUTE}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${STDOUT_LOG}</string>
    <key>StandardErrorPath</key>
    <string>${STDERR_LOG}</string>
    <key>RunAtLoad</key>
    <true/>
  </dict>
</plist>
EOF

launchctl unload "${PLIST_PATH}" 2>/dev/null || true
launchctl load "${PLIST_PATH}"

echo "LaunchAgent installed: ${PLIST_PATH}"
echo "Verify: launchctl list | grep com.yeg.aifs-download"
