#!/usr/bin/env python3
"""
Export all MAC addresses for server interfaces
"""

import os
import sys
import django
import csv
from io import StringIO

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, DeviceRole, Interface


def export_mac_addresses():
    """Export MAC addresses for all server interfaces."""
    print("=" * 70)
    print("SERVER MAC ADDRESS EXPORT")
    print("=" * 70)

    # Get all compute servers
    compute_role = DeviceRole.objects.get(slug='compute-server')
    servers = Device.objects.filter(role=compute_role).order_by('site__name', 'rack__name', 'name')

    total_servers = servers.count()
    print(f"\nExporting MAC addresses for {total_servers} servers...\n")

    # Create CSV output
    output = StringIO()
    csv_writer = csv.writer(output)

    # Write header
    csv_writer.writerow([
        'Datacenter',
        'Rack',
        'Server',
        'Interface',
        'MAC Address',
        'Type',
        'Description'
    ])

    total_interfaces = 0
    servers_with_macs = 0

    for server in servers:
        interfaces = Interface.objects.filter(device=server).order_by('name')

        has_mac = False
        for iface in interfaces:
            if iface.mac_address:
                csv_writer.writerow([
                    server.site.name,
                    server.rack.name,
                    server.name,
                    iface.name,
                    iface.mac_address,
                    str(iface.type) if iface.type else 'Unknown',
                    iface.description or ''
                ])
                total_interfaces += 1
                has_mac = True

        if has_mac:
            servers_with_macs += 1

    # Get CSV content
    csv_content = output.getvalue()
    output.close()

    # Save to file
    output_file = '/tmp/server_mac_addresses.csv'
    with open(output_file, 'w') as f:
        f.write(csv_content)

    print(f"✓ Exported {total_interfaces} MAC addresses")
    print(f"✓ From {servers_with_macs} servers")
    print(f"\nCSV file saved to: {output_file}")

    # Display sample data
    print("\n" + "=" * 70)
    print("SAMPLE MAC ADDRESSES")
    print("=" * 70)

    sample_servers = servers[:3]
    for server in sample_servers:
        print(f"\n{server.name} ({server.site.name}, {server.rack.name}):")
        interfaces = Interface.objects.filter(device=server).order_by('name')
        for iface in interfaces:
            if iface.mac_address:
                mac_str = str(iface.mac_address)
                type_str = str(iface.type) if iface.type else 'Unknown'
                print(f"  {iface.name:12} - {mac_str:17} - {type_str}")

    # Summary by MAC prefix
    print("\n" + "=" * 70)
    print("MAC ADDRESS ALLOCATION SUMMARY")
    print("=" * 70)
    print("\nMAC Prefixes Used:")
    print("  a0:36:9f:xx:xx:xx - BMC and Management NICs (HPE OUI)")
    print("  3c:fd:fe:xx:xx:xx - Production NICs (Intel OUI)")
    print(f"\nTotal MAC addresses in NetBox: {total_interfaces}")
    print(f"Expected: {total_servers * 4} (4 interfaces per server)")

    if total_interfaces == total_servers * 4:
        print("✓ All interfaces have MAC addresses assigned")
    else:
        print(f"⚠ Missing {(total_servers * 4) - total_interfaces} MAC addresses")

    print("=" * 70)


if __name__ == '__main__':
    try:
        export_mac_addresses()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
