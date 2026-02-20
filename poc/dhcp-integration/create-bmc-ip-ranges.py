#!/usr/bin/env python3
"""
Create BMC IP Ranges for Each Datacenter
=========================================
Creates /24 IP ranges in NetBox for BMC management, one per datacenter.

This script:
- Queries all sites (datacenters) in NetBox
- Creates a /24 subnet for each site within 10.55.0.0/16
- Assigns "BMC Management" role to each prefix
- Creates the parent 10.55.0.0/16 aggregate if needed

Address Allocation:
- Parent: 10.55.0.0/16 (BMC Management aggregate)
- Per-site: 10.55.X.0/24 where X is assigned sequentially
  - DC-Center: 10.55.1.0/24
  - DC-East:   10.55.2.0/24
  - DC-West:   10.55.3.0/24
  - DC-North:  10.55.4.0/24
  - DC-South:  10.55.5.0/24

Usage:
    docker cp create-bmc-ip-ranges.py netbox:/tmp/
    docker exec netbox python /tmp/create-bmc-ip-ranges.py [--dry-run]

Options:
    --dry-run    Show what would be created without making changes
"""

import os
import sys
import django
import ipaddress
import argparse

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Site
from ipam.models import Prefix, Role, RIR, Aggregate


def get_or_create_role():
    """Get or create the BMC Management role."""
    role_name = "BMC Management"
    role_slug = "bmc-management"

    try:
        role = Role.objects.get(slug=role_slug)
        print(f"✓ Found existing role: {role_name}")
        return role
    except Role.DoesNotExist:
        role = Role.objects.create(
            name=role_name,
            slug=role_slug,
            description="IP ranges for BMC (iLO/iDRAC) management interfaces"
        )
        print(f"✓ Created role: {role_name}")
        return role


def get_or_create_rir():
    """Get or create a RIR for private address space."""
    rir_name = "RFC1918"
    rir_slug = "rfc1918"

    try:
        rir = RIR.objects.get(slug=rir_slug)
        return rir
    except RIR.DoesNotExist:
        rir = RIR.objects.create(
            name=rir_name,
            slug=rir_slug,
            is_private=True,
            description="Private IP address space (RFC1918)"
        )
        print(f"✓ Created RIR: {rir_name}")
        return rir


def create_parent_aggregate(rir, dry_run=False):
    """Create the parent 10.55.0.0/16 aggregate."""
    parent_prefix = "10.55.0.0/16"

    # Check if aggregate exists
    existing = Aggregate.objects.filter(prefix=parent_prefix)
    if existing.exists():
        print(f"✓ Parent aggregate exists: {parent_prefix}")
        return existing.first()

    if dry_run:
        print(f"  [DRY RUN] Would create aggregate: {parent_prefix}")
        return None

    aggregate = Aggregate.objects.create(
        prefix=parent_prefix,
        rir=rir,
        description="BMC Management IP ranges for all datacenters"
    )
    print(f"✓ Created parent aggregate: {parent_prefix}")
    return aggregate


def create_bmc_ranges(dry_run=False):
    """Create BMC IP ranges for each datacenter."""
    print("=" * 70)
    print("CREATE BMC IP RANGES")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    # Get or create role
    if not dry_run:
        role = get_or_create_role()
        rir = get_or_create_rir()
        parent_aggregate = create_parent_aggregate(rir, dry_run)
    else:
        role = None
        rir = None
        parent_aggregate = None
        print("  [DRY RUN] Would create/verify BMC Management role")
        print("  [DRY RUN] Would create/verify RFC1918 RIR")
        print("  [DRY RUN] Would create parent aggregate: 10.55.0.0/16")

    # Get all sites
    sites = Site.objects.all().order_by('name')
    if not sites:
        print("\n✗ No sites found in NetBox")
        return False

    print(f"\nFound {sites.count()} site(s)")
    print()

    # Statistics
    stats = {
        'sites': sites.count(),
        'created': 0,
        'existing': 0,
        'skipped': 0
    }

    # Base network
    base_network = ipaddress.IPv4Network('10.55.0.0/16')

    # Allocate /24 subnets starting from 10.55.1.0/24
    # (Skip 10.55.0.0/24 to avoid confusion with parent)
    subnet_number = 1

    for site in sites:
        # Generate subnet for this site
        subnet_ip = f"10.55.{subnet_number}.0/24"
        subnet_network = ipaddress.IPv4Network(subnet_ip)

        # Check if subnet is within parent range
        if subnet_network.subnet_of(base_network):
            print(f"[{subnet_number}/{sites.count()}] {site.name}")
            print(f"  Site: {site.name}")
            print(f"  Subnet: {subnet_ip}")
            print(f"  Usable IPs: {subnet_network.num_addresses - 2} (excluding network/broadcast)")

            # Check if prefix already exists
            existing = Prefix.objects.filter(prefix=subnet_ip)
            if existing.exists():
                print(f"  ⚠ Prefix already exists")
                stats['existing'] += 1
            else:
                if dry_run:
                    print(f"  [DRY RUN] Would create prefix")
                    stats['created'] += 1
                else:
                    # Create prefix
                    prefix = Prefix.objects.create(
                        prefix=subnet_ip,
                        site=site,
                        role=role,
                        status='active',
                        is_pool=True,
                        description=f"BMC management network for {site.name}"
                    )
                    print(f"  ✓ Created prefix")
                    stats['created'] += 1

            subnet_number += 1
            print()
        else:
            print(f"✗ Subnet {subnet_ip} not within parent range")
            stats['skipped'] += 1

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total sites:          {stats['sites']}")
    print(f"Prefixes created:     {stats['created']}")
    print(f"Already existing:     {stats['existing']}")
    if stats['skipped'] > 0:
        print(f"Skipped:              {stats['skipped']}")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN - No changes were made")
        print("Run without --dry-run to create the prefixes")
    else:
        print("\n✓ BMC IP ranges created successfully")
        print("\nNext steps:")
        print("1. Review prefixes in NetBox: IPAM → Prefixes")
        print("2. Configure DHCP server to use these ranges")
        print("3. Update BMC discovery worker configuration")

    print("=" * 70)
    return True


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(
        description='Create BMC IP ranges for each datacenter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would be created
  python create-bmc-ip-ranges.py --dry-run

  # Create the IP ranges
  python create-bmc-ip-ranges.py

Address Allocation:
  Parent:     10.55.0.0/16 (aggregate)
  DC-Center:  10.55.1.0/24
  DC-East:    10.55.2.0/24
  DC-West:    10.55.3.0/24
  DC-North:   10.55.4.0/24
  DC-South:   10.55.5.0/24
  ... etc (one /24 per site)
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without making changes'
    )

    args = parser.parse_args()

    try:
        success = create_bmc_ranges(dry_run=args.dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
