#!/usr/bin/env python3
"""
Phase 1 Testing - Bulk BMC Discovery Simulation
================================================
Simulates BMC DHCP requests for all servers in NetBox.

This script:
- Queries all servers from NetBox
- For each server, finds its datacenter's BMC subnet
- Allocates the next available IP from that subnet
- Simulates a DHCP request by pushing event to Redis
- Assigns the IP to the BMC interface in NetBox

Usage:
    python test-phase1-all.py [--limit N] [--site SITE] [--delay SECONDS]

Options:
    --limit N          Process only N servers (default: all)
    --site SITE        Only process servers in specific site
    --delay SECONDS    Delay between requests (default: 0.5)
    --dry-run          Show what would be done without doing it
"""

import os
import sys
import json
import time
import redis
import requests
import argparse
import ipaddress
from datetime import datetime


# Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6380'))
REDIS_QUEUE = os.getenv('REDIS_QUEUE', 'netbox:bmc:discovered')
NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')


def get_netbox_servers(site_filter=None, limit=None):
    """Fetch servers from NetBox."""
    # Fetch more devices initially to account for filtering
    # Need at least 200 devices to skip the switches at the beginning
    fetch_limit = 2000 if not limit else max(200, limit * 10)  # Fetch 10x limit, minimum 200

    params = {
        'limit': fetch_limit,
    }

    if site_filter:
        params['site__name'] = site_filter

    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params=params,
            timeout=10
        )
        response.raise_for_status()

        # Filter for devices with 'server' in role name
        all_devices = response.json()['results']

        # Debug: print first few devices
        # print(f"DEBUG: Fetched {len(all_devices)} devices")
        # if all_devices:
        #     print(f"DEBUG: First device role: {all_devices[0].get('role', {}).get('name', 'N/A')}")

        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        # Apply limit after filtering
        if limit:
            servers = servers[:limit]

        return servers
    except Exception as e:
        print(f"✗ Error fetching servers: {e}")
        return []


def get_server_bmc_interface(device_id, device_name):
    """Get BMC interface details for a device."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/interfaces/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={
                'device_id': device_id,
                'name': 'bmc'
            },
            timeout=5
        )
        response.raise_for_status()

        data = response.json()
        if data['count'] > 0:
            return data['results'][0]
        else:
            print(f"    ⚠ No BMC interface found for {device_name}")
            return None
    except Exception as e:
        print(f"    ✗ Error fetching BMC interface: {e}")
        return None


def get_site_bmc_prefix(site_id, site_name):
    """Get the BMC management prefix for a site."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/ipam/prefixes/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={
                'site_id': site_id,
                'role__name': 'BMC Management'
            },
            timeout=5
        )
        response.raise_for_status()

        data = response.json()
        if data['count'] > 0:
            # Prefer 10.55.x.x ranges (our new ones)
            prefixes = data['results']
            for prefix in prefixes:
                if prefix['prefix'].startswith('10.55.'):
                    return prefix
            # Fallback to first available
            return prefixes[0]
        else:
            print(f"    ⚠ No BMC prefix found for site {site_name}")
            return None
    except Exception as e:
        print(f"    ✗ Error fetching BMC prefix: {e}")
        return None


