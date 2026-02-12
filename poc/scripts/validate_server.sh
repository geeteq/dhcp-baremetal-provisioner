#!/bin/bash
#
# Server Validation Script
# Runs inside PXE-booted RHEL9 validation ISO
# Collects hardware info, LLDP neighbors, interface data
# Posts results to callback API
#

set -e

# Configuration from kernel command line
DEVICE_ID=$(cat /proc/cmdline | grep -oP 'device_id=\K[^ ]+' || echo "unknown")
API_ENDPOINT=$(cat /proc/cmdline | grep -oP 'api_endpoint=\K[^ ]+' || echo "http://10.1.100.5:5000/api/v1/validation/report")

echo "==> Server Validation Script"
echo "    Device ID: $DEVICE_ID"
echo "    API Endpoint: $API_ENDPOINT"

# Wait for network to be ready
echo "==> Waiting for network..."
sleep 10

# Start LLDP daemon
echo "==> Starting LLDP daemon..."
systemctl start lldpd || service lldpd start || lldpd -d
sleep 5

# Collect LLDP data
echo "==> Collecting LLDP neighbor data..."
if command -v lldpctl &> /dev/null; then
    LLDP_DATA=$(lldpctl -f json 2>/dev/null || echo "{}")
else
    echo "Warning: lldpctl not found"
    LLDP_DATA="{}"
fi

# Collect hardware information
echo "==> Collecting hardware information..."
if command -v dmidecode &> /dev/null; then
    HARDWARE_MODEL=$(dmidecode -s system-product-name 2>/dev/null | tr -d '\n' || echo "Unknown")
    SERIAL_NUMBER=$(dmidecode -s system-serial-number 2>/dev/null | tr -d '\n' || echo "Unknown")
    MANUFACTURER=$(dmidecode -s system-manufacturer 2>/dev/null | tr -d '\n' || echo "Unknown")
else
    echo "Warning: dmidecode not found"
    HARDWARE_MODEL="Unknown"
    SERIAL_NUMBER="Unknown"
    MANUFACTURER="Unknown"
fi

echo "    Manufacturer: $MANUFACTURER"
echo "    Model: $HARDWARE_MODEL"
echo "    Serial: $SERIAL_NUMBER"

# Collect interface information
echo "==> Collecting network interface data..."
if command -v ip &> /dev/null; then
    INTERFACES=$(ip -j link show 2>/dev/null | jq '[.[] | select(.link_type == "ether") | {name: .ifname, mac: .address, state: .operstate}]' 2>/dev/null || echo "[]")
else
    echo "Warning: ip command not found"
    INTERFACES="[]"
fi

# Build JSON payload
echo "==> Building validation report..."
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

PAYLOAD=$(cat <<EOF
{
  "device_id": "$DEVICE_ID",
  "timestamp": "$TIMESTAMP",
  "hardware": {
    "manufacturer": "$MANUFACTURER",
    "model": "$HARDWARE_MODEL",
    "serial": "$SERIAL_NUMBER"
  },
  "lldp": $LLDP_DATA,
  "interfaces": $INTERFACES
}
EOF
)

# Save payload to file for debugging
echo "$PAYLOAD" > /tmp/validation_report.json
echo "==> Payload saved to /tmp/validation_report.json"

# Send to callback API
echo "==> Sending validation report to API..."
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /tmp/api_response.txt -w "%{http_code}" \
        -X POST "$API_ENDPOINT" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --connect-timeout 30 \
        --max-time 60)

    echo "    HTTP Status: $HTTP_CODE"

    if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
        echo "==> Validation report sent successfully"
        cat /tmp/api_response.txt
    else
        echo "==> ERROR: Failed to send validation report"
        cat /tmp/api_response.txt
        exit 1
    fi
else
    echo "ERROR: curl not found"
    exit 1
fi

# Shutdown after reporting
echo "==> Validation complete. Shutting down..."
sleep 5
poweroff || shutdown -h now

exit 0
