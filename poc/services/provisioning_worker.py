#!/usr/bin/env python3
"""
Provisioning Worker Service

Consumes device_discovered events from Redis queue.
Connects to iLO via Redfish API.
Configures one-time PXE boot and powers on/restarts server.
Updates device state to 'validating'.
Publishes pxe_boot_initiated event.
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
from lib.netbox_client import NetBoxClient
from lib.redfish_client import RedfishClient
import config


def process_device_discovered(event, netbox, queue, logger):
    """
    Process a device_discovered event.

    Args:
        event: Device discovered event dictionary
        netbox: NetBox client instance
        queue: Redis queue instance
        logger: Logger instance
    """
    data = event.get('data', {})
    device_id = data.get('device_id')
    device_name = data.get('device_name')
    ip = data.get('ip')

    logger.info(f"Processing device_discovered: device={device_name}, ip={ip}")

    try:
        # Step 1: Connect to iLO via Redfish
        logger.info(f"Connecting to iLO at {ip}")

        ilo = RedfishClient(
            host=ip,
            username=config.ILO_DEFAULT_USER,
            password=config.ILO_DEFAULT_PASSWORD,
            verify_ssl=config.ILO_VERIFY_SSL
        )

        # Verify connection by getting system info
        try:
            system_info = ilo.get_system_info()
            log_event(logger, 'ilo_connected', device_id=device_name, data={
                'ip': ip,
                'manufacturer': system_info.get('Manufacturer', 'Unknown'),
                'model': system_info.get('Model', 'Unknown')
            })
        except Exception as e:
            logger.error(f"Failed to connect to iLO at {ip}: {e}")
            return

        # Step 2: Get current power state
        power_state = ilo.get_power_state()
        logger.info(f"Current power state: {power_state}")

        # Step 3: Configure one-time PXE boot
        logger.info("Configuring one-time PXE boot")
        try:
            ilo.set_one_time_pxe_boot()
            log_event(logger, 'pxe_boot_configured', device_id=device_name, data={
                'ip': ip
            })
        except Exception as e:
            logger.error(f"Failed to configure PXE boot: {e}")
            return

        # Step 4: Power on or restart server
        try:
            if power_state.lower() == 'off':
                logger.info("Server is off, powering on...")
                ilo.power_on()
                log_event(logger, 'server_powered_on', device_id=device_name)
            else:
                logger.info("Server is on, forcing restart...")
                ilo.force_restart()
                log_event(logger, 'server_restarted', device_id=device_name)
        except Exception as e:
            logger.error(f"Failed to power on/restart server: {e}")
            return

        # Step 5: Update device state to 'validating'
        timestamp = datetime.utcnow().isoformat() + 'Z'

        logger.info(f"Updating device {device_id} state to 'validating'")
        netbox.update_device(device_id, {
            'custom_fields': {
                config.NETBOX_FIELD_LIFECYCLE_STATE: config.STATE_VALIDATING,
                config.NETBOX_FIELD_PXE_BOOT_INITIATED_AT: timestamp
            }
        })

        log_event(logger, 'device_state_updated', device_id=device_name, data={
            'state': config.STATE_VALIDATING,
            'timestamp': timestamp
        })

        # Step 6: Publish pxe_boot_initiated event
        pxe_event = {
            'event_type': 'pxe_boot_initiated',
            'timestamp': timestamp,
            'data': {
                'device_id': device_id,
                'device_name': device_name,
                'ip': ip
            }
        }

        success = queue.publish(config.QUEUE_PXE_BOOT_INITIATED, pxe_event)

        if success:
            log_event(logger, 'pxe_boot_initiated', device_id=device_name, data={
                'device_id': device_id,
                'ip': ip
            })
        else:
            logger.error("Failed to publish pxe_boot_initiated event")

    except Exception as e:
        log_error(logger, e, context={
            'device_id': device_id,
            'device_name': device_name,
            'ip': ip,
            'event': 'device_provisioning'
        })


def main():
    """Main service loop."""
    # Setup logging
    logger = setup_logger(
        'provisioning-worker',
        log_file=os.path.join(config.LOG_DIR, 'provisioning_worker.log')
    )

    logger.info("Provisioning Worker starting...")

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

    # Test Redis connection
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
    logger.info(f"Listening on queue: {config.QUEUE_DEVICE_DISCOVERED}")

    # Main event loop
    try:
        while True:
            # Block and wait for events
            event = queue.consume(config.QUEUE_DEVICE_DISCOVERED, timeout=5)

            if event:
                process_device_discovered(event, netbox, queue, logger)

    except KeyboardInterrupt:
        logger.info("Provisioning Worker stopped by user")
    except Exception as e:
        log_error(logger, e)
        sys.exit(1)


if __name__ == '__main__':
    main()