def get_next_available_ip(prefix_id):
    """Get next available IP from a prefix."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/ipam/prefixes/{prefix_id}/available-ips/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            timeout=5
        )
        response.raise_for_status()

        available = response.json()
        if available:
            return available[0]['address'].split('/')[0]  # Remove /24 suffix
        else:
            print(f"    ⚠ No available IPs in prefix")
            return None
    except Exception as e:
        print(f"    ✗ Error fetching available IP: {e}")
        return None


def set_device_failed(device_id, device_name, dry_run=False):
    """Set device status to failed."""
    if dry_run:
        print(f"    [DRY RUN] Would set device status to failed")
        return True

    try:
        response = requests.patch(
            f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            json={'status': 'failed'},
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error setting device to failed: {e}")
        return False


def set_device_planned(device_id, device_name, dry_run=False):
    """Set device status to planned."""
    if dry_run:
        print(f"    [DRY RUN] Would set device status to planned")
        return True

    try:
        url = f"{NETBOX_URL}/api/dcim/devices/{device_id}/"
        headers = {
            'Authorization': f'Token {NETBOX_TOKEN}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        data = {'status': 'planned'}

        response = requests.patch(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()

        # Verify the update
        result = response.json()
        new_status = result.get('status', {}).get('value', 'unknown')

        return True
    except Exception as e:
        print(f"    ✗ Error setting device to planned: {e}")
        return False


def add_journal_entry(device_id, message, kind='danger', dry_run=False):
    """Add a journal entry to a device."""
    if dry_run:
        print(f"    [DRY RUN] Would add journal entry: {message[:50]}...")
        return True

    try:
        response = requests.post(
            f"{NETBOX_URL}/api/extras/journal-entries/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            json={
                'assigned_object_type': 'dcim.device',
                'assigned_object_id': device_id,
                'kind': kind,
                'comments': message
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error adding journal entry: {e}")
        return False


def push_dhcp_event(mac_address, ip_address, device_name, redis_client, dry_run=False):
    """Push DHCP event to Redis queue."""
    timestamp = datetime.utcnow().isoformat() + 'Z'

    event = {
        'event_type': 'bmc_dhcp_lease',
        'timestamp': timestamp,
        'mac_address': mac_address,
        'ip_address': ip_address,
        'hostname': device_name,
        'source': 'phase1_bulk_test'
    }

    if dry_run:
        print(f"    [DRY RUN] Would push event: {mac_address} → {ip_address}")
        return True

    try:
        event_json = json.dumps(event)
        redis_client.lpush(REDIS_QUEUE, event_json)
        return True
    except Exception as e:
        print(f"    ✗ Error pushing to Redis: {e}")
        return False


def test_all_servers(site_filter=None, limit=None, delay=0.5, dry_run=False):
    """Test BMC discovery for all servers."""
    print("=" * 70)
    print("PHASE 1 BULK TEST - BMC DISCOVERY FOR ALL SERVERS")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN MODE - No events will be pushed\n")

    # Connect to Redis
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False
        )
        redis_client.ping()
        print(f"✓ Connected to Redis: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        print(f"✗ Failed to connect to Redis: {e}")
        return False

    # Fetch servers
    print(f"✓ Fetching servers from NetBox...")
    if site_filter:
        print(f"  Filter: Site = {site_filter}")
    if limit:
        print(f"  Limit: {limit} servers")

    servers = get_netbox_servers(site_filter, limit)

    if not servers:
        print("\n✗ No servers found")
        return False

    print(f"✓ Found {len(servers)} server(s)\n")

    # Statistics
    stats = {
        'total': len(servers),
        'success': 0,
        'no_bmc': 0,
        'no_mac': 0,
        'no_prefix': 0,
        'no_ip': 0,
        'errors': 0
    }

    # Process each server
    for i, server in enumerate(servers, 1):
        device_name = server['name']
        device_id = server['id']
        site_name = server['site']['name'] if server.get('site') else 'Unknown'

        print(f"[{i}/{len(servers)}] {device_name}")
        print(f"  Site: {site_name}")

        try:
            # Get BMC interface
            bmc_interface = get_server_bmc_interface(device_id, device_name)
            if not bmc_interface:
                # No BMC interface - set device to failed and log
                print(f"    ✗ No BMC interface found")

                if set_device_failed(device_id, device_name, dry_run):
                    print(f"    ✓ Device status set to failed")

                journal_message = f"""Phase 1 BMC Discovery Failed - No BMC Interface

Site: {site_name}

Error: No BMC interface found on this device.

The device does not have a BMC (Baseboard Management Controller) interface configured in NetBox. Phase 1 requires a BMC interface for out-of-band management and discovery.

Recommended Actions:
1. Verify the device has BMC hardware installed
2. Add the BMC interface to the device in NetBox
3. Configure the BMC MAC address
4. Ensure BMC is properly cabled to management network
"""
                if add_journal_entry(device_id, journal_message, 'danger', dry_run):
                    print(f"    ✓ Journal entry added")

                stats['no_bmc'] += 1
                print()
                continue

            mac_address = bmc_interface.get('mac_address')
            if not mac_address:
                print(f"    ✗ BMC interface has no MAC address")

                if set_device_failed(device_id, device_name, dry_run):
                    print(f"    ✓ Device status set to failed")

                journal_message = f"""Phase 1 BMC Discovery Failed - No MAC Address

Site: {site_name}
BMC Interface: {bmc_interface['name']}

Error: BMC interface exists but has no MAC address configured.

The BMC interface is present in NetBox but lacks a MAC address. DHCP discovery requires the BMC MAC address to assign an IP and track the device.

Recommended Actions:
1. Obtain the BMC MAC address from the physical server or iLO/iDRAC interface
2. Update the BMC interface in NetBox with the correct MAC address
3. Verify the MAC address is unique in the network
"""
                if add_journal_entry(device_id, journal_message, 'danger', dry_run):
                    print(f"    ✓ Journal entry added")

                stats['no_mac'] += 1
                print()
                continue

            print(f"  BMC MAC: {mac_address}")

            # Get site ID
            site_id = server['site']['id'] if server.get('site') else None
            if not site_id:
                print(f"    ✗ Server has no site assigned")

                if set_device_failed(device_id, device_name, dry_run):
                    print(f"    ✓ Device status set to failed")

                journal_message = f"""Phase 1 BMC Discovery Failed - No Site Assignment

BMC MAC: {mac_address}

Error: Device is not assigned to any site/datacenter.

The device must be assigned to a site to determine the correct BMC management subnet. Each datacenter has its own BMC IP range.

Recommended Actions:
1. Assign the device to the correct site/datacenter in NetBox
2. Verify the site has a BMC Management subnet configured
3. Ensure the device is physically located in the assigned datacenter
"""
                if add_journal_entry(device_id, journal_message, 'danger', dry_run):
                    print(f"    ✓ Journal entry added")

                stats['no_prefix'] += 1
                print()
                continue

            # Get site's BMC prefix
            bmc_prefix = get_site_bmc_prefix(site_id, site_name)
            if not bmc_prefix:
                print(f"    ✗ No BMC subnet found for site {site_name}")

                if set_device_failed(device_id, device_name, dry_run):
                    print(f"    ✓ Device status set to failed")

                journal_message = f"""Phase 1 BMC Discovery Failed - No BMC Subnet

