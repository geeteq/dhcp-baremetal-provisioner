# Phase 1 Testing Guide - BMC Discovery with Journal Logging

## Overview

This guide covers Phase 1 of the baremetal server lifecycle automation: **Initial Racking and Power-On**. The system automatically detects when a server's BMC requests a DHCP lease and updates NetBox accordingly, with full audit trail through journal entries.

## What's New: Journal Logging

All NetBox updates now include **journal entries** for complete audit trail. Every change made by the automation system is logged in the device's journal with:

- **Timestamp** - When the change occurred
- **Action** - What was changed (state transition, IP assignment, discovery event)
- **Kind** - Success (green), Info (blue), Warning (yellow), or Danger (red)
- **Comments** - Detailed description of the change

### Journal Entry Types

| Kind | When Used | Example |
|------|-----------|---------|
| `success` | State transitions, successful discovery | "Lifecycle state changed: offline → discovered" |
| `info` | IP assignments, configuration updates | "IP address 10.22.4.202 assigned to interface bmc" |
| `warning` | Unexpected conditions, non-critical issues | "BMC discovery attempted but device in unexpected state" |
| `danger` | Errors, failures | "ERROR: Failed to assign IP address" |

## Phase 1 Test Scenario

As specified in `PHASES.md`:

**Initial State:**
- Server is physically racked and powered on
- Connected to management switch (BMC port)
- Device exists in NetBox in `offline` state
- No IP addresses assigned

**Test Case:**
- **Device Name:** CENT-SRV-035
- **BMC MAC Address:** A0:36:9F:77:05:00
- **Expected IP:** 10.22.4.202
- **State Transition:** offline → discovered

**Expected Behavior:**
1. BMC requests DHCP lease when server powers on
2. DHCP hook detects BMC OUI and publishes event to Redis
3. NetBox worker processes event:
   - Finds device by BMC MAC address
   - **Logs discovery event to journal**
   - Assigns IP 10.22.4.202 to BMC interface
   - **Logs IP assignment to journal**
   - Transitions state: offline → discovered
   - **Logs state change to journal**
4. All actions recorded in device journal for audit trail

## Setup Instructions

### Step 1: Ensure Infrastructure is Running

```bash
cd dhcp-integration

# Start Redis and NetBox BMC worker
docker-compose up -d

# Verify services are running
docker-compose ps

# Check worker is ready
docker-compose logs bmc-worker | tail -20
```

You should see:
```
NetBox BMC Discovery Worker Started
Waiting for BMC discovery events...
```

### Step 2: Create Phase 1 Test Device

Run the setup script to create/configure CENT-SRV-035:

```bash
# Copy setup script to NetBox container
docker cp setup-phase1-device.py netbox:/tmp/

# Run setup
docker exec netbox python /tmp/setup-phase1-device.py
```

**Output:**
```
PHASE 1 DEVICE SETUP
====================================================================
[1/6] Getting site...
  ✓ Using site: DC-Central
[2/6] Getting device role...
  ✓ Using role: Server
[3/6] Getting device type...
  ✓ Using device type: DL360 Gen10
[4/6] Creating/updating device: CENT-SRV-035...
  ✓ Device created: CENT-SRV-035
[5/6] Creating BMC interface...
  ✓ BMC interface created: A0:36:9F:77:05:00
[6/6] Creating management interface...
  ✓ Management interface created

SETUP COMPLETE
Device Configuration:
  Name:           CENT-SRV-035
  Lifecycle State: offline

Interfaces:
  BMC (bmc):      A0:36:9F:77:05:00
  Management (mgmt0): A0:36:9F:77:05:01
```

### Step 3: Run Phase 1 Test

Execute the automated test:

```bash
./test-phase1.sh
```

The script will:
1. ✓ Verify device exists in NetBox
2. ✓ Verify BMC interface with correct MAC
3. ✓ Check current device state
4. ✓ Simulate BMC DHCP request
5. ✓ Wait for worker to process event
6. ✓ Verify IP assignment
7. ✓ Verify state transition
8. ✓ Check journal entries were created

**Expected Output:**
```
╔══════════════════════════════════════════════════════════════════╗
║                    PHASE 1 TEST - BMC Discovery                 ║
╚══════════════════════════════════════════════════════════════════╝

Test Configuration:
  Device:      CENT-SRV-035
  BMC MAC:     A0:36:9F:77:05:00
  BMC IP:      10.22.4.202

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: Verify Device Exists in NetBox
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Device found: CENT-SRV-035 (ID: 123)

...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 8: Verify Journal Entries
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Found 3 journal entries

Recent journal entries:
  • [success] BMC discovered via DHCP - MAC: A0:36:9F:77:05:00, IP: 10.22.4.202
  • [info] IP address 10.22.4.202 assigned to interface bmc
  • [success] Lifecycle state changed: offline → discovered

╔══════════════════════════════════════════════════════════════════╗
║                    PHASE 1 TEST COMPLETE                         ║
╚══════════════════════════════════════════════════════════════════╝

Summary:
  Device:         CENT-SRV-035
  Initial State:  offline
  Final State:    discovered
  BMC MAC:        A0:36:9F:77:05:00
  BMC IP:         10.22.4.202
  Journal Entries: 3

✓ Phase 1 test PASSED
```

