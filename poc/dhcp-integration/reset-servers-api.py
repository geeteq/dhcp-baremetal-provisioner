#!/usr/bin/env python3
"""
Reset Servers to Offline State (API Version)
============================================
Standalone script that uses NetBox REST API to reset servers.
Can run on any machine with network access to NetBox.

This script:
- Queries all servers from NetBox via API
- Sets their status to 'offline'
- Clears IP assignments from BMC and management interfaces
- Provides detailed output of changes

Usage:
    python reset-servers-api.py [--dry-run] [--clear-ips] [--site SITE] [--limit N]

Options:
    --dry-run       Show what would be changed without making changes
    --clear-ips     Also clear IP assignments from BMC/management interfaces
    --site SITE     Only process servers in specified site
    --limit N       Only process N servers
    --status STATUS Only reset servers with this status (default: any)

Examples:
    # Dry run - see what would change
    python reset-servers-api.py --dry-run

    # Reset all servers to offline
    python reset-servers-api.py

    # Reset and clear IPs
    python reset-servers-api.py --clear-ips

    # Reset only servers in DC-East site
    python reset-servers-api.py --site dc-east --clear-ips

    # Reset only 10 servers
    python reset-servers-api.py --limit 10 --clear-ips
"""

import os
import sys
import json
import requests
import argparse
from typing import List, Dict, Optional


# Configuration
NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}


def get_servers(site_filter: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """Fetch servers from NetBox via API."""
    # Fetch more devices initially to account for filtering
    # Need at least 200 devices to skip the switches at the beginning
    fetch_limit = 2000 if not limit else max(200, limit * 10)  # Fetch 10x limit, minimum 200

    params = {
        'limit': fetch_limit,
    }

    if site_filter:
        params['site__name__iec'] = site_filter  # case-insensitive contains

    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        response.raise_for_status()

        all_devices = response.json()['results']

        # Filter for devices with 'server' in role name
        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        # Apply limit after filtering
        if limit:
            servers = servers[:limit]

        return servers
    except Exception as e:
        print(f"✗ Error fetching servers: {e}")
        return []


def update_device_state(device_id: int, device_name: str, dry_run: bool = False) -> bool:
    """Update device status to offline."""
    try:
        # First, get current device state
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
            headers=HEADERS,
            timeout=10
        )
        response.raise_for_status()
        device_data = response.json()

        current_status = device_data.get('status', {}).get('value', 'unknown')

        # Check if already offline
        if current_status == 'offline':
            print(f"    ✓ Already offline")
            return True

        if dry_run:
            print(f"    [DRY RUN] Would set: status={current_status}→offline")
            return True

        # Update device
        update_data = {
            'status': 'offline'
        }

        response = requests.patch(
            f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
            headers=HEADERS,
            json=update_data,
            timeout=10
        )
        response.raise_for_status()

        print(f"    ✓ Updated: status={current_status}→offline")
        return True

    except Exception as e:
        print(f"    ✗ Error updating device: {e}")
        return False


def get_interface_ips(device_id: int, interface_name: str) -> List[Dict]:
    """Get IP addresses assigned to an interface."""
    try:
        # First, get the interface
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/interfaces/",
            headers=HEADERS,
            params={
                'device_id': device_id,
                'name': interface_name
            },
            timeout=10
        )
        response.raise_for_status()

        interfaces = response.json()['results']
        if not interfaces:
            return []

        interface_id = interfaces[0]['id']

        # Get IPs assigned to this interface
        response = requests.get(
            f"{NETBOX_URL}/api/ipam/ip-addresses/",
            headers=HEADERS,
            params={
                'interface_id': interface_id
            },
            timeout=10
        )
        response.raise_for_status()

        return response.json()['results']

    except Exception as e:
        print(f"    ⚠ Error getting IPs for {interface_name}: {e}")
        return []


