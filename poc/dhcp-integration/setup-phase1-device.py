#!/usr/bin/env python3
"""
Setup Phase 1 Test Device
==========================
Creates or updates the CENT-SRV-035 device in NetBox for Phase 1 testing.

This script ensures:
- Device CENT-SRV-035 exists
- BMC interface exists with MAC A0:36:9F:77:05:00
- Device is in 'offline' state
- Management interfaces are set up

Usage:
    # Run inside NetBox container:
    docker cp setup-phase1-device.py netbox:/tmp/
    docker exec netbox python /tmp/setup-phase1-device.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Site, DeviceRole, DeviceType, Manufacturer, Interface
from ipam.models import IPAddress

DEVICE_NAME = "CENT-SRV-035"
BMC_MAC = "A0:36:9F:77:05:00"

def main():
    print("=" * 70)
    print("PHASE 1 DEVICE SETUP")
    print("=" * 70)
    print(f"\nSetting up device: {DEVICE_NAME}")
    print(f"BMC MAC: {BMC_MAC}\n")

    # Step 1: Get or create site
    print("[1/6] Getting site...")
    site = Site.objects.filter(name__icontains='central').first()
    if not site:
        site = Site.objects.first()
    if not site:
        print("  ✗ No sites found in NetBox. Create a site first.")
        sys.exit(1)
    print(f"  ✓ Using site: {site.name}")

    # Step 2: Get device role
    print("[2/6] Getting device role...")
    role = DeviceRole.objects.filter(name__icontains='server').first()
    if not role:
        role = DeviceRole.objects.first()
    if not role:
        print("  ✗ No device roles found. Create a device role first.")
        sys.exit(1)
    print(f"  ✓ Using role: {role.name}")

    # Step 3: Get device type
    print("[3/6] Getting device type...")
    manufacturer = Manufacturer.objects.filter(name='HPE').first()
    if not manufacturer:
        print("  ⚠ HPE manufacturer not found, using first available")
        manufacturer = Manufacturer.objects.first()

    device_type = DeviceType.objects.filter(manufacturer=manufacturer).first()
    if not device_type:
        device_type = DeviceType.objects.first()
    if not device_type:
        print("  ✗ No device types found. Create a device type first.")
        sys.exit(1)
    print(f"  ✓ Using device type: {device_type.model}")

    # Step 4: Create or update device
    print(f"[4/6] Creating/updating device: {DEVICE_NAME}...")
    device, created = Device.objects.get_or_create(
        name=DEVICE_NAME,
        defaults={
            'site': site,
            'device_role': role,
            'device_type': device_type,
            'status': 'active',
            'custom_field_data': {
                'lifecycle_state': 'offline'
            }
        }
    )

    if not created:
        # Update existing device
        device.site = site
        device.device_role = role
        device.device_type = device_type
        device.custom_field_data['lifecycle_state'] = 'offline'
        device.save()
        print(f"  ✓ Device updated: {DEVICE_NAME}")
    else:
        print(f"  ✓ Device created: {DEVICE_NAME}")

    # Step 5: Create BMC interface
    print("[5/6] Creating BMC interface...")
    bmc_interface, bmc_created = Interface.objects.get_or_create(
        device=device,
        name='bmc',
        defaults={
            'type': 'other',
            'mac_address': BMC_MAC,
            'enabled': True,
            'mgmt_only': True,
            'description': 'BMC management interface (iLO/iDRAC)'
        }
    )

    if not bmc_created:
        # Update existing BMC interface
        bmc_interface.mac_address = BMC_MAC
        bmc_interface.type = 'other'
        bmc_interface.enabled = True
        bmc_interface.mgmt_only = True
        bmc_interface.save()
        print(f"  ✓ BMC interface updated: {BMC_MAC}")
    else:
        print(f"  ✓ BMC interface created: {BMC_MAC}")

    # Clear any existing IP assignments on BMC interface
    existing_ips = IPAddress.objects.filter(
        assigned_object_type__model='interface',
        assigned_object_id=bmc_interface.id
    )
    if existing_ips.exists():
        count = existing_ips.count()
        existing_ips.delete()
        print(f"  ✓ Cleared {count} existing IP assignment(s) from BMC interface")

    # Step 6: Create management interface
    print("[6/6] Creating management interface...")
    mgmt_interface, mgmt_created = Interface.objects.get_or_create(
        device=device,
        name='mgmt0',
        defaults={
            'type': '1000base-t',
            'mac_address': 'A0:36:9F:77:05:01',  # Sequential MAC
            'enabled': True,
            'mgmt_only': True,
            'description': 'Management network interface'
        }
    )

    if mgmt_created:
        print(f"  ✓ Management interface created")
    else:
        print(f"  ✓ Management interface exists")

    # Summary
    print("\n" + "=" * 70)
    print("SETUP COMPLETE")
    print("=" * 70)
    print(f"\nDevice Configuration:")
    print(f"  Name:           {device.name}")
    print(f"  ID:             {device.id}")
    print(f"  Site:           {device.site.name}")
    print(f"  Role:           {device.device_role.name}")
    print(f"  Type:           {device.device_type.model}")
    print(f"  Lifecycle State: {device.custom_field_data.get('lifecycle_state', 'unknown')}")
    print(f"\nInterfaces:")
    print(f"  BMC (bmc):      {bmc_interface.mac_address}")
    print(f"  Management (mgmt0): {mgmt_interface.mac_address}")
    print(f"\n✓ Device ready for Phase 1 testing")
    print(f"\nRun the Phase 1 test:")
    print(f"  ./test-phase1.sh")
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
