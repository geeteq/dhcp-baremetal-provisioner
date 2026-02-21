#!/bin/bash
# BM-Validate — Main Orchestrator
# Runs all validation phases in sequence. Called by the systemd unit on boot.
# Environment variables (NETBOX_URL, NETBOX_TOKEN, CALLBACK_API_URL) are
# injected via kernel cmdline → /proc/cmdline → sourced here.

set -euo pipefail

SCRIPT_DIR="/opt/bm-validate"
LOG_FILE="/var/log/bm-validate.log"
export LOG_FILE

# ── Parse kernel cmdline args into env vars ──────────────────────────────────
# PXE boot adds: bm.netbox_url=http://... bm.netbox_token=xxx bm.callback_url=http://...
for param in $(cat /proc/cmdline); do
    case "$param" in
        bm.netbox_url=*)    export NETBOX_URL="${param#bm.netbox_url=}" ;;
        bm.netbox_token=*)  export NETBOX_TOKEN="${param#bm.netbox_token=}" ;;
        bm.callback_url=*)  export CALLBACK_API_URL="${param#bm.callback_url=}" ;;
    esac
done

mkdir -p /run/bm-validate /var/log

echo "======================================================" | tee "$LOG_FILE"
echo "  Baremetal Validation Image" | tee -a "$LOG_FILE"
echo "  $(date)" | tee -a "$LOG_FILE"
echo "  NetBox: ${NETBOX_URL:-NOT SET}" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Run each phase; on failure log the error and continue (best-effort reporting)
run_phase() {
    local script="$1"
    if [[ -x "${SCRIPT_DIR}/${script}" ]]; then
        "${SCRIPT_DIR}/${script}" || {
            echo "$(date '+%Y-%m-%dT%H:%M:%S') [ERROR] Phase ${script} failed (exit $?)" | tee -a "$LOG_FILE"
        }
    else
        echo "$(date '+%Y-%m-%dT%H:%M:%S') [WARN] ${script} not found or not executable" | tee -a "$LOG_FILE"
    fi
}

run_phase scripts/01-init.sh
run_phase scripts/02-memory.sh
run_phase scripts/03-disk.sh
run_phase scripts/04-lldp.sh
run_phase scripts/05-report.sh

echo "" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"
echo "  Validation finished at $(date)" | tee -a "$LOG_FILE"
echo "  Log saved to ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Copy log to a location DHCP/tftp server can retrieve (optional)
cp "$LOG_FILE" /var/www/html/bm-validate.log 2>/dev/null || true

# Power off after 30s (gives time to read console output)
echo "System will power off in 30 seconds…"
sleep 30
poweroff -f
