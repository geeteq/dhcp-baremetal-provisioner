#!/usr/bin/env python3
"""
Verify cable terminations have correct A/B orientation:
- A side: Server interface
- B side: Switch/PDU
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


def verify_cable_terminations():
    """Verify all cables have correct A/B termination order."""
    print("=" * 70)
    print("CABLE TERMINATION VERIFICATION")
    print("Expected: A=Server, B=Switch/PDU")
    print("=" * 70)

    # Get all cables
    cables = Cable.objects.all()
    total_cables = cables.count()

    print(f"\nChecking {total_cables} cables...\n")

    correct_order = 0
    reversed_order = 0
    ambiguous = 0
    errors = []

    compute_role = DeviceRole.objects.get(slug='compute-server')

    for cable in cables:
        # Get terminations for this cable
        terminations = list(CableTermination.objects.filter(cable=cable).order_by('id'))

        if len(terminations) != 2:
            errors.append(f"Cable {cable.id}: Has {len(terminations)} terminations (expected 2)")
            continue

        term_a = terminations[0]  # First termination created
        term_b = terminations[1]  # Second termination created

        # Get the devices for each termination
        if term_a.termination_type == ContentType.objects.get_for_model(Interface):
            device_a = Interface.objects.get(id=term_a.termination_id).device
        elif term_a.termination_type == ContentType.objects.get_for_model(PowerPort):
            device_a = PowerPort.objects.get(id=term_a.termination_id).device
        else:
            device_a = None

        if term_b.termination_type == ContentType.objects.get_for_model(Interface):
            device_b = Interface.objects.get(id=term_b.termination_id).device
        elif term_b.termination_type == ContentType.objects.get_for_model(PowerOutlet):
            device_b = PowerOutlet.objects.get(id=term_b.termination_id).device
        else:
            device_b = None

        if not device_a or not device_b:
            ambiguous += 1
            continue

        # Check if A is server and B is infrastructure
        is_a_server = device_a.role == compute_role
        is_b_server = device_b.role == compute_role

        if is_a_server and not is_b_server:
            correct_order += 1
        elif is_b_server and not is_a_server:
            reversed_order += 1
            errors.append(f"Cable {cable.id} ({cable.label}): Reversed - A={device_b.name}, B={device_a.name}")
        else:
            ambiguous += 1

    # Results
    print(f"{'='*70}")
    print("VERIFICATION RESULTS")
    print(f"{'='*70}")
    print(f"  Total Cables:           {total_cables}")
    print(f"  Correct Order (A→B):    {correct_order}")
    print(f"  Reversed Order (B→A):   {reversed_order}")
    print(f"  Ambiguous/Other:        {ambiguous}")

    if reversed_order > 0:
        print(f"\n⚠ Found {reversed_order} cables with reversed terminations")
        print("\nSample reversed cables:")
        for error in errors[:5]:
            print(f"  {error}")
    else:
        print(f"\n✓ All cables have correct termination order!")

    # Sample verification
    print(f"\n{'='*70}")
    print("SAMPLE CABLE VERIFICATION")
    print(f"{'='*70}")

    sample_cables = Cable.objects.filter(label__icontains='SRV-001')[:3]

    for cable in sample_cables:
        terminations = list(CableTermination.objects.filter(cable=cable).order_by('id'))

        if len(terminations) == 2:
            term_a = terminations[0]
            term_b = terminations[1]

            # Get interface/port names
            if term_a.termination_type == ContentType.objects.get_for_model(Interface):
                iface_a = Interface.objects.get(id=term_a.termination_id)
                name_a = f"{iface_a.device.name}/{iface_a.name}"
            elif term_a.termination_type == ContentType.objects.get_for_model(PowerPort):
                port_a = PowerPort.objects.get(id=term_a.termination_id)
                name_a = f"{port_a.device.name}/{port_a.name}"
            else:
                name_a = "Unknown"

            if term_b.termination_type == ContentType.objects.get_for_model(Interface):
                iface_b = Interface.objects.get(id=term_b.termination_id)
                name_b = f"{iface_b.device.name}/{iface_b.name}"
            elif term_b.termination_type == ContentType.objects.get_for_model(PowerOutlet):
                outlet_b = PowerOutlet.objects.get(id=term_b.termination_id)
                name_b = f"{outlet_b.device.name}/{outlet_b.name}"
            else:
                name_b = "Unknown"

            print(f"\nCable: {cable.label}")
            print(f"  Side A: {name_a}")
            print(f"  Side B: {name_b}")

    print(f"\n{'='*70}")


if __name__ == '__main__':
    try:
        verify_cable_terminations()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
