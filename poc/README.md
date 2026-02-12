# Baremetal Server Automation - Proof of Concept

Automated workflow for baremetal server discovery, validation, hardening, and monitoring.

## Overview

This PoC implements an event-driven pipeline that automates the complete lifecycle from BMC power-on through monitoring:

```
BMC Powers On → DHCP Hook → Discovery → Provisioning →
PXE Boot → Validation → Hardening → Monitoring
```

## Architecture

### Components

1. **DHCP Hook** (`scripts/dhcp_hook.sh`)
   - Captures DHCP lease events
   - Writes to append-only log file

2. **DHCP Tailer** (`services/dhcp_tailer.py`)
   - Tails DHCP event log
   - Publishes events to Redis queue

3. **Discovery Worker** (`services/discovery_worker.py`)
   - Finds devices in NetBox by MAC address
   - Assigns IP addresses
   - Transitions to 'discovered' state

4. **Provisioning Worker** (`services/provisioning_worker.py`)
   - Connects to iLO via Redfish API
   - Configures one-time PXE boot
   - Powers on/restarts server

5. **Validation Script** (`scripts/validate_server.sh`)
   - Runs in PXE-booted RHEL9 ISO
   - Collects LLDP neighbors, hardware info, interfaces
   - POSTs results to callback API

6. **Callback API** (`services/callback_api.py`)
   - Receives validation reports
   - Updates NetBox with collected data
   - Transitions to 'validated' state

7. **Hardening Worker** (`services/hardening_worker.py`)
   - Executes Ansible playbook
   - Hardens BMC security settings
   - Transitions to 'ready' state

8. **Monitoring Worker** (`services/monitoring_worker.py`)
   - Polls Redfish for metrics (CPU, memory, power, thermal)
   - Saves to JSON files
   - Updates NetBox timestamp

### Technology Stack

- **Language**: Python 3.9+
- **Event Bus**: Redis
- **APIs**: NetBox REST API, Redfish API
- **Automation**: Ansible
- **Web Framework**: Flask

### Dependencies

Minimal dependencies:
- `redis` - Event queue
- `requests` - HTTP client
- `flask` - Callback API
- `ansible` - BMC hardening

## Prerequisites

### System Requirements

- RHEL 9 or compatible Linux
- Python 3.9 or higher
- Redis server
- Ansible
- Access to:
  - NetBox instance with API token
  - HPE iLO Gen10 BMCs
  - DHCP server (ISC DHCP)

### NetBox Setup

1. Create custom fields for `dcim.device`:
   - `lifecycle_state` (selection)
   - `discovered_at` (date & time)
   - `pxe_boot_initiated_at` (date & time)
   - `hardened_at` (date & time)
   - `last_monitored_at` (date & time)
   - `last_power_watts` (integer)

2. Create lifecycle_state choices:
   - `racked`
   - `discovered`
   - `validating`
   - `validated`
   - `hardening`
   - `ready`
   - `monitored`

3. Create device in NetBox:
   - Add to "baremetal-staging" tenant
   - Create BMC interface with MAC address
   - Set `lifecycle_state` to `racked`

## Installation

### Option 1: Docker (Recommended)

**Fastest way to get started!**

```bash
cd /Users/gabe/ai/bm/poc

# Configure environment
cp .env.example .env
vi .env  # Add your NetBox URL, token, and iLO password

# Run all workers in single container
docker-compose --profile all-in-one up -d

# View logs
docker-compose logs -f
```

See [DOCKER.md](DOCKER.md) for complete Docker documentation.

### Option 2: Native Installation

### 1. Clone and Setup

```bash
# Clone repository
cd /opt
git clone <repo-url> bm
cd bm/poc

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Install and Configure Redis

```bash
# Install Redis
sudo dnf install redis

# Start Redis
sudo systemctl enable --now redis
```

### 3. Create Log Directories

```bash
sudo mkdir -p /var/log/bm/metrics
sudo chown -R $USER:$USER /var/log/bm
```

### 4. Configure Environment Variables

Create `/opt/bm/poc/.env`:

```bash
# NetBox Configuration
export NETBOX_URL="http://netbox.example.com"
export NETBOX_TOKEN="your-api-token-here"
export NETBOX_TENANT="baremetal-staging"

# Redis Configuration
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# iLO Configuration
export ILO_DEFAULT_USER="Administrator"
export ILO_DEFAULT_PASSWORD="your-ilo-password"
export ILO_VERIFY_SSL="false"

# Callback API
export CALLBACK_API_URL="http://10.1.100.5:5000"

# Paths
export LOG_DIR="/var/log/bm"
export ANSIBLE_PLAYBOOK_DIR="/opt/bm/poc/ansible"

# Monitoring
export MONITORING_INTERVAL_SECONDS="300"
```

Load environment:

```bash
source /opt/bm/poc/.env
```

### 5. Configure DHCP Server

Edit `/etc/dhcp/dhcpd.conf` and add:

```
on commit {
    set clientIP = binary-to-ascii(10, 8, ".", leased-address);
    set clientMAC = binary-to-ascii(16, 8, ":", substring(hardware, 1, 6));
    execute("/opt/bm/poc/scripts/dhcp_hook.sh", clientIP, clientMAC);
}
```

Restart DHCP:

```bash
sudo systemctl restart dhcpd
```

## Running the Services

### Manual Execution (for testing)

Start each service in a separate terminal:

```bash
# Terminal 1: DHCP Tailer
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/dhcp_tailer.py

# Terminal 2: Discovery Worker
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/discovery_worker.py

# Terminal 3: Provisioning Worker
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/provisioning_worker.py

