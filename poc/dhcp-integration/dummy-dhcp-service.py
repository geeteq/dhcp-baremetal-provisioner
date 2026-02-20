#!/usr/bin/env python3
"""
Dummy DHCP Service
==================
Simulates a DHCP server that:
1. Receives DHCP request with MAC address
2. Allocates IP from appropriate site's management pool
3. Publishes lease event to Redis

This service ONLY talks to Redis - no direct NetBox access.

Usage:
    python dummy-dhcp-service.py <MAC_ADDRESS> <SITE>

Example:
    python dummy-dhcp-service.py A0:36:9F:C8:C0:52 dc-east
"""

import sys
import json
import redis
import random
from datetime import datetime


def allocate_ip_from_pool(site_slug):
    """Allocate random IP from site's management pool."""
    # Management network pools by site
    pools = {
        'dc-east': {
            'network': '10.23.0.0/23',
            'range_start': '10.23.0.10',
            'range_end': '10.23.1.250',
        },
        'dc-west': {
            'network': '10.23.2.0/23',
            'range_start': '10.23.2.10',
            'range_end': '10.23.3.250',
        },
        'dc-center': {
            'network': '10.23.4.0/23',
            'range_start': '10.23.4.10',
            'range_end': '10.23.5.250',
        }
    }

    pool = pools.get(site_slug)
    if not pool:
        print(f"✗ Unknown site: {site_slug}")
        return None

    # Generate random IP in range (simplified for demo)
    # In real DHCP, this would check lease database
    third_octet = int(pool['range_start'].split('.')[2])
    fourth_octet = random.randint(10, 250)

    ip = f"10.23.{third_octet}.{fourth_octet}"

    return ip, pool['network']


def publish_dhcp_lease(mac_address, ip_address, site_slug, network_type='management'):
    """Publish DHCP lease event to Redis."""
    # Connect to Redis
    try:
        redis_client = redis.Redis(host='localhost', port=6380, decode_responses=False)
        redis_client.ping()
    except redis.RedisError as e:
        print(f"✗ Failed to connect to Redis: {e}")
        return False

    # Create DHCP lease event
    event = {
        'event_type': 'dhcp_lease',
        'network_type': network_type,  # 'bmc' or 'management'
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'mac_address': mac_address,
        'ip_address': ip_address,
        'site': site_slug,
        'source': 'dummy_dhcp_service'
    }

    queue_name = 'netbox:dhcp:leases'

    try:
        event_json = json.dumps(event)
        redis_client.lpush(queue_name, event_json)
        print(f"✓ Published to Redis queue: {queue_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to publish: {e}")
        return False
    finally:
        redis_client.close()


def main():
    """Main DHCP service logic."""
    print("="*70)
    print("DUMMY DHCP SERVICE")
    print("="*70)

    if len(sys.argv) < 3:
        print("\nUsage: python dummy-dhcp-service.py <MAC_ADDRESS> <SITE>")
        print("Example: python dummy-dhcp-service.py A0:36:9F:C8:C0:52 dc-east")
        sys.exit(1)

    mac_address = sys.argv[1]
    site_slug = sys.argv[2]

    print(f"\n[1/3] DHCP REQUEST RECEIVED")
    print(f"  MAC Address: {mac_address}")
    print(f"  Site: {site_slug}")

    print(f"\n[2/3] IP ALLOCATION")
    result = allocate_ip_from_pool(site_slug)
    if not result:
        sys.exit(1)

    ip_address, network = result
    print(f"  Network: {network}")
    print(f"  Allocated IP: {ip_address}")

    print(f"\n[3/3] PUBLISHING LEASE EVENT")
    success = publish_dhcp_lease(mac_address, ip_address, site_slug)

    if success:
        print(f"\n{'='*70}")
        print("✓ DHCP LEASE COMPLETED")
        print("="*70)
        print(f"\nLease Details:")
        print(f"  MAC: {mac_address}")
        print(f"  IP:  {ip_address}/24")
        print(f"  Site: {site_slug}")
        print(f"\nEvent published to ESB - Worker will process.")
        print("="*70)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
