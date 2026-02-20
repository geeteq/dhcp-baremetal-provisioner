#!/usr/bin/env python3
"""
Set All Servers to Offline State
==================================
Resets all server devices in NetBox to 'offline' lifecycle state.

This script:
- Queries all devices with role containing 'server'
- Sets their lifecycle_state to 'offline'
- Optionally adds journal entries
- Clears IP assignments from BMC and management interfaces
- Provides detailed output of changes

Usage:
    # Run inside NetBox container:
    docker cp set-all-servers-offline.py netbox:/tmp/
    docker exec netbox python /tmp/set-all-servers-offline.py

Options:
    --dry-run           Show what would be changed without making changes
    --clear-ips         Also clear IP assignments from BMC/management interfaces
    --add-journal       Add journal entries for each change
    --site <name>       Only process devices in specified site
    --role <name>       Only process devices with specified role (default: server)
"""

import os
import sys
import django
import argparse

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, DeviceRole, Site
from ipam.models import IPAddress
from extras.models import JournalEntry
from django.contrib.contenttypes.models import ContentType


def add_journal_entry(device, message, kind='info'):
    """Add a journal entry to a device."""
    try:
        device_ct = ContentType.objects.get_for_model(device)
        JournalEntry.objects.create(
            assigned_object_type=device_ct,
            assigned_object_id=device.id,
            kind=kind,
            comments=message
        )
        return True
    except Exception as e:
        print(f"    ⚠ Failed to add journal entry: {e}")
        return False


def clear_interface_ips(device, interface_names=['bmc', 'mgmt0'], dry_run=False):
    """Clear IP assignments from specified interfaces."""
    cleared_count = 0

    for interface in device.interfaces.filter(name__in=interface_names):
        ips = IPAddress.objects.filter(
            assigned_object_type__model='interface',
            assigned_object_id=interface.id
        )

        if ips.exists():
            for ip in ips:
                if not dry_run:
                    # Delete the IP address completely
                    ip.delete()
                print(f"    → Deleted IP {ip.address} from {interface.name}")
                cleared_count += 1

    return cleared_count


def reset_servers_to_offline(dry_run=False, clear_ips=False, add_journals=False,
                              site_name=None, role_name='server'):
    """Reset all servers to offline state."""

    print("=" * 70)
    print("SET ALL SERVERS TO OFFLINE STATE")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    # Build query
    query = Device.objects.all()

    # Filter by role
    if role_name:
        roles = DeviceRole.objects.filter(name__icontains=role_name)
        if not roles.exists():
            print(f"✗ No device role found matching '{role_name}'")
            return
        query = query.filter(role__in=roles)
        print(f"Filter: Device role contains '{role_name}'")

    # Filter by site
    if site_name:
        sites = Site.objects.filter(name__icontains=site_name)
        if not sites.exists():
            print(f"✗ No site found matching '{site_name}'")
            return
        query = query.filter(site__in=sites)
        print(f"Filter: Site contains '{site_name}'")

    # Get devices
    devices = list(query.select_related('site', 'role'))

    if not devices:
        print("\n✗ No devices found matching criteria")
        return

    print(f"\nFound {len(devices)} device(s) to process\n")

    # Statistics
    stats = {
        'total': len(devices),
        'already_offline': 0,
        'changed': 0,
        'ips_cleared': 0,
        'journals_added': 0,
        'errors': 0
    }

    # Process each device
    for i, device in enumerate(devices, 1):
        current_state = device.custom_field_data.get('lifecycle_state', 'unknown')
        current_status = device.status

        print(f"[{i}/{len(devices)}] {device.name}")
        print(f"  Site: {device.site.name}")
        print(f"  Role: {device.role.name}")
        print(f"  Status: {current_status}")
        print(f"  Lifecycle state: {current_state}")

        try:
            # Check if already offline in both fields
            if current_status == 'offline' and current_state == 'offline':
                print(f"  ✓ Already offline")
                stats['already_offline'] += 1
            else:
                # Set to offline
                if not dry_run:
                    device.status = 'offline'
                    device.custom_field_data['lifecycle_state'] = 'offline'
                    device.save()
                print(f"  ✓ Changed: status={current_status}→offline, lifecycle={current_state}→offline")
                stats['changed'] += 1

                # Add journal entry
                if add_journals and not dry_run:
                    if add_journal_entry(
                        device,
                        f"Device reset to offline (status: {current_status}→offline, lifecycle: {current_state}→offline)",
                        kind='info'
                    ):
                        stats['journals_added'] += 1

            # Clear IPs if requested
            if clear_ips:
                cleared = clear_interface_ips(device, dry_run=dry_run)
                stats['ips_cleared'] += cleared

            print()

        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats['errors'] += 1
            print()

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total devices processed:  {stats['total']}")
    print(f"Already offline:          {stats['already_offline']}")
    print(f"Changed to offline:       {stats['changed']}")

    if clear_ips:
        print(f"IP addresses cleared:     {stats['ips_cleared']}")

    if add_journals:
        print(f"Journal entries added:    {stats['journals_added']}")

    if stats['errors'] > 0:
        print(f"Errors:                   {stats['errors']}")

    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN - No changes were made")
        print("Run without --dry-run to apply changes")
    else:
        print("\n✓ All changes applied successfully")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset all server devices to offline state',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would change
  python set-all-servers-offline.py --dry-run

  # Reset all servers to offline
  python set-all-servers-offline.py

  # Reset and clear IPs
  python set-all-servers-offline.py --clear-ips

  # Reset with journal entries
  python set-all-servers-offline.py --add-journal

  # Reset only servers in DC-East site
  python set-all-servers-offline.py --site dc-east

  # Reset only specific role
  python set-all-servers-offline.py --role "rack server"

  # Full reset with all options
  python set-all-servers-offline.py --clear-ips --add-journal
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making changes'
    )

    parser.add_argument(
        '--clear-ips',
        action='store_true',
        help='Clear IP assignments from BMC and management interfaces'
    )

    parser.add_argument(
        '--add-journal',
        action='store_true',
        help='Add journal entries for each change'
    )

    parser.add_argument(
        '--site',
        type=str,
        help='Only process devices in specified site (partial match)'
    )

    parser.add_argument(
        '--role',
        type=str,
        default='server',
        help='Only process devices with specified role (default: server)'
    )

    args = parser.parse_args()

    try:
        reset_servers_to_offline(
            dry_run=args.dry_run,
            clear_ips=args.clear_ips,
            add_journals=args.add_journal,
            site_name=args.site,
            role_name=args.role
        )
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
