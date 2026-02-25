#!/bin/bash
# Phase 01 — BOOT INIT
# 1. Collect full hardware inventory via dmidecode
# 2. Bring up all physical NICs via DHCP (required for NetBox access)
# 3. Find device in NetBox — serial number first, MAC address as fallback
# 4. Log hardware info to the device's NetBox journal (no objects updated)

source /opt/bm-validate/lib/log.sh
source /opt/bm-validate/lib/netbox.sh

log_section "PHASE 01 — BOOT INIT"

mkdir -p /run/bm-validate

# ── 1. Hardware inventory (dmidecode) ────────────────────────────────────────
log_info "Collecting hardware inventory…"

SYS_VENDOR=$(dmidecode  -s system-manufacturer   2>/dev/null | head -1 | xargs)
SYS_MODEL=$(dmidecode   -s system-product-name   2>/dev/null | head -1 | xargs)
SYS_SERIAL=$(dmidecode  -s system-serial-number  2>/dev/null | head -1 | xargs)
SYS_UUID=$(dmidecode    -s system-uuid           2>/dev/null | head -1 | xargs)
BIOS_VENDOR=$(dmidecode -s bios-vendor           2>/dev/null | head -1 | xargs)
BIOS_VERSION=$(dmidecode -s bios-version         2>/dev/null | head -1 | xargs)
BIOS_DATE=$(dmidecode   -s bios-release-date     2>/dev/null | head -1 | xargs)
CHASSIS_TYPE=$(dmidecode   -s chassis-type            2>/dev/null | head -1 | xargs)
CHASSIS_SERIAL=$(dmidecode -s chassis-serial-number   2>/dev/null | head -1 | xargs)

CPU_MODEL=$(dmidecode -t processor 2>/dev/null \
    | awk '/^\s*Version:/{sub(/.*Version:[[:space:]]*/,""); print; exit}' | xargs)
CPU_SOCKETS=$(dmidecode -t processor 2>/dev/null \
    | grep -c "^Processor Information" || true)
CPU_CORES=$(dmidecode -t processor 2>/dev/null \
    | awk '/^\s*Core Count:/{print $NF; exit}')
CPU_THREADS=$(dmidecode -t processor 2>/dev/null \
    | awk '/^\s*Thread Count:/{print $NF; exit}')
CPU_SPEED=$(dmidecode -t processor 2>/dev/null \
    | awk '/^\s*Current Speed:/{print $3" "$4; exit}')

MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_GB=$(( MEM_TOTAL_KB / 1024 / 1024 ))
MEM_DIMM_COUNT=$(dmidecode -t memory 2>/dev/null \
    | awk '/^\s*Size:/ && !/No Module/{c++} END{print c+0}')
