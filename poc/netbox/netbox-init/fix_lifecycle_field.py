#!/usr/bin/env python3
"""
Fix the lifecycle_state custom field by linking it to the ChoiceSet
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from extras.models import CustomField, CustomFieldChoiceSet

def fix_lifecycle_field():
    """Update the lifecycle_state field with the proper ChoiceSet."""
    print("Fixing lifecycle_state custom field...")

    try:
        # Get the choice set
        choice_set = CustomFieldChoiceSet.objects.get(name='Lifecycle States')
        print(f"  ✓ Found choice set: {choice_set.name}")

        # Get the custom field
        field = CustomField.objects.get(name='lifecycle_state')
        print(f"  ✓ Found custom field: {field.name}")
        print(f"    Current choice_set: {field.choice_set}")

        # Update the field
        field.choice_set = choice_set
        field.save()
        print(f"  ✓ Updated custom field with choice_set")
        print(f"    New choice_set: {field.choice_set}")

        print("\n✓ Fix completed successfully!")

    except CustomFieldChoiceSet.DoesNotExist:
        print("  ✗ Error: Lifecycle States choice set not found")
        sys.exit(1)
    except CustomField.DoesNotExist:
        print("  ✗ Error: lifecycle_state custom field not found")
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    fix_lifecycle_field()
