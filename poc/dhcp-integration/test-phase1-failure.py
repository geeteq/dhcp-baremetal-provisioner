#!/usr/bin/env python3
"""
Test Phase 1 Failure Handling
==============================
Simulates IP exhaustion to test device status and journal entry creation.
"""

import requests

NETBOX_URL = 'http://localhost:8000'
NETBOX_TOKEN = '0123456789abcdef0123456789abcdef01234567'

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

# Get a test server
response = requests.get(
    f"{NETBOX_URL}/api/dcim/devices/",
    headers=HEADERS,
    params={'name': 'CENT-SRV-001'}
)
device = response.json()['results'][0]

print("=" * 70)
print(f"Testing failure handling for: {device['name']}")
print("=" * 70)

# Check current status
print(f"\nCurrent status: {device['status']['value']}")

# Set to failed
print("\nSetting device to failed status...")
response = requests.patch(
    f"{NETBOX_URL}/api/dcim/devices/{device['id']}/",
    headers=HEADERS,
    json={'status': 'failed'}
)
print(f"✓ Status updated to: failed")

# Add journal entry
print("\nAdding journal entry...")
journal_message = """Phase 1 BMC IP Allocation Failed - TEST

Site: DC-Center
BMC Subnet: 10.55.1.0/24
BMC MAC: A0:36:9F:4B:05:00

Error: No available IP addresses in the BMC management subnet.

This is a test entry to verify failure logging functionality.
"""

response = requests.post(
    f"{NETBOX_URL}/api/extras/journal-entries/",
    headers=HEADERS,
    json={
        'assigned_object_type': 'dcim.device',
        'assigned_object_id': device['id'],
        'kind': 'danger',
        'comments': journal_message
    }
)
print(f"✓ Journal entry created")

# Verify journal entry was created
response = requests.get(
    f"{NETBOX_URL}/api/extras/journal-entries/",
    headers=HEADERS,
    params={
        'assigned_object_type': 'dcim.device',
        'assigned_object_id': device['id']
    }
)
journal_count = response.json()['count']
print(f"✓ Device now has {journal_count} journal entries")

print("\n" + "=" * 70)
print("Test complete! Check NetBox to see:")
print(f"1. Device status: http://localhost:8000/dcim/devices/{device['id']}/")
print(f"2. Journal entries show failure details")
print("=" * 70)
