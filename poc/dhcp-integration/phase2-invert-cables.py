#!/usr/bin/env python3
"""
Phase 2: Production NIC Cable Inversion Service
================================================
Simulates cable misconfiguration by inverting production NIC cables in NetBox.

This service:
1. Queries all servers with production interfaces (description: "Production Network SFP Interface")
2. Gets current cable peer device and port for each production NIC
3. Inverts/swaps the cables between the two production NICs
4. Sets server status to 'Failed'
5. Logs the failure in device journal with original vs detected config
6. Pushes event to Redis queue 'update_server_prod_nics'

This simulates a scenario where:
- Physical cabling is correct (what LLDP would detect)
- NetBox documentation is incorrect (cables are inverted)
- Service detects the mismatch and logs failure

Usage:
    python phase2-invert-cables.py [--limit N] [--site SITE] [--dry-run]

Options:
    --limit N       Process only N servers
    --site SITE     Only process servers in specific site
    --dry-run       Show what would be done without making changes
"""

import os
import sys
import json
import redis
import requests
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple


# Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6380'))
REDIS_QUEUE = 'netbox:phase2:update_server_prod_nics'
NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}


def get_servers(site_filter: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """Fetch servers from NetBox."""
    fetch_limit = 2000 if not limit else max(200, limit * 10)

    params = {
        'limit': fetch_limit,
    }

    if site_filter:
        params['site__name__iec'] = site_filter

    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        response.raise_for_status()

        all_devices = response.json()['results']

        # Filter for servers with status = 'staged'
        servers = [
            d for d in all_devices
            if d.get('role') and 'server' in d['role']['name'].lower()
            and d.get('status', {}).get('value') == 'staged'
        ]

        if limit:
            servers = servers[:limit]

        return servers
    except Exception as e:
        print(f"✗ Error fetching servers: {e}")
        return []


def get_production_interfaces(device_id: int) -> List[Dict]:
    """Get production interfaces for a device."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/interfaces/",
            headers=HEADERS,
            params={
                'device_id': device_id,
                'description__ic': 'Production Network SFP Interface'
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json()['results']
    except Exception as e:
        print(f"    ✗ Error fetching interfaces: {e}")
        return []


def get_cable_for_interface(interface_id: int) -> Optional[Dict]:
    """Get cable connected to an interface."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/cables/",
            headers=HEADERS,
            params={
                'interface_id': interface_id
            },
            timeout=10
        )
        response.raise_for_status()

        cables = response.json()['results']
        return cables[0] if cables else None
    except Exception as e:
        print(f"    ✗ Error fetching cable: {e}")
        return None


def get_cable_peer(cable: Dict, interface_id: int) -> Optional[Tuple[str, str, int]]:
    """Get the peer device and interface from a cable."""
    try:
        # Cable has two terminations: a_terminations and b_terminations
        # We need to find which side our interface is on, then return the other side

        a_terms = cable.get('a_terminations', [])
        b_terms = cable.get('b_terminations', [])

        # Check if our interface is on A side
        for term in a_terms:
            if term['object_id'] == interface_id:
                # Our interface is on A side, return B side peer
                if b_terms:
                    peer = b_terms[0]
                    peer_device = peer.get('object', {}).get('device', {}).get('name', 'Unknown')
                    peer_port = peer.get('object', {}).get('name', 'Unknown')
                    peer_id = peer.get('object', {}).get('id', 0)
                    return (peer_device, peer_port, peer_id)

        # Check if our interface is on B side
        for term in b_terms:
            if term['object_id'] == interface_id:
                # Our interface is on B side, return A side peer
                if a_terms:
                    peer = a_terms[0]
                    peer_device = peer.get('object', {}).get('device', {}).get('name', 'Unknown')
                    peer_port = peer.get('object', {}).get('name', 'Unknown')
                    peer_id = peer.get('object', {}).get('id', 0)
                    return (peer_device, peer_port, peer_id)

        return None
    except Exception as e:
        print(f"    ✗ Error parsing cable peer: {e}")
        return None