## Viewing Journal Entries

### Via NetBox Web UI

1. Navigate to: `http://localhost:8000`
2. Go to **Devices** → **Devices**
3. Click on **CENT-SRV-035**
4. Click the **Journal** tab
5. View all automated entries with timestamps

### Via NetBox API

```bash
# Get device ID
DEVICE_ID=$(curl -s "http://localhost:8000/api/dcim/devices/?name=CENT-SRV-035" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq -r '.results[0].id')

# Get journal entries for device
curl -s "http://localhost:8000/api/extras/journal-entries/?assigned_object_id=$DEVICE_ID&assigned_object_type=dcim.device" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.results[] | {kind, created, comments}'
```

**Output:**
```json
{
  "kind": "success",
  "created": "2026-02-13T14:30:15.123Z",
  "comments": "[2026-02-13T14:30:15.123456Z] BMC discovered via DHCP - MAC: A0:36:9F:77:05:00, IP: 10.22.4.202"
}
{
  "kind": "info",
  "created": "2026-02-13T14:30:15.234Z",
  "comments": "[2026-02-13T14:30:15.234567Z] IP address 10.22.4.202 assigned to interface bmc"
}
{
  "kind": "success",
  "created": "2026-02-13T14:30:15.345Z",
  "comments": "[2026-02-13T14:30:15.345678Z] Lifecycle state changed: offline → discovered"
}
```

## Architecture: Journal Logging Implementation

### Shared Utilities Module (`netbox_utils.py`)

Provides journal logging functions for both workers:

**API-based (for external workers):**
- `NetBoxJournalMixin` - Mixin class for NetBox API clients
- `add_journal_entry()` - Generic journal entry
- `add_journal_state_change()` - State transition logging
- `add_journal_ip_assignment()` - IP assignment logging
- `add_journal_discovery()` - Discovery event logging
- `add_journal_error()` - Error logging

**Django ORM-based (for workers inside NetBox container):**
- `add_journal_entry_django()` - Generic journal entry
- `add_journal_state_change_django()` - State transition
- `add_journal_ip_assignment_django()` - IP assignment
- `add_journal_discovery_django()` - Discovery event
- `add_journal_error_django()` - Error logging

### Updated Workers

#### `netbox-bmc-worker.py`
Uses API-based journal logging via `NetBoxJournalMixin`:

```python
from netbox_utils import NetBoxJournalMixin

class NetBoxClient(NetBoxJournalMixin):
    # Now has journal logging methods
    pass

# Usage in worker:
netbox.add_journal_discovery(device_id, device_name, 'BMC', mac, ip)
netbox.add_journal_state_change(device_id, device_name, old_state, new_state)
netbox.add_journal_ip_assignment(device_id, device_name, 'bmc', ip)
```

#### `dhcp-lease-worker.py`
Uses Django ORM-based journal logging:

```python
from netbox_utils import (
    add_journal_discovery_django,
    add_journal_state_change_django,
    add_journal_ip_assignment_django
)

# Usage in worker:
add_journal_discovery_django(device, 'BMC', mac, ip)
add_journal_state_change_django(device, old_state, new_state)
add_journal_ip_assignment_django(device, interface_name, ip)
```

## Troubleshooting

### No Journal Entries Created

**Check worker logs:**
```bash
docker-compose logs bmc-worker | grep -i journal
```

**Verify NetBox permissions:**
```bash
# Test journal entry creation
curl -X POST "http://localhost:8000/api/extras/journal-entries/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  -H "Content-Type: application/json" \
  -d '{
    "assigned_object_type": "dcim.device",
    "assigned_object_id": 1,
    "kind": "info",
    "comments": "Test entry"
  }'
```

### Device Not Found

**Check BMC MAC in NetBox:**
```bash
curl -s "http://localhost:8000/api/dcim/interfaces/?mac_address=A0:36:9F:77:05:00" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.count'
```

Should return `1`. If `0`, run `setup-phase1-device.py` again.

### State Not Changing

**Check custom field exists:**
```bash
curl -s "http://localhost:8000/api/extras/custom-fields/?name=lifecycle_state" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | jq '.count'
```

Should return `1`. If `0`, run the lifecycle states setup:
```bash
docker cp add-lifecycle-states.py netbox:/tmp/
docker exec netbox python /tmp/add-lifecycle-states.py
```

## Next Steps

After Phase 1 completes successfully:

1. **Phase 2: Hardware Validation** - PXE boot validation image, check LLDP
2. **Phase 3: Provisioning** - Apply firmware updates, BIOS configuration
3. **Phase 4: Ready State** - Mark as ready for tenant assignment

Each phase will add its own journal entries, creating a complete audit trail of the server's lifecycle.

## Files Reference

| File | Purpose |
|------|---------|
| `netbox_utils.py` | Shared journal logging utilities |
| `netbox-bmc-worker.py` | BMC discovery worker (updated with journals) |
| `dhcp-lease-worker.py` | DHCP lease worker (updated with journals) |
| `setup-phase1-device.py` | Creates CENT-SRV-035 test device |
| `test-phase1.sh` | Automated Phase 1 test script |
| `PHASE1-GUIDE.md` | This guide |

---

**Last Updated:** 2026-02-13
**Version:** 1.0
