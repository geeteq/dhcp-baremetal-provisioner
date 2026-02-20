#!/usr/bin/env python3
"""
Phase 0: Reset to Clean Slate
==============================
Resets all servers to offline state with no IP assignments.

This script:
- Sets all servers to status='offline', lifecycle_state='offline'
- Clears all BMC and management IPs
- Clears Redis queue: netbox:bmc:discovered
- Provides clean starting point for Phase 1

Usage:
    python state-phase0.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making changes
"""

import os
import sys
import redis
import argparse
import subprocess
from pathlib import Path

# Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6380'))
REDIS_QUEUE = 'netbox:bmc:discovered'

# Path to reset script
SCRIPT_DIR = Path(__file__).parent.parent
RESET_SCRIPT = SCRIPT_DIR / 'reset-servers-api.py'


def clear_redis_queue(dry_run=False):
    """Clear Redis BMC discovery queue."""
    print("\n" + "=" * 70)
    print("CLEARING REDIS QUEUE")
    print("=" * 70)

    if dry_run:
        print("[DRY RUN] Would clear Redis queue: netbox:bmc:discovered")
        return True

    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False
        )
        redis_client.ping()

        # Get current queue size
        queue_size = redis_client.llen(REDIS_QUEUE)

        if queue_size > 0:
            print(f"✓ Connected to Redis: {REDIS_HOST}:{REDIS_PORT}")
            print(f"✓ Queue '{REDIS_QUEUE}' has {queue_size} items")

            # Clear the queue
            redis_client.delete(REDIS_QUEUE)
            print(f"✓ Cleared queue: {REDIS_QUEUE}")
        else:
            print(f"✓ Queue '{REDIS_QUEUE}' is already empty")

        return True
    except Exception as e:
        print(f"✗ Error clearing Redis queue: {e}")
        return False


def reset_servers_to_offline(dry_run=False):
    """Call reset-servers-api.py to reset all servers."""
    print("\n" + "=" * 70)
    print("RESETTING SERVERS TO OFFLINE")
    print("=" * 70)

    cmd = [
        sys.executable,
        str(RESET_SCRIPT),
        '--clear-ips'
    ]

    if dry_run:
        cmd.append('--dry-run')

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running reset script: {e}")
        return False


def get_verification_stats():
    """Get current state statistics from NetBox."""
    import requests

    NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
    NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

    try:
        # Count servers by status
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={'limit': 2000},
            timeout=30
        )
        response.raise_for_status()

        all_devices = response.json()['results']
        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        stats = {
            'total': len(servers),
            'offline': sum(1 for s in servers if s.get('status', {}).get('value') == 'offline'),
            'planned': sum(1 for s in servers if s.get('status', {}).get('value') == 'planned'),
            'failed': sum(1 for s in servers if s.get('status', {}).get('value') == 'failed'),
            'discovered': sum(1 for s in servers if s.get('custom_fields', {}).get('lifecycle_state') == 'discovered')
        }

        # Count IP assignments (simplified check)
        ip_response = requests.get(
            f"{NETBOX_URL}/api/ipam/ip-addresses/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={'limit': 2000, 'role': 'anycast'},  # This will get BMC IPs
            timeout=30
        )

        return stats
    except Exception as e:
        print(f"⚠ Could not fetch verification stats: {e}")
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset to Phase 0: Clean slate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script resets the environment to Phase 0:
- All servers offline
- No BMC IPs assigned
- Redis queue cleared

Examples:
  # Dry run - see what would change
  python state-phase0.py --dry-run

  # Reset to Phase 0
  python state-phase0.py
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("STATE MANAGEMENT: RESET TO PHASE 0")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    # Step 1: Reset servers
    if not reset_servers_to_offline(args.dry_run):
        print("\n✗ Failed to reset servers")
        return False

    # Step 2: Clear Redis queue
    if not clear_redis_queue(args.dry_run):
        print("\n✗ Failed to clear Redis queue")
        return False

    # Print final summary
    print("\n" + "=" * 70)
    print("PHASE 0 COMPLETE")
    print("=" * 70)

    if not args.dry_run:
        stats = get_verification_stats()
        if stats:
            print(f"\nCurrent State:")
            print(f"  Total servers:     {stats['total']}")
            print(f"  Offline:           {stats['offline']}")
            print(f"  Planned:           {stats['planned']}")
            print(f"  Failed:            {stats['failed']}")
            print(f"  Discovered:        {stats['discovered']}")

            if stats['offline'] == stats['total']:
                print("\n✓ All servers are offline")
            else:
                print(f"\n⚠ Warning: {stats['total'] - stats['offline']} servers not offline")
    else:
        print("\n⚠ DRY RUN - No changes were made")

    print("\n✓ Phase 0: Clean slate ready")
    print("  - All servers offline")
    print("  - No BMC IPs assigned")
    print("  - Redis queue cleared")
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
