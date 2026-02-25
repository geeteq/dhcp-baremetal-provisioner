#!/usr/bin/env bash
# =============================================================================
# DHCP Hook — Direct NetBox Integration
# =============================================================================
# Called by ISC DHCP server on every lease commit. Filters for BMC MAC OUIs,
# then updates NetBox directly — no Redis, no separate worker process.
#
# For ISC DHCP, add to /etc/dhcp/dhcpd.conf:
#
#   on commit {
#       set ClientIP   = binary-to-ascii(10, 8, ".", leased-address);
#       set ClientMac  = binary-to-ascii(16, 8, ":", substring(hardware, 1, 6));
#       set ClientHost = pick-first-value(option host-name, "unknown");
#       execute("/usr/local/bin/dhcp_hook2.sh", ClientIP, ClientMac, ClientHost);
#   }
#
# Arguments (or environment variables as fallback):
#   $1 / LEASED_IP      - IP address assigned by DHCP
#   $2 / CLIENT_MAC     - Client MAC address (any separator, any case)
#   $3 / CLIENT_HOSTNAME - Client hostname (optional)
#
# Dependencies: bash 4+, curl, jq
#
# Environment variables:
#   NETBOX_URL          NetBox base URL     (default: http://localhost:8000)
#   NETBOX_TOKEN        NetBox API token    (required)
#   BMC_SUBNET_PREFIX   Prefix length for BMC IPs (default: 24)
#   LOG_FILE            Log file path       (default: /var/log/bm/dhcp-hook.log)
# =============================================================================

# Do not use set -e here — dhcpd must not see a non-zero exit or it may
# retry / log errors. We handle all failures internally.
set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NETBOX_URL="${NETBOX_URL:-http://localhost:8000}"
NETBOX_TOKEN="${NETBOX_TOKEN:-0123456789abcdef0123456789abcdef01234567}"
BMC_SUBNET_PREFIX="${BMC_SUBNET_PREFIX:-24}"
LOG_FILE="${LOG_FILE:-/var/log/bm/dhcp-hook.log}"

# BMC OUI prefixes — add/remove as needed for your hardware vendors
# HPE iLO, Dell iDRAC, Supermicro IPMI, Lenovo XCC, Cisco CIMC
BMC_OUIS=(
    "a0:36:9f"   # HPE iLO (ProLiant)
    "d0:67:e5"   # Dell iDRAC
    "3c:a8:2a"   # Dell iDRAC (newer)
    "14:18:77"   # Supermicro IPMI
    "18:fb:7b"   # Supermicro IPMI
    "b4:96:91"   # Lenovo XClarity (XCC)
    "d0:94:66"   # Cisco CIMC
)

# ---------------------------------------------------------------------------
# Arguments — accept both positional args and environment variables
# ---------------------------------------------------------------------------
IP_ADDRESS="${1:-${LEASED_IP:-}}"
MAC_ADDRESS="${2:-${CLIENT_MAC:-}}"
HOSTNAME="${3:-${CLIENT_HOSTNAME:-unknown}}"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    local level="$1"; shift
    printf '%s [%s] %s\n' "$TIMESTAMP" "$level" "$*" | tee -a "$LOG_FILE" >&2
}
log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
if [[ -z "$IP_ADDRESS" || -z "$MAC_ADDRESS" ]]; then
    log_error "Missing required arguments: IP=${IP_ADDRESS} MAC=${MAC_ADDRESS}"
    exit 0  # exit 0 so dhcpd doesn't treat this as a fatal error
fi

# ---------------------------------------------------------------------------
# BMC OUI filter — normalise MAC then check against known BMC OUIs
# ---------------------------------------------------------------------------
MAC_NORM="$(echo "$MAC_ADDRESS" | tr '[:upper:]' '[:lower:]' | tr '-' ':')"

is_bmc_mac() {
    local mac_lower="$1"
    local oui="${mac_lower:0:8}"   # first 3 octets: xx:xx:xx
    for prefix in "${BMC_OUIS[@]}"; do
        [[ "$oui" == "$prefix" ]] && return 0
    done
    return 1
}

if ! is_bmc_mac "$MAC_NORM"; then
    # Not a BMC — nothing to do, exit silently
    exit 0
fi

log_info "BMC DHCP lease: IP=${IP_ADDRESS} MAC=${MAC_ADDRESS} HOST=${HOSTNAME}"

