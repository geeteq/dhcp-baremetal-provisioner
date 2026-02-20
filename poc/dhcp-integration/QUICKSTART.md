# Quick Start: BMC Discovery Testing

Test the complete BMC discovery workflow in under 5 minutes!

## Prerequisites

- NetBox running with 600 servers populated (all in "offline" state)
- Docker and docker-compose installed
- Redis-cli installed (`apt-get install redis-tools` or `brew install redis`)

## Step 1: Add Lifecycle States to NetBox

First, add the new lifecycle states (discovered, provisioning, ready) to NetBox:

```bash
cd /Users/gabe/ai/bm/poc/dhcp-integration

# Copy script to NetBox container and run
docker cp add-lifecycle-states.py netbox:/tmp/
docker exec netbox python /tmp/add-lifecycle-states.py
```

Expected output:
```
✓ LIFECYCLE STATES CONFIGURED!

Complete lifecycle workflow (8 states):
  - offline: Offline
  - discovered: Discovered
  - provisioning: Provisioning
  - ready: Ready
  - active: Active
  - maintenance: Maintenance
  - decommissioned: Decommissioned
  - failed: Failed
```

## Step 2: Start Redis and BMC Worker

```bash
# Start Redis and BMC worker with docker-compose
docker-compose up -d

# Watch the logs
docker-compose logs -f bmc-worker
```

You should see:
```
NetBox BMC Discovery Worker Started
======================================================================
Redis: redis:6379
Queue: netbox:bmc:discovered
NetBox: http://host.docker.internal:8000
Waiting for BMC discovery events...
```

## Step 3: Get a Test Server's BMC MAC Address

Open a new terminal and query NetBox for a server's BMC MAC:

```bash
curl -s "http://localhost:8000/api/dcim/interfaces/?device=EAST-SRV-001&name=bmc" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].mac_address'
```

Example output: `A0:36:9F:01:00:00`

Verify the server is currently offline:

```bash
curl -s "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].custom_fields.lifecycle_state'
```

Should return: `offline`

## Step 4: Simulate BMC DHCP Lease Event

Send a test event to simulate the BMC requesting a DHCP lease:

```bash
./test-bmc-discovery.sh A0:36:9F:01:00:00 10.0.100.50
```

Expected output:
```
╔══════════════════════════════════════════════════════════════════╗
║          Testing BMC Discovery Event                            ║
╚══════════════════════════════════════════════════════════════════╝

Redis:       localhost:6379
Queue:       netbox:bmc:discovered
MAC Address: A0:36:9F:01:00:00
IP Address:  10.0.100.50
Hostname:    test-bmc

Event payload:
{
  "event_type": "bmc_dhcp_lease",
  "timestamp": "2026-02-13T10:30:00Z",
  "mac_address": "A0:36:9F:01:00:00",
  "ip_address": "10.0.100.50",
  "hostname": "test-bmc",
  "source": "test_script"
}

✓ Event pushed successfully!
```

## Step 5: Verify Worker Processed the Event

Switch back to the worker logs terminal. You should see:

```
----------------------------------------------------------------------
Processing event: bmc_dhcp_lease
Searching for device with BMC MAC: A0:36:9F:01:00:00
Found device: EAST-SRV-001 (ID: 123)
Device EAST-SRV-001 current state: offline
Updating device 123 to state: discovered
Device 123 state updated to: discovered
✓ State transition: EAST-SRV-001 offline → discovered
Assigning IP 10.0.100.50 to interface 456
IP 10.0.100.50 assigned to interface 456
✓ Successfully processed BMC discovery for EAST-SRV-001
Event processed successfully
----------------------------------------------------------------------
```

## Step 6: Verify State Change in NetBox

Check the server's new state:

```bash
curl -s "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].custom_fields.lifecycle_state'
```

Should now return: `discovered` ✓

Check the BMC interface now has an IP address:

```bash
curl -s "http://localhost:8000/api/dcim/interfaces/?device=EAST-SRV-001&name=bmc" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].assigned_object.address'
```

Should return: `10.0.100.50/24` ✓

## Step 7: Test Multiple Servers

Test the workflow with multiple servers at once:

```bash
# Get BMC MACs for first 5 servers in East datacenter
for i in {1..5}; do
  SERVER=$(printf "EAST-SRV-%03d" $i)
  MAC=$(curl -s "http://localhost:8000/api/dcim/interfaces/?device=$SERVER&name=bmc" \
    -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
    | jq -r '.results[0].mac_address')
  IP="10.0.100.$((50 + i))"

  echo "Discovering: $SERVER (MAC: $MAC, IP: $IP)"
  ./test-bmc-discovery.sh "$MAC" "$IP"
  sleep 1
done
```

Watch the worker logs process all 5 events!

## Step 8: View All Discovered Servers

Query NetBox for all servers that have been discovered:

```bash
curl -s "http://localhost:8000/api/dcim/devices/?cf_lifecycle_state=discovered" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.count'
```

Should show the number of discovered servers.

View the list:

```bash
curl -s "http://localhost:8000/api/dcim/devices/?cf_lifecycle_state=discovered&limit=10" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[] | "\(.name) - \(.custom_fields.lifecycle_state)"'
```

## Success! 🎉

You've successfully tested the complete BMC discovery automation:

✅ DHCP lease event simulated
✅ Event published to Redis queue
✅ Worker consumed and processed event
✅ Device found in NetBox by BMC MAC address
✅ Lifecycle state transitioned: offline → discovered
✅ IP address assigned to BMC interface

## Next Steps

### 1. Connect Real DHCP Server

Configure your ISC DHCP server to use the hook script (see main README.md).

### 2. Add More Automation

Create additional workers for next lifecycle stages:
- **Hardware validation worker** - Transitions discovered → provisioning
- **Firmware update worker** - Applies updates via vendor tools
- **Configuration worker** - Runs Ansible hardening playbooks
- **Readiness worker** - Transitions provisioning → ready

### 3. Monitor in Production

```bash
# Watch queue depth
watch -n 1 'redis-cli LLEN netbox:bmc:discovered'

# Monitor worker performance
docker-compose logs -f bmc-worker | grep "processed successfully"
```

### 4. Scale Horizontally

Run multiple workers for higher throughput:

```bash
docker-compose up -d --scale bmc-worker=3
```

## Troubleshooting

### Event Not Processing

**Check queue depth:**
```bash
redis-cli LLEN netbox:bmc:discovered
```

If > 0, events are queued but not being processed. Check worker logs.

**Manually inspect event:**
```bash
redis-cli LRANGE netbox:bmc:discovered 0 0 | jq '.'
```

### Device Not Found

**Verify MAC exists in NetBox:**
```bash
curl -s "http://localhost:8000/api/dcim/interfaces/?mac_address=A0:36:9F:01:00:00" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.count'
```

Should return 1. If 0, the MAC address doesn't exist in NetBox.

### Worker Not Starting

**Check Docker logs:**
```bash
docker-compose logs bmc-worker
```

**Check Redis connectivity:**
```bash
docker-compose exec bmc-worker redis-cli -h redis ping
```

Should return: `PONG`

## Clean Up

Reset servers back to offline state:

```bash
docker exec netbox python /tmp/populate_netbox_sample_data.py
```

This will repopulate NetBox with all 600 servers in "offline" state.

---

**Ready for production?** See the main README.md for full deployment instructions!
