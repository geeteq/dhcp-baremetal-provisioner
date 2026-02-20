#!/usr/bin/env python3
"""
Phase 2: Cable Validation Complete
===================================
Advances environment to Phase 2 with cable validation (inverted cables).

This script:
1. Ensures Phase 1 is complete (runs Phase 1)
2. Sets servers from 'planned' to 'staged' status
3. Runs cable inversion script (phase2-invert-cables.py)
4. Verifies servers have status='failed' with inverted cables
5. Provides summary of Phase 2 completion

Usage:
    python state-phase2.py [--limit N] [--dry-run]

Options:
    --limit N    Only process N servers (default: all)
    --dry-run    Show what would be done without making changes
"""

import os
import sys
import time
import argparse
import subprocess
import requests
from pathlib import Path

# Configuration
NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

HEADERS = {
    'Authorization': f'Token {NETBOX_TOKEN}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

# Path to scripts
SCRIPT_DIR = Path(__file__).parent
STATE_DIR = SCRIPT_DIR
DHCP_DIR = SCRIPT_DIR.parent

PHASE1_SCRIPT = STATE_DIR / 'state-phase1.py'
PHASE2_INVERT_SCRIPT = DHCP_DIR / 'phase2-invert-cables.py'


def run_phase1(limit=None, dry_run=False):
    """Ensure Phase 1 is complete."""
    print("\n" + "=" * 70)
    print("STEP 1: ENSURE PHASE 1 COMPLETE")
    print("=" * 70)

    cmd = [sys.executable, str(PHASE1_SCRIPT)]

    if limit:
        cmd.extend(['--limit', str(limit)])

    if dry_run:
        cmd.append('--dry-run')

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running Phase 1: {e}")
        return False


def set_servers_to_staged(limit=None, dry_run=False):
    """Set servers from 'planned' to 'staged' status."""
    print("\n" + "=" * 70)
    print("STEP 2: SET SERVERS TO 'staged' STATUS")
    print("=" * 70)

    if dry_run:
        print("[DRY RUN] Would set servers to 'staged' status")
        return True

    try:
        # Get all servers with status='planned'
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers=HEADERS,
            params={
                'limit': 2000,
                'status': 'planned'
            },
            timeout=30
        )
        response.raise_for_status()

        all_devices = response.json()['results']
        servers = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        if limit:
            servers = servers[:limit]

        if not servers:
            print("✗ No servers found with status='planned'")
            return False

        print(f"✓ Found {len(servers)} server(s) with status='planned'")

        # Update each server to 'staged' status
        success_count = 0
        for i, server in enumerate(servers, 1):
            device_id = server['id']
            device_name = server['name']

            print(f"[{i}/{len(servers)}] {device_name}")

            update_data = {
                'status': 'staged'
            }

            try:
                response = requests.patch(
                    f"{NETBOX_URL}/api/dcim/devices/{device_id}/",
                    headers=HEADERS,
                    json=update_data,
                    timeout=10
                )
                response.raise_for_status()
                print(f"  ✓ Set to 'staged'")
                success_count += 1
            except Exception as e:
                print(f"  ✗ Error: {e}")

        print(f"\n✓ Updated {success_count}/{len(servers)} servers to 'staged'")
        return success_count > 0

    except Exception as e:
        print(f"✗ Error setting servers to staged: {e}")
        return False


def run_cable_inversion(limit=None, dry_run=False):
    """Run cable inversion script."""
    print("\n" + "=" * 70)
    print("STEP 3: RUN CABLE INVERSION")
    print("=" * 70)

    cmd = [sys.executable, str(PHASE2_INVERT_SCRIPT)]

    if limit:
        cmd.extend(['--limit', str(limit)])

    if dry_run:
        cmd.append('--dry-run')

    try:
        print(f"✓ Starting cable inversion...")
        if limit:
            print(f"  Limit: {limit} servers")
        else:
            print(f"  Processing: All staged servers")

        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running cable inversion: {e}")
        return False


