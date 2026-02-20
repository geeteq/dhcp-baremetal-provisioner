#!/usr/bin/env python3
"""
DHCP Lease Worker
=================
Consumes DHCP lease events from Redis and updates NetBox.

Handles both BMC and management network leases.
This worker ONLY interacts with NetBox - it consumes from Redis.

Event format:
{
  "event_type": "dhcp_lease",
  "network_type": "management" | "bmc",
  "mac_address": "A0:36:9F:XX:XX:XX",
  "ip_address": "10.23.0.50",
  "site": "dc-east",
  "timestamp": "2026-02-13T12:00:00Z",
  "source": "dhcp_server"
}

Usage:
    docker cp dhcp-lease-worker.py netbox:/tmp/
    docker exec -d netbox python /tmp/dhcp-lease-worker.py
"""

import os
import sys
import json
import time
import django

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

import redis
from dcim.models import Device, Interface
from ipam.models import IPAddress
from netbox_utils import (
    add_journal_entry_django,
    add_journal_state_change_django,
    add_journal_ip_assignment_django,
    add_journal_discovery_django,
    add_journal_error_django
)


def find_device_by_mac(mac_address, interface_name=None):
    """Find device by MAC address on specific interface."""
    mac_normalized = mac_address.upper().replace('-', ':')

    print(f"  → Searching for device with MAC: {mac_normalized}")

    # Search for interface with this MAC
    query = Interface.objects.filter(mac_address=mac_normalized)

    if interface_name:
        query = query.filter(name=interface_name)

    interfaces = list(query)

    if not interfaces:
        print(f"  ✗ No interface found with MAC: {mac_normalized}")
        return None, None

    interface = interfaces[0]
    device = interface.device

    print(f"  ✓ Found: {device.name}/{interface.name}")

    return device, interface


def assign_ip_to_interface(interface, ip_address, description):
    """Assign IP address to interface."""
    print(f"  → Assigning IP {ip_address} to {interface.device.name}/{interface.name}")

    # Check if IP already assigned to this interface
    existing = IPAddress.objects.filter(
        assigned_object_type__model='interface',
        assigned_object_id=interface.id
    )

    if existing.exists():
        print(f"  ⚠ Interface already has IP: {existing.first().address}")
        # Update existing IP
        ip_obj = existing.first()
        old_ip = ip_obj.address
        ip_obj.address = f"{ip_address}/24"
        ip_obj.description = description
        ip_obj.save()
        print(f"  ✓ Updated IP: {old_ip} → {ip_address}/24")

        # Add journal entry for IP update
        add_journal_entry_django(
            interface.device,
            f"IP address updated on {interface.name}: {old_ip} → {ip_address}/24",
            kind='info'
        )
        return True

    # Create new IP
    try:
        ip_obj = IPAddress.objects.create(
            address=f"{ip_address}/24",
            status='active',
            description=description
        )
        ip_obj.assigned_object = interface
        ip_obj.save()
        print(f"  ✓ Assigned: {ip_address}/24")

        # Add journal entry for IP assignment
        add_journal_ip_assignment_django(interface.device, interface.name, ip_address)
        return True
    except Exception as e:
        print(f"  ✗ Failed to assign IP: {e}")
        # Add journal entry for error
        add_journal_error_django(interface.device, f"Failed to assign IP {ip_address} to {interface.name}: {e}")
        return False


def update_device_state(device, new_state):
    """Update device lifecycle state."""
    current_state = device.custom_field_data.get('lifecycle_state', 'unknown')

    if current_state == new_state:
        print(f"  - Device already in state: {new_state}")
        return

    print(f"  → Updating state: {current_state} → {new_state}")
    device.custom_field_data['lifecycle_state'] = new_state
    device.save()
    print(f"  ✓ State updated")

    # Add journal entry for state change
    add_journal_state_change_django(device, current_state, new_state)


