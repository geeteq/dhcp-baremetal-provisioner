#!/usr/bin/env python3
"""
Populate NetBox with realistic baremetal infrastructure:
- 3 Datacenters (East, West, Central)
- 100 servers per datacenter (300 total)
- 12 servers per rack (~9 racks per DC)
- Full network topology with management and production switches
- Dual power feeds with PDUs
- Complete cabling for BMC, management, and production networks
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from dcim.models import (
    Site, Manufacturer, DeviceType, DeviceRole, Device,
    Interface, Cable, CableTermination, PowerFeed, PowerPanel, PowerPort,
    PowerOutlet, Rack, RackRole, Location
)
from extras.models import CustomField
from ipam.models import VLAN, VLANGroup, IPAddress, Prefix


def create_cable_connection(termination_a, termination_b, cable_type='cat6', label=''):
    """
    Create a cable connection between two terminations.
    Works with NetBox 3.7.3+ cable termination model.

    Args:
        termination_a: First termination object (Interface, PowerPort, etc.)
        termination_b: Second termination object
        cable_type: Type of cable
        label: Cable label

    Returns:
        tuple: (cable, created)
    """
    # Check if either termination already has a cable
    termination_a_content_type = ContentType.objects.get_for_model(termination_a)
    termination_b_content_type = ContentType.objects.get_for_model(termination_b)

    existing_term_a = CableTermination.objects.filter(
        termination_type=termination_a_content_type,
        termination_id=termination_a.id
    ).first()

    if existing_term_a:
        return existing_term_a.cable, False

    existing_term_b = CableTermination.objects.filter(
        termination_type=termination_b_content_type,
        termination_id=termination_b.id
    ).first()

    if existing_term_b:
        return existing_term_b.cable, False

    # Create the cable
    cable = Cable.objects.create(
        type=cable_type,
        status='connected',
        label=label
    )

    # Create terminations
    CableTermination.objects.create(
        cable=cable,
        termination=termination_a,
    )

    CableTermination.objects.create(
        cable=cable,
        termination=termination_b,
    )

    return cable, True


def create_infrastructure_device_types(manufacturers):
    """Create device types for infrastructure equipment."""
    print("\nCreating infrastructure device types...")

    device_types = []

    # Server device types
    server_types = [
        {
            'manufacturer': manufacturers['hpe'],
            'model': 'ProLiant DL360 Gen10 Plus',
            'slug': 'proliant-dl360-gen10-plus',
            'u_height': 1,
            'is_full_depth': True,
        },
        {
            'manufacturer': manufacturers['dell'],
            'model': 'PowerEdge R650',
            'slug': 'poweredge-r650',
            'u_height': 1,
            'is_full_depth': True,
        },
    ]

    # Network device types
    network_types = [
        {
            'manufacturer': manufacturers.get('arista', manufacturers['dell']),
            'model': 'DCS-7050SX3-48YC12',
            'slug': 'arista-7050sx3-48yc12',
            'u_height': 1,
            'is_full_depth': False,
        },
        {
            'manufacturer': manufacturers.get('juniper', manufacturers['dell']),
            'model': 'EX4300-48P',
            'slug': 'juniper-ex4300-48p',
            'u_height': 1,
            'is_full_depth': False,
            'part_number': 'EX4300-48P',
        },
    ]

    # PDU types
    pdu_types = [
        {
            'manufacturer': manufacturers.get('apc', manufacturers['hpe']),
            'model': 'AP8959',
            'slug': 'apc-ap8959',
            'u_height': 0,  # Zero-U PDU
            'is_full_depth': False,
        },
    ]

    all_types = server_types + network_types + pdu_types

    for dt_data in all_types:
        dt, created = DeviceType.objects.get_or_create(
            slug=dt_data['slug'],
            defaults=dt_data
        )
        if created:
            print(f"  ✓ Created device type: {dt.model}")
            device_types.append(dt)
        else:
            print(f"  - Device type exists: {dt.model}")
            device_types.append(dt)

    return {dt.slug: dt for dt in DeviceType.objects.filter(
        slug__in=[dt['slug'] for dt in all_types]
    )}


def create_datacenters():
    """Create three datacenter sites."""
    print("\nCreating datacenters...")

    sites_data = [
        {
            'name': 'DC-East',
            'slug': 'dc-east',
            'status': 'active',
            'description': 'East Coast Datacenter',
            'physical_address': '123 East St, New York, NY 10001',
        },
        {
            'name': 'DC-West',
            'slug': 'dc-west',
            'status': 'active',
            'description': 'West Coast Datacenter',
            'physical_address': '456 West Ave, San Francisco, CA 94102',
        },
        {
            'name': 'DC-Central',
            'slug': 'dc-central',
            'status': 'active',
            'description': 'Central US Datacenter',
            'physical_address': '789 Central Blvd, Chicago, IL 60601',
        },
    ]

    sites = {}
    for site_data in sites_data:
        site, created = Site.objects.get_or_create(
            slug=site_data['slug'],
            defaults=site_data
        )
        if created:
            print(f"  ✓ Created site: {site.name}")
        else:
            print(f"  - Site exists: {site.name}")
        sites[site.slug] = site

    return sites


def create_racks(sites):
    """Create racks in each datacenter (9 racks per DC for 100 servers)."""
    print("\nCreating racks...")

    rack_role, _ = RackRole.objects.get_or_create(
        name='Compute Rack',
        slug='compute-rack',
        defaults={'color': '2196f3'}
    )

    racks = {}
    servers_per_rack = 12
    total_servers = 100
    racks_needed = (total_servers + servers_per_rack - 1) // servers_per_rack  # Ceiling division

    for site in sites.values():
        site_prefix = site.slug.split('-')[1][:3].upper()  # EAST, WEST, CENT

        for i in range(1, racks_needed + 1):
            rack_name = f"{site_prefix}-R{i:02d}"
            rack, created = Rack.objects.get_or_create(
                site=site,
                name=rack_name,
                defaults={
                    'u_height': 42,
                    'role': rack_role,
                    'desc_units': False,
                    'status': 'active',
                }
            )
            if created:
                print(f"  ✓ Created rack: {rack.name} at {site.name}")
            else:
                print(f"  - Rack exists: {rack.name}")

            racks[rack_name] = rack

    return racks


def create_device_roles():
    """Create device roles."""
    print("\nCreating device roles...")

    roles_data = [
        {'name': 'Compute Server', 'slug': 'compute-server', 'color': '4caf50'},
        {'name': 'Management Switch', 'slug': 'management-switch', 'color': 'ff9800'},
        {'name': 'Production Switch', 'slug': 'production-switch', 'color': '2196f3'},
        {'name': 'PDU', 'slug': 'pdu', 'color': '9e9e9e'},
    ]

    roles = {}
    for role_data in roles_data:
        role, created = DeviceRole.objects.get_or_create(
            slug=role_data['slug'],
            defaults=role_data
        )
        if created:
            print(f"  ✓ Created role: {role.name}")
        else:
            print(f"  - Role exists: {role.name}")
        roles[role.slug] = role

    return roles


def create_rack_infrastructure(rack, device_types, roles, tenant):
    """
    Create infrastructure for a single rack:
    - 1 Management Switch
    - 2 Production Switches
    - 2 PDUs (for dual power)
    """
    infrastructure = {
        'mgmt_switch': None,
        'prod_switch_a': None,
        'prod_switch_b': None,
        'pdu_a': None,
        'pdu_b': None,
    }

    site_prefix = rack.name.split('-')[0]
    rack_num = rack.name.split('-')[1]

    # Management Switch (Juniper EX4300-48P)
    mgmt_switch_name = f"{site_prefix}-MGT-SW-{rack_num}"
    mgmt_switch, _ = Device.objects.get_or_create(
        name=mgmt_switch_name,
        defaults={
            'device_type': device_types['juniper-ex4300-48p'],
            'role': roles['management-switch'],
            'site': rack.site,
            'rack': rack,
            'position': 42,
            'face': 'front',
            'status': 'active',
            'tenant': tenant,
        }
    )
    infrastructure['mgmt_switch'] = mgmt_switch

    # Production Switches
    for switch_id in ['A', 'B']:
        prod_switch_name = f"{site_prefix}-PROD-SW{switch_id}-{rack_num}"
        position = 41 if switch_id == 'A' else 40
        prod_switch, _ = Device.objects.get_or_create(
            name=prod_switch_name,
            defaults={
                'device_type': device_types['arista-7050sx3-48yc12'],
                'role': roles['production-switch'],
                'site': rack.site,
                'rack': rack,
                'position': position,
                'face': 'front',
                'status': 'active',
                'tenant': tenant,
            }
        )
        if switch_id == 'A':
            infrastructure['prod_switch_a'] = prod_switch
        else:
            infrastructure['prod_switch_b'] = prod_switch

    # PDUs (Zero-U, no position)
    for pdu_id in ['A', 'B']:
        pdu_name = f"{site_prefix}-PDU{pdu_id}-{rack_num}"
        pdu, _ = Device.objects.get_or_create(
            name=pdu_name,
            defaults={
                'device_type': device_types['apc-ap8959'],
                'role': roles['pdu'],
                'site': rack.site,
                'rack': rack,
                'status': 'active',
                'tenant': tenant,
            }
        )
        if pdu_id == 'A':
            infrastructure['pdu_a'] = pdu
        else:
            infrastructure['pdu_b'] = pdu

    return infrastructure


def create_server_interfaces(server):
    """Create all interfaces for a server."""
    interfaces = {}

    # BMC Interface (iLO/iDRAC)
    bmc_mac = f"00:50:56:{server.pk % 256:02x}:{(server.pk // 256) % 256:02x}:{(server.pk // 65536) % 256:02x}"
    bmc_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='iLO',
        defaults={
            'type': '1000base-t',
            'mgmt_only': True,
            'mac_address': bmc_mac,
            'description': 'BMC Management Interface',
        }
    )
    interfaces['bmc'] = bmc_iface

    # Management NIC (OS-accessible)
    mgmt_mac = f"00:50:57:{server.pk % 256:02x}:{(server.pk // 256) % 256:02x}:{(server.pk // 65536) % 256:02x}"
    mgmt_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='eno1',
        defaults={
            'type': '1000base-t',
            'mac_address': mgmt_mac,
            'description': 'OS Management Interface',
        }
    )
    interfaces['mgmt'] = mgmt_iface

    # Production NICs (25Gbit Intel E810)
    for port_num in [1, 2]:
        prod_mac = f"b4:96:91:{server.pk % 256:02x}:{(server.pk // 256) % 256:02x}:{port_num:02x}"
        prod_iface, _ = Interface.objects.get_or_create(
            device=server,
            name=f'ens1f{port_num - 1}',
            defaults={
                'type': '25gbase-x-sfp28',
                'mac_address': prod_mac,
                'description': f'Production Network Interface {port_num}',
            }
        )
        interfaces[f'prod{port_num}'] = prod_iface

    return interfaces


def create_switch_interfaces(switch, port_count=48):
    """Create interfaces on a switch."""
    interfaces = []

    # Determine interface type and naming based on switch model
    if '7050SX3' in switch.device_type.model:
        # Arista production switch
        iface_type = '25gbase-x-sfp28'
        prefix = 'Ethernet'
        name_format = lambda port: f"{prefix}{port}"
    elif 'EX4300' in switch.device_type.model:
        # Juniper management switch
        iface_type = '1000base-t'
        name_format = lambda port: f"ge-0/0/{port - 1}"  # Juniper format: ge-FPC/PIC/Port (0-indexed)
    else:
        # Default/generic
        iface_type = '1000base-t'
        prefix = 'GigabitEthernet'
        name_format = lambda port: f"{prefix}{port}"

    for port in range(1, port_count + 1):
        iface_name = name_format(port)
        iface, _ = Interface.objects.get_or_create(
            device=switch,
            name=iface_name,
            defaults={
                'type': iface_type,
                'enabled': True,
            }
        )
        interfaces.append(iface)

    return interfaces


def create_pdu_outlets(pdu, outlet_count=24):
    """Create power outlets on a PDU."""
    outlets = []

    for outlet_num in range(1, outlet_count + 1):
        outlet, _ = PowerOutlet.objects.get_or_create(
            device=pdu,
            name=f"Outlet-{outlet_num}",
            defaults={
                'type': 'iec-60320-c13',
                'feed_leg': 'A' if outlet_num % 2 else 'B',
            }
        )
        outlets.append(outlet)

    return outlets


def create_server_power_ports(server):
    """Create dual power ports on a server."""
    power_ports = []

    for psu_num in [1, 2]:
        port, _ = PowerPort.objects.get_or_create(
            device=server,
            name=f"PSU{psu_num}",
            defaults={
                'type': 'iec-60320-c14',
                'maximum_draw': 800,  # 800W per PSU
                'allocated_draw': 400,  # Typical 400W usage
            }
        )
        power_ports.append(port)

    return power_ports


def connect_server_to_rack_infrastructure(server, server_ifaces, infrastructure, port_allocations):
    """
    Connect a server to rack infrastructure:
    - BMC -> Management Switch
    - Management NIC -> Management Switch
    - Prod NIC 1 -> Production Switch A
    - Prod NIC 2 -> Production Switch B
    - PSU1 -> PDU A
    - PSU2 -> PDU B
    """
    cables_created = []

    # Get infrastructure interfaces/outlets
    if not hasattr(infrastructure['mgmt_switch'], '_interfaces_cache'):
        infrastructure['mgmt_switch']._interfaces_cache = create_switch_interfaces(
            infrastructure['mgmt_switch']
        )
    if not hasattr(infrastructure['prod_switch_a'], '_interfaces_cache'):
        infrastructure['prod_switch_a']._interfaces_cache = create_switch_interfaces(
            infrastructure['prod_switch_a']
        )
    if not hasattr(infrastructure['prod_switch_b'], '_interfaces_cache'):
        infrastructure['prod_switch_b']._interfaces_cache = create_switch_interfaces(
            infrastructure['prod_switch_b']
        )
    if not hasattr(infrastructure['pdu_a'], '_outlets_cache'):
        infrastructure['pdu_a']._outlets_cache = create_pdu_outlets(infrastructure['pdu_a'])
    if not hasattr(infrastructure['pdu_b'], '_outlets_cache'):
        infrastructure['pdu_b']._outlets_cache = create_pdu_outlets(infrastructure['pdu_b'])

    rack_name = server.rack.name

    # BMC -> Management Switch
    mgmt_port_idx = port_allocations[rack_name]['mgmt_next_port']
    if mgmt_port_idx < len(infrastructure['mgmt_switch']._interfaces_cache):
        mgmt_switch_port = infrastructure['mgmt_switch']._interfaces_cache[mgmt_port_idx]
        cable, created = create_cable_connection(
            server_ifaces['bmc'],
            mgmt_switch_port,
            cable_type='cat6',
            label=f"{server.name}-BMC"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['mgmt_next_port'] += 1

    # Management NIC -> Management Switch
    mgmt_port_idx = port_allocations[rack_name]['mgmt_next_port']
    if mgmt_port_idx < len(infrastructure['mgmt_switch']._interfaces_cache):
        mgmt_switch_port = infrastructure['mgmt_switch']._interfaces_cache[mgmt_port_idx]
        cable, created = create_cable_connection(
            server_ifaces['mgmt'],
            mgmt_switch_port,
            cable_type='cat6',
            label=f"{server.name}-MGMT"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['mgmt_next_port'] += 1

    # Prod NIC 1 -> Production Switch A
    prod_a_port_idx = port_allocations[rack_name]['prod_a_next_port']
    if prod_a_port_idx < len(infrastructure['prod_switch_a']._interfaces_cache):
        prod_switch_a_port = infrastructure['prod_switch_a']._interfaces_cache[prod_a_port_idx]
        cable, created = create_cable_connection(
            server_ifaces['prod1'],
            prod_switch_a_port,
            cable_type='dac-active',
            label=f"{server.name}-PROD1"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['prod_a_next_port'] += 1

    # Prod NIC 2 -> Production Switch B
    prod_b_port_idx = port_allocations[rack_name]['prod_b_next_port']
    if prod_b_port_idx < len(infrastructure['prod_switch_b']._interfaces_cache):
        prod_switch_b_port = infrastructure['prod_switch_b']._interfaces_cache[prod_b_port_idx]
        cable, created = create_cable_connection(
            server_ifaces['prod2'],
            prod_switch_b_port,
            cable_type='dac-active',
            label=f"{server.name}-PROD2"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['prod_b_next_port'] += 1

    # Power connections
    power_ports = create_server_power_ports(server)

    # PSU1 -> PDU A
    pdu_a_outlet_idx = port_allocations[rack_name]['pdu_a_next_outlet']
    if pdu_a_outlet_idx < len(infrastructure['pdu_a']._outlets_cache):
        pdu_a_outlet = infrastructure['pdu_a']._outlets_cache[pdu_a_outlet_idx]
        cable, created = create_cable_connection(
            power_ports[0],
            pdu_a_outlet,
            cable_type='power',
            label=f"{server.name}-PSU1"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['pdu_a_next_outlet'] += 1

    # PSU2 -> PDU B
    pdu_b_outlet_idx = port_allocations[rack_name]['pdu_b_next_outlet']
    if pdu_b_outlet_idx < len(infrastructure['pdu_b']._outlets_cache):
        pdu_b_outlet = infrastructure['pdu_b']._outlets_cache[pdu_b_outlet_idx]
        cable, created = create_cable_connection(
            power_ports[1],
            pdu_b_outlet,
            cable_type='power',
            label=f"{server.name}-PSU2"
        )
        if created:
            cables_created.append(cable)
        port_allocations[rack_name]['pdu_b_next_outlet'] += 1

    return cables_created


def populate_datacenter_infrastructure():
    """Main function to populate all infrastructure."""
    print("=" * 70)
    print("NetBox Infrastructure Population")
    print("Populating 3 datacenters with 100 servers each")
    print("=" * 70)

    # Create manufacturers
    print("\nCreating manufacturers...")
    manufacturers = {}
    for mfr_data in [
        {'name': 'HPE', 'slug': 'hpe'},
        {'name': 'Dell', 'slug': 'dell'},
        {'name': 'Arista', 'slug': 'arista'},
        {'name': 'APC', 'slug': 'apc'},
    ]:
        mfr, created = Manufacturer.objects.get_or_create(
            slug=mfr_data['slug'],
            defaults=mfr_data
        )
        if created:
            print(f"  ✓ Created: {mfr.name}")
        else:
            print(f"  - Exists: {mfr.name}")
        manufacturers[mfr.slug] = mfr

    # Create device types
    device_types = create_infrastructure_device_types(manufacturers)

    # Create device roles
    roles = create_device_roles()

    # Create datacenters
    sites = create_datacenters()

    # Create racks
    racks = create_racks(sites)

    # Get or create staging tenant
    from tenancy.models import Tenant
    tenant, _ = Tenant.objects.get_or_create(
        slug='baremetal-staging',
        defaults={'name': 'Baremetal Staging'}
    )

    # Track infrastructure by rack
    rack_infrastructure = {}

    # Track port allocations per rack
    port_allocations = {}

    # Create servers across all datacenters
    print("\nCreating servers and infrastructure...")
    total_servers = 0
    servers_per_rack = 12

    for site in sites.values():
        site_prefix = site.slug.split('-')[1][:3].upper()
        site_racks = [r for r in racks.values() if r.site == site]

        print(f"\n  Datacenter: {site.name}")

        for rack_idx, rack in enumerate(site_racks):
            print(f"    Rack: {rack.name}")

            # Create rack infrastructure
            if rack.name not in rack_infrastructure:
                infrastructure = create_rack_infrastructure(
                    rack, device_types, roles, tenant
                )
                rack_infrastructure[rack.name] = infrastructure
                print(f"      ✓ Created infrastructure (switches, PDUs)")

                # Initialize port allocation tracking
                port_allocations[rack.name] = {
                    'mgmt_next_port': 0,
                    'prod_a_next_port': 0,
                    'prod_b_next_port': 0,
                    'pdu_a_next_outlet': 0,
                    'pdu_b_next_outlet': 0,
                }

            infrastructure = rack_infrastructure[rack.name]

            # Create servers for this rack
            servers_in_rack = min(servers_per_rack, 100 - (rack_idx * servers_per_rack))

            for server_num in range(1, servers_in_rack + 1):
                total_servers += 1
                global_server_num = (rack_idx * servers_per_rack) + server_num

                server_name = f"{site_prefix}-SRV-{global_server_num:03d}"

                # Alternate between HPE and Dell
                device_type = (device_types['proliant-dl360-gen10-plus']
                              if server_num % 2 == 1
                              else device_types['poweredge-r650'])

                # Calculate position (bottom-up, leave space for switches at top)
                position = 39 - ((server_num - 1) * 1)

                server, created = Device.objects.get_or_create(
                    name=server_name,
                    defaults={
                        'device_type': device_type,
                        'role': roles['compute-server'],
                        'site': site,
                        'rack': rack,
                        'position': position,
                        'face': 'front',
                        'status': 'active',
                        'tenant': tenant,
                    }
                )

                if created:
                    # Create server interfaces
                    server_ifaces = create_server_interfaces(server)

                    # Connect to infrastructure
                    cables = connect_server_to_rack_infrastructure(
                        server, server_ifaces, infrastructure, port_allocations
                    )

                    if server_num % 10 == 0:
                        print(f"      ✓ Created {server_num} servers in rack...")

            print(f"      ✓ Completed {servers_in_rack} servers in {rack.name}")

    print("\n" + "=" * 70)
    print("✓ Infrastructure population completed!")
    print("=" * 70)
    print(f"\nSummary:")
    print(f"  - Datacenters: {len(sites)}")
    print(f"  - Racks: {len(racks)}")
    print(f"  - Total Servers: {total_servers}")
    print(f"  - Management Switches: {len(racks)}")
    print(f"  - Production Switches: {len(racks) * 2}")
    print(f"  - PDUs: {len(racks) * 2}")
    print(f"  - Network Cables: ~{total_servers * 4}")
    print(f"  - Power Cables: {total_servers * 2}")
    print("\nAccess NetBox at: http://localhost:8000")
    print("=" * 70)


if __name__ == '__main__':
    try:
        populate_datacenter_infrastructure()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
