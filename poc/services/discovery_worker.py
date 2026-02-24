#!/usr/bin/env python3.12
"""
Discovery Worker Service

Consumes DHCP lease events from Redis queue.
Looks up devices in NetBox by MAC address.
Updates IP address and transitions device state to 'discovered'.
Publishes device_discovered event for next stage.
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# poc/ for lib/, ../config/ for config module
_poc_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_poc_dir))
sys.path.insert(0, str(_poc_dir.parent / 'config'))

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
from lib.netbox_client import NetBoxClient
import config


def log_mac_not_found(mac_address, ip):
    """
    Log MAC address not found to error log file.

    Args:
        mac_address: MAC address that wasn't found
        ip: IP address that was assigned
    """
    error_log_path = config.ERROR_LOG
    Path(error_log_path).parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().isoformat() + 'Z'
    error_msg = f"{timestamp} | MAC_NOT_FOUND | mac={mac_address} | ip={ip}\n"

    with open(error_log_path, 'a') as f:
        f.write(error_msg)


def process_dhcp_event(event, netbox, queue, logger):
    """
    Process a DHCP lease event.

    Args:
        event: DHCP event dictionary
        netbox: NetBox client instance
        queue: Redis queue instance
        logger: Logger instance
    """
    data = event.get('data', {})
    ip = data.get('ip')
    mac = data.get('mac')
    hostname = data.get('hostname', '')

    logger.info(f"Processing DHCP lease: ip={ip}, mac={mac}, hostname={hostname}")

    try:
        # Step 1: Find interface by MAC address
        logger.info(f"Looking up interface by MAC: {mac}")
        interface = netbox.find_interface_by_mac(mac)

        if not interface:
            logger.warning(f"Interface not found for MAC: {mac}")
            log_mac_not_found(mac, ip)
            return

        # Get device information
        device = interface.get('device')
        if not device:
            logger.error(f"Interface {interface['id']} has no device associated")
            return

        device_id = device['id']
        device_name = device['name']

        log_event(logger, 'interface_found', device_id=device_name, data={
            'interface_id': interface['id'],
            'interface_name': interface['name'],
            'device_id': device_id,
            'device_name': device_name
        })

        # Step 2: Assign IP address to interface
        # NetBox expects IP with mask (assuming /24 for management network)
        ip_with_mask = f"{ip}/24"

        logger.info(f"Assigning IP {ip_with_mask} to interface {interface['id']}")
        try:
            ip_obj = netbox.assign_ip_to_interface(interface['id'], ip_with_mask)
            log_event(logger, 'ip_assigned', device_id=device_name, data={
                'ip': ip,
                'interface_id': interface['id']
            })
        except Exception as e:
            # IP might already exist, that's OK
            logger.warning(f"Failed to assign IP (may already exist): {e}")

        # Step 3: Update device state to 'planned'
        timestamp = datetime.utcnow().isoformat() + 'Z'

        logger.info(f"Updating device {device_id} state to 'planned'")
        netbox.update_device(device_id, {
            'custom_fields': {
                config.NETBOX_FIELD_LIFECYCLE_STATE: config.STATE_PLANNED,
                config.NETBOX_FIELD_DISCOVERED_AT: timestamp
            }
        })

        log_event(logger, 'device_state_updated', device_id=device_name, data={
            'state': config.STATE_PLANNED,
            'timestamp': timestamp
        })

        # Step 4: Publish device_discovered event
        discovered_event = {
            'event_type': 'device_discovered',
            'timestamp': timestamp,
            'data': {
                'device_id': device_id,
                'device_name': device_name,
                'ip': ip,
                'mac': mac
            }
        }

        success = queue.publish(config.QUEUE_DEVICE_DISCOVERED, discovered_event)

        if success:
            log_event(logger, 'device_discovered', device_id=device_name, data={
                'device_id': device_id,
                'ip': ip
            })
        else:
            logger.error("Failed to publish device_discovered event")

    except Exception as e:
        log_error(logger, e, context={
            'ip': ip,
            'mac': mac,
            'event': 'dhcp_processing'
        })


def main():
    """Main service loop."""
    # Setup logging
    logger = setup_logger(
        'discovery-worker',
        log_file=os.path.join(config.LOG_DIR, 'discovery_worker.log')
    )

    logger.info("Discovery Worker starting...")

    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Initialize Redis queue
    queue = Queue(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB
    )

    queue.ping_verbose(logger)
    logger.info(f"Connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")

    # Initialize NetBox client
    netbox = NetBoxClient(
        url=config.NETBOX_URL,
        token=config.NETBOX_TOKEN,
        verify_ssl=False  # For PoC
    )

    logger.info(f"Connected to NetBox at {config.NETBOX_URL}")
    logger.info(f"Listening on queue: {config.QUEUE_DHCP_LEASE}")

    # Main event loop
    try:
        while True:
            # Block and wait for events
            event = queue.consume(config.QUEUE_DHCP_LEASE, timeout=5)

            if event:
                process_dhcp_event(event, netbox, queue, logger)

    except KeyboardInterrupt:
        logger.info("Discovery Worker stopped by user")
    except Exception as e:
        log_error(logger, e)
        sys.exit(1)


if __name__ == '__main__':
    main()
