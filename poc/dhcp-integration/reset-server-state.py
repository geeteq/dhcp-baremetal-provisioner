#!/usr/bin/env python3
"""
Reset Server State to Offline
==============================
Resets server(s) lifecycle state to 'offline' and clears all IP addresses
from BMC and management interfaces.

This script runs inside the NetBox container and directly accesses the database.

Actions performed:
- Sets lifecycle_state custom field to 'offline'
- Sets status field to 'offline'
- Clears all IP addresses from BMC interface
- Clears all IP addresses from management interface (mgmt0)

Usage:
    docker cp reset-server-state.py netbox:/tmp/
    docker exec netbox python /tmp/reset-server-state.py <SERVER_NAME> [--keep-ip]
    docker exec netbox python /tmp/reset-server-state.py --all [--keep-ip] [--role <role>] [--site <site>]

Examples:
    # Reset single server and clear all IPs
    docker exec netbox python /tmp/reset-server-state.py EAST-SRV-001

    # Reset single server but keep IPs
    docker exec netbox python /tmp/reset-server-state.py EAST-SRV-001 --keep-ip

    # Reset ALL servers
    docker exec netbox python /tmp/reset-server-state.py --all

    # Reset all servers in specific site
    docker exec netbox python /tmp/reset-server-state.py --all --site dc-east

    # Reset all servers with specific role
    docker exec netbox python /tmp/reset-server-state.py --all --role server
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface, DeviceRole, Site
from ipam.models import IPAddress


def reset_single_server(server, keep_ip=False):
    """Reset a single server to offline state."""
    print(f"\n{'='*70}")
    print(f"Processing: {server.name}")
    print(f"{'='*70}")
    print(f"  Site: {server.site.name}")
    print(f"  Role: {server.role.name}")

    # Get current state
    current_state = server.custom_field_data.get('lifecycle_state', 'unknown')
    current_status = server.status
    print(f"  Current state: {current_state}")
    print(f"  Current status: {current_status}")

    # Update to offline
    if current_state != 'offline' or current_status != 'offline':
        server.custom_field_data['lifecycle_state'] = 'offline'
        server.status = 'offline'
        server.save()
        print(f"  ✓ State updated: {current_state} → offline")
        print(f"  ✓ Status updated: {current_status} → offline")
    else:
        print(f"  - Already offline")

        # Clear IPs from BMC and Management interfaces (unless --keep-ip flag)
        if not keep_ip:
            # Clear BMC IPs
            print(f"\n[Clearing BMC IP]")
            try:
                bmc = Interface.objects.get(device=server, name='bmc')

                # Find IPs assigned to BMC
                bmc_ips = IPAddress.objects.filter(
                    assigned_object_type__model='interface',
                    assigned_object_id=bmc.id
                )

                if bmc_ips.exists():
                    for ip in bmc_ips:
                        print(f"  → Removing BMC IP: {ip.address}")
                        ip.delete()
                        print(f"  ✓ IP cleared")
                else:
                    print(f"  - No BMC IP assigned")

            except Interface.DoesNotExist:
                print(f"  ✗ No bmc interface found")

            # Clear Management IPs
            print(f"\n[Clearing Management IP]")
            try:
                mgmt = Interface.objects.get(device=server, name='mgmt0')

                # Find IPs assigned to mgmt0
                ips = IPAddress.objects.filter(
                    assigned_object_type__model='interface',
                    assigned_object_id=mgmt.id
                )

                if ips.exists():
                    for ip in ips:
                        print(f"  → Removing Management IP: {ip.address}")
                        ip.delete()
                        print(f"  ✓ IP cleared")
                else:
                    print(f"  - No management IP assigned")

            except Interface.DoesNotExist:
                print(f"  ✗ No mgmt0 interface found")
        else:
            print(f"\n[Keeping IPs - --keep-ip flag set]")

    print(f"  ✓ Reset complete")
    return True


def reset_server_state(server_name, keep_ip=False):
    """Reset server to offline state."""
    print("="*70)
    print("RESET SERVER STATE")
    print("="*70)

    try:
        # Get server
        server = Device.objects.get(name=server_name)
        success = reset_single_server(server, keep_ip)

        if success:
            print(f"\n{'='*70}")
            print(f"✓ SERVER RESET COMPLETE")
            print(f"{'='*70}")
            print(f"\nServer: {server.name}")
            print(f"State: offline")
            print(f"Status: offline")
            print(f"Ready for DHCP simulation")
            print("="*70)

        return success

    except Device.DoesNotExist:
        print(f"\n✗ Server '{server_name}' not found!")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def reset_all_servers(keep_ip=False, role_name=None, site_name=None):
    """Reset all servers to offline state."""
    print("="*70)
    print("RESET ALL SERVERS TO OFFLINE")
    print("="*70)

    # Build query
    query = Device.objects.all()

    # Filter by role
    if role_name:
        roles = DeviceRole.objects.filter(name__icontains=role_name)
        if not roles.exists():
            print(f"\n✗ No device role found matching '{role_name}'")
            return False
        query = query.filter(role__in=roles)
        print(f"Filter: Device role contains '{role_name}'")

    # Filter by site
    if site_name:
        sites = Site.objects.filter(name__icontains=site_name)
        if not sites.exists():
            print(f"\n✗ No site found matching '{site_name}'")
            return False
        query = query.filter(site__in=sites)
        print(f"Filter: Site contains '{site_name}'")

    # Get devices
    devices = list(query.select_related('site', 'role'))

    if not devices:
        print("\n✗ No devices found matching criteria")
        return False

    print(f"\nFound {len(devices)} device(s) to reset\n")

    # Statistics
    stats = {
        'total': len(devices),
        'success': 0,
        'errors': 0,
        'ips_cleared': 0
    }

    # Process each device
    for i, device in enumerate(devices, 1):
        try:
            print(f"\n[{i}/{len(devices)}] {device.name}")
            success = reset_single_server(device, keep_ip)
            if success:
                stats['success'] += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats['errors'] += 1

    # Print summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total devices processed:  {stats['total']}")
    print(f"Successfully reset:       {stats['success']}")
    if stats['errors'] > 0:
        print(f"Errors:                   {stats['errors']}")
    print("="*70)
    print("\n✓ All servers reset to offline state")
    print("Ready for DHCP simulation")
    print("="*70)

    return True


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Reset server(s) to offline state and clear IPs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset single server
  python reset-server-state.py EAST-SRV-001

  # Reset single server but keep IPs
  python reset-server-state.py EAST-SRV-001 --keep-ip

  # Reset ALL servers
  python reset-server-state.py --all

  # Reset all servers in specific site
  python reset-server-state.py --all --site dc-east

  # Reset all servers with specific role
  python reset-server-state.py --all --role server

  # Reset all but keep IPs
  python reset-server-state.py --all --keep-ip
        """
    )

    parser.add_argument(
        'server_name',
        nargs='?',
        help='Name of server to reset (required unless --all is used)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Reset all servers instead of a single server'
    )

    parser.add_argument(
        '--keep-ip',
        action='store_true',
        help='Keep IP addresses (do not clear them)'
    )

    parser.add_argument(
        '--role',
        type=str,
        help='Filter by device role (only with --all)'
    )

    parser.add_argument(
        '--site',
        type=str,
        help='Filter by site (only with --all)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.all:
        # Reset all servers
        success = reset_all_servers(
            keep_ip=args.keep_ip,
            role_name=args.role,
            site_name=args.site
        )
    elif args.server_name:
        # Reset single server
        if args.role or args.site:
            print("✗ Error: --role and --site can only be used with --all")
            sys.exit(1)
        success = reset_server_state(args.server_name, args.keep_ip)
    else:
        print("✗ Error: Either provide a server name or use --all")
        print("\nUsage:")
        print("  python reset-server-state.py <SERVER_NAME> [--keep-ip]")
        print("  python reset-server-state.py --all [options]")
        print("\nRun with --help for more information")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
