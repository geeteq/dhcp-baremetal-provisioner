#!/usr/bin/env python3
"""
NetBox Initialization Script for Baremetal Provisioning Testing

This script creates the necessary NetBox objects for testing:
- Custom fields for lifecycle tracking
- Device types (HPE and Dell servers)
- Sites and racks
- Test devices
- Tenants
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from django.contrib.contenttypes.models import ContentType
from dcim.models import (
    Site, Manufacturer, DeviceType, DeviceRole, Device,
    Interface, Rack, RackRole, Location
)
from extras.models import CustomField, CustomFieldChoiceSet
from tenancy.models import Tenant
from users.models import Token, User

def create_custom_fields():
    """Create custom fields for lifecycle tracking."""
    print("Creating custom fields...")

    device_content_type = ContentType.objects.get_for_model(Device)

    # First, create the ChoiceSet for lifecycle states
    # NetBox 3.7+ requires choices as list of [value, label] pairs
    lifecycle_choices = [
        ['offline', 'Offline'],
        ['planned', 'Planned'],
        ['validating', 'Validating'],
        ['validated', 'Validated'],
        ['hardening', 'Hardening'],
        ['staged', 'Staged'],
        ['ready', 'Ready'],
        ['monitored', 'Monitored'],
        ['error', 'Error']
    ]

    lifecycle_choice_set, cs_created = CustomFieldChoiceSet.objects.get_or_create(
        name='Lifecycle States',
        defaults={
            'extra_choices': lifecycle_choices,
            'order_alphabetically': False
        }
    )
    if cs_created:
        print(f"  ✓ Created choice set: Lifecycle States")
    else:
        print(f"  - Choice set already exists: Lifecycle States")

    fields = [
        {
            'name': 'lifecycle_state',
            'label': 'Lifecycle State',
            'type': 'select',
            'choice_set': lifecycle_choice_set,
            'default': 'offline',
            'description': 'Current lifecycle state of the device in provisioning workflow',
        },
        {
            'name': 'discovered_at',
            'label': 'Discovered At',
            'type': 'date',
            'description': 'Timestamp when device was discovered via DHCP',
        },
        {
            'name': 'pxe_boot_initiated_at',
            'label': 'PXE Boot Initiated At',
            'type': 'date',
            'description': 'Timestamp when PXE boot was initiated',
        },
        {
            'name': 'hardened_at',
            'label': 'Hardened At',
            'type': 'date',
            'description': 'Timestamp when BMC hardening was completed',
        },
        {
            'name': 'last_monitored_at',
            'label': 'Last Monitored At',
            'type': 'date',
            'description': 'Timestamp of last monitoring check',
        },
        {
            'name': 'last_power_watts',
            'label': 'Last Power Reading (Watts)',
            'type': 'integer',
            'description': 'Last power consumption reading in watts',
        },
    ]

    for field_data in fields:
        field, created = CustomField.objects.get_or_create(
            name=field_data['name'],
            defaults=field_data
        )
        if created:
            field.content_types.set([device_content_type])
            field.save()
            print(f"  ✓ Created custom field: {field_data['name']}")
        else:
            print(f"  - Custom field already exists: {field_data['name']}")

def create_manufacturers():
    """Create server manufacturers."""
    print("\nCreating manufacturers...")

    manufacturers = [
        {'name': 'HPE', 'slug': 'hpe'},
        {'name': 'Dell', 'slug': 'dell'},
    ]

    for mfr_data in manufacturers:
        mfr, created = Manufacturer.objects.get_or_create(
            slug=mfr_data['slug'],
            defaults=mfr_data
        )
        if created:
            print(f"  ✓ Created manufacturer: {mfr.name}")
        else:
            print(f"  - Manufacturer already exists: {mfr.name}")

    return {m.slug: m for m in Manufacturer.objects.all()}

def create_device_types(manufacturers):
    """Create device types for servers."""
    print("\nCreating device types...")

    device_types_data = [
        {
            'manufacturer': manufacturers['hpe'],
            'model': 'ProLiant DL360 Gen10',
            'slug': 'proliant-dl360-gen10',
            'u_height': 1,
            'is_full_depth': True,
        },
        {
            'manufacturer': manufacturers['hpe'],
            'model': 'ProLiant DL380 Gen10',
            'slug': 'proliant-dl380-gen10',
            'u_height': 2,
            'is_full_depth': True,
        },
        {
            'manufacturer': manufacturers['dell'],
            'model': 'PowerEdge R640',
            'slug': 'poweredge-r640',
            'u_height': 1,
            'is_full_depth': True,
        },
        {
            'manufacturer': manufacturers['dell'],
            'model': 'PowerEdge R740',
            'slug': 'poweredge-r740',
            'u_height': 2,
            'is_full_depth': True,
        },
    ]

    created_types = {}
    for dt_data in device_types_data:
        dt, created = DeviceType.objects.get_or_create(
            slug=dt_data['slug'],
            defaults=dt_data
        )
        if created:
            print(f"  ✓ Created device type: {dt.model}")
        else:
            print(f"  - Device type already exists: {dt.model}")
        created_types[dt.slug] = dt

    return created_types

def create_sites():
    """Create test sites."""
    print("\nCreating sites...")

    sites_data = [
        {'name': 'DC-Chicago', 'slug': 'dc-chicago'},
        {'name': 'DC-NewYork', 'slug': 'dc-newyork'},
        {'name': 'DC-LosAngeles', 'slug': 'dc-losangeles'},
    ]

    created_sites = {}
    for site_data in sites_data:
        site, created = Site.objects.get_or_create(
            slug=site_data['slug'],
            defaults=site_data
        )
        if created:
            print(f"  ✓ Created site: {site.name}")
        else:
            print(f"  - Site already exists: {site.name}")
        created_sites[site.slug] = site

    return created_sites

def create_racks(sites):
    """Create test racks."""
    print("\nCreating racks...")

    rack_role, _ = RackRole.objects.get_or_create(
        name='Server Rack',
        slug='server-rack',
        defaults={'color': '2196f3'}
    )

    racks_data = [
        {'site': sites['dc-chicago'], 'name': 'CHI-R01', 'u_height': 42},
        {'site': sites['dc-chicago'], 'name': 'CHI-R02', 'u_height': 42},
        {'site': sites['dc-newyork'], 'name': 'NYC-R01', 'u_height': 42},
    ]

    created_racks = {}
    for rack_data in racks_data:
        rack, created = Rack.objects.get_or_create(
            site=rack_data['site'],
            name=rack_data['name'],
            defaults={
                'u_height': rack_data['u_height'],
                'role': rack_role,
            }
        )
        if created:
            print(f"  ✓ Created rack: {rack.name}")
        else:
            print(f"  - Rack already exists: {rack.name}")
        created_racks[rack.name] = rack

    return created_racks

def create_device_roles():
    """Create device roles."""
    print("\nCreating device roles...")

    roles_data = [
        {'name': 'Bare Metal Server', 'slug': 'bare-metal-server', 'color': '4caf50'},
        {'name': 'Compute Node', 'slug': 'compute-node', 'color': '2196f3'},
    ]

    created_roles = {}
    for role_data in roles_data:
        role, created = DeviceRole.objects.get_or_create(
            slug=role_data['slug'],
            defaults=role_data
        )
        if created:
            print(f"  ✓ Created device role: {role.name}")
        else:
            print(f"  - Device role already exists: {role.name}")
        created_roles[role.slug] = role

    return created_roles

def create_tenants():
    """Create test tenants."""
    print("\nCreating tenants...")

    tenants_data = [
        {'name': 'Baremetal Staging', 'slug': 'baremetal-staging'},
        {'name': 'Customer A', 'slug': 'customer-a'},
        {'name': 'Customer B', 'slug': 'customer-b'},
    ]

    created_tenants = {}
    for tenant_data in tenants_data:
        tenant, created = Tenant.objects.get_or_create(
            slug=tenant_data['slug'],
            defaults=tenant_data
        )
        if created:
            print(f"  ✓ Created tenant: {tenant.name}")
        else:
            print(f"  - Tenant already exists: {tenant.name}")
        created_tenants[tenant.slug] = tenant

    return created_tenants

def create_test_devices(device_types, racks, roles, tenants):
    """Create test devices."""
    print("\nCreating test devices...")

    devices_data = [
        {
            'name': 'chi-server-001',
            'device_type': device_types['proliant-dl360-gen10'],
            'role': roles['bare-metal-server'],
            'site': racks['CHI-R01'].site,
            'rack': racks['CHI-R01'],
            'position': 40,
            'tenant': tenants['baremetal-staging'],
            'status': 'offline',
        },
        {
            'name': 'chi-server-002',
            'device_type': device_types['proliant-dl380-gen10'],
            'role': roles['bare-metal-server'],
            'site': racks['CHI-R01'].site,
            'rack': racks['CHI-R01'],
            'position': 38,
            'tenant': tenants['baremetal-staging'],
            'status': 'offline',
        },
        {
            'name': 'chi-server-003',
            'device_type': device_types['poweredge-r640'],
            'role': roles['compute-node'],
            'site': racks['CHI-R02'].site,
            'rack': racks['CHI-R02'],
            'position': 40,
            'tenant': tenants['baremetal-staging'],
            'status': 'offline',
        },
    ]

    for device_data in devices_data:
        device, created = Device.objects.get_or_create(
            name=device_data['name'],
            defaults=device_data
        )
        if created:
            print(f"  ✓ Created device: {device.name}")

            # Create management interface
            iface, _ = Interface.objects.get_or_create(
                device=device,
                name='iLO',
                defaults={
                    'type': '1000base-t',
                    'mgmt_only': True,
                    'mac_address': f'00:50:56:{device.pk:02x}:{device.pk:02x}:{device.pk:02x}',
                }
            )
            print(f"    ✓ Created interface: {iface.name} (MAC: {iface.mac_address})")
        else:
            print(f"  - Device already exists: {device.name}")

def create_api_token():
    """Ensure API token exists for automation."""
    print("\nVerifying API token...")

    try:
        admin_user = User.objects.get(username='admin')
        token, created = Token.objects.get_or_create(
            user=admin_user,
            key='0123456789abcdef0123456789abcdef01234567'
        )
        if created:
            print(f"  ✓ Created API token for admin user")
        else:
            print(f"  - API token already exists")
        print(f"  Token: {token.key}")
    except User.DoesNotExist:
        print("  ⚠ Admin user not yet created. Token will be created after superuser creation.")

def main():
    """Run all initialization steps."""
    print("=" * 60)
    print("NetBox Initialization for Baremetal Provisioning")
    print("=" * 60)

    try:
        # Create custom fields
        create_custom_fields()

        # Create manufacturers
        manufacturers = create_manufacturers()

        # Create device types
        device_types = create_device_types(manufacturers)

        # Create sites
        sites = create_sites()

        # Create racks
        racks = create_racks(sites)

        # Create device roles
        roles = create_device_roles()

        # Create tenants
        tenants = create_tenants()

        # Create test devices
        create_test_devices(device_types, racks, roles, tenants)

        # Create API token
        create_api_token()

        print("\n" + "=" * 60)
        print("✓ NetBox initialization completed successfully!")
        print("=" * 60)
        print("\nAccess NetBox at: http://localhost:8000")
        print("Username: admin")
        print("Password: admin")
        print("API Token: 0123456789abcdef0123456789abcdef01234567")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error during initialization: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
