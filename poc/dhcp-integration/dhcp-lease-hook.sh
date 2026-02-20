#!/bin/bash
#
# DHCP Lease Hook Script
# ======================
# This script is called by the DHCP server (ISC DHCP) when a lease is granted.
# It publishes the lease information to Redis for processing by the NetBox worker.
#
# For ISC DHCP, add to /etc/dhcp/dhcpd.conf:
#
#   on commit {
#       set ClientIP = binary-to-ascii(10, 8, ".", leased-address);
#       set ClientMac = binary-to-ascii(16, 8, ":", substring(hardware, 1, 6));
#       set ClientHost = pick-first-value(option host-name, "unknown");
#       execute("/usr/local/bin/dhcp-lease-hook.sh", ClientIP, ClientMac, ClientHost);
#   }
#
# Arguments:
#   $1 - IP address assigned
#   $2 - MAC address (format: aa:bb:cc:dd:ee:ff)
#   $3 - Hostname (if provided by client)

set -e

# Configuration
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_QUEUE="${REDIS_QUEUE:-netbox:bmc:discovered}"
LOG_FILE="${LOG_FILE:-/var/log/dhcp-lease-hook.log}"

# Arguments
IP_ADDRESS="$1"
MAC_ADDRESS="$2"
HOSTNAME="${3:-unknown}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Log the event
echo "$(date) - DHCP Lease: IP=$IP_ADDRESS MAC=$MAC_ADDRESS HOST=$HOSTNAME" >> "$LOG_FILE"

# Check if this is a BMC (HPE iLO OUI: A0:36:9F or Dell iDRAC OUI: D0:67:E5, etc.)
BMC_OUIS=("A0:36:9F" "a0:36:9f" "D0:67:E5" "d0:67:e5" "14:18:77" "18:FB:7B")
IS_BMC=false

for OUI in "${BMC_OUIS[@]}"; do
    if [[ "$MAC_ADDRESS" == "$OUI"* ]]; then
        IS_BMC=true
        break
    fi
done

if [ "$IS_BMC" = false ]; then
    echo "$(date) - Not a BMC MAC, ignoring..." >> "$LOG_FILE"
    exit 0
fi

# Create JSON event payload
EVENT_JSON=$(cat <<EOF
{
  "event_type": "bmc_dhcp_lease",
  "timestamp": "$TIMESTAMP",
  "mac_address": "$MAC_ADDRESS",
  "ip_address": "$IP_ADDRESS",
  "hostname": "$HOSTNAME",
  "source": "dhcp_server"
}
EOF
)

# Push to Redis queue (using redis-cli)
if command -v redis-cli &> /dev/null; then
    REDIS_AUTH_ARGS=()
    [ -n "$REDIS_PASSWORD" ] && REDIS_AUTH_ARGS=(-a "$REDIS_PASSWORD")
    echo "$EVENT_JSON" | redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "${REDIS_AUTH_ARGS[@]}" LPUSH "$REDIS_QUEUE" 2>&1 >> "$LOG_FILE"
    echo "$(date) - Event pushed to Redis: $REDIS_QUEUE" >> "$LOG_FILE"
else
    echo "$(date) - ERROR: redis-cli not found!" >> "$LOG_FILE"
    exit 1
fi

exit 0
