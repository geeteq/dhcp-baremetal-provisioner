#!/bin/bash
# Phase 01 — BOOT INIT
# Brings up all NICs via DHCP, identifies this device in NetBox by MAC address,
# and logs the boot event to the NetBox device journal.

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh

log_section "PHASE 01 — BOOT INIT"

# ── 1. Bring up all NICs ─────────────────────────────────────────────────────
log_info "Bringing up all network interfaces via DHCP…"
for iface in $(ls /sys/class/net/ | grep -v lo); do
    ip link set "$iface" up
    dhclient -v "$iface" 2>>/var/log/dhclient-"${iface}".log &
done
sleep 10   # give DHCP time to complete

log_info "Network interfaces:"
ip -brief addr | tee -a "$LOG_FILE"

# ── 2. Collect MAC → interface mapping ──────────────────────────────────────
declare -A IFACE_MAC
for iface_path in /sys/class/net/*; do
    iface=$(basename "$iface_path")
    [[ "$iface" == "lo" ]] && continue
    mac=$(cat "${iface_path}/address" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    IFACE_MAC["$iface"]="$mac"
    log_info "  ${iface}  MAC=${mac}"
done
export IFACE_MAC

# ── 3. Find this device in NetBox ────────────────────────────────────────────
log_info "Looking up device in NetBox by MAC address…"
if ! nb_find_device_by_mac; then
    log_error "Could not identify this device in NetBox. No matching MAC address found."
    log_error "Ensure the device is registered in NetBox with correct interface MAC addresses."
    exit 1
fi
log_ok "Identified as: ${DEVICE_NAME}  (id=${DEVICE_ID}, site=${DEVICE_SITE})"

# Persist device identity for subsequent phases
cat > /run/bm-validate/device.env <<EOF
DEVICE_ID=${DEVICE_ID}
DEVICE_NAME=${DEVICE_NAME}
DEVICE_SITE=${DEVICE_SITE}
EOF

# ── 4. Collect hardware inventory ───────────────────────────────────────────
BIOS_VENDOR=$(dmidecode -s system-manufacturer 2>/dev/null | head -1)
BIOS_MODEL=$(dmidecode -s system-product-name 2>/dev/null | head -1)
BIOS_SERIAL=$(dmidecode -s system-serial-number 2>/dev/null | head -1)
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_GB=$(( MEM_TOTAL_KB / 1024 / 1024 ))
CPU_MODEL=$(grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
CPU_COUNT=$(grep -c '^processor' /proc/cpuinfo)
DISK_LIST=$(lsblk -dn -o NAME,SIZE,MODEL 2>/dev/null | grep -v '^loop' | awk '{print $1" "$2" "$3}' | tr '\n' '; ')

log_info "Hardware: ${BIOS_VENDOR} ${BIOS_MODEL} (s/n: ${BIOS_SERIAL})"
log_info "CPU: ${CPU_COUNT}x ${CPU_MODEL}"
log_info "Memory: ${MEM_TOTAL_GB} GB"
log_info "Disks: ${DISK_LIST}"

# Export for later phases
cat >> /run/bm-validate/device.env <<EOF
MEM_TOTAL_GB=${MEM_TOTAL_GB}
CPU_COUNT=${CPU_COUNT}
CPU_MODEL=${CPU_MODEL}
BIOS_VENDOR=${BIOS_VENDOR}
BIOS_MODEL=${BIOS_MODEL}
BIOS_SERIAL=${BIOS_SERIAL}
DISK_LIST=${DISK_LIST}
EOF

# ── 5. Log boot event to NetBox journal ──────────────────────────────────────
NB_MSG="PXE validation image booted.
Hardware: ${BIOS_VENDOR} ${BIOS_MODEL} | Serial: ${BIOS_SERIAL}
CPU: ${CPU_COUNT}x ${CPU_MODEL}
Memory: ${MEM_TOTAL_GB} GB
Disks: ${DISK_LIST}
Kernel: $(uname -r)"

nb_journal "$DEVICE_ID" "info" "$NB_MSG"
log_ok "Journal entry written to NetBox for device ${DEVICE_NAME}"