# ---------------------------------------------------------------------------
# NetBox API helpers — all calls timeout after 20 seconds
# ---------------------------------------------------------------------------
nb_curl() {
    local method="$1" path="$2" body="${3:-}"
    local tmp; tmp="$(mktemp)"
    local curl_args=(
        --silent --show-error
        --max-time 20
        -X "$method"
        -H "Authorization: Token ${NETBOX_TOKEN}"
        -H "Content-Type: application/json"
        -H "Accept: application/json"
        -o "$tmp"
        -w '%{http_code}'
    )
    [[ -n "$body" ]] && curl_args+=(--data-raw "$body")

    local http_code
    http_code="$(curl "${curl_args[@]}" "${NETBOX_URL%/}${path}")" || {
        rm -f "$tmp"
        log_error "curl transport error: ${method} ${path}"
        return 1
    }

    local resp; resp="$(cat "$tmp")"; rm -f "$tmp"

    if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
        echo "$resp"
        return 0
    fi

    log_error "NetBox ${method} ${path} => HTTP ${http_code}: ${resp}"
    return 1
}

# Returns response body AND appends HTTP status code as last line (for callers
# that need to distinguish specific non-2xx codes, e.g. 400 on duplicate IP).
nb_curl_raw() {
    local method="$1" path="$2" body="${3:-}"
    local tmp; tmp="$(mktemp)"
    local curl_args=(
        --silent --show-error
        --max-time 20
        -X "$method"
        -H "Authorization: Token ${NETBOX_TOKEN}"
        -H "Content-Type: application/json"
        -H "Accept: application/json"
        -o "$tmp"
        -w '%{http_code}'
    )
    [[ -n "$body" ]] && curl_args+=(--data-raw "$body")

    local http_code
    http_code="$(curl "${curl_args[@]}" "${NETBOX_URL%/}${path}")" || {
        rm -f "$tmp"
        log_error "curl transport error: ${method} ${path}"
        return 1
    }

    cat "$tmp"; rm -f "$tmp"
    echo "$http_code"
}

nb_get()   { nb_curl GET   "$1";      }
nb_post()  { nb_curl POST  "$1" "$2"; }
nb_patch() { nb_curl PATCH "$1" "$2"; }

# ---------------------------------------------------------------------------
# NetBox — find device by BMC MAC address
# Returns JSON: {device_id, device_name, interface_id, current_state}
# ---------------------------------------------------------------------------
nb_find_device_by_bmc_mac() {
    local mac="$1"
    local mac_upper; mac_upper="$(echo "$mac" | tr '[:lower:]' '[:upper:]')"

    log_info "Looking up NetBox device for MAC: ${mac_upper}"

    local iface_resp
    iface_resp="$(nb_get "/api/dcim/interfaces/?mac_address=${mac_upper}&name=bmc")" || return 1

    local count; count="$(echo "$iface_resp" | jq -r '.count')"
    if [[ "$count" == "0" || -z "$count" ]]; then
        log_warn "No NetBox device found for MAC ${mac_upper}"
        return 1
    fi

    local iface_id device_id
    iface_id="$(echo  "$iface_resp" | jq -r '.results[0].id')"
    device_id="$(echo "$iface_resp" | jq -r '.results[0].device.id')"

    local dev_resp
    dev_resp="$(nb_get "/api/dcim/devices/${device_id}/")" || return 1

    local device_name current_state
    device_name="$(echo   "$dev_resp" | jq -r '.name')"
    current_state="$(echo "$dev_resp" | jq -r '.status.value')"

    log_info "Found: ${device_name} (ID: ${device_id}) state=${current_state}"

    jq -n \
        --argjson device_id    "$device_id" \
        --arg     device_name  "$device_name" \
        --argjson interface_id "$iface_id" \
        --arg     current_state "$current_state" \
        '{device_id:$device_id, device_name:$device_name,
          interface_id:$interface_id, current_state:$current_state}'
}

# ---------------------------------------------------------------------------
# NetBox — state and IP operations
# ---------------------------------------------------------------------------
nb_update_device_state() {
    local device_id="$1" new_state="$2"
    nb_patch "/api/dcim/devices/${device_id}/" \
        "{\"status\": \"${new_state}\"}" > /dev/null || return 1
    log_info "Device ${device_id} state → ${new_state}"
}

nb_assign_ip() {
    local iface_id="$1" ip="$2"
    local ts; ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local body
    body="$(jq -n \
        --arg     address "${ip}/${BMC_SUBNET_PREFIX}" \
        --argjson obj_id  "$iface_id" \
        --arg     desc    "Auto-assigned by DHCP on ${ts}" \
        '{address:$address, assigned_object_type:"dcim.interface",
          assigned_object_id:$obj_id, status:"active", description:$desc}')"

    local output; output="$(nb_curl_raw POST "/api/ipam/ip-addresses/" "$body")" || return 1
    local http_code; http_code="$(echo "$output" | tail -1)"

    case "$http_code" in
        201) log_info "IP ${ip} assigned to interface ${iface_id}" ;;
        400) log_warn "IP ${ip} may already exist, skipping" ;;
        *)   log_error "Failed to assign IP ${ip}: HTTP ${http_code}"; return 1 ;;
    esac
}

