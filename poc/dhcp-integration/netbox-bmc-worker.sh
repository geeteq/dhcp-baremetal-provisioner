#!/usr/bin/env bash
# =============================================================================
# NetBox BMC Discovery Worker — Shell Version
# =============================================================================
# Processes BMC DHCP lease events from Redis and updates NetBox device states.
#
# Workflow:
#   1. Poll Redis queue (BRPOP) for BMC DHCP lease events
#   2. Extract MAC / IP from event JSON
#   3. Find device in NetBox by BMC MAC address
#   4. Transition state: offline → discovered  (or refresh IP if active)
#   5. Assign / update IP on BMC interface
#   6. Write journal entries in NetBox for audit trail
#
# Dependencies: bash 4+, curl, redis-cli, jq
#
# Environment variables:
#   REDIS_HOST          Redis hostname          (default: localhost)
#   REDIS_PORT          Redis port              (default: 6379)
#   REDIS_PASSWORD      Redis password          (default: empty)
#   REDIS_QUEUE         Queue name              (default: netbox:bmc:discovered)
#   REDIS_USE_TLS       Enable TLS              (default: false)
#   REDIS_TLS_CERT      TLS client certificate  (default: empty)
#   REDIS_TLS_KEY       TLS client key          (default: empty)
#   REDIS_TLS_CA        TLS CA certificate      (default: empty)
#   NETBOX_URL          NetBox base URL         (default: http://localhost:8000)
#   NETBOX_TOKEN        NetBox API token
#   LOG_DIR             Log directory           (default: /var/log/bm)
# =============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_QUEUE="${REDIS_QUEUE:-netbox:bmc:discovered}"
REDIS_USE_TLS="${REDIS_USE_TLS:-false}"
REDIS_TLS_CERT="${REDIS_TLS_CERT:-}"
REDIS_TLS_KEY="${REDIS_TLS_KEY:-}"
REDIS_TLS_CA="${REDIS_TLS_CA:-}"
NETBOX_URL="${NETBOX_URL:-http://localhost:8000}"
NETBOX_TOKEN="${NETBOX_TOKEN:-0123456789abcdef0123456789abcdef01234567}"
LOG_DIR="${LOG_DIR:-/var/log/bm}"
LOG_FILE="${LOG_DIR}/netbox-bmc-worker.log"
SEP="======================================================================"

mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Logging — writes to stdout and log file simultaneously
# ---------------------------------------------------------------------------
log() {
    local level="$1"; shift
    local ts; ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s [%s] %s\n' "$ts" "$level" "$*" | tee -a "$LOG_FILE"
}
log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# ---------------------------------------------------------------------------
# Redis helper — builds the redis-cli argument list honouring TLS and auth
# ---------------------------------------------------------------------------
redis_cmd() {
    local args=(-h "$REDIS_HOST" -p "$REDIS_PORT")
    [[ -n "$REDIS_PASSWORD" ]] && args+=(-a "$REDIS_PASSWORD" --no-auth-warning)
    if [[ "$REDIS_USE_TLS" == "true" ]]; then
        args+=(--tls)
        [[ -n "$REDIS_TLS_CA"   ]] && args+=(--cacert "$REDIS_TLS_CA")
        [[ -n "$REDIS_TLS_CERT" ]] && args+=(--cert   "$REDIS_TLS_CERT")
        [[ -n "$REDIS_TLS_KEY"  ]] && args+=(--key    "$REDIS_TLS_KEY")
    fi
    redis-cli --raw "${args[@]}" "$@"
}

# ---------------------------------------------------------------------------
# NetBox HTTP helper
#
# nb_curl METHOD PATH [BODY]
#   Sends a request with a 20-second timeout.
#   Prints response body to stdout.
#   Returns 0 on HTTP 2xx, 1 on any error or non-2xx status.
#   Caller sees the raw body on success.
#
# nb_curl_raw METHOD PATH [BODY]
#   Same, but also outputs the HTTP status code as the LAST line.
#   Useful when the caller needs to inspect the code (e.g. tolerate 400).
# ---------------------------------------------------------------------------
nb_curl() {
    local method="$1" path="$2" body="${3:-}"
    local tmp; tmp="$(mktemp)"
    local http_code
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

    http_code="$(curl "${curl_args[@]}" "${NETBOX_URL%/}${path}")" || {
        rm -f "$tmp"
        log_error "curl transport error for ${method} ${path}"
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
        log_error "curl transport error for ${method} ${path}"
        return 1
    }

    cat "$tmp"; rm -f "$tmp"
    echo "$http_code"   # status code is always the last line
}

