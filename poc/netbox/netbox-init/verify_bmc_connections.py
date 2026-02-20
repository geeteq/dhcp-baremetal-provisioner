#!/usr/bin/env python3
"""
Verify and fix BMC connections to management switches
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from dcim.models import Device, DeviceRole, Interface, Cable, CableTermination


def verify_and_fix_bmc_connections():
    """Verify all BMC ports are connected to the correct management switch."""
    print("=" * 70)
    print("Verifying BMC Connections to Management Switches")
    print("=" * 70)

    # Get all compute servers
    compute_role = DeviceRole.objects.get(slug='compute-server')
    servers = Device.objects.filter(role=compute_role).select_related('rack', 'site')

    total_servers = servers.count()
    print(f"\nChecking {total_servers} servers...\n")

    correct_connections = 0
    missing_connections = 0
    wrong_connections = 0
    fixed = 0

    for idx, server in enumerate(servers, 1):
        # Get BMC interface
        bmc_interface = Interface.objects.filter(device=server, name='bmc').first()

        if not bmc_interface:
            print(f"  ✗ {server.name}: No BMC interface found")
            continue

        # Get the expected management switch (in the same rack)
        rack = server.rack
        if not rack:
            print(f"  ✗ {server.name}: No rack assigned")
            continue

        # Find management switch in the same rack
        mgmt_switch_role = DeviceRole.objects.get(slug='management-switch')
        mgmt_switch = Device.objects.filter(
            rack=rack,
            role=mgmt_switch_role
        ).first()

        if not mgmt_switch:
            print(f"  ✗ {server.name}: No management switch found in rack {rack.name}")
            continue

        # Check if BMC interface has a cable
        bmc_termination = CableTermination.objects.filter(
            termination_type=ContentType.objects.get_for_model(Interface),
            termination_id=bmc_interface.id
        ).first()

        if bmc_termination:
            # BMC has a cable, check if it goes to the right switch
            cable = bmc_termination.cable

            # Get the other end of the cable
            other_terminations = CableTermination.objects.filter(
                cable=cable
            ).exclude(termination_id=bmc_interface.id)

            if other_terminations:
                other_term = other_terminations.first()
                # Get the interface on the other end
                other_interface = Interface.objects.filter(id=other_term.termination_id).first()

                if other_interface and other_interface.device == mgmt_switch:
                    correct_connections += 1
                    if idx % 50 == 0:
                        print(f"  ✓ Checked {idx}/{total_servers} servers...")
                else:
                    # Connected to wrong device
                    print(f"  ⚠ {server.name}: BMC connected to wrong device")
                    wrong_connections += 1
            else:
                # Cable exists but no other end?
                print(f"  ⚠ {server.name}: BMC cable incomplete")
                missing_connections += 1
        else:
            # No cable at all
            print(f"  ⚠ {server.name}: BMC not connected")
            missing_connections += 1

    print(f"\n{'='*70}")
    print("VERIFICATION RESULTS")
    print(f"{'='*70}")
    print(f"  Total Servers:        {total_servers}")
    print(f"  Correct Connections:  {correct_connections}")
    print(f"  Missing Connections:  {missing_connections}")
    print(f"  Wrong Connections:    {wrong_connections}")

    if correct_connections == total_servers:
        print(f"\n✓ All BMC ports correctly connected!")
    else:
        print(f"\n⚠ Issues found: {missing_connections + wrong_connections} servers need attention")

    print("=" * 70)


if __name__ == '__main__':
    try:
        verify_and_fix_bmc_connections()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