def clear_interface_ips(device_id: int, device_name: str,
                       interface_names: List[str] = ['bmc', 'mgmt0'],
                       dry_run: bool = False) -> int:
    """Clear IP assignments from specified interfaces."""
    cleared_count = 0

    for interface_name in interface_names:
        ips = get_interface_ips(device_id, interface_name)

        if not ips:
            continue

        for ip in ips:
            ip_address = ip['address']
            ip_id = ip['id']

            if dry_run:
                print(f"    [DRY RUN] Would delete IP {ip_address} from {interface_name}")
                cleared_count += 1
                continue

            try:
                response = requests.delete(
                    f"{NETBOX_URL}/api/ipam/ip-addresses/{ip_id}/",
                    headers=HEADERS,
                    timeout=10
                )
                response.raise_for_status()
                print(f"    → Deleted IP {ip_address} from {interface_name}")
                cleared_count += 1

            except Exception as e:
                print(f"    ✗ Error deleting IP {ip_address}: {e}")

    return cleared_count


def reset_servers(site_filter: Optional[str] = None,
                 limit: Optional[int] = None,
                 clear_ips: bool = False,
                 dry_run: bool = False) -> bool:
    """Reset servers to offline state."""

    print("=" * 70)
    print("RESET SERVERS TO OFFLINE STATE (API)")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    # Fetch servers
    print(f"✓ Fetching servers from NetBox...")
    if site_filter:
        print(f"  Filter: Site contains '{site_filter}'")
    if limit:
        print(f"  Limit: {limit} servers")

    servers = get_servers(site_filter, limit)

    if not servers:
        print("\n✗ No servers found")
        return False

    print(f"✓ Found {len(servers)} server(s)\n")

    # Statistics
    stats = {
        'total': len(servers),
        'already_offline': 0,
        'updated': 0,
        'ips_cleared': 0,
        'errors': 0
    }

    # Process each server
    for i, server in enumerate(servers, 1):
        device_name = server['name']
        device_id = server['id']
        site_name = server['site']['name'] if server.get('site') else 'Unknown'
        role_name = server['role']['name'] if server.get('role') else 'Unknown'
        current_status = server.get('status', {}).get('value', 'unknown')

        print(f"[{i}/{len(servers)}] {device_name}")
        print(f"  Site: {site_name}")
        print(f"  Role: {role_name}")
        print(f"  Status: {current_status}")

        try:
            # Check if already offline
            if current_status == 'offline':
                print(f"  ✓ Already offline")
                stats['already_offline'] += 1
            else:
                # Update device state
                if update_device_state(device_id, device_name, dry_run):
                    stats['updated'] += 1
                else:
                    stats['errors'] += 1

            # Clear IPs if requested
            if clear_ips:
                cleared = clear_interface_ips(device_id, device_name, dry_run=dry_run)
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
    print(f"Total servers processed:  {stats['total']}")
    print(f"Already offline:          {stats['already_offline']}")
    print(f"Updated to offline:       {stats['updated']}")

    if clear_ips:
        print(f"IP addresses cleared:     {stats['ips_cleared']}")

    if stats['errors'] > 0:
        print(f"Errors:                   {stats['errors']}")

    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN - No changes were made")
        print("Run without --dry-run to apply changes")
    else:
        print("\n✓ All changes applied successfully")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset server devices to offline state via API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would change
  python reset-servers-api.py --dry-run

  # Reset all servers to offline
  python reset-servers-api.py

  # Reset and clear IPs
  python reset-servers-api.py --clear-ips

  # Reset only servers in DC-East
  python reset-servers-api.py --site dc-east --clear-ips

  # Reset only 10 servers
  python reset-servers-api.py --limit 10 --clear-ips
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
        '--site',
        type=str,
        help='Only process servers in specified site (partial match)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Only process N servers'
    )

    args = parser.parse_args()

    try:
        success = reset_servers(
            site_filter=args.site,
            limit=args.limit,
            clear_ips=args.clear_ips,
            dry_run=args.dry_run
        )
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
