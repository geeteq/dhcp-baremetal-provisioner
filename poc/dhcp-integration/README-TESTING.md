# DHCP Integration Testing

## Overview
Event-driven DHCP integration for NetBox using Redis as the ESB (Enterprise Service Bus).

## Architecture
```
┌─────────────────┐         ┌─────────────┐         ┌──────────────────┐
│  DHCP Service   │────────▶│    Redis    │────────▶│  Worker Process  │
│  (Simulator)    │         │  (ESB Queue)│         │  (NetBox Update) │
└─────────────────┘         └─────────────┘         └──────────────────┘
     │                                                         │
     │                                                         │
     ▼                                                         ▼
 Publishes                                              Consumes + Updates
 Events Only                                            NetBox Database
```

**Key Principles:**
- ✅ Complete decoupling between services
- ✅ All communication flows through Redis message queue
- ✅ DHCP service has NO direct NetBox access
- ✅ Worker has NO direct DHCP service access
- ✅ Asynchronous event processing

## Scripts

### 1. reset-server-state.py
Resets a server to offline state and clears DHCP-assigned IPs.

**Usage:**
```bash
# Reset with IP clearing (default)
docker exec netbox python /tmp/reset-server-state.py EAST-SRV-001

# Reset but keep IP
docker exec netbox python /tmp/reset-server-state.py EAST-SRV-001 --keep-ip
```

**What it does:**
- Sets lifecycle_state to 'offline'
- Removes DHCP-assigned management IPs (unless --keep-ip)
- Prepares server for DHCP simulation

### 2. dummy-dhcp-service.py
Simulates a DHCP server that allocates IPs and publishes events to Redis.

**Usage:**
```bash
python dummy-dhcp-service.py <MAC_ADDRESS> <SITE>

# Examples
python dummy-dhcp-service.py A0:36:9F:2B:07:00 dc-east
python dummy-dhcp-service.py A0:36:9F:6A:08:00 dc-west
```

**What it does:**
- Allocates random IP from site's management pool
- Publishes DHCP lease event to Redis queue: `netbox:dhcp:leases`
- NO direct NetBox access (ESB pattern)

**IP Allocation by Site:**
- dc-east: 10.23.0.0/23 (10.23.0.10 - 10.23.1.250)
- dc-west: 10.23.2.0/23 (10.23.2.10 - 10.23.3.250)
- dc-center: 10.23.4.0/23 (10.23.4.10 - 10.23.5.250)

### 3. dhcp-lease-worker.py
Worker that consumes DHCP events from Redis and updates NetBox.

**Usage:**
```bash
# Copy to container
docker cp dhcp-lease-worker.py netbox:/tmp/

# Start worker (runs in foreground)
docker exec netbox python /tmp/dhcp-lease-worker.py

# Start worker (background)
docker exec -d netbox python /tmp/dhcp-lease-worker.py
```

**What it does:**
- Connects to Redis and listens on queue: `netbox:dhcp:leases`
- Finds device by MAC address
- Assigns IP to management interface (mgmt0)
- Updates lifecycle state: offline → provisioning
- Only talks to Redis (consume) and NetBox (update)

### 4. test-dhcp-lifecycle.py
Comprehensive unit test for the complete DHCP lifecycle workflow.

**Usage:**
```bash
python test-dhcp-lifecycle.py <SERVER_NAME> <SITE>

# Examples
python test-dhcp-lifecycle.py EAST-SRV-001 dc-east
python test-dhcp-lifecycle.py WEST-SRV-050 dc-west
python test-dhcp-lifecycle.py CENTER-SRV-100 dc-center
```

**Test Coverage:**
1. ✅ Reset server to offline state
2. ✅ Retrieve management interface MAC
3. ✅ Simulate DHCP request
4. ✅ Verify worker processes event
5. ✅ Verify IP assignment (correct IP, description)
6. ✅ Verify state transition (offline → provisioning)

**Example Output:**
```
======================================================================
✓ ALL TESTS PASSED
======================================================================

The DHCP lifecycle workflow is functioning correctly:
  • Server reset to offline state
  • DHCP request simulated successfully
  • Worker processed event from Redis
  • IP assigned: 10.23.0.13/24
  • State transitioned: offline → provisioning
======================================================================
```

## Prerequisites

### Docker Network Setup
The NetBox container must be connected to the dhcp-integration network:

```bash
# Check current networks
docker network ls

# Connect NetBox to dhcp-integration network
docker network connect dhcp-integration_default netbox

# Verify connection
docker inspect netbox | grep -A 20 Networks
```

### Python Dependencies
```bash
# On host machine (for scripts)
pip3 install redis

# Redis library already available in NetBox container
```

### Running Services
```bash
# Check Redis is running
docker ps | grep redis

# Should see:
# - bmc-redis (dhcp-integration_default network)
# - netbox-redis (netbox_network)
# - netbox-redis-cache (netbox_network)

# Check NetBox is running
docker ps | grep netbox
```

## Event Format