Site: {site_name}
BMC MAC: {mac_address}

Error: No BMC Management subnet configured for this site.

The site does not have a BMC Management subnet (role: 'BMC Management') configured in NetBox. Phase 1 requires a dedicated subnet for BMC IP allocation.

Recommended Actions:
1. Create a BMC Management subnet for site {site_name} in NetBox
2. Set the subnet role to 'BMC Management'
3. Ensure the subnet has adequate capacity for all servers in the site
4. Configure the subnet as 10.55.x.0/24 following the standard naming convention
"""
                if add_journal_entry(device_id, journal_message, 'danger', dry_run):
                    print(f"    ✓ Journal entry added")

                stats['no_prefix'] += 1
                print()
                continue

            print(f"  BMC Subnet: {bmc_prefix['prefix']}")

            # Get next available IP
            ip_address = get_next_available_ip(bmc_prefix['id'])
            if not ip_address:
                # IP allocation failed - set device to failed and log
                print(f"    ✗ No available IPs in BMC subnet {bmc_prefix['prefix']}")

                # Set device status to failed
                if set_device_failed(device_id, device_name, dry_run):
                    print(f"    ✓ Device status set to failed")

                # Add journal entry with details
                journal_message = f"""Phase 1 BMC IP Allocation Failed

Site: {site_name}
BMC Subnet: {bmc_prefix['prefix']}
BMC MAC: {mac_address}

Error: No available IP addresses in the BMC management subnet.

The BMC subnet is exhausted. This server cannot proceed with Phase 1 discovery until additional IP addresses are made available in the subnet or the subnet is expanded.

Recommended Actions:
1. Expand the BMC subnet range in NetBox
2. Review and clean up unused BMC IP allocations
3. Verify subnet configuration matches datacenter capacity
"""
                if add_journal_entry(device_id, journal_message, 'danger', dry_run):
                    print(f"    ✓ Journal entry added")

                stats['no_ip'] += 1
                print()
                continue

            print(f"  Allocated IP: {ip_address}")

            # Push DHCP event
            if push_dhcp_event(mac_address, ip_address, device_name, redis_client, dry_run):
                print(f"  ✓ Event pushed to Redis")

                # Set device status to planned
                if set_device_planned(device_id, device_name, dry_run):
                    print(f"  ✓ Device status set to planned")

                # Add success journal entry
                journal_message = f"""Phase 1 BMC Discovery Successful

Site: {site_name}
BMC Subnet: {bmc_prefix['prefix']}
BMC MAC: {mac_address}
Allocated IP: {ip_address}

The BMC was successfully discovered and allocated an IP address from the datacenter's BMC management subnet.

Next Steps:
- BMC worker will process the DHCP event and update NetBox
- Physical connectivity verification (Phase 2)
- Firmware validation and configuration (Phase 3)
"""
                if add_journal_entry(device_id, journal_message, 'success', dry_run):
                    print(f"  ✓ Journal entry added")

                stats['success'] += 1
            else:
                stats['errors'] += 1

            print()

            # Delay between requests
            if not dry_run and delay > 0 and i < len(servers):
                time.sleep(delay)

        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats['errors'] += 1
            print()

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total servers:          {stats['total']}")
    print(f"Events pushed:          {stats['success']}")
    print(f"No BMC interface:       {stats['no_bmc']}")
    print(f"No MAC address:         {stats['no_mac']}")
    print(f"No BMC prefix:          {stats['no_prefix']}")
    print(f"No available IPs:       {stats['no_ip']}")
    if stats['errors'] > 0:
        print(f"Errors:                 {stats['errors']}")
    print("=" * 70)

    if dry_run:
        print("\n⚠ DRY RUN - No events were pushed to Redis")
    else:
        print(f"\n✓ Pushed {stats['success']} DHCP events to Redis")
        print(f"✓ Workers will process events and update NetBox")
        print(f"\nMonitor progress:")
        print(f"  Dashboard: http://localhost:5001")
        print(f"  Worker logs: docker-compose logs -f bmc-worker")

    print("=" * 70)
    return True


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(
        description='Simulate BMC DHCP discovery for all servers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would happen
  python test-phase1-all.py --dry-run

  # Test all servers
  python test-phase1-all.py

  # Test only 10 servers
  python test-phase1-all.py --limit 10

  # Test servers in specific site
  python test-phase1-all.py --site dc-east

  # Test with 2 second delay between requests
  python test-phase1-all.py --delay 2

  # Combine options
  python test-phase1-all.py --site dc-west --limit 20 --delay 1
        """
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Process only N servers'
    )

    parser.add_argument(
        '--site',
        type=str,
        help='Only process servers in specific site'
    )

    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it'
    )

    args = parser.parse_args()

    try:
        success = test_all_servers(
            site_filter=args.site,
            limit=args.limit,
            delay=args.delay,
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
