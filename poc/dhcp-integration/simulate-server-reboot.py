#!/usr/bin/env python3
"""
Simulate Server Reboot and BMC DHCP Discovery
==============================================
Simulates the complete lifecycle of a server reboot:
1. Clear existing BMC IP assignment
2. Simulate server power cycle
3. BMC requests DHCP lease
4. DHCP server assigns IP from site's BMC pool
5. Triggers BMC discovery workflow in NetBox

Usage:
    python simulate-server-reboot.py WEST-SRV-201
"""

import os
import sys
import django
import redis
import json
import ipaddress
import time
from datetime import datetime

# Setup Django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface
from ipam.models import IPAddress, Prefix


def clear_bmc_ip(server):
    """Remove existing BMC IP assignment."""
    print(f"\n{'='*70}")
    print(f"STEP 1: Clearing BMC IP Assignment")
    print(f"{'='*70}")

    try:
        bmc_interface = Interface.objects.get(device=server, name='bmc')

        # Find and delete any IPs assigned to this interface
        ips = IPAddress.objects.filter(
            assigned_object_type__model='interface',
            assigned_object_id=bmc_interface.id
        )

        count = ips.count()
        if count > 0:
            for ip in ips:
                print(f"  Removing IP: {ip.address}")
                ip.delete()
            print(f"  ✓ Cleared {count} IP assignment(s)")
        else:
            print(f"  - No IP assignments to clear")

        return bmc_interface

    except Interface.DoesNotExist:
        print(f"  ✗ BMC interface not found!")
        sys.exit(1)


def simulate_power_cycle(server):
    """Simulate server power cycle."""
    print(f"\n{'='*70}")
    print(f"STEP 2: Simulating Server Power Cycle")
    print(f"{'='*70}")

    print(f"  → Server: {server.name}")
    print(f"  → Location: {server.site.name}, {server.rack.name} U{server.position}")
    print(f"  → Initiating reboot...")

    for i in range(3):
        time.sleep(0.5)
        print(f"  {'.' * (i + 1)}")

    print(f"  ✓ Server power cycled")
    print(f"  ✓ BMC initializing...")


def get_available_bmc_ip(site):
    """Get next available IP from site's BMC pool."""
    print(f"\n{'='*70}")
    print(f"STEP 3: DHCP - Allocating BMC IP")
    print(f"{'='*70}")

    # Determine BMC prefix based on site
    site_to_prefix = {
        'dc-east': '10.22.0.0/23',
        'dc-west': '10.22.2.0/23',
        'dc-center': '10.22.4.0/23',
    }

    prefix_str = site_to_prefix.get(site.slug)
    if not prefix_str:
        print(f"  ✗ No BMC prefix defined for site {site.slug}")
        sys.exit(1)

    print(f"  → Site: {site.name}")
    print(f"  → BMC Subnet: {prefix_str}")
    print(f"  → Searching for available IP...")

    network = ipaddress.ip_network(prefix_str)

    # Find first available IP
    for ip in network.hosts():
        ip_str = str(ip)
        last_octet = int(ip_str.split('.')[-1])

        # Use safe range (.10 - .250)
        if last_octet < 10 or last_octet > 250:
            continue

        # Check if IP already exists in NetBox
        if not IPAddress.objects.filter(address=f"{ip_str}/24").exists():
            print(f"  ✓ Allocated IP: {ip_str}")
            return ip_str

    print(f"  ✗ No available IPs in range!")
    sys.exit(1)


