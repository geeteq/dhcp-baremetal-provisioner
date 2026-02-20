#!/usr/bin/env python3
"""
State Management: Universal Restore CLI
========================================
Restore PoC environment to any phase state.

This script provides a unified interface to restore the environment
to a specific phase:
- Phase 0: Clean slate (servers offline, no IPs)
- Phase 1: BMC Discovery complete (servers planned, BMC IPs assigned)
- Phase 2: Cable validation complete (servers failed, cables inverted)

Usage:
    python state-restore.py <phase> [--limit N] [--dry-run]

Arguments:
    phase        Phase number to restore to: 0, 1, or 2

Options:
    --limit N    Only process N servers (default: all)
    --dry-run    Show what would be done without making changes

Examples:
    # Reset to Phase 0 (clean slate)
    python state-restore.py 0

    # Advance to Phase 1 (BMC discovery)
    python state-restore.py 1

    # Advance to Phase 2 (cable validation)
    python state-restore.py 2

    # Advance to Phase 1 with only 10 servers
    python state-restore.py 1 --limit 10

    # Dry run - see what would happen
    python state-restore.py 2 --dry-run
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

# Path to phase scripts
SCRIPT_DIR = Path(__file__).parent

PHASE_SCRIPTS = {
    0: SCRIPT_DIR / 'state-phase0.py',
    1: SCRIPT_DIR / 'state-phase1.py',
    2: SCRIPT_DIR / 'state-phase2.py',
}

PHASE_DESCRIPTIONS = {
    0: "Clean slate - all servers offline, no IPs assigned",
    1: "BMC Discovery complete - servers planned, BMC IPs assigned",
    2: "Cable validation complete - servers failed, cables inverted"
}


def get_current_state():
    """Get current state statistics."""
    import requests

    NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
    NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')

    try:
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

        return {
            'total': len(servers),
            'offline': sum(1 for s in servers if s.get('status', {}).get('value') == 'offline'),
            'planned': sum(1 for s in servers if s.get('status', {}).get('value') == 'planned'),
            'failed': sum(1 for s in servers if s.get('status', {}).get('value') == 'failed'),
            'discovered': sum(1 for s in servers if s.get('custom_fields', {}).get('lifecycle_state') == 'discovered')
        }
    except Exception as e:
        print(f"⚠ Could not fetch current state: {e}")
        return None


def print_state_comparison(before, after):
    """Print before/after state comparison."""
    if not before or not after:
        return

    print("\n" + "=" * 70)
    print("STATE COMPARISON")
    print("=" * 70)

    print(f"\n{'Metric':<20} {'Before':>10} {'After':>10} {'Change':>10}")
    print("-" * 70)

    metrics = ['total', 'offline', 'planned', 'failed', 'discovered']
    for metric in metrics:
        before_val = before.get(metric, 0)
        after_val = after.get(metric, 0)
        change = after_val - before_val
        change_str = f"+{change}" if change > 0 else str(change)

        print(f"{metric.capitalize():<20} {before_val:>10} {after_val:>10} {change_str:>10}")

    print("=" * 70)


def restore_to_phase(phase, limit=None, dry_run=False):
    """Restore environment to specified phase."""
    if phase not in PHASE_SCRIPTS:
        print(f"✗ Invalid phase: {phase}")
        print(f"Valid phases: {', '.join(map(str, PHASE_SCRIPTS.keys()))}")
        return False

    script = PHASE_SCRIPTS[phase]

    if not script.exists():
        print(f"✗ Phase script not found: {script}")
        return False

    print("=" * 70)
    print(f"STATE RESTORE: PHASE {phase}")
    print("=" * 70)
    print(f"\nTarget: {PHASE_DESCRIPTIONS[phase]}")

    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made")

    # Get current state before
    print("\n✓ Checking current state...")
    before_state = get_current_state()

    if before_state:
        print(f"  Total servers:    {before_state['total']}")
        print(f"  Offline:          {before_state['offline']}")
        print(f"  Planned:          {before_state['planned']}")
        print(f"  Failed:           {before_state['failed']}")
        print(f"  Discovered:       {before_state['discovered']}")

    # Build command
    cmd = [sys.executable, str(script)]

    if limit:
        cmd.extend(['--limit', str(limit)])

    if dry_run:
        cmd.append('--dry-run')

    # Execute phase script
    print(f"\n✓ Running phase {phase} script...")
    start_time = time.time()

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"\n✗ Phase {phase} script failed")
            return False

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error running phase {phase} script: {e}")
        return False
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        return False

    # Get state after
    if not dry_run:
        print("\n✓ Verifying final state...")
        after_state = get_current_state()

        if after_state:
            print_state_comparison(before_state, after_state)

        print(f"\n✓ Successfully restored to Phase {phase}")
        print(f"  Time elapsed: {elapsed:.1f} seconds")
    else:
        print("\n⚠ DRY RUN - No changes were made")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Universal state restore for PoC phases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available Phases:
  0 - {PHASE_DESCRIPTIONS[0]}
  1 - {PHASE_DESCRIPTIONS[1]}
  2 - {PHASE_DESCRIPTIONS[2]}

Examples:
  # Reset to Phase 0 (clean slate)
  python state-restore.py 0

  # Advance to Phase 1 (BMC discovery)
  python state-restore.py 1

  # Advance to Phase 2 (cable validation)
  python state-restore.py 2

  # Dry run
  python state-restore.py 1 --dry-run

  # Limit to 10 servers
  python state-restore.py 1 --limit 10
        """
    )

    parser.add_argument(
        'phase',
        type=int,
        choices=[0, 1, 2],
        help='Phase number to restore to (0, 1, or 2)'
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

    try:
        success = restore_to_phase(args.phase, args.limit, args.dry_run)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
