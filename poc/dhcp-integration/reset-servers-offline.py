#!/usr/bin/env python3
"""
Reset All Servers to Offline State
===================================
Resets all compute servers in NetBox back to "offline" lifecycle state.
Useful for testing the BMC discovery workflow repeatedly.

This script can be run two ways:
1. Inside NetBox container (Django mode)
2. From anywhere using NetBox API (API mode)

Usage:
    # Django mode (inside NetBox container)
    docker cp reset-servers-offline.py netbox:/tmp/
    docker exec netbox python /tmp/reset-servers-offline.py --django

    # API mode (from anywhere)
    export NETBOX_URL=http://localhost:8000
    export NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
    python reset-servers-offline.py --api
"""

import os
import sys
import argparse


def reset_via_django():
    """Reset servers using Django ORM (run inside NetBox container)."""
    # Setup Django
    sys.path.insert(0, '/opt/netbox/netbox')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')

    import django
    django.setup()

    from dcim.models import Device, DeviceRole
    from ipam.models import IPAddress

    print("=" * 70)
    print("RESETTING SERVERS TO OFFLINE STATE (Django Mode)")
    print("=" * 70)

    # Get all compute servers
    try:
        compute_role = DeviceRole.objects.get(slug='compute-server')
    except DeviceRole.DoesNotExist:
        print("\n✗ Device role 'compute-server' not found!")
        sys.exit(1)

    servers = Device.objects.filter(role=compute_role)
    total_servers = servers.count()

    print(f"\nFound {total_servers} compute servers")
    print("\nResetting lifecycle states...")

    # Reset all servers to offline
    updated = 0
    for server in servers:
        old_state = server.custom_field_data.get('lifecycle_state', 'unknown')
        server.custom_field_data['lifecycle_state'] = 'offline'
        server.save()
        updated += 1

        if updated % 50 == 0:
            print(f"  ✓ Updated {updated}/{total_servers} servers...")

    print(f"\n✓ Reset {updated} servers to offline state")

    # Optionally remove BMC IP addresses
    print("\nRemoving BMC IP addresses...")
    bmc_ips = IPAddress.objects.filter(
        assigned_object_type__model='interface',
        description__icontains='DHCP'
    )
    ip_count = bmc_ips.count()

    if ip_count > 0:
        bmc_ips.delete()
        print(f"✓ Removed {ip_count} auto-assigned BMC IP addresses")
    else:
        print("  No auto-assigned IP addresses to remove")

    print("\n" + "=" * 70)
    print("✓ RESET COMPLETE!")
    print("=" * 70)
    print(f"\nAll {total_servers} servers are now in 'offline' state")
    print("Ready for BMC discovery testing!")
    print("=" * 70)


def reset_via_api():
    """Reset servers using NetBox API (run from anywhere)."""
    import requests

    NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000').rstrip('/')
    NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

    headers = {
        'Authorization': f'Token {NETBOX_TOKEN}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    print("=" * 70)
    print("RESETTING SERVERS TO OFFLINE STATE (API Mode)")
    print("=" * 70)
    print(f"\nNetBox URL: {NETBOX_URL}")

    # Get all compute servers
    print("\nFetching compute servers...")
    response = requests.get(
        f"{NETBOX_URL}/api/dcim/devices/",
        headers=headers,
        params={'role': 'compute-server', 'limit': 1000}
    )
    response.raise_for_status()

    data = response.json()
    servers = data['results']
    total_servers = data['count']

    print(f"Found {total_servers} compute servers")

    # Fetch all pages if needed
    while data['next']:
        response = requests.get(data['next'], headers=headers)
        response.raise_for_status()
        data = response.json()
        servers.extend(data['results'])

    print(f"\nResetting lifecycle states for {len(servers)} servers...")

    # Reset each server
    updated = 0
    errors = 0

    for server in servers:
        try:
            old_state = server.get('custom_fields', {}).get('lifecycle_state', 'unknown')

            # Update the server
            response = requests.patch(
                f"{NETBOX_URL}/api/dcim/devices/{server['id']}/",
                headers=headers,
                json={
                    'custom_fields': {
                        'lifecycle_state': 'offline'
                    }
                }
            )
            response.raise_for_status()
            updated += 1

            if updated % 50 == 0:
                print(f"  ✓ Updated {updated}/{len(servers)} servers...")

        except requests.HTTPError as e:
            errors += 1
            print(f"  ✗ Error updating {server['name']}: {e}")

    print(f"\n✓ Reset {updated} servers to offline state")
    if errors > 0:
        print(f"⚠ {errors} errors occurred")

    # Remove auto-assigned BMC IPs
    print("\nRemoving auto-assigned BMC IP addresses...")
    response = requests.get(
        f"{NETBOX_URL}/api/ipam/ip-addresses/",
        headers=headers,
        params={'description__ic': 'Auto-assigned by DHCP', 'limit': 1000}
    )
    response.raise_for_status()

    ips = response.json()['results']
    ip_count = len(ips)

    if ip_count > 0:
        for ip in ips:
            try:
                response = requests.delete(
                    f"{NETBOX_URL}/api/ipam/ip-addresses/{ip['id']}/",
                    headers=headers
                )
                response.raise_for_status()
            except requests.HTTPError:
                pass

        print(f"✓ Removed {ip_count} auto-assigned IP addresses")
    else:
        print("  No auto-assigned IP addresses to remove")

    print("\n" + "=" * 70)
    print("✓ RESET COMPLETE!")
    print("=" * 70)
    print(f"\nAll {updated} servers are now in 'offline' state")
    print("Ready for BMC discovery testing!")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Reset all servers to offline state in NetBox'
    )
    parser.add_argument(
        '--mode',
        choices=['django', 'api'],
        default='django',
        help='Execution mode: django (inside container) or api (from anywhere)'
    )
    parser.add_argument(
        '--django',
        action='store_const',
        const='django',
        dest='mode',
        help='Use Django mode (shortcut)'
    )
    parser.add_argument(
        '--api',
        action='store_const',
        const='api',
        dest='mode',
        help='Use API mode (shortcut)'
    )

    args = parser.parse_args()

    try:
        if args.mode == 'django':
            reset_via_django()
        else:
            reset_via_api()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