def process_dhcp_lease(event):
    """Process a DHCP lease event."""
    print("="*70)
    print(f"PROCESSING DHCP LEASE EVENT")
    print("="*70)

    try:
        network_type = event.get('network_type', 'unknown')
        mac_address = event['mac_address']
        ip_address = event['ip_address']
        site = event.get('site', 'unknown')

        print(f"\nEvent Details:")
        print(f"  Network Type: {network_type}")
        print(f"  MAC Address:  {mac_address}")
        print(f"  IP Address:   {ip_address}")
        print(f"  Site:         {site}")
        print(f"  Source:       {event.get('source', 'unknown')}")

        # Determine interface name based on network type
        if network_type == 'bmc':
            interface_name = 'bmc'
            description = f"BMC IP from DHCP - {event.get('timestamp', '')}"
        elif network_type == 'management':
            interface_name = 'mgmt0'
            description = f"Management IP from DHCP - {event.get('timestamp', '')}"
        else:
            print(f"  ✗ Unknown network type: {network_type}")
            return False

        print(f"\n[1/3] FINDING DEVICE")
        device, interface = find_device_by_mac(mac_address, interface_name)

        if not device or not interface:
            print(f"\n✗ FAILED: Device not found")
            # Cannot add journal entry since device not found
            return False

        # Add discovery journal entry
        add_journal_discovery_django(device, network_type.upper(), mac_address, ip_address)

        print(f"\n[2/3] ASSIGNING IP")
        success = assign_ip_to_interface(interface, ip_address, description)

        if not success:
            print(f"\n✗ FAILED: IP assignment failed")
            return False

        print(f"\n[3/3] UPDATING STATE")
        # Update device state based on network type
        if network_type == 'bmc':
            update_device_state(device, 'discovered')
        elif network_type == 'management':
            # Management network lease means server is being configured
            current_state = device.custom_field_data.get('lifecycle_state', 'offline')
            if current_state in ['offline', 'discovered']:
                update_device_state(device, 'provisioning')

        print(f"\n{'='*70}")
        print(f"✓ LEASE PROCESSED SUCCESSFULLY")
        print(f"  Device: {device.name}")
        print(f"  Interface: {interface.name}")
        print(f"  IP: {ip_address}/24")
        print("="*70)

        return True

    except KeyError as e:
        print(f"\n✗ FAILED: Missing required field: {e}")
        return False
    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main worker loop."""
    print("="*70)
    print("DHCP LEASE WORKER STARTED")
    print("="*70)
    print("\nWaiting for DHCP lease events from Redis...")
    print("Queue: netbox:dhcp:leases")
    print("="*70)

    # Connect to Redis
    try:
        # Try different Redis hosts
        redis_hosts = [
            ('bmc-redis', 6379),
            ('redis', 6379),
            ('localhost', 6380),
        ]

        redis_client = None
        for host, port in redis_hosts:
            try:
                client = redis.Redis(host=host, port=port, decode_responses=False, socket_connect_timeout=2)
                client.ping()
                redis_client = client
                print(f"\n✓ Connected to Redis at {host}:{port}\n")
                break
            except redis.RedisError:
                continue

        if not redis_client:
            print("\n✗ Failed to connect to Redis")
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ Failed to connect to Redis: {e}")
        sys.exit(1)

    # Main event loop
    queue_name = 'netbox:dhcp:leases'

    while True:
        try:
            # Blocking pop with 1 second timeout
            result = redis_client.brpop(queue_name, timeout=1)

            if result:
                queue, event_data = result
                event_data = event_data.decode('utf-8')

                try:
                    event = json.loads(event_data)
                    print(f"\n{'='*70}")
                    print(f"NEW EVENT RECEIVED")
                    print(f"{'='*70}\n")
                    process_dhcp_lease(event)
                except json.JSONDecodeError as e:
                    print(f"\n✗ Invalid JSON: {e}")

        except redis.RedisError as e:
            print(f"\n✗ Redis error: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n\n✓ Worker stopped by user")
            break
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)

    redis_client.close()
    print("\n✓ Worker shutdown complete")


if __name__ == '__main__':
    main()
