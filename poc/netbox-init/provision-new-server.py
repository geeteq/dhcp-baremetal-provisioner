#!/usr/bin/env python3
"""
Provision New Server in NetBox
===============================
Simulates receiving and racking a new server:
- Creates HPE DL365 Gen11 server device
- Finds next available rack space in DC-West
- Assigns random MAC addresses
- Creates all interfaces and power ports
- Cables to switches and PDUs according to specs
- Sets lifecycle state to offline

Usage:
    docker cp provision-new-server.py netbox:/tmp/
    docker exec netbox python /tmp/provision-new-server.py
"""

import os
import sys
import django
import random

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from dcim.models import (
    Site, Manufacturer, DeviceType, DeviceRole, Device,
    Interface, Cable, CableTermination, PowerPort, PowerOutlet, Rack
)
from tenancy.models import Tenant


def find_available_rack_space(site):
    """Find the first available rack position in the site."""
    print(f"\nSearching for available rack space in {site.name}...")

    # Get all racks in this site
    racks = Rack.objects.filter(site=site).order_by('name')

    for rack in racks:
        # Get all devices in this rack
        devices_in_rack = Device.objects.filter(rack=rack).exclude(position__isnull=True)

        # Build set of occupied positions
        occupied = set()
        for device in devices_in_rack:
            # Each device occupies device.position through device.position + u_height - 1
            u_height = int(device.device_type.u_height)
            pos = int(device.position)
            for u in range(pos, pos + u_height):
                occupied.add(u)

        # Find first available 1U space (from bottom to top, skipping infrastructure at top)
        # Infrastructure is at U40-42, so search U1-39
        for position in range(1, 40):
            if position not in occupied:
                print(f"  ✓ Found available space: {rack.name} at U{position}")
                return rack, position

    print(f"  ✗ No available space found in {site.name}")
    return None, None


def generate_random_mac(oui_prefix):
    """Generate a random MAC address with given OUI prefix."""
    # OUI prefix is like "A0:36:9F" (HPE) or "3C:FD:FE" (Intel)
    suffix = f"{random.randint(0, 255):02X}:{random.randint(0, 255):02X}:{random.randint(0, 255):02X}"
    return f"{oui_prefix}:{suffix}"


def get_next_server_number(site):
    """Get the next available server number for this site."""
    site_prefix = site.slug.split('-')[1][:4].upper()

    # Get all compute servers at this site
    compute_role = DeviceRole.objects.get(slug='compute-server')
    servers = Device.objects.filter(site=site, role=compute_role, name__startswith=site_prefix)

    # Extract numbers from server names
    max_num = 0
    for server in servers:
        try:
            # Extract number from name like "WEST-SRV-123"
            num_str = server.name.split('-')[-1]
            num = int(num_str)
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            continue

    next_num = max_num + 1
    return next_num


def create_server_interfaces(server):
    """Create interfaces for the server with random MAC addresses."""
    print("\n  Creating interfaces...")
    interfaces = {}

    # BMC Interface (HPE iLO)
    bmc_mac = generate_random_mac("A0:36:9F")
    bmc_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='bmc',
        defaults={
            'type': '1000base-t',
            'mgmt_only': True,
            'mac_address': bmc_mac,
            'description': 'BMC Management Interface (iLO)',
        }
    )
    print(f"    ✓ bmc: {bmc_mac}")
    interfaces['bmc'] = bmc_iface

    # Management NIC
    mgmt_mac = generate_random_mac("A0:36:9F")
    mgmt_iface, _ = Interface.objects.get_or_create(
        device=server,
        name='mgmt0',
        defaults={
            'type': '1000base-t',
            'mac_address': mgmt_mac,
            'description': 'Management Interface',
        }
    )
    print(f"    ✓ mgmt0: {mgmt_mac}")
    interfaces['mgmt'] = mgmt_iface

    # Production NICs (SFP)
    for port_num in [1, 2]:
        prod_mac = generate_random_mac("3C:FD:FE")
        prod_iface, _ = Interface.objects.get_or_create(
            device=server,
            name=f'ens{port_num}f0',
            defaults={
                'type': '25gbase-x-sfp28',
                'mac_address': prod_mac,
                'description': f'Production Network SFP Interface {port_num}',
            }
        )
        print(f"    ✓ ens{port_num}f0: {prod_mac}")
        interfaces[f'prod{port_num}'] = prod_iface

    return interfaces


