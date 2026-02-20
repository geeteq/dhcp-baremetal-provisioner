# NetBox Sample Data Population Script

This script populates a NetBox instance with realistic baremetal server infrastructure data for testing, development, and demonstration purposes.

## Overview

The script creates a complete multi-datacenter baremetal hosting infrastructure with:
- **600 servers** across 3 datacenters
- **36 racks** with full network and power topology
- **3,600 cables** with proper A/B terminations
- Realistic MAC addresses and interface configurations

## What Gets Created

### Infrastructure Summary

| Component | Quantity | Details |
|-----------|----------|---------|
| **Datacenters** | 3 | DC-East, DC-West, DC-Center |
| **Racks** | 36 | 12 per datacenter (42U each) |
| **Servers** | 600 | HPE ProLiant DL360 Gen11 (200 per DC) |
| **Management Switches** | 36 | Juniper EX4300-48P (1 per rack) |
| **Production Switches** | 72 | Cisco NCS-55A1-24Q6H-S (2 per rack) |
| **PDUs** | 72 | APC AP8959 (2 per rack for redundancy) |
| **Network Cables** | 2,400 | Cat6 patch cords and DAC cables |
| **Power Cables** | 1,200 | IEC C13/C14 power cords |

### Server Specifications

Each server (HPE ProLiant DL360 Gen11) has:

#### Network Interfaces
1. **BMC Interface** (`bmc`)
   - Type: 1000BASE-T (copper)
   - MAC: A0:36:9F:xx:xx:xx (HPE OUI)
   - Connection: Management Switch ports 1-24
   - Cable: Cat6 patch cord
   - Purpose: Out-of-band management (iLO)

2. **Management Interface** (`mgmt0`)
   - Type: 1000BASE-T (copper)
   - MAC: A0:36:9F:xx:xx:xx (HPE OUI)
   - Connection: Management Switch ports 25-48
   - Cable: Cat6 patch cord
   - Purpose: In-band OS-level management

3. **Production Interface 1** (`ens1f0`)
   - Type: 25GBASE-X SFP28
   - MAC: 3C:FD:FE:xx:xx:xx (Intel OUI)
   - Connection: Production Switch A
   - Cable: DAC (Direct Attach Copper)
   - Purpose: High-speed production traffic

4. **Production Interface 2** (`ens2f0`)
   - Type: 25GBASE-X SFP28
   - MAC: 3C:FD:FE:xx:xx:xx (Intel OUI)
   - Connection: Production Switch B
   - Cable: DAC (Direct Attach Copper)
   - Purpose: Redundant high-speed production traffic

#### Power
- **PSU1** → PDU A (redundant power feed)
- **PSU2** → PDU B (redundant power feed)
- Max draw: 800W per PSU
- Typical: 400W per PSU

### Network Topology

#### Per Rack Configuration
```
┌─────────────────────────────────────────────────────────┐
│                    Rack (e.g., EAST-R01)                │
├─────────────────────────────────────────────────────────┤
│ U42: Management Switch (Juniper EX4300-48P)            │
│      • Ports 1-24:  Server BMC interfaces               │
│      • Ports 25-48: Server Management interfaces        │
├─────────────────────────────────────────────────────────┤
│ U41: Production Switch A (Cisco NCS-55A1-24Q6H-S)      │
│      • 24x 25GbE ports for server production NICs       │
├─────────────────────────────────────────────────────────┤
│ U40: Production Switch B (Cisco NCS-55A1-24Q6H-S)      │
│      • 24x 25GbE ports for redundant production NICs    │
├─────────────────────────────────────────────────────────┤
│ U39-U23: Servers (16-17 per rack)                      │
│      • Each server: 1U, 4 NICs, 2 PSUs                 │
├─────────────────────────────────────────────────────────┤
│ Zero-U:                                                 │
│  • PDU A (24 outlets) - Feeds all PSU1                 │
│  • PDU B (24 outlets) - Feeds all PSU2                 │
└─────────────────────────────────────────────────────────┘
```

### Cable Termination Convention

All cables follow industry best practices:
- **Side A:** Server interface/power port (downstream)
- **Side B:** Switch port/PDU outlet (infrastructure/upstream)

This ensures:
- Consistent documentation
- Easy network path tracing
- Proper cable management diagrams
- Simplified troubleshooting

## Usage

### Prerequisites

1. **NetBox 3.7.3+** installed and running
2. **Python 3.11+** with Django
3. **Database access** with write permissions
4. **Custom fields** configured (lifecycle_state, etc.)

### Running the Script

#### Method 1: Docker (Recommended)

```bash
# Copy script to NetBox container
docker cp populate_netbox_sample_data.py netbox:/tmp/

# Run the script
docker exec netbox python /tmp/populate_netbox_sample_data.py
```

#### Method 2: Direct Execution

```bash
# From NetBox installation directory
cd /opt/netbox/netbox
python /path/to/populate_netbox_sample_data.py
```

### Execution Time

- **Full population:** ~4-6 minutes
- **Database wipe:** ~10 seconds
- **Server creation:** ~2-4 minutes
- **Cable creation:** ~1-2 minutes

### Output

The script provides detailed progress output:

```
======================================================================
NETBOX SAMPLE DATA POPULATION
======================================================================

Baremetal Server Infrastructure
  - 3 Datacenters (East, West, Center)
  - 100 Servers per datacenter (300 total)
  - 6 Racks per datacenter (18 total)
  - Full network and power topology
======================================================================

======================================================================
WIPING DATABASE
======================================================================

Deleting all cables...
  ✓ Deleted all cables
Deleting all devices...
  ✓ Deleted all devices
...

======================================================================
✓ POPULATION COMPLETED SUCCESSFULLY!
======================================================================
```

