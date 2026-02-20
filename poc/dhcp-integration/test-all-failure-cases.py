#!/usr/bin/env python3
"""
Test All Failure Cases in Phase 1
==================================
Creates test scenarios for each type of failure to verify status updates and journal entries.
"""

import requests
import json

NETBOX_URL = 'http://localhost:8000'
NETBOX_TOKEN = '0123456789abcdef0123456789abcdef01234567'

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

print("=" * 70)
print("TEST ALL PHASE 1 FAILURE CASES")
print("=" * 70)

# Test 1: Get a server with no BMC interface (simulate by checking current state)
print("\n1. Testing servers with failure states...")

# Get all failed servers
response = requests.get(
    f"{NETBOX_URL}/api/dcim/devices/",
    headers=HEADERS,
    params={'status': 'failed', 'limit': 10}
)
failed_devices = response.json()['results']
failed_servers = [d for d in failed_devices if d.get('role') and 'server' in d['role']['name'].lower()]

print(f"\n✓ Found {len(failed_servers)} servers with failed status")

if failed_servers:
    # Check first failed server's journal entries
    test_server = failed_servers[0]
    print(f"\nChecking journal entries for: {test_server['name']}")

    response = requests.get(
        f"{NETBOX_URL}/api/extras/journal-entries/",
        headers=HEADERS,
        params={
            'assigned_object_type': 'dcim.device',
            'assigned_object_id': test_server['id'],
            'limit': 5
        }
    )

    journals = response.json()['results']
    print(f"✓ Found {len(journals)} journal entries")

    if journals:
        print(f"\nMost recent journal entry:")
        print(f"  Kind: {journals[0]['kind']['value']}")
        print(f"  Timestamp: {journals[0]['created']}")
        print(f"  Comments (first 200 chars):")
        print(f"  {journals[0]['comments'][:200]}...")

# Test with actual Phase 1 script
print("\n" + "=" * 70)
print("Running Phase 1 script with --limit 5 to test failure handling...")
print("=" * 70)

import subprocess
result = subprocess.run(
    ['python', 'test-phase1-all.py', '--limit', '5', '--dry-run'],
    capture_output=True,
    text=True,
    cwd='/Users/gabe/ai/bm/poc/dhcp-integration'
)

# Show relevant output
output_lines = result.stdout.split('\n')
for line in output_lines:
    if 'Device status' in line or 'Journal entry' in line or 'Server' in line or '✗' in line or '✓' in line:
        print(line)

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