def get_phase2_stats():
    """Get Phase 2 statistics from NetBox."""
    try:
        # Get all devices
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers=HEADERS,
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
            'staged': sum(1 for s in servers if s.get('status', {}).get('value') == 'staged'),
        }

        # Count servers with inverted cables (check journal entries)
        inverted_count = 0
        for server in servers:
            if server.get('status', {}).get('value') == 'failed':
                device_id = server['id']

                # Check for journal entries about cable inversion
                journal_response = requests.get(
                    f"{NETBOX_URL}/api/extras/journal-entries/",
                    headers=HEADERS,
                    params={
                        'assigned_object_type': 'dcim.device',
                        'assigned_object_id': device_id
                    },
                    timeout=10
                )

                if journal_response.status_code == 200:
                    journals = journal_response.json()['results']
                    for journal in journals:
                        if 'Cable Inversion Detected' in journal.get('comments', ''):
                            inverted_count += 1
                            break

        stats['inverted_cables'] = inverted_count

        return stats
    except Exception as e:
        print(f"⚠ Could not fetch Phase 2 stats: {e}")
        return None


def verify_phase2(limit=None, dry_run=False):
    """Verify Phase 2 completion."""
    print("\n" + "=" * 70)
    print("STEP 4: VERIFY PHASE 2 COMPLETION")
    print("=" * 70)

    if dry_run:
        print("[DRY RUN] Would verify Phase 2 completion")
        return True

    print("✓ Fetching current state...")

    stats = get_phase2_stats()

    if not stats:
        print("✗ Could not verify Phase 2 completion")
        return False

    print(f"\nPhase 2 Statistics:")
    print(f"  Total servers:        {stats['total']}")
    print(f"  Status = Failed:      {stats['failed']}")
    print(f"  Status = Planned:     {stats['planned']}")
    print(f"  Status = Offline:     {stats['offline']}")
    print(f"  Inverted cables:      {stats['inverted_cables']}")

    if stats['failed'] > 0 and stats['inverted_cables'] > 0:
        print("\n✓ Phase 2 complete: Servers marked as failed with inverted cables")
        return True
    else:
        print("\n⚠ Warning: Phase 2 may not be fully complete")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Advance to Phase 2: Cable Validation Complete',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script advances the environment to Phase 2:
1. Ensures Phase 1 is complete
2. Sets servers to 'staged' status
3. Inverts production NIC cables
4. Marks servers as 'failed'

Examples:
  # Dry run - see what would happen
  python state-phase2.py --dry-run

  # Advance to Phase 2 (all servers)
  python state-phase2.py

  # Advance to Phase 2 (only 10 servers)
  python state-phase2.py --limit 10
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
    print("STATE MANAGEMENT: ADVANCE TO PHASE 2")
    print("=" * 70)

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")

    start_time = time.time()

    # Step 1: Ensure Phase 1 is complete
    #if not run_phase1(args.limit, args.dry_run):
    #    print("\n✗ Failed to complete Phase 1")
    #    return False

    # Step 2: Set servers to 'staged'
    if not set_servers_to_staged(args.limit, args.dry_run):
        print("\n✗ Failed to set servers to 'staged'")
        return False

    # Step 3: Run cable inversion
    if not run_cable_inversion(args.limit, args.dry_run):
        print("\n✗ Failed to run cable inversion")
        return False

    # Step 4: Verify completion
    if not verify_phase2(args.limit, args.dry_run):
        print("\n⚠ Phase 2 verification completed with warnings")

    elapsed = time.time() - start_time

    # Print final summary
    print("\n" + "=" * 70)
    print("PHASE 2 COMPLETE")
    print("=" * 70)

    if not args.dry_run:
        print(f"\n✓ Phase 2: Cable Validation complete")
        print(f"  - Servers have inverted cables")
        print(f"  - Status set to 'failed'")
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