## What the Script Does

### 1. Database Cleanup
- Deletes all existing cables
- Removes all devices
- Clears racks
- Removes test sites (dc-east, dc-west, dc-center)

### 2. Base Infrastructure
- Creates manufacturers (HPE, Cisco, Juniper, APC)
- Creates device types (servers, switches, PDUs)
- Creates device roles (compute-server, management-switch, etc.)

### 3. Datacenter Layout
- Creates 3 datacenter sites
- Creates 6 racks per datacenter
- Assigns rack roles and attributes

### 4. Per-Rack Provisioning
For each rack:
- Creates 1 management switch (Juniper EX4300-48P)
- Creates 2 production switches (Cisco NCS-55A1-24Q6H-S)
- Creates 2 PDUs (APC AP8959)
- Creates 16-17 servers (HPE DL360 Gen11)
- Creates all interfaces with unique MAC addresses
- Creates all cables with proper terminations
- Connects everything together

### 5. Finalization
- Sets all servers to "offline" lifecycle state
- Validates all connections
- Displays summary statistics

## Sample Data Generated

### Server Naming Convention
- **Format:** `{DC}-SRV-{NUMBER}`
- **Examples:**
  - `EAST-SRV-001` through `EAST-SRV-200`
  - `WEST-SRV-001` through `WEST-SRV-200`
  - `CENT-SRV-001` through `CENT-SRV-200`

### Infrastructure Naming Convention
- **Management Switches:** `{DC}-MGT-SW-{RACK}`
  - Example: `EAST-MGT-SW-R01`
- **Production Switches:** `{DC}-PROD-SW{A|B}-{RACK}`
  - Example: `EAST-PROD-SWA-R01`, `EAST-PROD-SWB-R01`
- **PDUs:** `{DC}-PDU{A|B}-{RACK}`
  - Example: `EAST-PDUA-R01`, `EAST-PDUB-R01`

### Cable Labels
- **BMC Cables:** `{SERVER}-BMC`
- **Management Cables:** `{SERVER}-MGMT`
- **Production Cables:** `{SERVER}-PROD{1|2}`
- **Power Cables:** `{SERVER}-PSU{1|2}`

## Accessing the Data

### Web Interface
```
URL:      http://localhost:8000
Username: admin
Password: admin
```

Navigate to:
- **Devices → Devices** - View all servers
- **Racks → Racks** - View rack elevations
- **Cables → Cables** - View cable connections
- **Organization → Sites** - View datacenters

### API Access
```bash
# Get all servers
curl "http://localhost:8000/api/dcim/devices/?role=compute-server" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"

# Get servers in specific datacenter
curl "http://localhost:8000/api/dcim/devices/?site=dc-east" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"

# Get specific server with interfaces
curl "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"

# Get all cables
curl "http://localhost:8000/api/dcim/cables/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"

# Get cable with terminations
curl "http://localhost:8000/api/dcim/cables/?label=EAST-SRV-001-BMC" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

## Use Cases

This sample data is perfect for:

### Development
- Testing NetBox integrations
- Developing automation workflows
- Building monitoring systems
- Creating provisioning tools

### Training
- Learning NetBox data models
- Understanding DCIM concepts
- Practicing API integration
- Demonstrating features

### Demo
- Showcasing baremetal infrastructure
- Presenting network topology
- Demonstrating cable management
- Visualizing datacenter operations

### Testing
- Load testing NetBox
- Performance benchmarking
- API response validation
- UI functionality testing

## Customization

### Modify Server Count
Edit the `servers_per_rack` variable:
```python
servers_per_rack = 17  # Change to desired number
```

### Change Datacenter Names
Edit the `sites_data` list:
```python
sites_data = [
    {'name': 'DC-Custom', 'slug': 'dc-custom', ...},
]
```

### Adjust MAC Address Ranges
Edit the MAC generation in `create_server_interfaces()`:
```python
bmc_mac = f"XX:XX:XX:{server.pk % 256:02X}:{...}"
```

### Modify Device Models
Edit the `device_types_data` list to use different hardware:
```python
{'manufacturer': manufacturers['dell'],
 'model': 'PowerEdge R650',
 'slug': 'dell-r650', ...}
```

## Troubleshooting

### Script Fails with Database Error
**Solution:** Ensure NetBox database is accessible and user has write permissions

### MAC Address Conflicts
**Solution:** Script generates unique MACs based on device ID, conflicts are rare

### Memory Issues
**Solution:** Reduce `servers_per_rack` or process fewer datacenters at once

### Slow Performance
**Solution:** Check database indexing and NetBox background workers

## Files

- `populate_netbox_sample_data.py` - Main population script
- `README.md` - This documentation file

## Version History

### Version 1.1 (2026-02-13)
- Expanded infrastructure to 600 servers (200 per datacenter)
- Increased to 12 racks per datacenter (36 total)
- All servers configured with "offline" lifecycle state
- Scaled network and power infrastructure accordingly

### Version 1.0 (2026-02-13)
- Initial release
- Support for 3 datacenters
- 300 servers with full topology
- Proper cable terminations (A/B)
- MAC address assignment
- Lifecycle state configuration

## License

This script is provided as-is for use with NetBox installations.

## Author

Created by Claude for baremetal infrastructure demonstration and testing.

## Support

For issues or questions:
1. Check NetBox documentation
2. Review script comments
3. Verify NetBox version compatibility
4. Check custom field configuration

---

**Last Updated:** 2026-02-13
**NetBox Version:** 3.7.3+
**Python Version:** 3.11+
