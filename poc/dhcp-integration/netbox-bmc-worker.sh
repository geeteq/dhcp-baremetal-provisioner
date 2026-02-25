#!/usr/bin/env bash
# =============================================================================
# NetBox BMC Discovery Worker
# =============================================================================
# Long-running daemon. Polls a Redis queue for BMC DHCP lease events and
# updates NetBox via the shared FSM library.
#
# Dependencies: bash 4+, curl, redis-cli, jq
#
# Environment variables:
#   REDIS_HOST          Redis hostname          (default: localhost)
#   REDIS_PORT          Redis port              (default: 6379)
#   REDIS_PASSWORD      Redis password          (default: empty)
#   REDIS_QUEUE         Queue name              (default: netbox:bmc:discovered)
#   REDIS_USE_TLS       Enable TLS              (default: false)
#   REDIS_TLS_CERT      TLS client certificate
#   REDIS_TLS_KEY       TLS client key
#   REDIS_TLS_CA        TLS CA certificate
#   LOG_FILE            defaults to /var/log/bm/netbox-bmc-worker.log
#   + all variables from lib/bmc-fsm.sh (NETBOX_URL, NETBOX_TOKEN, ...)
# =============================================================================

set -uo pipefail

# Script-specific log file — set before sourcing the lib
LOG_FILE="${LOG_FILE:-/var/log/bm/netbox-bmc-worker.log}"

# Load shared FSM library
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/lib/bmc-fsm.sh
source "${_SCRIPT_DIR}/../scripts/lib/bmc-fsm.sh"

# ---------------------------------------------------------------------------
# Redis configuration
# ---------------------------------------------------------------------------
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_QUEUE="${REDIS_QUEUE:-netbox:bmc:discovered}"
REDIS_USE_TLS="${REDIS_USE_TLS:-false}"
REDIS_TLS_CERT="${REDIS_TLS_CERT:-}"
REDIS_TLS_KEY="${REDIS_TLS_KEY:-}"
REDIS_TLS_CA="${REDIS_TLS_CA:-}"

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
# Main loop
# ---------------------------------------------------------------------------
SEP="======================================================================"

main() {
    log_info "$SEP"
    log_info "NetBox BMC Discovery Worker started"
    log_info "Redis:  ${REDIS_HOST}:${REDIS_PORT}  queue=${REDIS_QUEUE}"
    log_info "NetBox: ${NETBOX_URL}"
    log_info "$SEP"

    if ! redis_cmd PING > /dev/null 2>&1; then
        log_error "Cannot connect to Redis at ${REDIS_HOST}:${REDIS_PORT}"
        exit 1
    fi
    log_info "Connected to Redis"

    while true; do
        # BRPOP blocks up to 1 s, returns two lines: queue-name \n json-value
        local result
        result="$(redis_cmd BRPOP "$REDIS_QUEUE" 1 2>/dev/null)" || {
            log_error "Redis BRPOP failed — sleeping 5 s before retry"
            sleep 5
            continue
        }

        [[ -z "$result" ]] && continue

        local event_json; event_json="$(echo "$result" | tail -1)"
        [[ -z "$event_json" ]] && continue

        # Parse the event envelope
        local event_type mac_address ip_address
        event_type="$(echo  "$event_json" | jq -r '.event_type  // "unknown"')"
        mac_address="$(echo "$event_json" | jq -r '.mac_address // empty')"
        ip_address="$(echo  "$event_json" | jq -r '.ip_address  // empty')"

        if [[ -z "$mac_address" || -z "$ip_address" ]]; then
            log_error "Event missing mac_address or ip_address — skipping"
            continue
        fi

        log_info "----------------------------------------------------------------------"
        log_info "Event: ${event_type}  MAC=${mac_address}  IP=${ip_address}"

        if fsm_process_bmc_event "dhcp_seen" "$mac_address" "$ip_address"; then
            log_info "Event processed successfully"
        else
            log_error "Event processing failed"
        fi

        log_info "----------------------------------------------------------------------"
    done
}

trap 'log_info "Received shutdown signal — exiting"; exit 0' INT TERM

main "$@"
