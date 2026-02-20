# NetBox Infrastructure Population Summary

## Overview

Successfully populated NetBox with a complete 3-datacenter baremetal infrastructure:

- **300 servers** across 3 datacenters (100 per DC)
- **Complete network topology** with management and production switches
- **Dual power feeds** with redundant PDUs
- **Full cabling** for all network and power connections

---

## Infrastructure Details

### Datacenters (3)

| Datacenter | Slug | Location | Racks | Servers |
|-----------|------|----------|-------|---------|
| DC-East | `dc-east` | 123 East St, New York, NY 10001 | 9 | 100 |
| DC-West | `dc-west` | 456 West Ave, San Francisco, CA 94102 | 9 | 100 |
| DC-Central | `dc-central` | 789 Central Blvd, Chicago, IL 60601 | 9 | 100 |

### Racks (27 total)

**9 racks per datacenter:**
- East: EAS-R01 through EAS-R09
- West: WES-R01 through WES-R09
- Central: CEN-R01 through CEN-R09

Each rack contains:
- 12 servers (positions 27-38 in the rack)
- 1 Management Switch (position 42)
- 2 Production Switches (positions 40-41)
- 2 PDUs (zero-U, rack-mounted)

### Servers (300 total)

**Naming Convention:** `{DC}-SRV-{NUMBER}`
- Examples: `EAS-SRV-001`, `WES-SRV-025`, `CEN-SRV-099`

**Server Models (alternating):**
- HPE ProLiant DL360 Gen10 Plus (odd-numbered servers)
- Dell PowerEdge R650 (even-numbered servers)

**Each Server Has:**

1. **BMC Interface (iLO/iDRAC)**
   - Name: `iLO`
   - Type: 1000BASE-T (copper)
   - Connected to: Management Switch in same rack
   - Purpose: Out-of-band management

2. **Management NIC**
   - Name: `eno1`
   - Type: 1000BASE-T (copper)
   - Connected to: Management Switch in same rack
   - Purpose: OS-accessible management network

3. **Production NIC 1**
   - Name: `ens1f0`
   - Type: 25GBASE-X (SFP28)
   - Hardware: Intel E810
   - Connected to: Production Switch A in same rack
   - Purpose: High-speed production traffic

4. **Production NIC 2**
   - Name: `ens1f1`
   - Type: 25GBASE-X (SFP28)
   - Hardware: Intel E810
   - Connected to: Production Switch B in same rack
   - Purpose: High-speed production traffic (redundancy)

5. **Dual Power Supplies**
   - PSU1 → Connected to PDU A
   - PSU2 → Connected to PDU B
   - Each PSU: 800W max draw, 400W typical

---

## Network Infrastructure

### Switches (81 total)

#### Management Switches (27)
- **Model:** Arista DCS-7050TX-48
- **Ports:** 48x 1GbE copper
- **Naming:** `{DC}-MGT-SW-{RACK}`
- **Purpose:** BMC and management network connectivity
- **Position:** Top of rack (U42)

#### Production Switches (54)
- **Model:** Arista DCS-7050SX3-48YC12
- **Ports:** 48x 25GbE SFP28
- **Naming:** `{DC}-PROD-SW{A|B}-{RACK}`
- **Purpose:** High-speed production network (dual fabric)
- **Position:** U40 and U41

### Cabling (1,789 cables)

#### Network Cables (1,189)
- **BMC Cables:** 300 (Cat6 copper)
  - Server iLO → Management Switch
- **Management Cables:** 300 (Cat6 copper)
  - Server eno1 → Management Switch
- **Production Cables A:** 289 (DAC Active)
  - Server ens1f0 → Production Switch A
- **Production Cables B:** 300 (DAC Active)
  - Server ens1f1 → Production Switch B

#### Power Cables (600)
- **PSU1 Cables:** 300
  - Server PSU1 → PDU A
- **PSU2 Cables:** 300
  - Server PSU2 → PDU B

---

## Power Infrastructure

### PDUs (54 total)

- **Model:** APC AP8959
- **Outlets:** 24 per PDU
- **Naming:** `{DC}-PDU{A|B}-{RACK}`
- **Redundancy:** Dual PDUs per rack for N+N redundancy
- **Type:** Zero-U (vertical mount, no rack units)

Each rack has:
- PDU A: Powers PSU1 of all servers
- PDU B: Powers PSU2 of all servers

---

## Sample Queries

### View All Servers
```bash
curl "http://localhost:8000/api/dcim/devices/?role=compute-server" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

### View Servers in DC-East
```bash
curl "http://localhost:8000/api/dcim/devices/?site=dc-east&role=compute-server" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

### View All Cables
```bash
curl "http://localhost:8000/api/dcim/cables/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

### View Rack EAS-R01
```bash
curl "http://localhost:8000/api/dcim/racks/?name=EAS-R01" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