**DHCP Lease Event:**
```json
{
  "event_type": "dhcp_lease",
  "network_type": "management",
  "mac_address": "A0:36:9F:2B:07:00",
  "ip_address": "10.23.0.194",
  "site": "dc-east",
  "timestamp": "2026-02-13T07:40:37.928309Z",
  "source": "dummy_dhcp_service"
}
```

**Redis Queue:** `netbox:dhcp:leases`

## Lifecycle States

**State Machine:**
```
offline ────▶ discovered ────▶ provisioning ────▶ ready ────▶ active
   ▲              │                                              │
   │              │                                              │
   └──────────────┴──────────────────────────────────────────────┘
                        (decommissioned/rebooted)
```

**State Transitions via DHCP:**
- BMC network lease → offline → discovered
- Management network lease → offline/discovered → provisioning

## Testing Workflow

### Complete Test Run
```bash
# 1. Ensure worker is running
docker exec -d netbox python /tmp/dhcp-lease-worker.py

# 2. Run unit test for East DC
python test-dhcp-lifecycle.py EAST-SRV-001 dc-east

# 3. Run unit test for West DC
python test-dhcp-lifecycle.py WEST-SRV-050 dc-west

# 4. Run unit test for Center DC
python test-dhcp-lifecycle.py CENTER-SRV-100 dc-center
```

### Manual Testing
```bash
# 1. Reset server
docker exec netbox python /tmp/reset-server-state.py EAST-SRV-001

# 2. Get server MAC
docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device, Interface
server = Device.objects.get(name='EAST-SRV-001')
mgmt = Interface.objects.get(device=server, name='mgmt0')
print(mgmt.mac_address)
" 2>/dev/null

# 3. Simulate DHCP request
python dummy-dhcp-service.py A0:36:9F:2B:07:00 dc-east

# 4. Verify result (wait 2-3 seconds)
docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device, Interface
from ipam.models import IPAddress
server = Device.objects.get(name='EAST-SRV-001')
mgmt = Interface.objects.get(device=server, name='mgmt0')
ips = IPAddress.objects.filter(
    assigned_object_type__model='interface',
    assigned_object_id=mgmt.id
)
print(f'State: {server.custom_field_data.get(\"lifecycle_state\")}')
if ips.exists():
    print(f'IP: {ips.first().address}')
" 2>/dev/null
```

## Test Results

### East DC Test (EAST-SRV-001)
- ✅ Reset to offline
- ✅ MAC: A0:36:9F:2B:07:00
- ✅ Allocated IP: 10.23.0.13/24
- ✅ State transition: offline → provisioning
- ✅ All tests passed

### West DC Test (WEST-SRV-050)
- ✅ Reset to offline (from discovered)
- ✅ MAC: A0:36:9F:6A:08:00
- ✅ Allocated IP: 10.23.2.54/24
- ✅ State transition: offline → provisioning
- ✅ All tests passed

## Troubleshooting

### Worker Not Processing Events
```bash
# Check if worker is running
docker exec netbox ps aux | grep dhcp-lease-worker

# Check Redis connectivity from NetBox container
docker exec netbox python -c "
import redis
try:
    client = redis.Redis(host='bmc-redis', port=6379)
    client.ping()
    print('✓ Connected to Redis')
except Exception as e:
    print(f'✗ Connection failed: {e}')
"

# Check worker logs
docker logs netbox | tail -50
```

### IP Not Assigned
```bash
# Check if IP exists in NetBox
docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from ipam.models import IPAddress
ip = IPAddress.objects.filter(address='10.23.0.194/24')
if ip.exists():
    print(f'IP exists: {ip.first()}')
    print(f'Assigned to: {ip.first().assigned_object}')
else:
    print('IP not found')
" 2>/dev/null

# Check Redis queue
docker exec bmc-redis redis-cli LLEN netbox:dhcp:leases
```

### State Not Changing
```bash
# Verify current state
docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device
server = Device.objects.get(name='EAST-SRV-001')
print(f'State: {server.custom_field_data.get(\"lifecycle_state\", \"unknown\")}')
" 2>/dev/null

# Check if lifecycle_state custom field exists
docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from extras.models import CustomField
cf = CustomField.objects.filter(name='lifecycle_state')
print(f'Custom field exists: {cf.exists()}')
" 2>/dev/null
```

## Next Steps

1. **BMC Network Discovery**: Add BMC DHCP workflow (network_type: "bmc")
2. **Multiple Workers**: Run multiple worker instances for redundancy
3. **Event Replay**: Add dead-letter queue for failed events
4. **Monitoring**: Add Prometheus metrics for event processing
5. **Real DHCP Integration**: Replace dummy service with real DHCP hooks
6. **State Validation**: Add pre-condition checks for state transitions
7. **Rollback**: Add ability to rollback failed state transitions

## Files

```
dhcp-integration/
├── README-TESTING.md          # This file
├── reset-server-state.py      # Reset server to offline
├── dummy-dhcp-service.py      # DHCP service simulator
├── dhcp-lease-worker.py       # Event processor
└── test-dhcp-lifecycle.py     # Unit test suite
```
