#!/bin/bash
#
# Test BMC Discovery Event
# ========================
# Simulates a BMC DHCP lease event by pushing a test event to Redis.
# Use this to test the NetBox BMC worker without needing a real DHCP server.
#
# Usage:
#   ./test-bmc-discovery.sh <MAC_ADDRESS> [IP_ADDRESS]
#
# Example:
#   ./test-bmc-discovery.sh A0:36:9F:01:00:00 10.0.0.100

set -e

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_USE_TLS="${REDIS_USE_TLS:-false}"
REDIS_TLS_CERT="${REDIS_TLS_CERT:-}"
REDIS_TLS_KEY="${REDIS_TLS_KEY:-}"
REDIS_TLS_CA="${REDIS_TLS_CA:-}"
REDIS_QUEUE="${REDIS_QUEUE:-netbox:bmc:discovered}"

# Get MAC address from argument or use default
MAC_ADDRESS="${1:-A0:36:9F:01:00:00}"
IP_ADDRESS="${2:-10.0.0.100}"
HOSTNAME="${3:-test-bmc}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║          Testing BMC Discovery Event                            ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Redis:       $REDIS_HOST:$REDIS_PORT"
echo "Queue:       $REDIS_QUEUE"
echo "MAC Address: $MAC_ADDRESS"
echo "IP Address:  $IP_ADDRESS"
echo "Hostname:    $HOSTNAME"
echo ""

# Create JSON event
EVENT_JSON=$(cat <<EOF
{
  "event_type": "bmc_dhcp_lease",
  "timestamp": "$TIMESTAMP",
  "mac_address": "$MAC_ADDRESS",
  "ip_address": "$IP_ADDRESS",
  "hostname": "$HOSTNAME",
  "source": "test_script"
}
EOF
)

echo "Event payload:"
echo "$EVENT_JSON" | jq '.'
echo ""

# Build redis-cli args
REDIS_ARGS=(-h "$REDIS_HOST" -p "$REDIS_PORT")
[ -n "$REDIS_PASSWORD" ] && REDIS_ARGS+=(--no-auth-warning -a "$REDIS_PASSWORD")
if [ "$REDIS_USE_TLS" = "true" ]; then
    REDIS_ARGS+=(--tls --sni redis-server)
    [ -n "$REDIS_TLS_CERT" ] && REDIS_ARGS+=(--cert "$REDIS_TLS_CERT")
    [ -n "$REDIS_TLS_KEY" ]  && REDIS_ARGS+=(--key  "$REDIS_TLS_KEY")
    [ -n "$REDIS_TLS_CA" ]   && REDIS_ARGS+=(--cacert "$REDIS_TLS_CA")
fi

# Push to Redis
echo "Pushing event to Redis..."
echo "$EVENT_JSON" | redis-cli "${REDIS_ARGS[@]}" -x LPUSH "$REDIS_QUEUE" > /dev/null

echo "✓ Event pushed successfully!"
echo ""
echo "Check the worker logs to see if it processes the event."
echo "Expected: Device with BMC MAC $MAC_ADDRESS should transition offline → discovered"
