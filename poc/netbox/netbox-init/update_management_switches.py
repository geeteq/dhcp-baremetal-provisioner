#!/usr/bin/env python3
"""
Update all management switches to Juniper EX4300
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Manufacturer, DeviceType, DeviceRole, Device


def update_management_switches():
    """Update all management switches to Juniper EX4300."""
    print("=" * 70)
    print("Updating Management Switches to Juniper EX4300")
    print("=" * 70)

    # Get or create Juniper manufacturer
    juniper, created = Manufacturer.objects.get_or_create(
        slug='juniper',
        defaults={'name': 'Juniper Networks'}
    )
    if created:
        print(f"\n✓ Created manufacturer: {juniper.name}")
    else:
        print(f"\n- Manufacturer exists: {juniper.name}")

    # Create Juniper EX4300 device type
    print("\nCreating Juniper EX4300 device type...")
    ex4300_type, created = DeviceType.objects.get_or_create(
        slug='juniper-ex4300-48p',
        defaults={
            'manufacturer': juniper,
            'model': 'EX4300-48P',
            'slug': 'juniper-ex4300-48p',
            'u_height': 1,
            'is_full_depth': False,
            'part_number': 'EX4300-48P',
        }
    )
    if created:
        print(f"  ✓ Created device type: {ex4300_type.model}")
    else:
        print(f"  - Device type exists: {ex4300_type.model}")

    # Get management switch role
    mgmt_role = DeviceRole.objects.get(slug='management-switch')

    # Get all management switches
    mgmt_switches = Device.objects.filter(role=mgmt_role)
    switch_count = mgmt_switches.count()

    print(f"\nFound {switch_count} management switches to update...")

    # Update all management switches
    updated = 0
    for switch in mgmt_switches:
        old_type = switch.device_type.model
        switch.device_type = ex4300_type
        switch.save()
        updated += 1

        if updated % 5 == 0:
            print(f"  ✓ Updated {updated}/{switch_count} switches...")

    print(f"\n✓ Successfully updated all {updated} management switches")
    print(f"  Old type: Arista DCS-7050TX-48")
    print(f"  New type: Juniper EX4300-48P")

    # Update interface types on the switches
    print("\nUpdating interface naming convention...")
    from dcim.models import Interface

    interface_updates = 0
    for switch in mgmt_switches:
        interfaces = Interface.objects.filter(device=switch)
        for iface in interfaces:
            # Convert from "GigabitEthernet1" to "ge-0/0/0" format
            if iface.name.startswith('GigabitEthernet'):
                port_num = int(iface.name.replace('GigabitEthernet', ''))
                # Juniper format: ge-0/0/X (FPC/PIC/Port)
                new_name = f"ge-0/0/{port_num - 1}"
                iface.name = new_name
                iface.save()
                interface_updates += 1

    print(f"  ✓ Updated {interface_updates} interface names to Juniper format")

    print("\n" + "=" * 70)
    print("✓ Management switch update completed!")
    print("=" * 70)
    print(f"\nSummary:")
    print(f"  - Manufacturer: Juniper Networks")
    print(f"  - Model: EX4300-48P")
    print(f"  - Switches Updated: {updated}")
    print(f"  - Interface Format: ge-0/0/X (Juniper standard)")
    print(f"  - Ports: 48x 1GbE")
    print("=" * 70)


if __name__ == '__main__':
    try:
        update_management_switches()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
