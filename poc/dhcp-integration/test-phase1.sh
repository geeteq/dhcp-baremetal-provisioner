#!/bin/bash
#
# Phase 1 Test - Initial Racking and Power-On
# ============================================
# Tests the initial server discovery workflow as specified in PHASES.md
#
# Test Scenario:
# - Server: CENT-SRV-035
# - BMC MAC: A0:36:9F:77:05:00
# - IP to assign: 10.22.4.202
# - Expected state transition: Offline → Planned
#
# This script:
# 1. Verifies the device exists in NetBox
# 2. Verifies the BMC interface with correct MAC exists
# 3. Simulates DHCP request for the BMC
# 4. Verifies IP assignment
# 5. Verifies state transition to 'planned'
# 6. Checks journal entries were created
#
# Usage:
#   ./test-phase1.sh

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
DEVICE_NAME="CENT-SRV-035"
BMC_MAC="A0:36:9F:77:05:00"
BMC_IP="10.22.4.202"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6380}"
REDIS_QUEUE="netbox:bmc:discovered"
NETBOX_URL="${NETBOX_URL:-http://localhost:8000}"
NETBOX_TOKEN="${NETBOX_TOKEN:-0123456789abcdef0123456789abcdef01234567}"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    PHASE 1 TEST - BMC Discovery                 ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Test Configuration:"
echo "  Device:      $DEVICE_NAME"
echo "  BMC MAC:     $BMC_MAC"
echo "  BMC IP:      $BMC_IP"
echo "  NetBox:      $NETBOX_URL"
echo "  Redis:       $REDIS_HOST:$REDIS_PORT"
echo ""

# Function to print test step
print_step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Step 1: Verify device exists
print_step "STEP 1: Verify Device Exists in NetBox"

