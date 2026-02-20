#!/usr/bin/env python3
"""
Clean up incorrectly populated devices and repopulate properly
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, DeviceRole, Cable, CableTermination, Interface, PowerPort
from tenancy.models import Tenant


def cleanup_infrastructure():
    """Remove all compute servers, switches, PDUs and their cables."""
    print("=" * 70)
    print("Cleaning Up Infrastructure")
    print("=" * 70)

    # Get roles
    compute_role = DeviceRole.objects.filter(slug='compute-server').first()
    mgmt_switch_role = DeviceRole.objects.filter(slug='management-switch').first()
    prod_switch_role = DeviceRole.objects.filter(slug='production-switch').first()
    pdu_role = DeviceRole.objects.filter(slug='pdu').first()

    roles_to_delete = [r for r in [compute_role, mgmt_switch_role, prod_switch_role, pdu_role] if r]

    # Count devices
    devices_to_delete = Device.objects.filter(role__in=roles_to_delete)
    count = devices_to_delete.count()

    print(f"\nFound {count} devices to delete...")

    # Delete cables first (they reference the devices)
    print("Deleting cables...")
    Cable.objects.all().delete()
    print("  ✓ All cables deleted")

    # Delete devices
    print(f"Deleting {count} devices...")
    devices_to_delete.delete()
    print(f"  ✓ All devices deleted")

    print("\n" + "=" * 70)
    print("✓ Cleanup completed!")
    print("=" * 70)


if __name__ == '__main__':
    try:
        cleanup_infrastructure()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
