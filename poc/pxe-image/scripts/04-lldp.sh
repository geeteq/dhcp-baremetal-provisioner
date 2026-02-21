#!/bin/bash
# Phase 04 — LLDP DISCOVERY
# Enables LLDP on all interfaces, waits for neighbour advertisements,
# then maps each NIC to its adjacent switch port.
# Results logged to NetBox journal. No NetBox objects are modified.

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh
source /run/bm-validate/device.env

log_section "PHASE 04 — LLDP DISCOVERY"

LLDP_WAIT=60   # seconds — typical LLDP TX interval is 30s

# ── 1. Start lldpad ──────────────────────────────────────────────────────────
log_info "Starting lldpad…"
systemctl start lldpad 2>/dev/null || lldpad -d
sleep 2

# ── 2. Enable LLDP TX+RX on every interface ─────────────────────────────────
IFACES=()
for iface_path in /sys/class/net/*; do
    iface=$(basename "$iface_path")
    [[ "$iface" == "lo" ]] && continue
    ip link set "$iface" up 2>/dev/null
    lldptool set-lldp -i "$iface" adminStatus=rxtx 2>/dev/null
    IFACES+=("$iface")
    log_info "  LLDP enabled on ${iface}"
done

nb_journal "$DEVICE_ID" "info" \
    "LLDP discovery started on ${#IFACES[@]} interfaces: ${IFACES[*]}. Waiting ${LLDP_WAIT}s for neighbour advertisements."

log_info "Waiting ${LLDP_WAIT}s for LLDP advertisements…"
sleep "$LLDP_WAIT"

# ── 3. Parse LLDP neighbours ─────────────────────────────────────────────────
declare -A LLDP_NEIGHBOR     # iface → switch hostname
declare -A LLDP_PORT         # iface → switch port ID/description
declare -A LLDP_MGMT_IP      # iface → switch management IP

parse_lldp_iface() {
    local iface="$1"
    local raw
    raw=$(lldptool get-tlv -n -i "$iface" 2>/dev/null)

    # System Name
    local sys_name
    sys_name=$(echo "$raw" | awk '/^System Name TLV/{getline; print}' | xargs)

    # Port ID (prefer portDesc over portID for readability)
    local port_desc port_id
    port_desc=$(echo "$raw" | awk '/^Port Description TLV/{getline; print}' | xargs)
    port_id=$(echo "$raw"   | awk '/^Port ID TLV/{getline; print}' | xargs)
    local port="${port_desc:-$port_id}"

    # Management address
    local mgmt_ip
    mgmt_ip=$(echo "$raw" | awk '/^Management Address TLV/{getline; print}' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)

    if [[ -n "$sys_name" ]]; then
        LLDP_NEIGHBOR["$iface"]="$sys_name"
        LLDP_PORT["$iface"]="$port"
        LLDP_MGMT_IP["$iface"]="${mgmt_ip:-unknown}"
        return 0
    fi
    return 1
}

log_info "Collecting LLDP neighbour data…"
ADJACENCY_LINES=()

for iface in "${IFACES[@]}"; do
    if parse_lldp_iface "$iface"; then
        MAC=$(cat "/sys/class/net/${iface}/address" 2>/dev/null | tr '[:lower:]' '[:upper:]')
        SPEED=$(cat "/sys/class/net/${iface}/speed" 2>/dev/null || echo "?")
        LINE="${iface} (MAC ${MAC}, ${SPEED}Mbps) → ${LLDP_NEIGHBOR[$iface]} port ${LLDP_PORT[$iface]} (mgmt ${LLDP_MGMT_IP[$iface]})"
        ADJACENCY_LINES+=("$LINE")
        log_ok "  ${LINE}"
    else
        log_warn "  ${iface}: no LLDP neighbour found (not connected or switch LLDP disabled)"
        ADJACENCY_LINES+=("${iface}: no LLDP neighbour")
    fi
done

# ── 4. Serialize adjacency map for final report ──────────────────────────────
python3 - <<'PYEOF' > /run/bm-validate/lldp.json
import json, os, subprocess, sys

ifaces = {}
for iface_path in [p for p in os.listdir('/sys/class/net') if p != 'lo']:
    iface = os.path.basename(iface_path)
    try:
        mac = open(f'/sys/class/net/{iface}/address').read().strip().upper()
        speed = open(f'/sys/class/net/{iface}/speed').read().strip()
    except:
        mac, speed = 'unknown', 'unknown'

    raw = subprocess.run(['lldptool','get-tlv','-n','-i',iface],
                         capture_output=True, text=True).stdout

    def extract(marker):
        lines = raw.splitlines()
        for i, l in enumerate(lines):
            if marker in l and i+1 < len(lines):
                return lines[i+1].strip()
        return None

    import re
    sys_name  = extract('System Name TLV')
    port_desc = extract('Port Description TLV')
    port_id   = extract('Port ID TLV')
    mgmt_raw  = extract('Management Address TLV')
    mgmt_ip   = re.search(r'[\d.]{7,15}', mgmt_raw).group(0) if mgmt_raw else None

    ifaces[iface] = {
        'mac': mac,
        'speed_mbps': speed,
        'lldp_neighbor': sys_name,
        'lldp_port': port_desc or port_id,
        'lldp_mgmt_ip': mgmt_ip,
    }

print(json.dumps(ifaces, indent=2))
PYEOF

# ── 5. Write NetBox journal ───────────────────────────────────────────────────
if [[ ${#ADJACENCY_LINES[@]} -gt 0 ]]; then
    JOURNAL_MSG="LLDP discovery complete — port adjacencies:
$(printf '  %s\n' "${ADJACENCY_LINES[@]}")"
    nb_journal "$DEVICE_ID" "success" "$JOURNAL_MSG"
    log_ok "LLDP adjacency map written to NetBox journal"
else
    nb_journal "$DEVICE_ID" "warning" "LLDP discovery: no neighbours found on any interface"
    log_warn "No LLDP neighbours found"
fi
