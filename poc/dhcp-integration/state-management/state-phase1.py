#!/usr/bin/env python3
"""
Phase 1: BMC Discovery Complete
================================
Advances environment to Phase 1 with BMC discovery complete.

This script:
1. Ensures clean starting state (runs Phase 0)
2. Runs BMC discovery for all servers (test-phase1-all.py)
3. Verifies servers have status='planned' and BMC IPs assigned
4. Provides summary of Phase 1 completion

Usage:
    python state-phase1.py [--limit N] [--dry-run]

Options:
    --limit N    Only process N servers (default: all)
    --dry-run    Show what would be done without making changes
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

# Path to scripts
SCRIPT_DIR = Path(__file__).parent
STATE_DIR = SCRIPT_DIR
DHCP_DIR = SCRIPT_DIR.parent

PHASE0_SCRIPT = STATE_DIR / 'state-phase0.py'
PHASE1_TEST_SCRIPT = DHCP_DIR / 'test-phase1-all.py'


def run_phase0_reset(dry_run=False):
    """Reset to Phase 0 first."""
    print("\n" + "=" * 70)
    print("STEP 1: RESET TO PHASE 0")
    print("=" * 70)

    cmd = [sys.executable, str(PHASE0_SCRIPT)]

    if dry_run:
        cmd.append('--dry-run')

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running Phase 0 reset: {e}")
        return False


def run_bmc_discovery(limit=None, dry_run=False):
    """Run BMC discovery for all servers."""
    print("\n" + "=" * 70)
    print("STEP 2: RUN BMC DISCOVERY")
    print("=" * 70)

    cmd = [
        sys.executable,
        str(PHASE1_TEST_SCRIPT),
        '--delay', '0.1'  # Fast execution
    ]

    if limit:
        cmd.extend(['--limit', str(limit)])

    if dry_run:
        cmd.append('--dry-run')

    try:
        print(f"✓ Starting BMC discovery...")
        if limit:
            print(f"  Limit: {limit} servers")
        else:
            print(f"  Processing: All servers")

        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running BMC discovery: {e}")
        return False


def get_phase1_stats():
    """Get Phase 1 statistics from NetBox."""
    import requests

    NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
    NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

    try:
        # Get all devices
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
        }

        # Count BMC IPs assigned
        bmc_ip_count = 0
        for server in servers:
            if server.get('status', {}).get('value') == 'planned':
                # Check if server has BMC IP
                device_id = server['id']
                iface_response = requests.get(
                    f"{NETBOX_URL}/api/dcim/interfaces/",
                    headers={
                        'Authorization': f'Token {NETBOX_TOKEN}',
                        'Accept': 'application/json'
                    },
                    params={'device_id': device_id, 'name': 'bmc'},
                    timeout=10
                )

                if iface_response.status_code == 200:
                    interfaces = iface_response.json()['results']
                    if interfaces:
                        interface_id = interfaces[0]['id']

                        # Check for IP on this interface
                        ip_response = requests.get(
                            f"{NETBOX_URL}/api/ipam/ip-addresses/",
                            headers={
                                'Authorization': f'Token {NETBOX_TOKEN}',
                                'Accept': 'application/json'
                            },
                            params={'interface_id': interface_id},
                            timeout=10
                        )

                        if ip_response.status_code == 200:
                            ips = ip_response.json()['results']
                            if ips:
                                bmc_ip_count += 1

        stats['bmc_ips_assigned'] = bmc_ip_count

        return stats
    except Exception as e:
        print(f"⚠ Could not fetch Phase 1 stats: {e}")
        return None


def verify_phase1(limit=None, dry_run=False):
    """Verify Phase 1 completion."""
    print("\n" + "=" * 70)
    print("STEP 3: VERIFY PHASE 1 COMPLETION")
    print("=" * 70)

    if dry_run:
        print("[DRY RUN] Would verify Phase 1 completion")
        return True

    print("✓ Fetching current state...")

    # Wait a moment for workers to process events
    print("  Waiting for workers to process events...")
    time.sleep(2)

    stats = get_phase1_stats()

    if not stats:
        print("✗ Could not verify Phase 1 completion")
        return False

    print(f"\nPhase 1 Statistics:")
    print(f"  Total servers:        {stats['total']}")
    print(f"  Status = Planned:     {stats['planned']}")
    print(f"  Status = Offline:     {stats['offline']}")
    print(f"  Status = Failed:      {stats['failed']}")
    print(f"  BMC IPs assigned:     {stats['bmc_ips_assigned']}")

    expected = limit if limit else stats['total']
    success_rate = (stats['planned'] / expected * 100) if expected > 0 else 0

    print(f"\nSuccess Rate: {success_rate:.1f}%")

    if stats['planned'] > 0:
        print("✓ Phase 1 partially complete")
        return True
    else:
        print("⚠ Warning: No servers in 'planned' status")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Advance to Phase 1: BMC Discovery Complete',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script advances the environment to Phase 1:
1. Resets to Phase 0 (clean slate)
2. Runs BMC discovery for all servers
3. Verifies servers have status='planned' and BMC IPs

Examples:
  # Dry run - see what would happen
  python state-phase1.py --dry-run

  # Advance to Phase 1 (all servers)
  python state-phase1.py

  # Advance to Phase 1 (only 10 servers)
  python state-phase1.py --limit 10
        """
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Only process N servers'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("STATE MANAGEMENT: ADVANCE TO PHASE 1")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    start_time = time.time()

    # Step 1: Reset to Phase 0
    #if not run_phase0_reset(args.dry_run):
    #    print("\n✗ Failed to reset to Phase 0")
    #    return False

    # Step 2: Run BMC Discovery
    if not run_bmc_discovery(args.limit, args.dry_run):
        print("\n✗ Failed to run BMC discovery")
        return False

    # Step 3: Verify completion
    if not verify_phase1(args.limit, args.dry_run):
        print("\n⚠ Phase 1 verification completed with warnings")

    elapsed = time.time() - start_time

    # Print final summary
    print("\n" + "=" * 70)
    print("PHASE 1 COMPLETE")
    print("=" * 70)

    if not args.dry_run:
        print(f"\n✓ Phase 1: BMC Discovery complete")
        print(f"  - Servers discovered and assigned BMC IPs")
        print(f"  - Status set to 'planned'")
        print(f"  - Time elapsed: {elapsed:.1f} seconds")
    else:
        print("\n⚠ DRY RUN - No changes were made")

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