MEM_DIMM_DETAIL=$(dmidecode -t memory 2>/dev/null | awk '
    /^Memory Device/{loc=""; sz=""; tp=""; sp=""}
    /^\s*Locator:/ && !/Bank/{loc=$NF}
    /^\s*Size:/ && !/No Module/{sz=$2" "$3}
    /^\s*Type:/ && !/Error/{tp=$NF}
    /^\s*Speed:/ && /[0-9]/{sp=$2" "$3}
    /^$/{if(loc && sz) printf "%s:%s:%s:%s ", loc,sz,tp,sp}
' | xargs)

DISK_LIST=$(lsblk -dn -o NAME,SIZE,MODEL 2>/dev/null \
    | grep -v '^loop' | awk '{print $1" "$2" "$3}' | paste -sd'; ')

log_info "  Vendor:   ${SYS_VENDOR}"
log_info "  Model:    ${SYS_MODEL}"
log_info "  Serial:   ${SYS_SERIAL}"
log_info "  UUID:     ${SYS_UUID}"
log_info "  BIOS:     ${BIOS_VENDOR} ${BIOS_VERSION} (${BIOS_DATE})"
log_info "  Chassis:  ${CHASSIS_TYPE} s/n ${CHASSIS_SERIAL}"
log_info "  CPU:      ${CPU_SOCKETS}x ${CPU_MODEL} @ ${CPU_SPEED} — ${CPU_CORES}c/${CPU_THREADS}t"
log_info "  Memory:   ${MEM_TOTAL_GB} GB total, ${MEM_DIMM_COUNT} DIMM(s): ${MEM_DIMM_DETAIL}"
log_info "  Disks:    ${DISK_LIST}"

# ── 2. Bring up physical NICs via DHCP ──────────────────────────────────────
log_info "Bringing up physical network interfaces via DHCP…"
for iface_path in /sys/class/net/*/; do
    iface=$(basename "$iface_path")
    [[ "$iface" == "lo" ]] && continue
    [[ -e "${iface_path}/device" ]] || continue    # skip virtual/tunnel
    log_info "  dhcp → ${iface}"
    ip link set "$iface" up
    dhclient "$iface" 2>>/var/log/dhclient-"${iface}".log &
done
sleep 10

# Enumerate NICs (state + MAC after DHCP)
NIC_SUMMARY=""
for iface_path in /sys/class/net/*/; do
    iface=$(basename "$iface_path")
    [[ "$iface" == "lo" ]] && continue
    [[ -e "${iface_path}/device" ]] || continue
    mac=$(cat "${iface_path}/address" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    state=$(cat "${iface_path}/operstate" 2>/dev/null)
    spd=$(cat "${iface_path}/speed" 2>/dev/null 2>/dev/null)
    [[ "$spd" =~ ^[0-9]+$ && "$spd" -gt 0 ]] && speed="${spd}Mb/s" || speed="?"
    log_info "  ${iface}  MAC=${mac}  state=${state}  speed=${speed}"
    NIC_SUMMARY="${NIC_SUMMARY}${iface}/${mac}/${state} "
done
NIC_SUMMARY="${NIC_SUMMARY% }"

log_info "Addresses:"
ip -brief addr | grep -v '^lo' | tee -a "$LOG_FILE"

# ── 3. Find device in NetBox ─────────────────────────────────────────────────
log_info "Looking up device in NetBox…"
LOOKUP_METHOD=""

if nb_find_device_by_serial "$SYS_SERIAL"; then
    LOOKUP_METHOD="serial"
    log_ok "Found by serial (${SYS_SERIAL}): ${DEVICE_NAME}  (id=${DEVICE_ID}, site=${DEVICE_SITE})"
elif nb_find_device_by_mac; then
    LOOKUP_METHOD="mac"
    log_ok "Found by MAC: ${DEVICE_NAME}  (id=${DEVICE_ID}, site=${DEVICE_SITE})"
else
    log_error "Device not found in NetBox by serial or MAC address."
    log_error "  Serial: ${SYS_SERIAL}"
    log_error "  MACs:   $(cat /sys/class/net/*/address 2>/dev/null | grep -v '00:00:00:00:00:00' | tr '\n' ' ')"
    log_error "Register this device in NetBox before running validation."
    exit 1
fi

# ── 4. Persist state for subsequent phases ────────────────────────────────────
cat > /run/bm-validate/device.env <<EOF
DEVICE_ID="${DEVICE_ID}"
DEVICE_NAME="${DEVICE_NAME}"
DEVICE_SITE="${DEVICE_SITE}"
LOOKUP_METHOD="${LOOKUP_METHOD}"
SYS_VENDOR="${SYS_VENDOR}"
SYS_MODEL="${SYS_MODEL}"
SYS_SERIAL="${SYS_SERIAL}"
SYS_UUID="${SYS_UUID}"
BIOS_VERSION="${BIOS_VERSION}"
BIOS_DATE="${BIOS_DATE}"
CHASSIS_TYPE="${CHASSIS_TYPE}"
CHASSIS_SERIAL="${CHASSIS_SERIAL}"
CPU_SOCKETS="${CPU_SOCKETS}"
CPU_MODEL="${CPU_MODEL}"
CPU_CORES="${CPU_CORES}"
CPU_THREADS="${CPU_THREADS}"
CPU_SPEED="${CPU_SPEED}"
MEM_TOTAL_GB="${MEM_TOTAL_GB}"
MEM_DIMM_COUNT="${MEM_DIMM_COUNT}"
DISK_LIST="${DISK_LIST}"
NIC_SUMMARY="${NIC_SUMMARY}"
EOF

# ── 5. Log hardware found to NetBox journal (read-only — no object updates) ──
nb_journal "$DEVICE_ID" "info" "PXE validation booted. Hardware inventory:
Vendor:  ${SYS_VENDOR} | Model: ${SYS_MODEL} | Serial: ${SYS_SERIAL}
BIOS:    ${BIOS_VENDOR} ${BIOS_VERSION} (${BIOS_DATE})
Chassis: ${CHASSIS_TYPE} s/n ${CHASSIS_SERIAL}
CPU:     ${CPU_SOCKETS}x ${CPU_MODEL} @ ${CPU_SPEED} (${CPU_CORES}c/${CPU_THREADS}t per socket)
Memory:  ${MEM_TOTAL_GB} GB total — ${MEM_DIMM_COUNT} DIMM(s): ${MEM_DIMM_DETAIL}
Disks:   ${DISK_LIST}
NICs:    ${NIC_SUMMARY}
Kernel:  $(uname -r)
Found via: ${LOOKUP_METHOD}"

log_ok "Hardware inventory logged to NetBox journal for ${DEVICE_NAME}"