def create_server_power_ports(server):
    """Create dual power ports on the server."""
    print("\n  Creating power ports...")
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
        print(f"    ✓ PSU{psu_num}")
        power_ports.append(port)

    return power_ports


def create_cable_connection(termination_a, termination_b, cable_type='cat6', label=''):
    """Create a cable connection with proper A/B designation."""
    termination_a_content_type = ContentType.objects.get_for_model(termination_a)
    termination_b_content_type = ContentType.objects.get_for_model(termination_b)

    # Check if already cabled
    existing = CableTermination.objects.filter(
        termination_type=termination_a_content_type,
        termination_id=termination_a.id
    ).first()

    if existing:
        return existing.cable, False

    # Create cable
    cable = Cable.objects.create(
        type=cable_type,
        status='connected',
        label=label
    )

    # Create terminations
    CableTermination.objects.create(
        cable=cable,
        termination=termination_a,
        cable_end='A'  # Server side
    )

    CableTermination.objects.create(
        cable=cable,
        termination=termination_b,
        cable_end='B'  # Infrastructure side
    )

    return cable, True


def get_rack_infrastructure(rack):
    """Get infrastructure devices in the rack."""
    infrastructure = {}

    # Get management switch
    mgmt_switch = Device.objects.filter(
        rack=rack,
        role__slug='management-switch'
    ).first()

    # Get production switches
    prod_switches = Device.objects.filter(
        rack=rack,
        role__slug='production-switch'
    ).order_by('name')

    # Get PDUs
    pdus = Device.objects.filter(
        rack=rack,
        role__slug='pdu'
    ).order_by('name')

    if mgmt_switch:
        infrastructure['mgmt_switch'] = mgmt_switch
        # Get interfaces
        infrastructure['mgmt_switch_interfaces'] = list(
            Interface.objects.filter(device=mgmt_switch).order_by('name')
        )

    if prod_switches.count() >= 2:
        infrastructure['prod_switch_a'] = prod_switches[0]
        infrastructure['prod_switch_b'] = prod_switches[1]
        infrastructure['prod_switch_a_interfaces'] = list(
            Interface.objects.filter(device=prod_switches[0]).order_by('name')
        )
        infrastructure['prod_switch_b_interfaces'] = list(
            Interface.objects.filter(device=prod_switches[1]).order_by('name')
        )

    if pdus.count() >= 2:
        infrastructure['pdu_a'] = pdus[0]
        infrastructure['pdu_b'] = pdus[1]
        infrastructure['pdu_a_outlets'] = list(
            PowerOutlet.objects.filter(device=pdus[0]).order_by('name')
        )
        infrastructure['pdu_b_outlets'] = list(
            PowerOutlet.objects.filter(device=pdus[1]).order_by('name')
        )

    return infrastructure


def find_next_available_port(interfaces, exclude_ids=None):
    """Find next available port that's not cabled."""
    if exclude_ids is None:
        exclude_ids = set()

    for interface in interfaces:
        if interface.id in exclude_ids:
            continue

        # Check if already cabled
        existing = CableTermination.objects.filter(
            termination_type=ContentType.objects.get_for_model(interface),
            termination_id=interface.id
        ).first()

        if not existing:
            return interface

    return None