def send_dhcp_lease_event(server, bmc_interface, ip_address):
    """Send DHCP lease event to Redis queue."""
    print(f"\n{'='*70}")
    print(f"STEP 4: Publishing DHCP Lease Event")
    print(f"{'='*70}")

    # Connect to Redis (try container network first, then localhost)
    redis_hosts = [
        ('bmc-redis', 6379),  # Docker container network
        ('redis', 6379),       # Alternative container name
        ('localhost', 6380),   # Host machine
    ]

    redis_client = None
    for host, port in redis_hosts:
        try:
            client = redis.Redis(host=host, port=port, decode_responses=False, socket_connect_timeout=1)
            client.ping()
            redis_client = client
            print(f"  ✓ Connected to Redis at {host}:{port}")
            break
        except redis.RedisError:
            continue

    if not redis_client:
        print(f"  ✗ Failed to connect to Redis on any host")
        sys.exit(1)

    # Create DHCP lease event
    event = {
        'event_type': 'bmc_dhcp_lease',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'mac_address': str(bmc_interface.mac_address),
        'ip_address': ip_address,
        'hostname': server.name.lower(),
        'source': 'simulated_dhcp_server'
    }

    print(f"\n  Event Details:")
    print(f"    MAC Address: {event['mac_address']}")
    print(f"    IP Address:  {event['ip_address']}")
    print(f"    Hostname:    {event['hostname']}")
    print(f"    Timestamp:   {event['timestamp']}")

    # Push to Redis queue
    queue_name = 'netbox:bmc:discovered'
    try:
        event_json = json.dumps(event)
        redis_client.lpush(queue_name, event_json)
        print(f"\n  ✓ Event published to Redis queue: {queue_name}")
    except Exception as e:
        print(f"  ✗ Failed to publish event: {e}")
        sys.exit(1)
    finally:
        redis_client.close()


def wait_for_discovery(server):
    """Wait for NetBox worker to process the event."""
    print(f"\n{'='*70}")
    print(f"STEP 5: Waiting for NetBox Discovery")
    print(f"{'='*70}")

    print(f"  → Waiting for worker to process event...")

    # Wait up to 10 seconds for state change
    for i in range(10):
        time.sleep(1)
        server.refresh_from_db()

        state = server.custom_field_data.get('lifecycle_state', 'unknown')
        if state == 'discovered':
            print(f"  ✓ Server discovered! (after {i+1}s)")
            return True

        print(f"  {'.' * (i + 1)}", end='\r')

    print(f"\n  ⚠ Discovery not completed yet (check worker logs)")
    return False


def verify_result(server):
    """Verify the final result."""
    print(f"\n{'='*70}")
    print(f"STEP 6: Verification")
    print(f"{'='*70}")

    server.refresh_from_db()

    # Check lifecycle state
    state = server.custom_field_data.get('lifecycle_state', 'unknown')
    print(f"\n  Lifecycle State: {state}")

    # Check BMC IP
    try:
        bmc_interface = Interface.objects.get(device=server, name='bmc')
        bmc_ips = IPAddress.objects.filter(
            assigned_object_type__model='interface',
            assigned_object_id=bmc_interface.id
        )

        if bmc_ips.exists():
            ip = bmc_ips.first()
            print(f"  BMC IP Address:  {ip.address}")
            print(f"  BMC DNS Name:    {ip.dns_name or 'N/A'}")
            print(f"  BMC MAC Address: {bmc_interface.mac_address}")
        else:
            print(f"  BMC IP Address:  Not assigned")
    except Exception as e:
        print(f"  ✗ Error checking BMC: {e}")


def main():
    """Main execution."""
    if len(sys.argv) < 2:
        print("Usage: python simulate-server-reboot.py <SERVER_NAME>")
        print("Example: python simulate-server-reboot.py WEST-SRV-201")
        sys.exit(1)

    server_name = sys.argv[1]

    print("="*70)
    print("SERVER REBOOT & BMC DHCP DISCOVERY SIMULATION")
    print("="*70)
    print(f"\nTarget Server: {server_name}")

    # Get server
    try:
        server = Device.objects.get(name=server_name)
        print(f"✓ Server found: {server.name}")
        print(f"  Site: {server.site.name}")
        print(f"  Rack: {server.rack.name} U{server.position}")
    except Device.DoesNotExist:
        print(f"✗ Server '{server_name}' not found in NetBox!")
        sys.exit(1)

    # Execute simulation steps
    bmc_interface = clear_bmc_ip(server)
    simulate_power_cycle(server)
    ip_address = get_available_bmc_ip(server.site)
    send_dhcp_lease_event(server, bmc_interface, ip_address)
    wait_for_discovery(server)
    verify_result(server)

    # Final summary
    print(f"\n{'='*70}")
    print("✓ SIMULATION COMPLETED!")
    print("="*70)
    print(f"\nServer {server.name} has been rebooted and rediscovered.")
    print(f"Check NetBox UI: http://localhost:8000/dcim/devices/{server.id}/")
    print("="*70)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Simulation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
