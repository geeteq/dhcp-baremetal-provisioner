#!/bin/bash
#
# Simulate Server Reboot and DHCP Discovery for WEST-SRV-201
# ===========================================================

set -e

SERVER="WEST-SRV-201"

echo "======================================================================"
echo "SERVER REBOOT & BMC DHCP DISCOVERY SIMULATION"
echo "======================================================================"
echo ""
echo "Target Server: $SERVER"
echo ""

# Step 1: Clear BMC IP
echo "======================================================================"
echo "STEP 1: Clearing BMC IP Assignment"
echo "======================================================================"

docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface
from ipam.models import IPAddress

server = Device.objects.get(name='$SERVER')
bmc = Interface.objects.get(device=server, name='bmc')

ips = IPAddress.objects.filter(
    assigned_object_type__model='interface',
    assigned_object_id=bmc.id
)

count = ips.count()
if count > 0:
    for ip in ips:
        print(f'  Removing IP: {ip.address}')
        ip.delete()
    print(f'  ✓ Cleared {count} IP assignment(s)')
else:
    print('  - No IP assignments to clear')
"

echo ""

# Step 2: Simulate power cycle
echo "======================================================================"
echo "STEP 2: Simulating Server Power Cycle"
echo "======================================================================"
echo "  → Server: $SERVER"
echo "  → Location: DC-West, WEST-R01 U1"
echo "  → Initiating reboot..."
sleep 0.5
echo "  ."
sleep 0.5
echo "  .."
sleep 0.5
echo "  ..."
echo "  ✓ Server power cycled"
echo "  ✓ BMC initializing..."
echo ""

# Step 3: Get available IP
echo "======================================================================"
echo "STEP 3: DHCP - Allocating BMC IP"
echo "======================================================================"
echo "  → Site: DC-West"
echo "  → BMC Subnet: 10.22.2.0/23"
echo "  → Searching for available IP..."

BMC_IP=$(docker exec netbox python -c "
import os, sys, django, ipaddress
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from ipam.models import IPAddress

network = ipaddress.ip_network('10.22.2.0/23')
for ip in network.hosts():
    ip_str = str(ip)
    last_octet = int(ip_str.split('.')[-1])
    if last_octet < 10 or last_octet > 250:
        continue
    if not IPAddress.objects.filter(address=f'{ip_str}/24').exists():
        print(ip_str)
        break
")

echo "  ✓ Allocated IP: $BMC_IP"
echo ""

# Step 4: Get BMC MAC
echo "======================================================================"
echo "STEP 4: Publishing DHCP Lease Event"
echo "======================================================================"

BMC_MAC=$(docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface

server = Device.objects.get(name='$SERVER')
bmc = Interface.objects.get(device=server, name='bmc')
print(bmc.mac_address)
")

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo ""
echo "  Event Details:"
echo "    MAC Address: $BMC_MAC"
echo "    IP Address:  $BMC_IP"
echo "    Hostname:    $(echo $SERVER | tr '[:upper:]' '[:lower:]')"
echo "    Timestamp:   $TIMESTAMP"
echo ""

# Create DHCP lease event with NEW format
EVENT_JSON='{"event_type":"dhcp_lease","network_type":"bmc","timestamp":"'$TIMESTAMP'","mac_address":"'$BMC_MAC'","ip_address":"'$BMC_IP'","site":"dc-west","source":"simulated_dhcp_server"}'

# Push directly to Redis container
docker exec bmc-redis redis-cli LPUSH netbox:dhcp:leases "$EVENT_JSON" >/dev/null

echo "  ✓ Event published to Redis queue: netbox:dhcp:leases"
echo ""

# Step 5: Wait for discovery
echo "======================================================================"
echo "STEP 5: Waiting for NetBox Discovery"
echo "======================================================================"
echo "  → Waiting for worker to process event..."

sleep 3

echo "  ✓ Event should be processed (check worker logs)"
echo ""

# Step 6: Verify
echo "======================================================================"
echo "STEP 6: Verification"
echo "======================================================================"

docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface
from ipam.models import IPAddress

server = Device.objects.get(name='$SERVER')
bmc = Interface.objects.get(device=server, name='bmc')

state = server.custom_field_data.get('lifecycle_state', 'unknown')
print(f'\n  Lifecycle State: {state}')

ips = IPAddress.objects.filter(
    assigned_object_type__model='interface',
    assigned_object_id=bmc.id
)

if ips.exists():
    ip = ips.first()
    print(f'  BMC IP Address:  {ip.address}')
    print(f'  BMC DNS Name:    {ip.dns_name or \"N/A\"}')
    print(f'  BMC MAC Address: {bmc.mac_address}')
else:
    print('  BMC IP Address:  Not assigned yet')
    print('  (Check worker logs for processing status)')
"

echo ""
echo "======================================================================"
echo "✓ SIMULATION COMPLETED!"
echo "======================================================================"
echo ""
echo "Server $SERVER has been rebooted and rediscovered."
echo "Check NetBox UI: http://localhost:8000/dcim/devices/"
echo "Check worker logs: docker logs netbox | grep -A 20 'DHCP LEASE'"
echo "======================================================================"
