#!/usr/bin/env python3
"""
Create NetBox infrastructure based on final specifications:
- 3 Datacenters (East, West, Center)
- 100 servers per DC across 6 racks
- Complete network and power topology
- East DC: HPE DL360 Gen11
- West DC: HPE DL360 Gen11
- Center DC: HPE DL360 Gen11
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
    Interface, Cable, CableTermination, PowerPort, PowerOutlet,
    Rack, RackRole
)
from tenancy.models import Tenant


def create_cable_connection(termination_a, termination_b, cable_type='cat6', label=''):
    """Create a cable connection between two terminations."""
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


def wipe_database():
    """Wipe all devices, cables, and related infrastructure."""
    print("=" * 70)
    print("WIPING DATABASE")
    print("=" * 70)

    print("\nDeleting all cables...")
    Cable.objects.all().delete()
    print("  ✓ Deleted all cables")

    print("Deleting all devices...")
    Device.objects.all().delete()
    print("  ✓ Deleted all devices")

    print("Deleting all racks...")
    Rack.objects.all().delete()
    print("  ✓ Deleted all racks")

    print("Deleting all sites (except original test sites)...")
    Site.objects.exclude(slug__in=['dc-chicago', 'dc-newyork', 'dc-losangeles']).delete()
    print("  ✓ Deleted sites")

    print("\n" + "=" * 70)
    print("✓ Database wiped clean!")
    print("=" * 70)


def create_manufacturers():
    """Create all required manufacturers."""
    print("\nCreating manufacturers...")
    manufacturers = {}

    for mfr_data in [
        {'name': 'HPE', 'slug': 'hpe'},
        {'name': 'Cisco', 'slug': 'cisco'},
        {'name': 'Juniper Networks', 'slug': 'juniper'},
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

    return manufacturers


def create_device_types(manufacturers):
    """Create all device types."""
    print("\nCreating device types...")

    device_types_data = [
        # Servers
        {
            'manufacturer': manufacturers['hpe'],
            'model': 'ProLiant DL360 Gen11',
            'slug': 'hpe-dl360-gen11',
            'u_height': 1,
            'is_full_depth': True,
        },
        # Management Switches
        {
            'manufacturer': manufacturers['juniper'],
            'model': 'EX4300-48P',
            'slug': 'juniper-ex4300-48p',
            'u_height': 1,
            'is_full_depth': False,
        },
        # Production Switches
        {
            'manufacturer': manufacturers['cisco'],
            'model': 'NCS-55A1-24Q6H-S',
            'slug': 'cisco-ncs-55a1-24q6h-s',
            'u_height': 1,
            'is_full_depth': True,
        },
        # PDUs
        {
            'manufacturer': manufacturers['apc'],
            'model': 'AP8959',
            'slug': 'apc-ap8959',
            'u_height': 0,  # Zero-U
            'is_full_depth': False,
        },
    ]

    device_types = {}
    for dt_data in device_types_data:
        dt, created = DeviceType.objects.get_or_create(
            slug=dt_data['slug'],
            defaults=dt_data
        )
        if created:
            print(f"  ✓ Created: {dt.model}")
        else:
            print(f"  - Exists: {dt.model}")
        device_types[dt.slug] = dt

    return device_types


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
            print(f"  ✓ Created: {role.name}")
        else:
            print(f"  - Exists: {role.name}")
        roles[role.slug] = role

    return roles


def create_datacenters():
    """Create three datacenter sites."""
    print("\nCreating datacenters...")

    sites_data = [
        {
            'name': 'DC-East',
            'slug': 'dc-east',
            'status': 'active',
            'description': 'East Coast Datacenter',
        },
        {
            'name': 'DC-West',
            'slug': 'dc-west',
            'status': 'active',
            'description': 'West Coast Datacenter',
        },
        {
            'name': 'DC-Center',
            'slug': 'dc-center',
            'status': 'active',
            'description': 'Central US Datacenter',
        },
    ]

    sites = {}
    for site_data in sites_data:
        site, created = Site.objects.get_or_create(
            slug=site_data['slug'],
            defaults=site_data
        )
        if created:
            print(f"  ✓ Created: {site.name}")
        else:
            print(f"  - Exists: {site.name}")
        sites[site.slug] = site

    return sites


def create_racks(sites):
    """Create 6 racks per datacenter."""
    print("\nCreating racks...")

    rack_role, _ = RackRole.objects.get_or_create(
        name='Server Rack',
        slug='server-rack',
        defaults={'color': '2196f3'}
    )

    racks = []
    for site_slug, site in sites.items():
        site_prefix = site.slug.split('-')[1][:4].upper()  # EAST, WEST, CENT

        for rack_num in range(1, 7):  # 6 racks per DC
            rack_name = f"{site_prefix}-R{rack_num:02d}"
            rack, created = Rack.objects.get_or_create(
                site=site,
                name=rack_name,
                defaults={
                    'u_height': 42,
                    'role': rack_role,
                    'status': 'active',
                }
            )
            if created:
                print(f"  ✓ Created: {rack.name} at {site.name}")
            else:
                print(f"  - Exists: {rack.name}")
            racks.append(rack)

    return racks


def create_server_interfaces(server):
    """
    Create interfaces for a server:
    - 1 BMC interface (named 'bmc')
    - 1 Management interface
    - 2 Production SFP interfaces
    """
    interfaces = {}

    # BMC Interface
    bmc_mac = f"a0:36:9f:{server.pk % 256:02x}:{(server.pk // 256) % 256:02x}:{(server.pk // 65536) % 256:02x}"
    bmc_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='bmc',
        defaults={
            'type': '1000base-t',
            'mgmt_only': True,
            'mac_address': bmc_mac,
            'description': 'BMC Management Interface',
        }
    )
    interfaces['bmc'] = bmc_iface

    # Management NIC (PCI card)
    mgmt_mac = f"a0:36:9f:{(server.pk + 1000) % 256:02x}:{((server.pk + 1000) // 256) % 256:02x}:{((server.pk + 1000) // 65536) % 256:02x}"
    mgmt_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='mgmt0',
        defaults={
            'type': '1000base-t',
            'mac_address': mgmt_mac,
            'description': 'Management Interface (PCI Card)',
        }
    )
    interfaces['mgmt'] = mgmt_iface

    # Production NICs (SFP)
    for port_num in [1, 2]:
        prod_mac = f"3c:fd:fe:{server.pk % 256:02x}:{(server.pk // 256) % 256:02x}:{port_num:02x}"
        prod_iface, _ = Interface.objects.get_or_create(
            device=server,
            name=f'ens{port_num}f0',
            defaults={
                'type': '25gbase-x-sfp28',
                'mac_address': prod_mac,
                'description': f'Production Network SFP Interface {port_num}',
            }
        )
        interfaces[f'prod{port_num}'] = prod_iface

    return interfaces


def create_switch_interfaces(switch, port_count=48):
    """Create interfaces on a switch with appropriate naming."""
    interfaces = []

    if 'EX4300' in switch.device_type.model:
        # Juniper management switch
        iface_type = '1000base-t'
        name_format = lambda port: f"ge-0/0/{port - 1}"
    elif 'NCS-55A1' in switch.device_type.model:
        # Cisco production switch - 24 ports QSFP28 (100G)
        # We'll use the first 24 ports as broken out to 25G (each 100G = 4x25G)
        iface_type = '25gbase-x-sfp28'
        name_format = lambda port: f"HundredGigE0/0/0/{port}"
        port_count = 24  # Override for Cisco switch
    else:
        iface_type = '1000base-t'
        name_format = lambda port: f"Ethernet{port}"

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
                'maximum_draw': 800,
                'allocated_draw': 400,
            }
        )
        power_ports.append(port)

    return power_ports


def create_rack_infrastructure(rack, device_types, roles, tenant):
    """Create infrastructure for a rack."""
    infrastructure = {}

    site_prefix = rack.name.split('-')[0]
    rack_num = rack.name.split('-')[1]

    # Management Switch (Juniper EX4300)
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

    # Production Switches (Cisco NCS-55A1-24Q6H-S)
    for switch_id in ['A', 'B']:
        prod_switch_name = f"{site_prefix}-PROD-SW{switch_id}-{rack_num}"
        position = 41 if switch_id == 'A' else 40
        prod_switch, _ = Device.objects.get_or_create(
            name=prod_switch_name,
            defaults={
                'device_type': device_types['cisco-ncs-55a1-24q6h-s'],
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

    # PDUs
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


def connect_server(server, server_ifaces, infrastructure, port_counters):
    """Connect a server to rack infrastructure."""
    cables_created = 0

    # Get or create infrastructure interfaces
    if not hasattr(infrastructure['mgmt_switch'], '_interfaces'):
        infrastructure['mgmt_switch']._interfaces = create_switch_interfaces(
            infrastructure['mgmt_switch']
        )
    if not hasattr(infrastructure['prod_switch_a'], '_interfaces'):
        infrastructure['prod_switch_a']._interfaces = create_switch_interfaces(
            infrastructure['prod_switch_a']
        )
    if not hasattr(infrastructure['prod_switch_b'], '_interfaces'):
        infrastructure['prod_switch_b']._interfaces = create_switch_interfaces(
            infrastructure['prod_switch_b']
        )
    if not hasattr(infrastructure['pdu_a'], '_outlets'):
        infrastructure['pdu_a']._outlets = create_pdu_outlets(infrastructure['pdu_a'])
    if not hasattr(infrastructure['pdu_b'], '_outlets'):
        infrastructure['pdu_b']._outlets = create_pdu_outlets(infrastructure['pdu_b'])

    # BMC -> Management Switch
    if port_counters['mgmt'] < len(infrastructure['mgmt_switch']._interfaces):
        mgmt_port = infrastructure['mgmt_switch']._interfaces[port_counters['mgmt']]
        cable, created = create_cable_connection(
            server_ifaces['bmc'],
            mgmt_port,
            cable_type='cat6',
            label=f"{server.name}-BMC"
        )
        if created:
            cables_created += 1
        port_counters['mgmt'] += 1

    # Management NIC -> Management Switch
    if port_counters['mgmt'] < len(infrastructure['mgmt_switch']._interfaces):
        mgmt_port = infrastructure['mgmt_switch']._interfaces[port_counters['mgmt']]
        cable, created = create_cable_connection(
            server_ifaces['mgmt'],
            mgmt_port,
            cable_type='cat6',
            label=f"{server.name}-MGMT"
        )
        if created:
            cables_created += 1
        port_counters['mgmt'] += 1

    # Prod NIC 1 -> Prod Switch A (DAC cable)
    if port_counters['prod_a'] < len(infrastructure['prod_switch_a']._interfaces):
        prod_port = infrastructure['prod_switch_a']._interfaces[port_counters['prod_a']]
        cable, created = create_cable_connection(
            server_ifaces['prod1'],
            prod_port,
            cable_type='dac-active',
            label=f"{server.name}-PROD1"
        )
        if created:
            cables_created += 1
        port_counters['prod_a'] += 1

    # Prod NIC 2 -> Prod Switch B (DAC cable)
    if port_counters['prod_b'] < len(infrastructure['prod_switch_b']._interfaces):
        prod_port = infrastructure['prod_switch_b']._interfaces[port_counters['prod_b']]
        cable, created = create_cable_connection(
            server_ifaces['prod2'],
            prod_port,
            cable_type='dac-active',
            label=f"{server.name}-PROD2"
        )
        if created:
            cables_created += 1
        port_counters['prod_b'] += 1

    # Power connections
    power_ports = create_server_power_ports(server)

    # PSU1 -> PDU A
    if port_counters['pdu_a'] < len(infrastructure['pdu_a']._outlets):
        outlet = infrastructure['pdu_a']._outlets[port_counters['pdu_a']]
        cable, created = create_cable_connection(
            power_ports[0],
            outlet,
            cable_type='power',
            label=f"{server.name}-PSU1"
        )
        if created:
            cables_created += 1
        port_counters['pdu_a'] += 1

    # PSU2 -> PDU B
    if port_counters['pdu_b'] < len(infrastructure['pdu_b']._outlets):
        outlet = infrastructure['pdu_b']._outlets[port_counters['pdu_b']]
        cable, created = create_cable_connection(
            power_ports[1],
            outlet,
            cable_type='power',
            label=f"{server.name}-PSU2"
        )
        if created:
            cables_created += 1
        port_counters['pdu_b'] += 1

    return cables_created


def main():
    """Main execution function."""
    print("=" * 70)
    print("NetBox Infrastructure Creation")
    print("3 Datacenters | 100 Servers per DC | 6 Racks per DC")
    print("=" * 70)

    # Wipe database
    wipe_database()

    # Create base objects
    manufacturers = create_manufacturers()
    device_types = create_device_types(manufacturers)
    roles = create_device_roles()
    sites = create_datacenters()
    racks = create_racks(sites)

    # Get tenant
    tenant, _ = Tenant.objects.get_or_create(
        slug='baremetal-staging',
        defaults={'name': 'Baremetal Staging'}
    )

    # Create infrastructure
    print("\n" + "=" * 70)
    print("Creating Servers and Infrastructure")
    print("=" * 70)

    total_servers = 0
    total_cables = 0
    servers_per_rack = 17  # 100 servers / 6 racks ≈ 16-17 per rack

    for site_slug, site in sites.items():
        site_prefix = site.slug.split('-')[1][:4].upper()
        site_racks = [r for r in racks if r.site == site]

        print(f"\n{'='*70}")
        print(f"DATACENTER: {site.name}")
        print(f"{'='*70}")

        servers_in_dc = 0
        for rack_idx, rack in enumerate(site_racks):
            print(f"\n  Rack: {rack.name}")

            # Create rack infrastructure
            infrastructure = create_rack_infrastructure(rack, device_types, roles, tenant)
            print(f"    ✓ Infrastructure created (switches, PDUs)")

            # Port counters for this rack
            port_counters = {
                'mgmt': 0,
                'prod_a': 0,
                'prod_b': 0,
                'pdu_a': 0,
                'pdu_b': 0,
            }

            # Calculate servers for this rack
            if rack_idx < 4:
                servers_this_rack = 17
            else:
                servers_this_rack = 16  # Last 2 racks have 16 servers (4*17 + 2*16 = 100)

            # Create servers
            for server_num in range(1, servers_this_rack + 1):
                servers_in_dc += 1
                global_server_num = servers_in_dc

                server_name = f"{site_prefix}-SRV-{global_server_num:03d}"
                position = 39 - (server_num - 1)  # Start from U39 going down

                server, created = Device.objects.get_or_create(
                    name=server_name,
                    defaults={
                        'device_type': device_types['hpe-dl360-gen11'],
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
                    total_servers += 1

                    # Create interfaces
                    server_ifaces = create_server_interfaces(server)

                    # Connect to infrastructure
                    cables = connect_server(server, server_ifaces, infrastructure, port_counters)
                    total_cables += cables

            print(f"    ✓ Created {servers_this_rack} servers")
            print(f"    ✓ Total in {site.name}: {servers_in_dc}/100")

    # Summary
    print("\n" + "=" * 70)
    print("✓ INFRASTRUCTURE CREATION COMPLETED!")
    print("=" * 70)
    print(f"\nSummary:")
    print(f"  Datacenters:        {len(sites)}")
    print(f"  Racks:              {len(racks)} (6 per DC)")
    print(f"  Compute Servers:    {total_servers} (100 per DC)")
    print(f"  Management Switches: {len(racks)} (Juniper EX4300-48P)")
    print(f"  Production Switches: {len(racks) * 2} (Cisco NCS-55A1-24Q6H-S)")
    print(f"  PDUs:               {len(racks) * 2}")
    print(f"  Total Cables:       {total_cables}")
    print(f"\nServer Configuration:")
    print(f"  Model: HPE ProLiant DL360 Gen11")
    print(f"  Interfaces per server:")
    print(f"    - 1x BMC (bmc) → Management Switch (Cat6)")
    print(f"    - 1x Management (mgmt0) → Management Switch (Cat6)")
    print(f"    - 2x Production SFP (ens1f0, ens2f0) → Cisco switches (DAC)")
    print(f"    - 2x Power (PSU1, PSU2) → PDUs A & B")
    print(f"\nAccess NetBox: http://localhost:8000")
    print(f"Username: admin | Password: admin")
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