# Terminal 4: Callback API
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/callback_api.py

# Terminal 5: Hardening Worker
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/hardening_worker.py

# Terminal 6: Monitoring Worker
source /opt/bm/poc/.env
cd /opt/bm/poc
./services/monitoring_worker.py
```

### Systemd Services (production)

Create systemd service files in `/etc/systemd/system/`:

Example: `bm-discovery.service`

```ini
[Unit]
Description=Baremetal Discovery Worker
After=network.target redis.service

[Service]
Type=simple
User=bm
WorkingDirectory=/opt/bm/poc
EnvironmentFile=/opt/bm/poc/.env
ExecStart=/opt/bm/poc/venv/bin/python3 /opt/bm/poc/services/discovery_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable bm-discovery bm-provisioning bm-callback-api bm-hardening bm-monitoring
sudo systemctl start bm-discovery bm-provisioning bm-callback-api bm-hardening bm-monitoring
```

## Testing

### 1. Test DHCP Hook

```bash
# Simulate DHCP event
/opt/bm/poc/scripts/dhcp_hook.sh 10.1.100.50 94:40:c9:5e:7a:b0

# Check log
tail /var/log/bm/dhcp_events.log
```

### 2. Test Discovery Worker

```bash
# Publish test event to Redis
redis-cli LPUSH bm:events:dhcp_lease '{"event_type":"dhcp_lease_assigned","timestamp":"2026-02-11T10:00:00Z","data":{"ip":"10.1.100.50","mac":"94:40:c9:5e:7a:b0"}}'

# Watch logs
tail -f /var/log/bm/discovery_worker.log
```

### 3. Test Callback API

```bash
curl -X POST http://localhost:5000/api/v1/validation/report \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "123",
    "timestamp": "2026-02-11T10:00:00Z",
    "hardware": {
      "manufacturer": "HPE",
      "model": "ProLiant DL360 Gen10",
      "serial": "ABC123"
    },
    "lldp": {},
    "interfaces": [
      {"name": "eno1", "mac": "aa:bb:cc:dd:ee:01"},
      {"name": "eno2", "mac": "aa:bb:cc:dd:ee:02"}
    ]
  }'
```

### 4. End-to-End Test

1. Ensure test device exists in NetBox with BMC interface and MAC
2. Power on server BMC
3. Watch logs for each service
4. Verify state transitions in NetBox:
   - `racked` → `discovered` → `validating` → `validated` → `hardening` → `ready`
5. Check metrics files: `ls -lh /var/log/bm/metrics/`

## Monitoring

### Check Service Status

```bash
# View logs
tail -f /var/log/bm/*.log

# Check Redis queues
redis-cli LLEN bm:events:dhcp_lease
redis-cli LLEN bm:events:device_discovered
redis-cli LLEN bm:events:validation_completed

# View metrics
ls -lh /var/log/bm/metrics/
cat /var/log/bm/metrics/<device-name>-<timestamp>.json | jq .
```

### Common Issues

**DHCP hook not firing**
- Check dhcpd.conf syntax: `dhcpd -t`
- Verify execute permissions: `chmod +x /opt/bm/poc/scripts/dhcp_hook.sh`
- Check dhcpd logs: `journalctl -u dhcpd -f`

**MAC not found in NetBox**
- Check error log: `tail /var/log/bm/errors.log`
- Verify MAC address in NetBox interface
- Check NetBox API connectivity

**iLO connection fails**
- Verify IP reachability: `ping <ilo-ip>`
- Test credentials manually: `curl -k -u user:pass https://<ilo-ip>/redfish/v1/Systems/1`
- Check ILO_DEFAULT_PASSWORD environment variable

**Ansible playbook fails**
- Test Ansible manually: `ansible-playbook -i <ip>, ansible/bmc_hardening.yml`
- Check Ansible is installed: `ansible-playbook --version`
- Verify playbook path in config.py

## Project Structure

```
poc/
├── config.py                   # Central configuration
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── lib/                        # Shared libraries
│   ├── __init__.py
│   ├── logger.py              # JSON logging
│   ├── queue.py               # Redis queue wrapper
│   ├── netbox_client.py       # NetBox API client
│   └── redfish_client.py      # Redfish API client
├── scripts/                    # Shell scripts
│   ├── dhcp_hook.sh           # DHCP event capture
│   └── validate_server.sh     # PXE boot validation
├── services/                   # Python workers
│   ├── dhcp_tailer.py         # DHCP log tailer
│   ├── discovery_worker.py    # Device discovery
│   ├── provisioning_worker.py # PXE boot trigger
│   ├── callback_api.py        # Validation callback API
│   ├── hardening_worker.py    # BMC hardening
│   └── monitoring_worker.py   # Metrics collection
└── ansible/                    # Ansible playbooks
    └── bmc_hardening.yml      # BMC security hardening
```

## Next Steps

After validating the PoC:

1. **Replace Redis with Kafka** - For production durability and scale
2. **Add Temporal.io** - For workflow orchestration
3. **Integrate Prometheus** - Replace JSON files with proper metrics
4. **Add Grafana** - Visualize metrics and state
5. **Build Custom ISO** - Create RHEL9 validation ISO with scripts
6. **Add More Vendors** - Support Dell OpenManage
7. **Enhance Error Handling** - Add retry logic and dead letter queues
8. **Add Web UI** - Dashboard for ops team

## Contributing

This is a proof of concept. Feedback and improvements welcome!

## License

Internal use only.

---

**Version**: 1.0
**Last Updated**: 2026-02-11
**Status**: Proof of Concept