def wire_server(server, server_ifaces, power_ports, infrastructure):
    """Wire the server to rack infrastructure."""
    print("\n  Cabling server...")
    cables_created = 0

    if not infrastructure:
        print("    ✗ No infrastructure found in rack")
        return 0

    # BMC -> Management Switch
    if 'mgmt_switch_interfaces' in infrastructure:
        # Find available port in first 24 ports (BMC range)
        bmc_ports = [i for i in infrastructure['mgmt_switch_interfaces'] if i.name.endswith(('/0', '/1', '/2', '/3', '/4', '/5', '/6', '/7', '/8', '/9', '/10', '/11', '/12', '/13', '/14', '/15', '/16', '/17', '/18', '/19', '/20', '/21', '/22', '/23'))]
        switch_port = find_next_available_port(bmc_ports)

        if switch_port:
            cable, created = create_cable_connection(
                server_ifaces['bmc'],
                switch_port,
                cable_type='cat6',
                label=f"{server.name}-BMC"
            )
            if created:
                cables_created += 1
                print(f"    ✓ BMC → {infrastructure['mgmt_switch'].name}/{switch_port.name}")

    # Management NIC -> Management Switch
    if 'mgmt_switch_interfaces' in infrastructure:
        # Find available port in ports 24-47 (Management range)
        mgmt_ports = [i for i in infrastructure['mgmt_switch_interfaces'] if i.name.endswith(('/24', '/25', '/26', '/27', '/28', '/29', '/30', '/31', '/32', '/33', '/34', '/35', '/36', '/37', '/38', '/39', '/40', '/41', '/42', '/43', '/44', '/45', '/46', '/47'))]
        switch_port = find_next_available_port(mgmt_ports)

        if switch_port:
            cable, created = create_cable_connection(
                server_ifaces['mgmt'],
                switch_port,
                cable_type='cat6',
                label=f"{server.name}-MGMT"
            )
            if created:
                cables_created += 1
                print(f"    ✓ MGMT → {infrastructure['mgmt_switch'].name}/{switch_port.name}")

    # Production NIC 1 -> Production Switch A
    if 'prod_switch_a_interfaces' in infrastructure:
        switch_port = find_next_available_port(infrastructure['prod_switch_a_interfaces'])
        if switch_port:
            cable, created = create_cable_connection(
                server_ifaces['prod1'],
                switch_port,
                cable_type='dac-active',
                label=f"{server.name}-PROD1"
            )
            if created:
                cables_created += 1
                print(f"    ✓ PROD1 → {infrastructure['prod_switch_a'].name}/{switch_port.name}")

    # Production NIC 2 -> Production Switch B
    if 'prod_switch_b_interfaces' in infrastructure:
        switch_port = find_next_available_port(infrastructure['prod_switch_b_interfaces'])
        if switch_port:
            cable, created = create_cable_connection(
                server_ifaces['prod2'],
                switch_port,
                cable_type='dac-active',
                label=f"{server.name}-PROD2"
            )
            if created:
                cables_created += 1
                print(f"    ✓ PROD2 → {infrastructure['prod_switch_b'].name}/{switch_port.name}")

    # PSU1 -> PDU A
    if 'pdu_a_outlets' in infrastructure and len(power_ports) > 0:
        outlet = find_next_available_port(infrastructure['pdu_a_outlets'])
        if outlet:
            cable, created = create_cable_connection(
                power_ports[0],
                outlet,
                cable_type='power',
                label=f"{server.name}-PSU1"
            )
            if created:
                cables_created += 1
                print(f"    ✓ PSU1 → {infrastructure['pdu_a'].name}/{outlet.name}")

    # PSU2 -> PDU B
    if 'pdu_b_outlets' in infrastructure and len(power_ports) > 1:
        outlet = find_next_available_port(infrastructure['pdu_b_outlets'])
        if outlet:
            cable, created = create_cable_connection(
                power_ports[1],
                outlet,
                cable_type='power',
                label=f"{server.name}-PSU2"
            )
            if created:
                cables_created += 1
                print(f"    ✓ PSU2 → {infrastructure['pdu_b'].name}/{outlet.name}")

    return cables_created


