# NetBox BMC Discovery Automation

Event-driven automation for detecting baremetal servers when their BMCs request DHCP leases and automatically updating their lifecycle state in NetBox.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────┐     ┌────────────────┐     ┌─────────┐
│   Physical  │────▶│ DHCP Server  │────▶│   Redis   │────▶│  BMC Worker    │────▶│ NetBox  │
│   Server    │     │  (ISC DHCP)  │     │  (Queue)  │     │   (Python)     │     │ (DCIM)  │
│     BMC     │     │              │     │           │     │                │     │         │
└─────────────┘     └──────────────┘     └───────────┘     └────────────────┘     └─────────┘
      │                    │                    │                   │                    │
      │ 1. DHCP Request    │                    │                   │                    │
      │───────────────────▶│                    │                   │                    │
      │                    │ 2. Lease Granted   │                   │                    │
      │◀───────────────────│                    │                   │                    │
      │                    │ 3. Push Event      │                   │                    │
      │                    │───────────────────▶│                   │                    │
      │                    │                    │ 4. Consume Event  │                    │
      │                    │                    │──────────────────▶│                    │
      │                    │                    │                   │ 5. Query by MAC    │
      │                    │                    │                   │───────────────────▶│
      │                    │                    │                   │                    │
      │                    │                    │                   │ 6. Update State    │
      │                    │                    │                   │───────────────────▶│
      │                    │                    │                   │   offline→discovered│
```

## Workflow

1. **Physical Server Powers On** - BMC requests DHCP lease from network
2. **DHCP Server Grants Lease** - Executes hook script with MAC address and IP
3. **Hook Publishes to Redis** - Event pushed to Redis queue with lease details
4. **Worker Consumes Event** - Python worker picks up event from Redis
5. **NetBox Lookup** - Worker queries NetBox for device with matching BMC MAC
6. **State Transition** - Device lifecycle state updated: `offline` → `discovered`
7. **IP Assignment** - BMC IP address assigned to interface in NetBox

## Lifecycle State Transitions

```
┌──────────┐  BMC DHCP   ┌────────────┐  Config    ┌──────────────┐  Validation  ┌────────┐
│ offline  │────────────▶│ discovered │──────────▶ │ provisioning │─────────────▶│ ready  │
└──────────┘             └────────────┘            └──────────────┘              └────────┘
                                                                                       │
                                                                                       │ Assign
                                                                                       ▼
                                                                                  ┌────────┐
                                                                                  │ active │
                                                                                  └────────┘
```

- **offline** - Server exists in NetBox but hasn't been detected on network
- **discovered** - BMC detected via DHCP, server is online and reachable
- **provisioning** - Server being configured (firmware, BIOS, hardening)
- **ready** - Server fully configured and ready for tenant assignment
- **active** - Server assigned to tenant and in production use

## New: Journal Logging

**All NetBox updates now include journal entries for complete audit trail!**

Every action performed by the workers is logged in the device's journal:
- 📝 Discovery events (BMC/Management network detection)
- 🔄 State transitions (offline → discovered → provisioning)
- 🌐 IP address assignments
- ⚠️  Warnings and errors

**See:** `PHASE1-GUIDE.md` for complete documentation on journal logging feature.

## Components

### 1. DHCP Lease Hook (`dhcp-lease-hook.sh`)

Bash script executed by ISC DHCP server on lease commit. Detects BMC MAC addresses (HPE, Dell OUIs) and publishes events to Redis.

**Features:**
- Filters for known BMC OUI prefixes (A0:36:9F for HPE, D0:67:E5 for Dell, etc.)
- Creates JSON event payload
- Publishes to Redis queue
- Logs all actions

### 2. NetBox BMC Worker (`netbox-bmc-worker.py`)

Python service that consumes events from Redis and updates NetBox.

**Features:**
- Blocking consumer using Redis BRPOP
- Looks up devices by BMC MAC address
- Updates lifecycle state with proper transitions
- Assigns IP addresses to BMC interfaces
- **Comprehensive journal logging in NetBox for audit trail**
- **All changes logged with timestamps and descriptions**
- Comprehensive error handling and logging
- Graceful shutdown on SIGTERM/SIGINT

### 3. Redis (Message Queue)

Acts as the message broker between DHCP and NetBox systems.

**Queue:** `netbox:bmc:discovered`

## Installation

### Prerequisites

- NetBox 3.7.3+ with 600 servers populated (see main README)
- ISC DHCP server or dnsmasq
- Redis 5.0+
- Python 3.11+
- redis-cli

### Option 1: Docker Compose (Recommended for Testing)

```bash
# Install Redis and start worker
cd dhcp-integration
docker-compose up -d