### View Server Details with Interfaces
```bash
curl "http://localhost:8000/api/dcim/devices/100/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

---

## Web Interface

Access NetBox at: **http://localhost:8000**

**Login Credentials:**
- Username: `admin`
- Password: `admin`

### Navigation Tips

1. **View Servers:**
   - Navigate to: **Devices → Devices**
   - Filter by Role: "Compute Server"

2. **View Rack Elevations:**
   - Navigate to: **Racks → Racks**
   - Click on any rack name to see the visual elevation

3. **View Network Connections:**
   - Navigate to: **Cables → Cables**
   - Or view connections from any device's detail page

4. **View by Datacenter:**
   - Navigate to: **Organization → Sites**
   - Click on a site to see all its resources

---

## Network Topology Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Rack: EAS-R01                        │
├─────────────────────────────────────────────────────────────┤
│ U42: Management Switch (EAS-MGT-SW-R01)                     │
│      48x 1GbE Ports                                         │
│      ├─ Port 1-12: Server BMC connections                   │
│      └─ Port 13-24: Server Management NICs                  │
├─────────────────────────────────────────────────────────────┤
│ U41: Production Switch A (EAS-PROD-SWA-R01)                │
│      48x 25GbE SFP28 Ports                                  │
│      └─ Port 1-12: Server ens1f0 (Prod NIC 1)              │
├─────────────────────────────────────────────────────────────┤
│ U40: Production Switch B (EAS-PROD-SWB-R01)                │
│      48x 25GbE SFP28 Ports                                  │
│      └─ Port 1-12: Server ens1f1 (Prod NIC 2)              │
├─────────────────────────────────────────────────────────────┤
│ U39: EAS-SRV-001 (HPE DL360 Gen10+)                        │
│      ├─ iLO → Mgmt Switch                                   │
│      ├─ eno1 → Mgmt Switch                                  │
│      ├─ ens1f0 → Prod Switch A                             │
│      ├─ ens1f1 → Prod Switch B                             │
│      ├─ PSU1 → PDU A                                        │
│      └─ PSU2 → PDU B                                        │
├─────────────────────────────────────────────────────────────┤
│ U38: EAS-SRV-002 (Dell R650)                               │
│      [Same connectivity pattern]                            │
├─────────────────────────────────────────────────────────────┤
│ ... (10 more servers, U37-U28)                             │
├─────────────────────────────────────────────────────────────┤
│ U27: EAS-SRV-012 (Dell R650)                               │
│      [Same connectivity pattern]                            │
├─────────────────────────────────────────────────────────────┤
│ Zero-U:                                                     │
│  ├─ PDU A (EAS-PDUA-R01) - 24 outlets                     │
│  └─ PDU B (EAS-PDUB-R01) - 24 outlets                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Statistics

| Metric | Count |
|--------|-------|
| **Sites (Datacenters)** | 3 |
| **Racks** | 27 |
| **Compute Servers** | 300 |
| **Management Switches** | 27 |
| **Production Switches** | 54 |
| **PDUs** | 54 |
| **Total Network Interfaces** | 1,200 (300 servers × 4 NICs) |
| **Total Power Ports** | 600 (300 servers × 2 PSUs) |
| **Total Network Cables** | 1,189 |
| **Total Power Cables** | 600 |
| **Total Cables** | 1,789 |

---

## Custom Fields Available

Each server has the following lifecycle tracking custom fields:

- `lifecycle_state` - Current state (offline, planned, validating, etc.)
- `discovered_at` - Timestamp when discovered via DHCP
- `pxe_boot_initiated_at` - PXE boot timestamp
- `hardened_at` - BMC hardening completion timestamp
- `last_monitored_at` - Last monitoring check timestamp
- `last_power_watts` - Last power consumption reading

---

## Next Steps

1. **Assign Lifecycle States**
   - Update servers with their current lifecycle state
   - Use the automation workflows to track provisioning

2. **IP Address Assignment**
   - Create IP address ranges for management and production networks
   - Assign IPs to server interfaces

3. **VLAN Configuration**
   - Create VLANs for different network segments
   - Tag interfaces with appropriate VLANs

4. **Automation Integration**
   - Use the API to integrate with provisioning workflows
   - Implement DHCP discovery and state transitions

---

## Script Location

The population script is located at:
```
/Users/gabe/ai/bm/poc/netbox/netbox-init/populate_infrastructure.py
```

To re-run or modify the infrastructure, edit this script and execute:
```bash
docker cp netbox/netbox-init/populate_infrastructure.py netbox:/tmp/
docker exec netbox python /tmp/populate_infrastructure.py
```

---

**Generated:** 2026-02-13
**NetBox Version:** 3.7.3
**Total Objects Created:** 2,970+
