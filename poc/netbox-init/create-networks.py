#!/usr/bin/env python3
"""
Create Network Infrastructure in NetBox
========================================
Creates IP networks and VLANs for baremetal infrastructure:

- BMC Network: 10.22.0.0/16 (BMC management interfaces)
- Management Network: 10.23.0.0/16 (OS-level management)

Each datacenter gets:
- /23 subnet for BMC (512 IPs)
- /23 subnet for management (512 IPs)
- Dedicated VLANs mapped to each subnet

Datacenter Allocations:
-----------------------
DC-East:
  - BMC: 10.22.0.0/23 (VLAN 2200)
  - Management: 10.23.0.0/23 (VLAN 2300)

DC-West:
  - BMC: 10.22.2.0/23 (VLAN 2202)
  - Management: 10.23.2.0/23 (VLAN 2302)

DC-Center:
  - BMC: 10.22.4.0/23 (VLAN 2204)
  - Management: 10.23.4.0/23 (VLAN 2304)

Usage:
    docker cp create-networks.py netbox:/tmp/
    docker exec netbox python /tmp/create-networks.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from ipam.models import Prefix, VLAN, VLANGroup, RIR, Role
from dcim.models import Site
from tenancy.models import Tenant


def create_rirs():
    """Create Regional Internet Registry for RFC1918 space."""
    print("\nCreating RIR...")
    rir, created = RIR.objects.get_or_create(
        name='RFC1918',
        slug='rfc1918',
        defaults={
            'is_private': True,
            'description': 'Private IPv4 address space (RFC 1918)'
        }
    )
    if created:
        print(f"  ✓ Created RIR: {rir.name}")
    else:
        print(f"  - Exists: {rir.name}")
    return rir


def create_roles():
    """Create prefix and VLAN roles."""
    print("\nCreating roles...")

    roles = {}

    # Prefix roles
    for role_data in [
        {'name': 'BMC Management', 'slug': 'bmc-management', 'weight': 1000},
        {'name': 'OS Management', 'slug': 'os-management', 'weight': 2000},
    ]:
        role, created = Role.objects.get_or_create(
            slug=role_data['slug'],
            defaults=role_data
        )
        if created:
            print(f"  ✓ Created role: {role.name}")
        else:
            print(f"  - Exists: {role.name}")
        roles[role.slug] = role

    return roles


def create_vlan_groups(sites):
    """Create VLAN groups per site."""
    print("\nCreating VLAN groups...")

    vlan_groups = {}
    site_content_type = ContentType.objects.get_for_model(Site)

    for site_slug, site in sites.items():
        group, created = VLANGroup.objects.get_or_create(
            name=f"{site.name} VLANs",
            slug=f"{site_slug}-vlans",
            defaults={
                'scope_type': site_content_type,
                'scope_id': site.pk,
                'description': f'VLANs for {site.name}'
            }
        )
        if created:
            print(f"  ✓ Created VLAN group: {group.name}")
        else:
            print(f"  - Exists: {group.name}")
        vlan_groups[site_slug] = group

    return vlan_groups


def create_vlans(sites, vlan_groups, tenant):
    """Create VLANs for each site and network type."""
    print("\nCreating VLANs...")

    vlans = {}

    site_configs = [
        {'slug': 'dc-east', 'prefix': 'EAST', 'bmc_vid': 2200, 'mgmt_vid': 2300},
        {'slug': 'dc-west', 'prefix': 'WEST', 'bmc_vid': 2202, 'mgmt_vid': 2302},
        {'slug': 'dc-center', 'prefix': 'CENT', 'bmc_vid': 2204, 'mgmt_vid': 2304},
    ]

    for config in site_configs:
        site = sites[config['slug']]
        site_prefix = config['prefix']
        vlan_group = vlan_groups[config['slug']]

        vlans[config['slug']] = {}

        # BMC VLAN
        bmc_vlan, created = VLAN.objects.get_or_create(
            vid=config['bmc_vid'],
            group=vlan_group,
            defaults={
                'name': f'{site_prefix}-BMC',
                'site': site,
                'tenant': tenant,
                'status': 'active',
                'description': f'BMC management network for {site.name}'
            }
        )
        if created:
            print(f"  ✓ Created VLAN: {bmc_vlan.name} (VID {bmc_vlan.vid})")
        else:
            print(f"  - Exists: {bmc_vlan.name} (VID {bmc_vlan.vid})")
        vlans[config['slug']]['bmc'] = bmc_vlan

        # Management VLAN
        mgmt_vlan, created = VLAN.objects.get_or_create(
            vid=config['mgmt_vid'],
            group=vlan_group,
            defaults={
                'name': f'{site_prefix}-MGMT',
                'site': site,
                'tenant': tenant,
                'status': 'active',
                'description': f'OS management network for {site.name}'
            }
        )
        if created:
            print(f"  ✓ Created VLAN: {mgmt_vlan.name} (VID {mgmt_vlan.vid})")
        else:
            print(f"  - Exists: {mgmt_vlan.name} (VID {mgmt_vlan.vid})")
        vlans[config['slug']]['mgmt'] = mgmt_vlan

    return vlans


def create_parent_prefixes(roles):
    """Create parent /16 prefixes."""
    print("\nCreating parent prefixes...")

    parents = {}

    # BMC parent prefix
    bmc_parent, created = Prefix.objects.get_or_create(
        prefix='10.22.0.0/16',
        defaults={
            'status': 'container',
            'role': roles['bmc-management'],
            'is_pool': False,
            'description': 'BMC Management - Parent block'
        }
    )
    if created:
        print(f"  ✓ Created prefix: {bmc_parent.prefix} (BMC parent)")
    else:
        print(f"  - Exists: {bmc_parent.prefix} (BMC parent)")
    parents['bmc'] = bmc_parent

    # Management parent prefix
    mgmt_parent, created = Prefix.objects.get_or_create(
        prefix='10.23.0.0/16',
        defaults={
            'status': 'container',
            'role': roles['os-management'],
            'is_pool': False,
            'description': 'OS Management - Parent block'
        }
    )
    if created:
        print(f"  ✓ Created prefix: {mgmt_parent.prefix} (Management parent)")
    else:
        print(f"  - Exists: {mgmt_parent.prefix} (Management parent)")
    parents['mgmt'] = mgmt_parent

    return parents


def create_site_prefixes(sites, vlans, roles, tenant):
    """Create /23 prefixes for each site."""
    print("\nCreating site-specific prefixes...")

    prefixes = {}

    site_configs = [
        {
            'slug': 'dc-east',
            'bmc_prefix': '10.22.0.0/23',
            'mgmt_prefix': '10.23.0.0/23',
        },
        {
            'slug': 'dc-west',
            'bmc_prefix': '10.22.2.0/23',
            'mgmt_prefix': '10.23.2.0/23',
        },
        {
            'slug': 'dc-center',
            'bmc_prefix': '10.22.4.0/23',
            'mgmt_prefix': '10.23.4.0/23',
        },
    ]

    for config in site_configs:
        site = sites[config['slug']]
        prefixes[config['slug']] = {}

        # BMC prefix
        bmc_prefix, created = Prefix.objects.get_or_create(
            prefix=config['bmc_prefix'],
            defaults={
                'site': site,
                'vlan': vlans[config['slug']]['bmc'],
                'status': 'active',
                'role': roles['bmc-management'],
                'tenant': tenant,
                'is_pool': True,
                'description': f"BMC management network for {site.name}"
            }
        )
        if created:
            print(f"  ✓ Created: {bmc_prefix.prefix} → {site.name} (BMC, VLAN {vlans[config['slug']]['bmc'].vid})")
        else:
            print(f"  - Exists: {bmc_prefix.prefix} → {site.name}")
        prefixes[config['slug']]['bmc'] = bmc_prefix

        # Management prefix
        mgmt_prefix, created = Prefix.objects.get_or_create(
            prefix=config['mgmt_prefix'],
            defaults={
                'site': site,
                'vlan': vlans[config['slug']]['mgmt'],
                'status': 'active',
                'role': roles['os-management'],
                'tenant': tenant,
                'is_pool': True,
                'description': f"OS management network for {site.name}"
            }
        )
        if created:
            print(f"  ✓ Created: {mgmt_prefix.prefix} → {site.name} (Management, VLAN {vlans[config['slug']]['mgmt'].vid})")
        else:
            print(f"  - Exists: {mgmt_prefix.prefix} → {site.name}")
        prefixes[config['slug']]['mgmt'] = mgmt_prefix

    return prefixes


def display_summary(sites, vlans, prefixes):
    """Display network allocation summary."""
    print("\n" + "=" * 70)
    print("NETWORK ALLOCATION SUMMARY")
    print("=" * 70)

    for site_slug, site in sites.items():
        print(f"\n{site.name}:")
        print(f"  BMC Network:")
        print(f"    Prefix: {prefixes[site_slug]['bmc'].prefix} (512 IPs)")
        print(f"    VLAN:   {vlans[site_slug]['bmc'].vid} - {vlans[site_slug]['bmc'].name}")
        print(f"    Range:  10.22.X.1 - 10.22.X.254 (usable)")

        print(f"  Management Network:")
        print(f"    Prefix: {prefixes[site_slug]['mgmt'].prefix} (512 IPs)")
        print(f"    VLAN:   {vlans[site_slug]['mgmt'].vid} - {vlans[site_slug]['mgmt'].name}")
        print(f"    Range:  10.23.X.1 - 10.23.X.254 (usable)")

    print("\n" + "=" * 70)
    print("Parent Allocations:")
    print("=" * 70)
    print("  10.22.0.0/16 - BMC Management (65,536 IPs)")
    print("    10.22.0.0/23  - DC-East BMC")
    print("    10.22.2.0/23  - DC-West BMC")
    print("    10.22.4.0/23  - DC-Center BMC")
    print("    10.22.6.0/23+ - Available for expansion")

    print("\n  10.23.0.0/16 - OS Management (65,536 IPs)")
    print("    10.23.0.0/23  - DC-East Management")
    print("    10.23.2.0/23  - DC-West Management")
    print("    10.23.4.0/23  - DC-Center Management")
    print("    10.23.6.0/23+ - Available for expansion")


@transaction.atomic
def main():
    """Main execution."""
    print("=" * 70)
    print("NETBOX NETWORK INFRASTRUCTURE CREATION")
    print("=" * 70)
    print("\nCreating RFC1918 network allocations for baremetal infrastructure")
    print("  - BMC Network: 10.22.0.0/16")
    print("  - Management Network: 10.23.0.0/16")
    print("  - Per-site subnets: /23 (512 IPs each)")
    print("=" * 70)

    # Get sites
    print("\nFetching sites...")
    sites = {}
    for slug in ['dc-east', 'dc-west', 'dc-center']:
        try:
            site = Site.objects.get(slug=slug)
            sites[slug] = site
            print(f"  ✓ Found: {site.name}")
        except Site.DoesNotExist:
            print(f"  ✗ Site '{slug}' not found!")
            sys.exit(1)

    # Get tenant
    tenant, _ = Tenant.objects.get_or_create(
        slug='baremetal-staging',
        defaults={'name': 'Baremetal Staging'}
    )

    # Create infrastructure
    rir = create_rirs()
    roles = create_roles()
    vlan_groups = create_vlan_groups(sites)
    vlans = create_vlans(sites, vlan_groups, tenant)
    parent_prefixes = create_parent_prefixes(roles)
    site_prefixes = create_site_prefixes(sites, vlans, roles, tenant)

    # Display summary
    display_summary(sites, vlans, site_prefixes)

    print("\n" + "=" * 70)
    print("✓ NETWORK INFRASTRUCTURE CREATED!")
    print("=" * 70)
    print("\nNext Steps:")
    print("  1. Configure DHCP servers with these ranges")
    print("  2. Assign IP addresses to BMC interfaces")
    print("  3. Configure switch VLANs")
    print("  4. Update DNS zones for management networks")
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
