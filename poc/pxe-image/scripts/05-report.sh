#!/bin/bash
# Phase 05 — FINAL REPORT
# Assembles all test results and LLDP data, POSTs a "server_live" event
# to the ESB/callback API, and writes a final journal entry to NetBox.

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh
source /run/bm-validate/device.env

log_section "PHASE 05 — FINAL REPORT"

CALLBACK_API_URL="${CALLBACK_API_URL:-http://10.0.0.1:5000}"

# ── 1. Determine overall pass/fail ────────────────────────────────────────────
OVERALL="PASS"
[[ "$MEMORY_RESULT" == "FAIL" ]] && OVERALL="FAIL"
[[ "$DISK_RESULT"   == "FAIL" ]] && OVERALL="FAIL"

# ── 2. Build ESB payload ──────────────────────────────────────────────────────
LLDP_JSON=$(cat /run/bm-validate/lldp.json 2>/dev/null || echo '{}')
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

PAYLOAD=$(python3 - <<PYEOF
import json, os, sys

device_env = {}
with open('/run/bm-validate/device.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            device_env[k] = v

lldp = json.loads("""${LLDP_JSON}""")

# Build NIC list
nics = []
for iface, info in lldp.items():
    nics.append({
        'name':      iface,
        'mac':       info.get('mac'),
        'speed_mbps': info.get('speed_mbps'),
        'lldp_neighbor': info.get('lldp_neighbor'),
        'lldp_port':     info.get('lldp_port'),
        'lldp_mgmt_ip':  info.get('lldp_mgmt_ip'),
    })

payload = {
    'event':       'server_live',
    'timestamp':   '${TIMESTAMP}',
    'device_id':   int(device_env.get('DEVICE_ID', 0)),
    'device_name': device_env.get('DEVICE_NAME', 'unknown'),
    'site':        device_env.get('DEVICE_SITE', 'unknown'),
    'hardware': {
        'vendor':  device_env.get('BIOS_VENDOR'),
        'model':   device_env.get('BIOS_MODEL'),
        'serial':  device_env.get('BIOS_SERIAL'),
        'cpu_model': device_env.get('CPU_MODEL'),
        'cpu_count': int(device_env.get('CPU_COUNT', 0)),
        'memory_gb': int(device_env.get('MEM_TOTAL_GB', 0)),
        'disks':   device_env.get('DISK_LIST'),
    },
    'tests': {
        'memory': {
            'result':  device_env.get('MEMORY_RESULT', 'UNKNOWN'),
            'details': device_env.get('MEMORY_DETAILS', ''),
        },
        'disk_io': {
            'result':  device_env.get('DISK_RESULT', 'UNKNOWN'),
            'summary': device_env.get('DISK_SUMMARY', ''),
        },
    },
    'nics': nics,
    'overall_result': '${OVERALL}',
}
print(json.dumps(payload, indent=2))
PYEOF
)

log_info "ESB payload ready — posting to ${CALLBACK_API_URL}/api/event"
echo "$PAYLOAD" | tee -a "$LOG_FILE"

# ── 3. POST to ESB/callback API ───────────────────────────────────────────────
HTTP_CODE=$(curl -sf -o /tmp/esb_response.json -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "${CALLBACK_API_URL}/api/event" 2>/dev/null)

if [[ "$HTTP_CODE" =~ ^2 ]]; then
    log_ok "ESB accepted event (HTTP ${HTTP_CODE})"
    ESB_RESULT="Accepted by ESB (HTTP ${HTTP_CODE})"
else
    log_warn "ESB returned HTTP ${HTTP_CODE} — event may not have been processed"
    ESB_RESULT="ESB returned HTTP ${HTTP_CODE}"
fi

# ── 4. Final NetBox journal entry ─────────────────────────────────────────────
NIC_SUMMARY=$(echo "$LLDP_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
lines=[]
for iface,info in d.items():
    n=info.get('lldp_neighbor','?')
    p=info.get('lldp_port','?')
    lines.append(f'  {iface} → {n} {p}')
print('\n'.join(lines))
" 2>/dev/null)

if [[ "$OVERALL" == "PASS" ]]; then
    FINAL_KIND="success"
    FINAL_MSG="✓ Validation COMPLETE — all tests PASSED.

Hardware: ${BIOS_VENDOR} ${BIOS_MODEL} | S/N: ${BIOS_SERIAL}
Memory:   ${MEMORY_DETAILS}
Disk I/O: ${DISK_SUMMARY}
Port adjacencies:
${NIC_SUMMARY}

ESB event: ${ESB_RESULT}
Server is ready for staging pipeline."
else
    FINAL_KIND="danger"
    FINAL_MSG="✗ Validation FAILED — one or more tests did not pass.

Memory:   ${MEMORY_DETAILS}
Disk I/O: ${DISK_RESULT}
Port adjacencies:
${NIC_SUMMARY}

ESB event: ${ESB_RESULT}
Manual inspection required before proceeding."
fi

nb_journal "$DEVICE_ID" "$FINAL_KIND" "$FINAL_MSG"
log_ok "Final journal entry written to NetBox"

echo ""
log_section "VALIDATION COMPLETE — OVERALL: ${OVERALL}"