# Check logs
docker-compose logs -f bmc-worker
```

### Option 2: System Service

```bash
# Install Redis
sudo apt-get install redis-server

# Install Python dependencies
pip3 install -r requirements.txt

# Copy worker to system location
sudo mkdir -p /opt/netbox-bmc-worker
sudo cp netbox-bmc-worker.py /opt/netbox-bmc-worker/
sudo chmod +x /opt/netbox-bmc-worker/netbox-bmc-worker.py

# Install systemd service
sudo cp netbox-bmc-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable netbox-bmc-worker
sudo systemctl start netbox-bmc-worker

# Check status
sudo systemctl status netbox-bmc-worker
sudo journalctl -u netbox-bmc-worker -f
```

### Configure DHCP Server

#### ISC DHCP (`/etc/dhcp/dhcpd.conf`)

```conf
# BMC Management Subnet
subnet 10.0.100.0 netmask 255.255.255.0 {
    range 10.0.100.10 10.0.100.250;
    option routers 10.0.100.1;
    option domain-name-servers 8.8.8.8, 8.8.4.4;

    # DHCP lease hook
    on commit {
        set ClientIP = binary-to-ascii(10, 8, ".", leased-address);
        set ClientMac = binary-to-ascii(16, 8, ":", substring(hardware, 1, 6));
        set ClientHost = pick-first-value(option host-name, "unknown");
        execute("/usr/local/bin/dhcp-lease-hook.sh", ClientIP, ClientMac, ClientHost);
    }
}
```

```bash
# Install hook script
sudo cp dhcp-lease-hook.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/dhcp-lease-hook.sh

# Configure environment
sudo tee /etc/default/dhcp-lease-hook <<EOF
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_QUEUE=netbox:bmc:discovered
LOG_FILE=/var/log/dhcp-lease-hook.log
EOF

# Restart DHCP server
sudo systemctl restart isc-dhcp-server
```

## Testing

### Phase 1: Automated Testing

For a complete Phase 1 test (initial racking and power-on), see **`PHASE1-GUIDE.md`**:

```bash
# Setup test device
docker cp setup-phase1-device.py netbox:/tmp/
docker exec netbox python /tmp/setup-phase1-device.py

# Run automated Phase 1 test
./test-phase1.sh
```

This will test the complete workflow with journal logging verification.

### Manual Testing

### 1. Start the Worker

```bash
# Docker
docker-compose up -d
docker-compose logs -f bmc-worker

# Or systemd
sudo systemctl start netbox-bmc-worker
sudo journalctl -u netbox-bmc-worker -f
```

### 2. Simulate BMC Discovery

Get a BMC MAC address from one of your offline servers:

```bash
# Query NetBox for an offline server's BMC MAC
curl -s "http://localhost:8000/api/dcim/interfaces/?device=EAST-SRV-001&name=bmc" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].mac_address'
```

Example output: `A0:36:9F:01:00:00`

### 3. Send Test Event

```bash
# Make script executable
chmod +x test-bmc-discovery.sh

# Send test event with the BMC MAC
./test-bmc-discovery.sh A0:36:9F:01:00:00 10.0.100.50
```

### 4. Verify State Change

Check the worker logs - you should see:

```
Processing event: bmc_dhcp_lease
Found device: EAST-SRV-001 (ID: 123)
Device EAST-SRV-001 current state: offline
✓ State transition: EAST-SRV-001 offline → discovered
✓ Successfully processed BMC discovery for EAST-SRV-001
```

Verify in NetBox:

```bash
curl -s "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.results[0].custom_fields.lifecycle_state'
```

Expected output: `"discovered"`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_QUEUE` | `netbox:bmc:discovered` | Redis queue name |
| `NETBOX_URL` | `http://localhost:8000` | NetBox API URL |
| `NETBOX_TOKEN` | *(required)* | NetBox API authentication token |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Supported BMC OUIs