def delete_cable(cable_id: int, dry_run: bool = False) -> bool:
    """Delete a cable."""
    if dry_run:
        return True

    try:
        response = requests.delete(
            f"{NETBOX_URL}/api/dcim/cables/{cable_id}/",
            headers=HEADERS,
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error deleting cable: {e}")
        return False


def create_cable(interface_a_id: int, interface_b_id: int, dry_run: bool = False) -> bool:
    """Create a new cable between two interfaces."""
    if dry_run:
        return True

    try:
        cable_data = {
            'a_terminations': [
                {
                    'object_type': 'dcim.interface',
                    'object_id': interface_a_id
                }
            ],
            'b_terminations': [
                {
                    'object_type': 'dcim.interface',
                    'object_id': interface_b_id
                }
            ],
            'status': 'connected'
        }

        response = requests.post(
            f"{NETBOX_URL}/api/dcim/cables/",
            headers=HEADERS,
            json=cable_data,
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error creating cable: {e}")
        return False


def add_journal_entry(device_id: int, message: str, dry_run: bool = False) -> bool:
    """Add a journal entry to a device."""
    if dry_run:
        return True

    try:
        journal_data = {
            'assigned_object_type': 'dcim.device',
            'assigned_object_id': device_id,
            'kind': 'danger',
            'comments': message
        }

        response = requests.post(
            f"{NETBOX_URL}/api/extras/journal-entries/",
            headers=HEADERS,
            json=journal_data,
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error adding journal entry: {e}")
        return False


def set_device_failed(device_id: int, dry_run: bool = False) -> bool:
    """Set device status to failed."""
    if dry_run:
        return True

    try:
        update_data = {
            'status': 'failed'
        }

        response = requests.patch(
            f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
            headers=HEADERS,
            json=update_data,
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"    ✗ Error setting device to failed: {e}")
        return False


def push_redis_event(device_name: str, original_config: Dict, detected_config: Dict,
                     redis_client, dry_run: bool = False) -> bool:
    """Push cable inversion event to Redis queue."""
    if dry_run:
        return True

    timestamp = datetime.utcnow().isoformat() + 'Z'

    event = {
        'event_type': 'cable_inversion_detected',
        'timestamp': timestamp,
        'device_name': device_name,
        'original_config': original_config,
        'detected_config': detected_config,
        'status': 'failed',
        'source': 'phase2_cable_validator'
    }

    try:
        event_json = json.dumps(event)
        redis_client.lpush(REDIS_QUEUE, event_json)
        return True
    except Exception as e:
        print(f"    ✗ Error pushing to Redis: {e}")
        return False


def process_server(server: Dict, redis_client, dry_run: bool = False) -> Dict:
    """Process a single server - invert production NIC cables."""
    device_id = server['id']
    device_name = server['name']
    site_name = server['site']['name'] if server.get('site') else 'Unknown'

    result = {
        'success': False,
        'message': '',
        'original_config': {},
        'detected_config': {}
    }

    print(f"  Site: {site_name}")

    # Get production interfaces
    prod_interfaces = get_production_interfaces(device_id)

    if len(prod_interfaces) != 2:
        result['message'] = f"Expected 2 production interfaces, found {len(prod_interfaces)}"
        print(f"    ⚠ {result['message']}")
        return result

    print(f"  Production NICs: {prod_interfaces[0]['name']}, {prod_interfaces[1]['name']}")

    # Get cables for both interfaces
    cable1 = get_cable_for_interface(prod_interfaces[0]['id'])
    cable2 = get_cable_for_interface(prod_interfaces[1]['id'])

    if not cable1 or not cable2:
        result['message'] = "One or both production NICs have no cable"
        print(f"    ⚠ {result['message']}")
        return result

    # Get peers
    peer1 = get_cable_peer(cable1, prod_interfaces[0]['id'])
    peer2 = get_cable_peer(cable2, prod_interfaces[1]['id'])

    if not peer1 or not peer2:
        result['message'] = "Could not determine cable peers"
        print(f"    ⚠ {result['message']}")
        return result

    # Store original configuration
    original_config = {
        prod_interfaces[0]['name']: {
            'peer_device': peer1[0],
            'peer_port': peer1[1]
        },
        prod_interfaces[1]['name']: {
            'peer_device': peer2[0],
            'peer_port': peer2[1]
        }
    }

    print(f"  Original Config:")
    print(f"    {prod_interfaces[0]['name']} → {peer1[0]}:{peer1[1]}")
    print(f"    {prod_interfaces[1]['name']} → {peer2[0]}:{peer2[1]}")

    # Invert: swap the peers
    detected_config = {
        prod_interfaces[0]['name']: {
            'peer_device': peer2[0],
            'peer_port': peer2[1]
        },
        prod_interfaces[1]['name']: {
            'peer_device': peer1[0],
            'peer_port': peer1[1]
        }
    }

    print(f"  Detected Config (inverted):")
    print(f"    {prod_interfaces[0]['name']} → {peer2[0]}:{peer2[1]}")
    print(f"    {prod_interfaces[1]['name']} → {peer1[0]}:{peer1[1]}")

    if dry_run:
        print(f"  [DRY RUN] Would invert cables and mark as Failed")
        result['success'] = True
        result['original_config'] = original_config
        result['detected_config'] = detected_config
        return result

    # Delete existing cables
    print(f"  → Deleting existing cables...")
    if not delete_cable(cable1['id'], dry_run):
        result['message'] = "Failed to delete cable 1"
        return result

    if not delete_cable(cable2['id'], dry_run):
        result['message'] = "Failed to delete cable 2"
        return result

    # Create inverted cables
    print(f"  → Creating inverted cables...")
    # prod_interfaces[0] now connects to peer2
    if not create_cable(prod_interfaces[0]['id'], peer2[2], dry_run):
        result['message'] = "Failed to create inverted cable 1"
        return result

    # prod_interfaces[1] now connects to peer1
    if not create_cable(prod_interfaces[1]['id'], peer1[2], dry_run):
        result['message'] = "Failed to create inverted cable 2"
        return result

    # Set device to failed
    print(f"  → Setting device status to Failed...")
    if not set_device_failed(device_id, dry_run):
        result['message'] = "Failed to set device status"
        return result

    # Add journal entry
    journal_message = f"""Cable Inversion Detected - Phase 2 Validation Failed

Original NetBox Configuration:
  {prod_interfaces[0]['name']} → {peer1[0]}:{peer1[1]}
  {prod_interfaces[1]['name']} → {peer2[0]}:{peer2[1]}

Detected Configuration (from service):
  {prod_interfaces[0]['name']} → {peer2[0]}:{peer2[1]}
  {prod_interfaces[1]['name']} → {peer1[0]}:{peer1[1]}

The production NICs are cross-connected. Physical cabling does not match NetBox documentation.
Server marked as Failed pending manual verification and cable correction.
"""

    print(f"  → Adding journal entry...")
    if not add_journal_entry(device_id, journal_message, dry_run):
        result['message'] = "Failed to add journal entry"
        return result

    # Push event to Redis
    print(f"  → Pushing event to Redis...")
    if not push_redis_event(device_name, original_config, detected_config, redis_client, dry_run):
        result['message'] = "Failed to push Redis event"
        return result

    print(f"  ✓ Server marked as Failed with inverted cables")

    result['success'] = True
    result['original_config'] = original_config
    result['detected_config'] = detected_config
    result['message'] = "Cable inversion completed"

    return result


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(
        description='Phase 2: Invert production NIC cables and mark servers as Failed',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would happen
  python phase2-invert-cables.py --dry-run

  # Process all staged servers
  python phase2-invert-cables.py

  # Process only 5 servers
  python phase2-invert-cables.py --limit 5

  # Process servers in specific site
  python phase2-invert-cables.py --site dc-east
        """
    )

    parser.add_argument('--limit', type=int, help='Process only N servers')
    parser.add_argument('--site', type=str, help='Only process servers in specific site')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')

    args = parser.parse_args()

    print("=" * 70)
    print("PHASE 2 - PRODUCTION NIC CABLE INVERSION SERVICE")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    # Connect to Redis
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False
        )
        redis_client.ping()
        print(f"✓ Connected to Redis: {REDIS_HOST}:{REDIS_PORT}")
        print(f"✓ Queue: {REDIS_QUEUE}")
    except Exception as e:
        print(f"✗ Failed to connect to Redis: {e}")
        return False

    # Fetch servers
    print(f"✓ Fetching servers from NetBox...")
    if args.site:
        print(f"  Filter: Site = {args.site}")
    if args.limit:
        print(f"  Limit: {args.limit} servers")

    servers = get_servers(args.site, args.limit)

    if not servers:
        print("\n✗ No servers found in 'staged' state")
        return False

    print(f"✓ Found {len(servers)} server(s) in 'staged' state\n")

    # Statistics
    stats = {
        'total': len(servers),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    # Process each server
    for i, server in enumerate(servers, 1):
        device_name = server['name']

        print(f"[{i}/{len(servers)}] {device_name}")

        try:
            result = process_server(server, redis_client, args.dry_run)

            if result['success']:
                stats['success'] += 1
            else:
                print(f"    ✗ {result['message']}")
                stats['skipped'] += 1

            print()

        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats['failed'] += 1
            print()

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total servers:           {stats['total']}")
    print(f"Cables inverted:         {stats['success']}")
    print(f"Skipped:                 {stats['skipped']}")
    if stats['failed'] > 0:
        print(f"Errors:                  {stats['failed']}")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠ DRY RUN - No changes were made")
    else:
        print(f"\n✓ Processed {stats['success']} servers")
        print(f"✓ All servers marked as Failed with inverted cables")
        print(f"✓ Events pushed to Redis queue: {REDIS_QUEUE}")

    print("=" * 70)
    return True


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
