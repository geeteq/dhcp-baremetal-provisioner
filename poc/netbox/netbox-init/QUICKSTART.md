# Quick Start Guide

Get your NetBox instance populated with sample baremetal infrastructure in under 5 minutes!

## One-Command Setup

```bash
docker cp populate_netbox_sample_data.py netbox:/tmp/ && \
docker exec netbox python /tmp/populate_netbox_sample_data.py
```

## What You'll Get

✅ **600 servers** across 3 datacenters
✅ **3,600 cables** with proper connections
✅ **36 racks** fully populated
✅ **Realistic MAC addresses** pre-assigned
✅ **Complete power topology** with dual feeds
✅ **Production-ready** network layout

## Verification

After the script completes (4-6 minutes), verify your data:

### Check via Web UI
```
http://localhost:8000

Login: admin / admin
```

Go to: **Devices → Devices**
You should see **600 compute servers**

### Check via API
```bash
curl -s "http://localhost:8000/api/dcim/devices/?role=compute-server" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | python3 -c "import sys,json; print(f\"Servers: {json.load(sys.stdin)['count']}\")"
```

Expected output: `Servers: 600`

### Sample Queries

**View a specific server:**
```bash
curl -s "http://localhost:8000/api/dcim/devices/?name=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

**View rack elevation:**
```bash
curl -s "http://localhost:8000/api/dcim/racks/?name=EAST-R01" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

**View cables:**
```bash
curl -s "http://localhost:8000/api/dcim/cables/?label__ic=SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

## Infrastructure Overview

### Datacenters
- **DC-East** - 200 servers in 12 racks
- **DC-West** - 200 servers in 12 racks
- **DC-Center** - 200 servers in 12 racks

### Each Server Has
- 1× BMC interface (iLO) → Management Switch
- 1× Management NIC → Management Switch
- 2× 25GbE Production NICs → 2× Production Switches
- 2× Power supplies → 2× PDUs (redundant)

### Each Rack Contains
- 1× Juniper EX4300-48P Management Switch
- 2× Cisco NCS-55A1-24Q6H-S Production Switches
- 2× APC AP8959 PDUs
- 16-17× HPE ProLiant DL360 Gen11 Servers

## Next Steps

### Explore the Data
1. Browse devices by datacenter
2. View rack elevations
3. Trace cable paths
4. Check interface connections

### Use for Development
1. Test your automation scripts
2. Develop provisioning workflows
3. Build monitoring integrations
4. Create network diagrams

### API Integration
```python
import requests

# Get all servers in East datacenter
response = requests.get(
    'http://localhost:8000/api/dcim/devices/',
    headers={'Authorization': 'Token 0123456789abcdef0123456789abcdef01234567'},
    params={'site': 'dc-east', 'role': 'compute-server'}
)

servers = response.json()['results']
print(f"Found {len(servers)} servers")

for server in servers[:5]:
    print(f"  - {server['name']} in {server['rack']['name']}")
```

## Common Tasks

### Export Server List
```bash
curl -s "http://localhost:8000/api/dcim/devices/?role=compute-server&limit=600" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  | python3 -c "import sys,json,csv; data=json.load(sys.stdin); w=csv.writer(sys.stdout); w.writerow(['Name','Site','Rack','Position']); [w.writerow([s['name'],s['site']['name'],s['rack']['name'],s['position']]) for s in data['results']]" \
  > servers.csv
```

### Export MAC Addresses
See `server_mac_addresses.csv` (automatically generated)

### View Cable Connections
```bash
# Get all cables for a server
curl -s "http://localhost:8000/api/dcim/cables/?device=EAST-SRV-001" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

## Troubleshooting

**Problem:** Script fails with authentication error
**Solution:** Check NetBox is running: `docker ps | grep netbox`

**Problem:** No data appears
**Solution:** Check script output for errors, ensure database is accessible

**Problem:** Duplicate key errors
**Solution:** Run the script again - it wipes existing data first

**Problem:** Slow performance
**Solution:** This is normal for 600 servers - be patient (4-6 minutes)

## Clean Up

To remove all sample data and start fresh:

```bash
# Just run the script again - it wipes before populating
docker exec netbox python /tmp/populate_netbox_sample_data.py
```

## Success Indicators

When complete, you should see:

```
======================================================================
✓ POPULATION COMPLETED SUCCESSFULLY!
======================================================================

Infrastructure Created:
  Datacenters:            3
  Racks:                  36 (12 per DC)
  Compute Servers:        600 (200 per DC)
  Management Switches:    36 (Juniper EX4300-48P)
  Production Switches:    72 (Cisco NCS-55A1-24Q6H-S)
  PDUs:                   72 (APC AP8959)
  Total Cables:           3600
```

## Getting Help

- Review the full README.md for detailed documentation
- Check NetBox logs: `docker logs netbox`
- Verify NetBox version: `docker exec netbox cat /opt/netbox/netbox/netbox/configuration.py`

---

**Ready to get started?** Run the one-command setup at the top! 🚀