nb_get()   { nb_curl GET   "$1";       }
nb_post()  { nb_curl POST  "$1" "$2";  }
nb_patch() { nb_curl PATCH "$1" "$2";  }

# ---------------------------------------------------------------------------
# NetBox operations
# ---------------------------------------------------------------------------

# nb_find_device_by_bmc_mac MAC_ADDRESS
# Prints a JSON object: {device_id, device_name, interface_id, current_state}
# Returns 1 if not found or on error.
nb_find_device_by_bmc_mac() {
    local mac="$1"
    mac="$(echo "$mac" | tr '[:lower:]' '[:upper:]' | tr '-' ':')"

    log_info "Searching NetBox for BMC MAC: ${mac}"

    local iface_resp
    iface_resp="$(nb_get "/api/dcim/interfaces/?mac_address=${mac}&name=bmc")" || return 1

    local count; count="$(echo "$iface_resp" | jq -r '.count')"
    if [[ "$count" == "0" || -z "$count" ]]; then
        log_warn "No device found in NetBox for MAC ${mac}"
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

    log_info "Found device: ${device_name} (ID: ${device_id}), state: ${current_state}"

    jq -n \
        --argjson device_id    "$device_id" \
        --arg     device_name  "$device_name" \
        --argjson interface_id "$iface_id" \
        --arg     current_state "$current_state" \
        '{device_id:$device_id, device_name:$device_name, interface_id:$interface_id, current_state:$current_state}'
}

# nb_update_device_state DEVICE_ID NEW_STATE
nb_update_device_state() {
    local device_id="$1" new_state="$2"
    log_info "Updating device ${device_id} state → ${new_state}"
    nb_patch "/api/dcim/devices/${device_id}/" \
        "{\"status\": \"${new_state}\"}" > /dev/null || return 1
    log_info "Device ${device_id} state updated to ${new_state}"
}

# nb_assign_ip INTERFACE_ID IP_ADDRESS
# Tolerates HTTP 400 (IP already exists) as a non-fatal warning.
nb_assign_ip() {
    local iface_id="$1" ip="$2"
    local ts; ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local body
    body="$(jq -n \
        --arg     address  "${ip}/24" \
        --argjson obj_id   "$iface_id" \
        --arg     desc     "Auto-assigned by DHCP on ${ts}" \
        '{address:$address, assigned_object_type:"dcim.interface",
          assigned_object_id:$obj_id, status:"active", description:$desc}')"

    log_info "Assigning IP ${ip} to interface ${iface_id}"

    local output; output="$(nb_curl_raw POST "/api/ipam/ip-addresses/" "$body")" || return 1
    local http_code; http_code="$(echo "$output" | tail -1)"

    case "$http_code" in
        201) log_info "IP ${ip} assigned to interface ${iface_id}" ;;
        400) log_warn "IP ${ip} may already exist, skipping" ;;
        *)   log_error "Failed to assign IP ${ip}: HTTP ${http_code}"; return 1 ;;
    esac
}

# nb_update_bmc_ip INTERFACE_ID IP_ADDRESS
# Updates the existing IP on the interface; falls back to assign if none found.
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
        --arg address "${ip}/24" \
        --arg desc    "Auto-updated by DHCP on ${ts}" \
        '{address:$address, description:$desc}')"

    nb_patch "/api/ipam/ip-addresses/${ip_id}/" "$body" > /dev/null || return 1
    log_info "BMC IP updated to ${ip} on interface ${iface_id}"
}

# nb_journal DEVICE_ID MESSAGE KIND
# KIND: info | success | warning | danger
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
        log_warn "Journal entry failed for device ${device_id}: ${message}"
        return 0  # journal failure is non-fatal
    }
    local http_code; http_code="$(echo "$output" | tail -1)"

    if [[ "$http_code" == "201" ]]; then
        log_info "Journal entry added to device ${device_id}: ${message}"
    else
        log_warn "Journal entry HTTP ${http_code} for device ${device_id}"
    fi
}

# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------

