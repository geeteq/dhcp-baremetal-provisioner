#!/bin/bash
# Clean server reboot simulation for WEST-SRV-201

SERVER="${1:-WEST-SRV-201}"

echo "======================================================================"
echo "SERVER REBOOT SIMULATION: $SERVER"
echo "======================================================================"

# Clear BMC IP
echo ""
echo "[1/5] Clearing BMC IP..."
docker exec netbox python /tmp/assign-ip-to-srv-201.py 2>&1 | grep -v "🧬" | grep -v "loaded config" || true

docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ['DJANGO_SETTINGS_MODULE'] = 'netbox.settings'
django.setup()
from dcim.models import Device, Interface
from ipam.models import IPAddress
server = Device.objects.get(name='$SERVER')
bmc = Interface.objects.get(device=server, name='bmc')
ips = IPAddress.objects.filter(assigned_object_type__model='interface', assigned_object_id=bmc.id)
for ip in ips: ip.delete()
print('✓ BMC IP cleared')
" 2>&1 | grep -v "🧬" | grep -v "loaded config"

# Power cycle
echo "[2/5] Power cycling server..."
sleep 1
echo "✓ Server rebooted"

# Get details
echo "[3/5] Getting server details..."
BMC_MAC=$(docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ['DJANGO_SETTINGS_MODULE'] = 'netbox.settings'
django.setup()
from dcim.models import Device, Interface
server = Device.objects.get(name='$SERVER')
bmc = Interface.objects.get(device=server, name='bmc')
print(bmc.mac_address, end='')
" 2>/dev/null)

BMC_IP=$(docker exec netbox python -c "
import os, sys, django, ipaddress
sys.path.insert(0, '/opt/netbox/netbox')
os.environ['DJANGO_SETTINGS_MODULE'] = 'netbox.settings'
django.setup()
from ipam.models import IPAddress
network = ipaddress.ip_network('10.22.2.0/23')
for ip in network.hosts():
    ip_str = str(ip)
    if int(ip_str.split('.')[-1]) < 10: continue
    if not IPAddress.objects.filter(address=f'{ip_str}/24').exists():
        print(ip_str, end='')
        break
" 2>/dev/null)

echo "  MAC: $BMC_MAC"
echo "  IP:  $BMC_IP"

# Send DHCP event
echo "[4/5] Sending DHCP lease event..."
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EVENT='{"event_type":"bmc_dhcp_lease","timestamp":"'$TIMESTAMP'","mac_address":"'$BMC_MAC'","ip_address":"'$BMC_IP'","hostname":"west-srv-201","source":"dhcp"}'

cd /Users/gabe/ai/bm/poc/dhcp-integration
echo "$EVENT" | docker-compose exec -T redis redis-cli LPUSH netbox:bmc:discovered "$EVENT" >/dev/null 2>&1

echo "✓ Event published"

# Wait
echo "[5/5] Waiting for discovery..."
sleep 3

# Verify
STATE=$(docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ['DJANGO_SETTINGS_MODULE'] = 'netbox.settings'
django.setup()
from dcim.models import Device
server = Device.objects.get(name='$SERVER')
print(server.custom_field_data.get('lifecycle_state', 'unknown'), end='')
" 2>/dev/null)

echo "✓ State: $STATE"

echo ""
echo "======================================================================"
echo "✓ DONE - Check: docker-compose logs bmc-worker | tail -20"
echo "======================================================================"