The DHCP hook script recognizes these OUI prefixes as BMCs:

- **A0:36:9F** - HPE iLO
- **D0:67:E5** - Dell iDRAC
- **14:18:77** - Dell iDRAC (alternate)
- **18:FB:7B** - Supermicro IPMI

Add more OUIs in `dhcp-lease-hook.sh`:

```bash
BMC_OUIS=("A0:36:9F" "D0:67:E5" "14:18:77" "18:FB:7B" "YOUR:OUI:HERE")
```

## Monitoring

### Check Queue Depth

```bash
redis-cli LLEN netbox:bmc:discovered
```

### View Pending Events

```bash
redis-cli LRANGE netbox:bmc:discovered 0 -1
```

### Worker Logs

```bash
# Docker
docker-compose logs -f bmc-worker

# Systemd
sudo journalctl -u netbox-bmc-worker -f

# Log file
tail -f /var/log/netbox-bmc-worker.log
```

### DHCP Hook Logs

```bash
tail -f /var/log/dhcp-lease-hook.log
```

## Troubleshooting

### Worker Not Processing Events

**Check Redis Connection:**
```bash
redis-cli ping
# Should return: PONG
```

**Check Queue:**
```bash
redis-cli LLEN netbox:bmc:discovered
# Should return: number of pending events
```

**Check Worker Status:**
```bash
docker-compose ps
# or
sudo systemctl status netbox-bmc-worker
```

### Device Not Found in NetBox

**Verify MAC Address:**
```bash
curl -s "http://localhost:8000/api/dcim/interfaces/?mac_address=A0:36:9F:01:00:00&name=bmc" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.count'
```

Should return `1`. If `0`, the MAC doesn't exist in NetBox.

### DHCP Hook Not Firing

**Check DHCP Server Logs:**
```bash
sudo journalctl -u isc-dhcp-server -f
```

**Test Hook Manually:**
```bash
sudo /usr/local/bin/dhcp-lease-hook.sh 10.0.100.50 A0:36:9F:01:00:00 test-host
cat /var/log/dhcp-lease-hook.log
```

### State Not Changing

**Check Current State:**
```bash
curl -s "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.results[0].custom_fields.lifecycle_state'
```

**Check Worker Logs for Errors:**
```bash
docker-compose logs bmc-worker | grep ERROR
```

## Integration Points

### Next Steps in Automation

After a server transitions to `discovered`, trigger additional automation:

1. **Hardware Validation** - PXE boot validation image to check LLDP connectivity
2. **Firmware Updates** - Push to HPE OneView or Dell OpenManage for firmware
3. **BIOS Configuration** - Apply hardening profiles via Ansible
4. **Provisioning** - Deploy to Canonical MaaS for OS installation
5. **Monitoring** - Add to Prometheus for hardware monitoring
6. **Ticketing** - Create Jira ticket for datacenter tech to verify physical installation

### Additional Redis Queues

Create additional queues for other lifecycle events:

- `netbox:server:validated` - Hardware validation complete
- `netbox:server:provisioned` - Firmware and config complete
- `netbox:server:ready` - Ready for tenant assignment
- `netbox:server:failure` - Hardware failure detected

## Security Considerations

1. **NetBox API Token** - Use a dedicated service account with minimal permissions
2. **Redis Authentication** - Enable Redis AUTH in production
3. **Network Segmentation** - Isolate BMC network from production networks
4. **DHCP Security** - Use DHCP snooping and MAC address filtering
5. **Log Retention** - Rotate and archive logs for audit trail

## Performance

**Expected Throughput:**
- ~100-200 events/second per worker
- Sub-second latency from DHCP lease to NetBox update
- Horizontal scaling: Run multiple workers for higher throughput

**Resource Usage:**
- Worker: ~50MB RAM, <5% CPU
- Redis: ~10MB RAM per 10K queued events

## License

This automation is part of the NetBox baremetal hosting integration project.

---

**Author:** Claude
**Version:** 1.0
**Last Updated:** 2026-02-13
