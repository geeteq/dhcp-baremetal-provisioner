#!/bin/bash
# Phase 02 — MEMORY TEST
# Runs memtester against available RAM (leaving 512 MB for the OS).
# Logs pass/fail result and measured bandwidth to NetBox journal.

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh
source /run/bm-validate/device.env

log_section "PHASE 02 — MEMORY TEST"

MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_FREE_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
# Test all available memory minus 512 MB reserve for the OS
TEST_MB=$(( (MEM_FREE_KB / 1024) - 512 ))
[[ $TEST_MB -lt 256 ]] && TEST_MB=256

log_info "Total RAM: $((MEM_TOTAL_KB / 1024)) MB  |  Testing: ${TEST_MB} MB (1 pass)"
nb_journal "$DEVICE_ID" "info" "Memory test started: testing ${TEST_MB} MB of ${MEM_TOTAL_GB} GB total"

MEMTEST_OUT=$(mktemp)
START_TS=$(date +%s)

memtester "${TEST_MB}M" 1 2>&1 | tee "$MEMTEST_OUT" | grep -E 'Loop|ok|FAILURE|error' | tee -a "$LOG_FILE"

END_TS=$(date +%s)
DURATION=$(( END_TS - START_TS ))

# Parse result
if grep -qi 'FAILURE\|error' "$MEMTEST_OUT"; then
    FAILED_TESTS=$(grep -i 'FAILURE' "$MEMTEST_OUT" | head -5 | tr '\n' ' ')
    log_error "Memory test FAILED: ${FAILED_TESTS}"
    nb_journal "$DEVICE_ID" "danger" \
        "MEMORY TEST FAILED after ${DURATION}s.
Tested: ${TEST_MB} MB | Total: ${MEM_TOTAL_GB} GB
Failures: ${FAILED_TESTS}"
    echo "MEMORY_RESULT=FAIL" >> /run/bm-validate/device.env
    echo "MEMORY_DETAILS=FAILED: ${FAILED_TESTS}" >> /run/bm-validate/device.env
else
    log_ok "Memory test PASSED (${TEST_MB} MB tested in ${DURATION}s)"
    nb_journal "$DEVICE_ID" "success" \
        "Memory test PASSED.
Tested: ${TEST_MB} MB of ${MEM_TOTAL_GB} GB | Duration: ${DURATION}s | Passes: 1"
    echo "MEMORY_RESULT=PASS" >> /run/bm-validate/device.env
    echo "MEMORY_DETAILS=PASSED: ${TEST_MB}MB tested in ${DURATION}s" >> /run/bm-validate/device.env
fi

rm -f "$MEMTEST_OUT"
