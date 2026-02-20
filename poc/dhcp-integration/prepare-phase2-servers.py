#!/usr/bin/env python3
"""
Prepare Servers for Phase 2 Testing
====================================
Sets servers to 'discovered' state so they can be processed by Phase 2.

This script:
- Queries offline servers
- Sets their lifecycle_state to 'discovered'
- Sets their status to 'discovered'

Usage:
    python prepare-phase2-servers.py [--limit N] [--site SITE]
"""

import os
import sys
import requests
import argparse
from typing import List, Dict, Optional


NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}


def get_servers(site_filter: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """Fetch offline servers from NetBox."""
    fetch_limit = 2000 if not limit else max(200, limit * 10)

    params = {
        'limit': fetch_limit,
        'status': 'offline'
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
        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        if limit:
            servers = servers[:limit]

        return servers
    except Exception as e:
        print(f"✗ Error fetching servers: {e}")
        return []


def set_server_discovered(device_id: int, device_name: str) -> bool:
    """Set server to discovered state."""
    try:
        update_data = {
            'status': 'active',  # NetBox requires valid status
            'custom_fields': {
                'lifecycle_state': 'discovered'
            }
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
        print(f"  ✗ Error updating {device_name}: {e}")
        return False


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description='Prepare servers for Phase 2 testing')
    parser.add_argument('--limit', type=int, help='Process only N servers')
    parser.add_argument('--site', type=str, help='Only process servers in specific site')
    args = parser.parse_args()

    print("=" * 70)
    print("PREPARE SERVERS FOR PHASE 2")
    print("=" * 70)

    servers = get_servers(args.site, args.limit)

    if not servers:
        print("\n✗ No offline servers found")
        return False

    print(f"✓ Found {len(servers)} offline server(s)\n")

    success_count = 0

    for i, server in enumerate(servers, 1):
        device_name = server['name']
        device_id = server['id']
        site_name = server['site']['name'] if server.get('site') else 'Unknown'

        print(f"[{i}/{len(servers)}] {device_name} ({site_name})")

        if set_server_discovered(device_id, device_name):
            print(f"  ✓ Set to 'discovered' state")
            success_count += 1
        print()

    print("=" * 70)
    print(f"✓ Prepared {success_count}/{len(servers)} servers for Phase 2")
    print("=" * 70)
    return True


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