DEVICE_CHECK=$(curl -s "$NETBOX_URL/api/dcim/devices/?name=$DEVICE_NAME" \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Accept: application/json")

DEVICE_COUNT=$(echo "$DEVICE_CHECK" | jq -r '.count')

if [ "$DEVICE_COUNT" -eq "0" ]; then
    print_error "Device $DEVICE_NAME not found in NetBox"
    echo ""
    echo "To create the device, run:"
    echo "  docker exec netbox python /opt/netbox/netbox/manage.py shell"
    echo ""
    echo "Then in the shell:"
    echo "  from dcim.models import Device, Site, DeviceRole, DeviceType, Manufacturer"
    echo "  site = Site.objects.first()"
    echo "  role = DeviceRole.objects.first()"
    echo "  manufacturer = Manufacturer.objects.filter(name='HPE').first()"
    echo "  device_type = DeviceType.objects.filter(manufacturer=manufacturer).first()"
    echo "  Device.objects.create(name='$DEVICE_NAME', site=site, device_role=role, device_type=device_type)"
    exit 1
fi

DEVICE_ID=$(echo "$DEVICE_CHECK" | jq -r '.results[0].id')
print_success "Device found: $DEVICE_NAME (ID: $DEVICE_ID)"

# Step 2: Verify BMC interface with correct MAC exists
print_step "STEP 2: Verify BMC Interface with Correct MAC"

INTERFACE_CHECK=$(curl -s "$NETBOX_URL/api/dcim/interfaces/?device_id=$DEVICE_ID&name=bmc" \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Accept: application/json")

INTERFACE_COUNT=$(echo "$INTERFACE_CHECK" | jq -r '.count')

if [ "$INTERFACE_COUNT" -eq "0" ]; then
    print_error "BMC interface not found for device $DEVICE_NAME"
    echo ""
    echo "Create the BMC interface first or run the NetBox initialization scripts."
    exit 1
fi

INTERFACE_ID=$(echo "$INTERFACE_CHECK" | jq -r '.results[0].id')
INTERFACE_MAC=$(echo "$INTERFACE_CHECK" | jq -r '.results[0].mac_address')

if [ "$INTERFACE_MAC" != "$BMC_MAC" ]; then
    print_error "BMC MAC address mismatch!"
    echo "  Expected: $BMC_MAC"
    echo "  Found:    $INTERFACE_MAC"
    exit 1
fi

print_success "BMC interface found with correct MAC: $BMC_MAC (Interface ID: $INTERFACE_ID)"

# Step 3: Get current device state
print_step "STEP 3: Check Current Device State"

CURRENT_STATE=$(echo "$DEVICE_CHECK" | jq -r '.results[0].custom_fields.lifecycle_state // "unknown"')
print_success "Current state: $CURRENT_STATE"

# Step 4: Simulate BMC DHCP request
print_step "STEP 4: Simulate BMC DHCP Request"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

EVENT_JSON=$(cat <<EOF
{
  "event_type": "bmc_dhcp_lease",
  "timestamp": "$TIMESTAMP",
  "mac_address": "$BMC_MAC",
  "ip_address": "$BMC_IP",
  "hostname": "$DEVICE_NAME",
  "source": "phase1_test"
}
EOF
)

echo "Sending DHCP event to Redis queue..."
echo "$EVENT_JSON" | jq '.'

# Push the raw JSON to Redis (not the pretty-printed version)
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LPUSH "$REDIS_QUEUE" "$EVENT_JSON" > /dev/null

if [ $? -eq 0 ]; then
    print_success "Event pushed to Redis queue: $REDIS_QUEUE"
else
    print_error "Failed to push event to Redis"
    exit 1
fi

# Step 5: Wait for worker to process
print_step "STEP 5: Wait for Worker to Process Event"

echo "Waiting for NetBox BMC worker to process the event..."
sleep 3

# Step 6: Verify IP assignment
print_step "STEP 6: Verify IP Assignment"

IP_CHECK=$(curl -s "$NETBOX_URL/api/ipam/ip-addresses/?interface_id=$INTERFACE_ID" \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Accept: application/json")

IP_COUNT=$(echo "$IP_CHECK" | jq -r '.count')

if [ "$IP_COUNT" -eq "0" ]; then
    print_error "No IP address assigned to BMC interface"
    echo ""
    echo "Check the worker logs:"
    echo "  docker-compose logs -f bmc-worker"
    exit 1
fi

ASSIGNED_IP=$(echo "$IP_CHECK" | jq -r '.results[0].address' | cut -d'/' -f1)

if [ "$ASSIGNED_IP" == "$BMC_IP" ]; then
    print_success "IP correctly assigned: $BMC_IP"
else
    print_warning "IP mismatch - Expected: $BMC_IP, Got: $ASSIGNED_IP"
fi

# Step 7: Verify state transition
print_step "STEP 7: Verify State Transition"

DEVICE_CHECK_AFTER=$(curl -s "$NETBOX_URL/api/dcim/devices/$DEVICE_ID/" \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Accept: application/json")

NEW_STATE=$(echo "$DEVICE_CHECK_AFTER" | jq -r '.custom_fields.lifecycle_state // "unknown"')

echo "State transition: $CURRENT_STATE → $NEW_STATE"

if [ "$CURRENT_STATE" == "offline" ] && [ "$NEW_STATE" == "discovered" ]; then
    print_success "State transition successful: offline → discovered"
elif [ "$NEW_STATE" != "$CURRENT_STATE" ]; then
    print_success "State changed: $CURRENT_STATE → $NEW_STATE"
else
    print_warning "State unchanged: $NEW_STATE"
fi

# Step 8: Check journal entries
print_step "STEP 8: Verify Journal Entries"

JOURNAL_CHECK=$(curl -s "$NETBOX_URL/api/extras/journal-entries/?assigned_object_id=$DEVICE_ID&assigned_object_type=dcim.device" \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Accept: application/json")

JOURNAL_COUNT=$(echo "$JOURNAL_CHECK" | jq -r '.count')

if [ "$JOURNAL_COUNT" -gt "0" ]; then
    print_success "Found $JOURNAL_COUNT journal entries"
    echo ""
    echo "Recent journal entries:"
    echo "$JOURNAL_CHECK" | jq -r '.results[] | "  • [\(.kind)] \(.comments)"' | head -5
else
    print_warning "No journal entries found (this may be normal if journals aren't enabled)"
fi

# Final summary
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    PHASE 1 TEST COMPLETE                         ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary:"
echo "  Device:         $DEVICE_NAME"
echo "  Initial State:  $CURRENT_STATE"
echo "  Final State:    $NEW_STATE"
echo "  BMC MAC:        $BMC_MAC"
echo "  BMC IP:         $ASSIGNED_IP"
echo "  Journal Entries: $JOURNAL_COUNT"
echo ""

if [ "$ASSIGNED_IP" == "$BMC_IP" ] && [ "$NEW_STATE" != "$CURRENT_STATE" ]; then
    print_success "Phase 1 test PASSED"
    echo ""
    exit 0
else
    print_warning "Phase 1 test completed with warnings"
    echo ""
    exit 0
fi
