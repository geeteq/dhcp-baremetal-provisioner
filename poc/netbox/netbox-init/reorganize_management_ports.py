#!/usr/bin/env python3
"""
Reorganize management switch connections:
- Ports 1-24 (ge-0/0/0 to ge-0/0/23): Server BMC interfaces
- Ports 25-48 (ge-0/0/24 to ge-0/0/47): Server Management interfaces
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from dcim.models import Device, DeviceRole, Interface, Cable, CableTermination, Rack


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


def reorganize_management_connections():
    """Reorganize management switch connections by port range."""
    print("=" * 70)
    print("Reorganizing Management Switch Port Assignments")
    print("Ports 1-24:  Server BMC interfaces")
    print("Ports 25-48: Server Management interfaces")
    print("=" * 70)

    # Get all racks
    racks = Rack.objects.all().order_by('site__name', 'name')

    mgmt_switch_role = DeviceRole.objects.get(slug='management-switch')
    compute_role = DeviceRole.objects.get(slug='compute-server')

    total_racks = racks.count()
    total_reconnected = 0

    for rack_idx, rack in enumerate(racks, 1):
        print(f"\nRack {rack_idx}/{total_racks}: {rack.name} at {rack.site.name}")

        # Get management switch in this rack
        mgmt_switch = Device.objects.filter(
            rack=rack,
            role=mgmt_switch_role
        ).first()

        if not mgmt_switch:
            print(f"  ✗ No management switch found")
            continue

        # Get servers in this rack
        servers = Device.objects.filter(
            rack=rack,
            role=compute_role
        ).order_by('position')

        server_count = servers.count()
        print(f"  Management Switch: {mgmt_switch.name}")
        print(f"  Servers: {server_count}")

        # Get all switch interfaces
        switch_interfaces = list(Interface.objects.filter(
            device=mgmt_switch
        ).order_by('name'))

        # Delete existing cables to this management switch
        print(f"  Removing old connections...")
        interface_ids = [iface.id for iface in switch_interfaces]
        cable_terms = CableTermination.objects.filter(
            termination_type=ContentType.objects.get_for_model(Interface),
            termination_id__in=interface_ids
        )
        cables_to_delete = Cable.objects.filter(
            id__in=cable_terms.values_list('cable_id', flat=True)
        )
        deleted_count = cables_to_delete.count()
        cables_to_delete.delete()
        print(f"    ✓ Deleted {deleted_count} old cables")

        # Reconnect with proper port assignments
        print(f"  Reconnecting with proper port assignments...")

        bmc_port_idx = 0  # Start at port 0 (ge-0/0/0)
        mgmt_port_idx = 24  # Start at port 24 (ge-0/0/24)

        for server in servers:
            # Get server interfaces
            bmc_iface = Interface.objects.filter(device=server, name='bmc').first()
            mgmt_iface = Interface.objects.filter(device=server, name='mgmt0').first()

            # Connect BMC to ports 1-24
            if bmc_iface and bmc_port_idx < 24:
                switch_port = switch_interfaces[bmc_port_idx]
                cable, created = create_cable_connection(
                    bmc_iface,
                    switch_port,
                    cable_type='cat6',
                    label=f"{server.name}-BMC"
                )
                if created:
                    total_reconnected += 1
                bmc_port_idx += 1

            # Connect Management to ports 25-48
            if mgmt_iface and mgmt_port_idx < 48:
                switch_port = switch_interfaces[mgmt_port_idx]
                cable, created = create_cable_connection(
                    mgmt_iface,
                    switch_port,
                    cable_type='cat6',
                    label=f"{server.name}-MGMT"
                )
                if created:
                    total_reconnected += 1
                mgmt_port_idx += 1

        print(f"    ✓ BMC ports used: 1-{bmc_port_idx}")
        print(f"    ✓ Management ports used: 25-{mgmt_port_idx}")

    print("\n" + "=" * 70)
    print("✓ REORGANIZATION COMPLETED")
    print("=" * 70)
    print(f"\nTotal cables reconnected: {total_reconnected}")
    print("\nPort Assignment:")
    print("  Ports 1-24  (ge-0/0/0 to ge-0/0/23):  Server BMC interfaces")
    print("  Ports 25-48 (ge-0/0/24 to ge-0/0/47): Server Management interfaces")
    print("=" * 70)


if __name__ == '__main__':
    try:
        reorganize_management_connections()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