@transaction.atomic
def main():
    """Main execution."""
    print("=" * 70)
    print("PROVISION NEW SERVER")
    print("=" * 70)
    print("\nSimulating receiving and racking a new HPE DL365 Gen11 server")
    print("=" * 70)

    # Get DC-West site
    try:
        site = Site.objects.get(slug='dc-west')
        print(f"\n✓ Target site: {site.name}")
    except Site.DoesNotExist:
        print("\n✗ Site 'dc-west' not found!")
        sys.exit(1)

    # Get device type
    try:
        device_type = DeviceType.objects.get(slug='hpe-dl360-gen11')
        print(f"✓ Device type: {device_type.model}")
    except DeviceType.DoesNotExist:
        print("\n✗ Device type 'hpe-dl360-gen11' not found!")
        sys.exit(1)

    # Get role
    compute_role = DeviceRole.objects.get(slug='compute-server')

    # Get tenant
    tenant = Tenant.objects.get(slug='baremetal-staging')

    # Find available rack space
    rack, position = find_available_rack_space(site)
    if not rack or not position:
        print("\n✗ No available rack space found!")
        sys.exit(1)

    # Get next server number
    server_num = get_next_server_number(site)
    server_name = f"WEST-SRV-{server_num:03d}"

    print(f"\n✓ Server name: {server_name}")
    print(f"✓ Rack position: {rack.name} U{position}")

    # Create server device
    print(f"\nCreating server device...")
    server = Device.objects.create(
        name=server_name,
        device_type=device_type,
        role=compute_role,
        site=site,
        rack=rack,
        position=position,
        face='front',
        status='active',
        tenant=tenant,
    )
    print(f"  ✓ Device created: {server.name}")

    # Create interfaces
    server_ifaces = create_server_interfaces(server)

    # Create power ports
    power_ports = create_server_power_ports(server)

    # Get rack infrastructure
    print(f"\n  Getting rack infrastructure...")
    infrastructure = get_rack_infrastructure(rack)
    if infrastructure:
        print(f"    ✓ Found management switch: {infrastructure.get('mgmt_switch', 'N/A')}")
        print(f"    ✓ Found production switches: {infrastructure.get('prod_switch_a', 'N/A')}, {infrastructure.get('prod_switch_b', 'N/A')}")
        print(f"    ✓ Found PDUs: {infrastructure.get('pdu_a', 'N/A')}, {infrastructure.get('pdu_b', 'N/A')}")

    # Wire server
    cables_created = wire_server(server, server_ifaces, power_ports, infrastructure)

    # Set lifecycle state to offline
    print(f"\n  Setting lifecycle state...")
    server.custom_field_data['lifecycle_state'] = 'offline'
    server.save()
    print(f"    ✓ Lifecycle state: offline")

    # Summary
    print("\n" + "=" * 70)
    print("✓ SERVER PROVISIONED SUCCESSFULLY!")
    print("=" * 70)
    print(f"\nServer Details:")
    print(f"  Name:           {server.name}")
    print(f"  Model:          {device_type.model}")
    print(f"  Site:           {site.name}")
    print(f"  Rack:           {rack.name}")
    print(f"  Position:       U{position}")
    print(f"  Lifecycle:      offline")
    print(f"\nInterfaces:")
    print(f"  BMC:            {server_ifaces['bmc'].mac_address}")
    print(f"  Management:     {server_ifaces['mgmt'].mac_address}")
    print(f"  Production 1:   {server_ifaces['prod1'].mac_address}")
    print(f"  Production 2:   {server_ifaces['prod2'].mac_address}")
    print(f"\nCables created: {cables_created}")
    print("=" * 70)
    print(f"\nServer is ready for discovery when powered on!")
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
