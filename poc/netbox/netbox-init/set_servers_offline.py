#!/usr/bin/env python3
"""
Set all compute servers to 'offline' lifecycle state
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, DeviceRole


def set_servers_offline():
    """Set all compute servers to offline state."""
    print("=" * 70)
    print("Setting All Servers to Offline State")
    print("=" * 70)

    # Get compute server role
    compute_role = DeviceRole.objects.get(slug='compute-server')

    # Get all compute servers
    servers = Device.objects.filter(role=compute_role)
    total_servers = servers.count()

    print(f"\nFound {total_servers} compute servers")
    print("Setting lifecycle_state to 'offline'...\n")

    updated = 0
    for server in servers:
        # Set custom field
        server.custom_field_data['lifecycle_state'] = 'offline'
        server.save()
        updated += 1

        if updated % 50 == 0:
            print(f"  ✓ Updated {updated}/{total_servers} servers...")

    print(f"\n✓ Successfully updated all {updated} servers to 'offline' state")
    print("=" * 70)


if __name__ == '__main__':
    try:
        set_servers_offline()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
