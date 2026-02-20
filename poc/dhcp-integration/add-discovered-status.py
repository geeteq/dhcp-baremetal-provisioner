#!/usr/bin/env python3
"""
Add 'discovered' status to NetBox device choices
Run inside NetBox container
"""

import os
import sys

# Find and modify the DeviceStatusChoices file
choices_file = '/opt/netbox/netbox/dcim/choices.py'

print("Adding 'discovered' status to NetBox...")

# Read the file
with open(choices_file, 'r') as f:
    content = f.read()

# Check if discovered is already there
if "'discovered'" in content.lower() or '"discovered"' in content.lower():
    print("✓ 'discovered' status already exists!")
    sys.exit(0)

# Find DeviceStatusChoices and add discovered
if 'class DeviceStatusChoices' in content:
    # Add discovered status after offline
    content = content.replace(
        "STATUS_OFFLINE = 'offline'",
        "STATUS_OFFLINE = 'offline'\n    STATUS_DISCOVERED = 'discovered'"
    )

    # Add to CHOICES tuple
    content = content.replace(
        "(STATUS_OFFLINE, 'Offline', 'gray'),",
        "(STATUS_OFFLINE, 'Offline', 'gray'),\n        (STATUS_DISCOVERED, 'Discovered', 'cyan'),"
    )

    # Write back
    with open(choices_file, 'w') as f:
        f.write(content)

    print("✓ Added 'discovered' status to DeviceStatusChoices")
    print("\nRestart NetBox container for changes to take effect:")
    print("  docker restart netbox")
else:
    print("✗ Could not find DeviceStatusChoices class")
    sys.exit(1)
