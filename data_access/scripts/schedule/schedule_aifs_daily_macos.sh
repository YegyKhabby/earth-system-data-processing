#!/usr/bin/env bash
set -euo pipefail

# macOS helper: create/update LaunchAgent for daily AIFS downloads.
# Edit the variables below for your setup, then run this script.

PLIST_NAME="com.yeg.aifs-download.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

# Project paths (auto-detected from this script's location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ACCESS_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROJECT_DIR="$(cd "${DATA_ACCESS_DIR}/.." && pwd)"
SCRIPT_AIFS="${DATA_ACCESS_DIR}/scripts/download_aifs_forecasts.py"
SCRIPT_ERA5="${DATA_ACCESS_DIR}/scripts/download_era5_reanalysis.py"
CONFIG_PATH="${DATA_ACCESS_DIR}/aifs_config.yaml"

# Conda settings (optional). Options for USE_CONDA: "auto", "yes", "no".
USE_CONDA="auto"
CONDA_ENV="aifs_clean"

# Schedule time (24h)
SCHEDULE_HOUR=23
SCHEDULE_MINUTE=0

# Logs
LOG_DIR="${DATA_ACCESS_DIR}/logs/aifs_log"
STDOUT_LOG="${LOG_DIR}/aifs_download_stdout.log"
STDERR_LOG="${LOG_DIR}/aifs_download_stderr.log"

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"

CONDA_EXE="${CONDA_EXE:-$(command -v conda || true)}"
USE_CONDA_RESOLVED="no"
if [[ "${USE_CONDA}" == "yes" || "${USE_CONDA}" == "auto" ]]; then
  if [[ -n "${CONDA_EXE}" ]]; then
    USE_CONDA_RESOLVED="yes"
    CONDA_EXE="${CONDA_EXE}"
  elif [[ "${USE_CONDA}" == "yes" ]]; then
    echo "conda not found on PATH. Set CONDA_EXE or set USE_CONDA=\"no\"."
    exit 1
  fi
fi

PYTHON_EXE=""
if [[ "${USE_CONDA_RESOLVED}" == "no" ]]; then
  PYTHON_EXE="$(command -v python3)"
  if [[ -z "${PYTHON_EXE}" ]]; then
    echo "python3 not found on PATH."
    exit 1
  fi
fi

PLIST_PATH="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"
q() { printf '%q' "$1"; }
if [[ "${USE_CONDA_RESOLVED}" == "yes" ]]; then
  CMD="$(q "${CONDA_EXE}") run -n $(q "${CONDA_ENV}") python $(q "${SCRIPT_AIFS}") --config $(q "${CONFIG_PATH}") && $(q "${CONDA_EXE}") run -n $(q "${CONDA_ENV}") python $(q "${SCRIPT_ERA5}")"
else
  CMD="$(q "${PYTHON_EXE}") $(q "${SCRIPT_AIFS}") --config $(q "${CONFIG_PATH}") && $(q "${PYTHON_EXE}") $(q "${SCRIPT_ERA5}")"
fi

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