nb_update_bmc_ip() {
    local iface_id="$1" ip="$2"
    local ts; ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    local ip_resp
    ip_resp="$(nb_get "/api/ipam/ip-addresses/?assigned_object_type=dcim.interface&assigned_object_id=${iface_id}")" || {
        log_warn "Could not query existing IPs for interface ${iface_id}, falling back to assign"
        nb_assign_ip "$iface_id" "$ip"
        return
    }

    local count; count="$(echo "$ip_resp" | jq -r '.count')"
    if [[ "$count" == "0" || -z "$count" ]]; then
        nb_assign_ip "$iface_id" "$ip"
        return
    fi

    local ip_id; ip_id="$(echo "$ip_resp" | jq -r '.results[0].id')"
    local body
    body="$(jq -n \
        --arg address "${ip}/${BMC_SUBNET_PREFIX}" \
        --arg desc    "Auto-updated by DHCP on ${ts}" \
        '{address:$address, description:$desc}')"

    nb_patch "/api/ipam/ip-addresses/${ip_id}/" "$body" > /dev/null || return 1
    log_info "BMC IP updated to ${ip} on interface ${iface_id}"
}

nb_journal() {
    local device_id="$1" message="$2" kind="${3:-info}"
    local ts; ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local body
    body="$(jq -n \
        --argjson device_id "$device_id" \
        --arg     kind      "$kind" \
        --arg     comments  "[${ts}] ${message}" \
        '{assigned_object_type:"dcim.device", assigned_object_id:$device_id,
          kind:$kind, comments:$comments}')"

    local output; output="$(nb_curl_raw POST "/api/extras/journal-entries/" "$body")" || {
        log_warn "Journal entry failed (non-fatal): ${message}"
        return 0
    }
    local http_code; http_code="$(echo "$output" | tail -1)"
    [[ "$http_code" == "201" ]] || log_warn "Journal entry HTTP ${http_code} for device ${device_id}"
    return 0  # journal failure is always non-fatal
}

# ---------------------------------------------------------------------------
# Main processing logic
# ---------------------------------------------------------------------------
main() {
    # Look up device in NetBox
    local device_info
    if ! device_info="$(nb_find_device_by_bmc_mac "$MAC_NORM")"; then
        log_error "Device not found in NetBox for MAC ${MAC_NORM} — no action taken"
        exit 0
    fi

    local device_id device_name interface_id current_state
    device_id="$(echo     "$device_info" | jq -r '.device_id')"
    device_name="$(echo   "$device_info" | jq -r '.device_name')"
    interface_id="$(echo  "$device_info" | jq -r '.interface_id')"
    current_state="$(echo "$device_info" | jq -r '.current_state')"

    # Audit trail — always written regardless of state
    nb_journal "$device_id" \
        "BMC discovered via DHCP - MAC: ${MAC_ADDRESS}, IP: ${IP_ADDRESS}" \
        "success"

    case "$current_state" in
        active)
            # Live device — only refresh BMC IP, do not touch state or tenant
            log_info "Device ${device_name} is active (live); updating BMC IP only"
            nb_update_bmc_ip "$interface_id" "$IP_ADDRESS"
            nb_journal "$device_id" \
                "IP address ${IP_ADDRESS} assigned to interface bmc" "info"
            log_info "BMC IP refreshed for live device ${device_name}"
            ;;
        offline)
            # New device coming online: offline → discovered
            nb_update_device_state "$device_id" "discovered"
            nb_journal "$device_id" \
                "Lifecycle state changed: offline -> discovered" "success"
            log_info "State transition: ${device_name} offline -> discovered"
            nb_assign_ip "$interface_id" "$IP_ADDRESS"
            nb_journal "$device_id" \
                "IP address ${IP_ADDRESS} assigned to interface bmc" "info"
            ;;
        discovered)
            log_info "Device ${device_name} already discovered; refreshing IP"
            nb_assign_ip "$interface_id" "$IP_ADDRESS"
            nb_journal "$device_id" \
                "IP address ${IP_ADDRESS} assigned to interface bmc" "info"
            ;;
        *)
            log_warn "Device ${device_name} in unexpected state: ${current_state} — skipping state change"
            nb_journal "$device_id" \
                "BMC discovery attempted but device in unexpected state: ${current_state}" \
                "warning"
            ;;
    esac

    log_info "Done processing BMC DHCP lease for ${device_name}"
}

main

# Always exit 0 — dhcpd must not see a failure exit code from this hook
exit 0
