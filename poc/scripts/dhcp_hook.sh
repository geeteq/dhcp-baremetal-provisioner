#!/bin/bash
#
# DHCP Hook Script
# Called by ISC DHCP server on lease commit
# Writes event to log file for processing by dhcp_tailer.py
#
# Usage: Called automatically by dhcpd with environment variables:
#   LEASED_IP - The IP address assigned
#   CLIENT_MAC - The client MAC address
#   CLIENT_HOSTNAME - The client hostname (if provided)
#

set -e

# Configuration
#LOG_FILE="${LOG_FILE:-/var/log/bm/dhcp_events.log}"
LOG_FILE="${LOG_FILE:-log/bm/dhcp_events.log}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Get lease information from environment or arguments
IP="${LEASED_IP:-$1}"
MAC="${CLIENT_MAC:-$2}"
HOSTNAME="${CLIENT_HOSTNAME:-$3}"

# Validate required fields
if [[ -z "$IP" || -z "$MAC" ]]; then
    echo "Error: Missing required fields (IP: $IP, MAC: $MAC)" >&2
    exit 1
fi

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Create JSON event (single line)
EVENT=$(cat <<EOF
{"event_type":"dhcp_lease_assigned","timestamp":"$TIMESTAMP","data":{"ip":"$IP","mac":"$MAC","hostname":"$HOSTNAME"}}
EOF
)

# Append to log file (atomic operation)
echo "$EVENT" >> "$LOG_FILE"

exit 0
