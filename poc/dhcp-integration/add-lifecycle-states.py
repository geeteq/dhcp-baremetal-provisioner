#!/usr/bin/env python3
"""
Add Additional Lifecycle States to NetBox
==========================================
Extends the lifecycle_state custom field with new states for automation workflow:
- discovered (BMC detected on network)
- provisioning (being configured)
- ready (ready for tenant assignment)

Run this script against your NetBox instance to add the new states.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from extras.models import CustomField, CustomFieldChoiceSet


def add_lifecycle_states():
    """Add new lifecycle states to the choice set."""
    print("=" * 70)
    print("ADDING LIFECYCLE STATES TO NETBOX")
    print("=" * 70)

    # Get the lifecycle state custom field
    try:
        cf = CustomField.objects.get(name='lifecycle_state')
        print(f"\n✓ Found custom field: {cf.name}")
    except CustomField.DoesNotExist:
        print("\n✗ Custom field 'lifecycle_state' not found!")
        print("Run the NetBox init script first to create the field.")
        sys.exit(1)

    # Get the choice set
    choice_set = cf.choice_set
    if not choice_set:
        print("\n✗ No choice set associated with lifecycle_state field!")
        sys.exit(1)

    print(f"✓ Found choice set: {choice_set.name}")

    # Current choices
    current_choices = choice_set.extra_choices
    print(f"\nCurrent choices ({len(current_choices)}):")
    for value, label in current_choices:
        print(f"  - {value}: {label}")

    # New choices to add
    new_choices = [
        ['discovered', 'Discovered'],      # BMC detected via DHCP
        ['provisioning', 'Provisioning'],  # Being configured
        ['ready', 'Ready'],                # Ready for tenant assignment
    ]

    # Complete lifecycle workflow choices (in logical order)
    complete_choices = [
        ['offline', 'Offline'],            # Initial state
        ['discovered', 'Discovered'],      # BMC detected
        ['provisioning', 'Provisioning'],  # Being configured
        ['ready', 'Ready'],                # Ready for assignment
        ['active', 'Active'],              # In production
        ['maintenance', 'Maintenance'],    # Undergoing maintenance
        ['decommissioned', 'Decommissioned'],  # End of life
        ['failed', 'Failed'],              # Hardware failure
    ]

    # Update choice set
    print(f"\nUpdating choice set with complete lifecycle workflow...")
    choice_set.extra_choices = complete_choices
    choice_set.save()

    print("\n✓ Choice set updated successfully!")
    print(f"\nComplete lifecycle workflow ({len(complete_choices)} states):")
    for value, label in complete_choices:
        print(f"  - {value}: {label}")

    print("\n" + "=" * 70)
    print("State Transition Flow:")
    print("=" * 70)
    print("""
    offline         → BMC DHCP detected
    discovered      → Firmware/config applied
    provisioning    → Validation passed
    ready           → Assigned to tenant
    active          → Scheduled maintenance
    maintenance     → Back to production
    active          → Hardware failure
    failed          → Repaired/replaced
    active          → End of service
    decommissioned
    """)

    print("=" * 70)
    print("✓ LIFECYCLE STATES CONFIGURED!")
    print("=" * 70)


if __name__ == '__main__':
    try:
        add_lifecycle_states()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