process_event() {
    local event_json="$1"

    local event_type mac_address ip_address
    event_type="$(echo  "$event_json" | jq -r '.event_type  // "unknown"')"
    mac_address="$(echo "$event_json" | jq -r '.mac_address // empty')"
    ip_address="$(echo  "$event_json" | jq -r '.ip_address  // empty')"

    if [[ -z "$mac_address" || -z "$ip_address" ]]; then
        log_error "Event missing mac_address or ip_address"
        return 1
    fi

    log_info "Processing event: ${event_type}  MAC=${mac_address}  IP=${ip_address}"

    local device_info
    if ! device_info="$(nb_find_device_by_bmc_mac "$mac_address")"; then
        log_error "Device not found in NetBox for MAC ${mac_address}"
        return 1
    fi

    local device_id device_name interface_id current_state
    device_id="$(echo     "$device_info" | jq -r '.device_id')"
    device_name="$(echo   "$device_info" | jq -r '.device_name')"
    interface_id="$(echo  "$device_info" | jq -r '.interface_id')"
    current_state="$(echo "$device_info" | jq -r '.current_state')"

    # Audit trail — always log discovery regardless of state
    nb_journal "$device_id" \
        "BMC discovered via DHCP - MAC: ${mac_address}, IP: ${ip_address}" \
        "success"

    case "$current_state" in
        active)
            # Live device — refresh IP only, do not touch state or tenant
            log_info "Device ${device_name} is active (live); updating BMC IP only"
            nb_update_bmc_ip "$interface_id" "$ip_address"
            nb_journal "$device_id" "IP address ${ip_address} assigned to interface bmc" "info"
            log_info "BMC IP refreshed for live device ${device_name}"
            ;;
        offline)
            # Normal new-device flow: offline → discovered
            nb_update_device_state "$device_id" "discovered"
            nb_journal "$device_id" "Lifecycle state changed: offline -> discovered" "success"
            log_info "State transition: ${device_name} offline -> discovered"
            nb_assign_ip "$interface_id" "$ip_address"
            nb_journal "$device_id" "IP address ${ip_address} assigned to interface bmc" "info"
            ;;
        discovered)
            log_info "Device ${device_name} already in discovered state"
            nb_assign_ip "$interface_id" "$ip_address"
            nb_journal "$device_id" "IP address ${ip_address} assigned to interface bmc" "info"
            ;;
        *)
            log_warn "Device ${device_name} in unexpected state: ${current_state}"
            nb_journal "$device_id" \
                "BMC discovery attempted but device in unexpected state: ${current_state}" \
                "warning"
            ;;
    esac

    log_info "Successfully processed BMC discovery for ${device_name}"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

main() {
    log_info "$SEP"
    log_info "NetBox BMC Discovery Worker Started (shell)"
    log_info "$SEP"
    log_info "Redis:  ${REDIS_HOST}:${REDIS_PORT}  queue=${REDIS_QUEUE}"
    log_info "NetBox: ${NETBOX_URL}"
    log_info "Waiting for BMC discovery events..."
    log_info "$SEP"

    # Verify Redis connectivity before entering the loop
    if ! redis_cmd PING > /dev/null 2>&1; then
        log_error "Cannot connect to Redis at ${REDIS_HOST}:${REDIS_PORT}"
        exit 1
    fi
    log_info "Connected to Redis at ${REDIS_HOST}:${REDIS_PORT}"

    while true; do
        # BRPOP with 1-second timeout — returns two lines on success:
        #   line 1: queue name
        #   line 2: event JSON
        # Returns empty output on timeout.
        local result
        result="$(redis_cmd BRPOP "$REDIS_QUEUE" 1 2>/dev/null)" || {
            log_error "Redis BRPOP failed — sleeping 5 s before retry"
            sleep 5
            continue
        }

        [[ -z "$result" ]] && continue

        # With --raw, output is two plain lines: queue-name \n json-value
        local event_json; event_json="$(echo "$result" | tail -1)"
        [[ -z "$event_json" ]] && continue

        log_info "----------------------------------------------------------------------"
        if process_event "$event_json"; then
            log_info "Event processed successfully"
        else
            log_error "Event processing failed"
        fi
        log_info "----------------------------------------------------------------------"
    done
}

trap 'log_info "Received shutdown signal, exiting"; exit 0' INT TERM

main "$@"
