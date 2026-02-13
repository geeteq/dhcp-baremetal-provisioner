#!/usr/bin/env python3
"""
Hardening Worker Service

Consumes validation_completed events from Redis queue.
Executes Ansible playbook to harden BMC security settings.
Updates device state to 'ready'.
Publishes hardening_completed event.
"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
from lib.netbox_client import NetBoxClient
import config


def run_ansible_playbook(device_ip, logger):
    """
    Run Ansible hardening playbook against device.

    Args:
        device_ip: Device BMC IP address
        logger: Logger instance

    Returns:
        True if successful, False otherwise
    """
    playbook_path = config.ANSIBLE_BMC_HARDENING_PLAYBOOK

    if not os.path.exists(playbook_path):
        logger.error(f"Ansible playbook not found: {playbook_path}")
        return False

    logger.info(f"Running Ansible playbook: {playbook_path}")
    logger.info(f"Target: {device_ip}")

    try:
        # Run ansible-playbook with ad-hoc inventory
        # The comma after IP makes it an ad-hoc inventory
        result = subprocess.run([
            'ansible-playbook',
            playbook_path,
            '-i', f'{device_ip},',  # Ad-hoc inventory
            '-e', f'ansible_user={config.ILO_DEFAULT_USER}',
            '-e', f'ansible_password={config.ILO_DEFAULT_PASSWORD}',
            '-v'  # Verbose output
        ], capture_output=True, text=True, timeout=600)

        # Log output
        if result.stdout:
            logger.info(f"Ansible stdout:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Ansible stderr:\n{result.stderr}")

        if result.returncode == 0:
            logger.info("Ansible playbook completed successfully")
            return True
        else:
            logger.error(f"Ansible playbook failed with return code: {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Ansible playbook timed out after 600 seconds")
        return False
    except FileNotFoundError:
        logger.error("ansible-playbook command not found. Is Ansible installed?")
        return False
    except Exception as e:
        log_error(logger, e, context={'playbook': playbook_path, 'target': device_ip})
        return False


def process_validation_completed(event, netbox, queue, logger):
    """
    Process a validation_completed event.

    Args:
        event: Validation completed event dictionary
        netbox: NetBox client instance
        queue: Redis queue instance
        logger: Logger instance
    """
    data = event.get('data', {})
    device_id = data.get('device_id')
    device_name = data.get('device_name')

    logger.info(f"Processing validation_completed: device={device_name}")

    try:
        # Step 1: Get device BMC IP from NetBox
        device = netbox.get_device(device_id)

        # Find BMC interface
        bmc_interface = None
        for iface in device.get('interfaces', []):
            if iface.get('mgmt_only') or 'ilo' in iface['name'].lower() or 'bmc' in iface['name'].lower():
                bmc_interface = iface
                break

        if not bmc_interface:
            logger.error(f"No BMC interface found for device {device_name}")
            return

        # Get IP from interface
        # Note: This is simplified - in reality you'd query the IP addresses endpoint
        # For now, we'll use the IP from the discovered event (stored in custom field or retrieved differently)
        # As a workaround, we can look for primary_ip4
        device_ip = None
        if device.get('primary_ip4'):
            device_ip = device['primary_ip4']['address'].split('/')[0]

        if not device_ip:
            logger.error(f"No IP address found for device {device_name}")
            return

        logger.info(f"Found BMC IP: {device_ip}")

        # Step 2: Update state to 'hardening'
        timestamp = datetime.utcnow().isoformat() + 'Z'
        logger.info(f"Updating device {device_id} state to 'hardening'")
        netbox.set_device_state(device_id, config.STATE_HARDENING)

        # Step 3: Run Ansible playbook
        logger.info(f"Executing BMC hardening playbook")
        success = run_ansible_playbook(device_ip, logger)

        if not success:
            logger.error(f"Hardening failed for device {device_name}")
            # Could set state to 'error' here
            return

        log_event(logger, 'hardening_completed', device_id=device_name)

        # Step 4: Update state to 'staged'
        logger.info(f"Updating device {device_id} state to 'staged'")
        netbox.update_device(device_id, {
            'custom_fields': {
                config.NETBOX_FIELD_LIFECYCLE_STATE: config.STATE_STAGED,
                config.NETBOX_FIELD_HARDENED_AT: timestamp
            }
        })

        log_event(logger, 'device_state_updated', device_id=device_name, data={
            'state': config.STATE_STAGED,
            'timestamp': timestamp
        })

        # Step 5: Publish hardening_completed event
        hardening_event = {
            'event_type': 'hardening_completed',
            'timestamp': timestamp,
            'data': {
                'device_id': device_id,
                'device_name': device_name
            }
        }

        success = queue.publish(config.QUEUE_HARDENING_COMPLETED, hardening_event)

        if success:
            log_event(logger, 'hardening_event_published', device_id=device_name)
        else:
            logger.error("Failed to publish hardening_completed event")

    except Exception as e:
        log_error(logger, e, context={
            'device_id': device_id,
            'device_name': device_name,
            'event': 'hardening'
        })


def main():
    """Main service loop."""
    # Setup logging
    logger = setup_logger(
        'hardening-worker',
        log_file=os.path.join(config.LOG_DIR, 'hardening_worker.log')
    )

    logger.info("Hardening Worker starting...")

    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Check if Ansible is installed
    try:
        subprocess.run(['ansible-playbook', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Ansible not found. Please install Ansible.")
        sys.exit(1)

    # Initialize Redis queue
    queue = Queue(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB
    )

    if not queue.ping():
        logger.error("Failed to connect to Redis")
        sys.exit(1)

    logger.info(f"Connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")

    # Initialize NetBox client
    netbox = NetBoxClient(
        url=config.NETBOX_URL,
        token=config.NETBOX_TOKEN,
        verify_ssl=False  # For PoC
    )

    logger.info(f"Connected to NetBox at {config.NETBOX_URL}")
    logger.info(f"Listening on queue: {config.QUEUE_VALIDATION_COMPLETED}")

    # Main event loop
    try:
        while True:
            # Block and wait for events
            event = queue.consume(config.QUEUE_VALIDATION_COMPLETED, timeout=5)

            if event:
                process_validation_completed(event, netbox, queue, logger)

    except KeyboardInterrupt:
        logger.info("Hardening Worker stopped by user")
    except Exception as e:
        log_error(logger, e)
        sys.exit(1)


if __name__ == '__main__':
    main()
