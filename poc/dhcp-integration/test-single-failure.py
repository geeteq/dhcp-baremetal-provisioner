#!/usr/bin/env python3
"""
Test single server failure handling (non-dry-run)
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
print("Getting test server...")
response = requests.get(
    f"{NETBOX_URL}/api/dcim/devices/",
    headers=HEADERS,
    params={'name': 'CENT-SRV-010', 'limit': 1}
)
server = response.json()['results'][0]

print(f"Test server: {server['name']}")
print(f"Current status: {server['status']['value']}")
print(f"Device ID: {server['id']}")

# Try to update status to failed
print("\nAttempting to set status to 'failed'...")
response = requests.patch(
    f"{NETBOX_URL}/api/dcim/devices/{server['id']}/",
    headers=HEADERS,
    json={'status': 'failed'}
)

print(f"Response status code: {response.status_code}")

if response.status_code == 200:
    print("✓ Status update successful")
    updated = response.json()
    print(f"New status: {updated['status']['value']}")
else:
    print(f"✗ Status update failed")
    print(f"Error: {response.text}")

# Verify by re-fetching
print("\nVerifying status change...")
response = requests.get(
    f"{NETBOX_URL}/api/dcim/devices/{server['id']}/",
    headers=HEADERS
)
current = response.json()
print(f"Current status: {current['status']['value']}")

# Add a test journal entry
print("\nAdding test journal entry...")
response = requests.post(
    f"{NETBOX_URL}/api/extras/journal-entries/",
    headers=HEADERS,
    json={
        'assigned_object_type': 'dcim.device',
        'assigned_object_id': server['id'],
        'kind': 'danger',
        'comments': 'Test journal entry from test-single-failure.py'
    }
)

print(f"Response status code: {response.status_code}")
if response.status_code == 201:
    print("✓ Journal entry created successfully")
else:
    print(f"✗ Journal entry creation failed")
    print(f"Error: {response.text}")
