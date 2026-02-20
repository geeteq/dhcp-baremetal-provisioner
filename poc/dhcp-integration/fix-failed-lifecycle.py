#!/usr/bin/env python3
"""
Fix Failed Servers Lifecycle State
===================================
Updates all servers with status='failed' to also have lifecycle_state='failed'
"""

import os
import requests

NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

def get_failed_servers():
    """Get all servers with status=failed."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers=HEADERS,
            params={'limit': 2000, 'status': 'failed'},
            timeout=30
        )
        response.raise_for_status()
        all_devices = response.json()['results']
        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]
        return servers
    except Exception as e:
        print(f"✗ Error: {e}")
        return []

def update_lifecycle_state(device_id, device_name):
    """Update lifecycle_state to failed."""
    try:
        update_data = {
            'custom_fields': {
                'lifecycle_state': 'failed'
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

print("=" * 70)
print("FIX FAILED SERVERS LIFECYCLE STATE")
print("=" * 70)

servers = get_failed_servers()
print(f"✓ Found {len(servers)} failed servers\n")

success = 0
for i, server in enumerate(servers, 1):
    name = server['name']
    device_id = server['id']
    lifecycle = server.get('custom_fields', {}).get('lifecycle_state', 'unknown')

    print(f"[{i}/{len(servers)}] {name} (lifecycle: {lifecycle})")

    if lifecycle == 'failed':
        print(f"  ✓ Already set to failed")
        success += 1
    else:
        if update_lifecycle_state(device_id, name):
            print(f"  ✓ Updated: {lifecycle} → failed")
            success += 1

print(f"\n{'=' * 70}")
print(f"✓ Updated {success}/{len(servers)} servers")
print("=" * 70)
