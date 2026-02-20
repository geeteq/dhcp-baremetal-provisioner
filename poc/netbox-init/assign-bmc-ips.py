#!/usr/bin/env python3
"""
Assign BMC IP Addresses to Servers
===================================
Assigns random IP addresses from each datacenter's BMC subnet to server BMC interfaces.

IP Allocation by Site:
- DC-East:   10.22.0.1 - 10.22.1.254 (10.22.0.0/23)
- DC-West:   10.22.2.1 - 10.22.3.254 (10.22.2.0/23)
- DC-Center: 10.22.4.1 - 10.22.5.254 (10.22.4.0/23)

Usage:
    docker cp assign-bmc-ips.py netbox:/tmp/
    docker exec netbox python /tmp/assign-bmc-ips.py
"""

import os
import sys
import django
import random
import ipaddress

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.db import transaction
from dcim.models import Device, DeviceRole, Interface, Site
from ipam.models import IPAddress, Prefix


def get_available_ips(prefix_str):
    """Get list of available IPs from a prefix."""
    network = ipaddress.ip_network(prefix_str)
    # Exclude network, broadcast, and gateway (.0, .1, .255 equivalents)
    # Use .10 - .254 in each /24 block to be safe
    available = []

    for ip in network.hosts():
        ip_str = str(ip)
        # Skip .0, .1, .255 in each octet for safety
        last_octet = int(ip_str.split('.')[-1])
        if last_octet >= 10 and last_octet <= 250:
            # Check if IP already exists in NetBox
            if not IPAddress.objects.filter(address=f"{ip_str}/24").exists():
                available.append(ip_str)

    return available


def assign_ips_for_site(site, prefix_str):
    """Assign BMC IPs to all servers in a site."""
    print(f"\n{site.name}:")
    print(f"  BMC Subnet: {prefix_str}")

    # Get all compute servers at this site
    compute_role = DeviceRole.objects.get(slug='compute-server')
    servers = Device.objects.filter(site=site, role=compute_role).order_by('name')

    total_servers = servers.count()
    print(f"  Servers: {total_servers}")

    # Get available IPs
    available_ips = get_available_ips(prefix_str)
    print(f"  Available IPs: {len(available_ips)}")

    if len(available_ips) < total_servers:
        print(f"  ⚠ WARNING: Not enough IPs! Need {total_servers}, have {len(available_ips)}")
        return 0, 0

    # Shuffle for random assignment
    random.shuffle(available_ips)

    assigned = 0
    skipped = 0

    for idx, server in enumerate(servers):
        # Get BMC interface
        try:
            bmc_interface = Interface.objects.get(device=server, name='bmc')
        except Interface.DoesNotExist:
            print(f"  ✗ {server.name}: No BMC interface found")
            skipped += 1
            continue

        # Check if already has IP
        existing_ip = IPAddress.objects.filter(
            assigned_object_type__model='interface',
            assigned_object_id=bmc_interface.id
        ).first()

        if existing_ip:
            skipped += 1
            continue

        # Assign random IP
        ip_str = available_ips[idx]

        try:
            # Create IP address and assign to interface
            ip_address = IPAddress.objects.create(
                address=f"{ip_str}/24",
                status='active',
                dns_name=f"{server.name.lower()}-bmc",
                description=f"BMC for {server.name}"
            )

            # Associate with interface
            ip_address.assigned_object = bmc_interface
            ip_address.save()

            assigned += 1

            if assigned % 50 == 0:
                print(f"  ✓ Assigned {assigned}/{total_servers} IPs...")

        except Exception as e:
            print(f"  ✗ {server.name}: Failed to assign {ip_str} - {e}")
            skipped += 1

    print(f"  ✓ Assigned: {assigned}, Skipped: {skipped}")
    return assigned, skipped


@transaction.atomic
def main():
    """Main execution."""
    print("=" * 70)
    print("ASSIGN BMC IP ADDRESSES")
    print("=" * 70)
    print("\nAssigning random IPs from each site's BMC subnet")
    print("=" * 70)

    # Site to subnet mapping
    site_configs = [
        {'slug': 'dc-east', 'prefix': '10.22.0.0/23'},
        {'slug': 'dc-west', 'prefix': '10.22.2.0/23'},
        {'slug': 'dc-center', 'prefix': '10.22.4.0/23'},
    ]

    total_assigned = 0
    total_skipped = 0

    for config in site_configs:
        try:
            site = Site.objects.get(slug=config['slug'])
            assigned, skipped = assign_ips_for_site(site, config['prefix'])
            total_assigned += assigned
            total_skipped += skipped
        except Site.DoesNotExist:
            print(f"\n✗ Site '{config['slug']}' not found!")
            continue

    print("\n" + "=" * 70)
    print("✓ BMC IP ASSIGNMENT COMPLETE!")
    print("=" * 70)
    print(f"\nTotal IPs assigned: {total_assigned}")
    print(f"Total skipped: {total_skipped}")
    print("\nServers now have BMC IPs from their datacenter's subnet")
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
