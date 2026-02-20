#!/usr/bin/env python3
"""
Fix cable terminations by setting proper cable_end (A or B)
Server side = A, Infrastructure side = B
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from dcim.models import Device, DeviceRole, Cable, CableTermination, Interface, PowerPort, PowerOutlet


def fix_cable_terminations():
    """Set proper cable_end for all terminations."""
    print("=" * 70)
    print("FIXING CABLE TERMINATIONS")
    print("Setting cable_end: A=Server, B=Infrastructure")
    print("=" * 70)

    # Get all cables
    cables = Cable.objects.all()
    total_cables = cables.count()

    print(f"\nProcessing {total_cables} cables...\n")

    compute_role = DeviceRole.objects.get(slug='compute-server')
    fixed_count = 0
    error_count = 0

    for idx, cable in enumerate(cables, 1):
        try:
            # Get terminations for this cable
            terminations = list(CableTermination.objects.filter(cable=cable).order_by('id'))

            if len(terminations) != 2:
                error_count += 1
                continue

            term_1 = terminations[0]
            term_2 = terminations[1]

            # Get the devices for each termination
            device_1 = None
            device_2 = None

            if term_1.termination_type == ContentType.objects.get_for_model(Interface):
                device_1 = Interface.objects.get(id=term_1.termination_id).device
            elif term_1.termination_type == ContentType.objects.get_for_model(PowerPort):
                device_1 = PowerPort.objects.get(id=term_1.termination_id).device

            if term_2.termination_type == ContentType.objects.get_for_model(Interface):
                device_2 = Interface.objects.get(id=term_2.termination_id).device
            elif term_2.termination_type == ContentType.objects.get_for_model(PowerOutlet):
                device_2 = PowerOutlet.objects.get(id=term_2.termination_id).device

            if not device_1 or not device_2:
                error_count += 1
                continue

            # Determine which is server (A) and which is infrastructure (B)
            is_1_server = device_1.role == compute_role
            is_2_server = device_2.role == compute_role

            if is_1_server and not is_2_server:
                # term_1 is server (A), term_2 is infrastructure (B)
                term_1.cable_end = 'A'
                term_2.cable_end = 'B'
            elif is_2_server and not is_1_server:
                # term_2 is server (A), term_1 is infrastructure (B)
                term_2.cable_end = 'A'
                term_1.cable_end = 'B'
            else:
                # Can't determine or both are same type
                error_count += 1
                continue

            # Save both terminations
            term_1.save()
            term_2.save()

            fixed_count += 1

            if idx % 100 == 0:
                print(f"  ✓ Processed {idx}/{total_cables} cables...")

        except Exception as e:
            error_count += 1
            continue

    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"  Total Cables:         {total_cables}")
    print(f"  Fixed:                {fixed_count}")
    print(f"  Errors/Skipped:       {error_count}")

    if fixed_count == total_cables:
        print(f"\n✓ All cable terminations fixed successfully!")
    else:
        print(f"\n⚠ Some cables had issues")

    print(f"{'='*70}")


if __name__ == '__main__':
    try:
        fix_cable_terminations()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
