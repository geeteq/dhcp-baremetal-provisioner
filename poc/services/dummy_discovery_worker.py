#!/usr/bin/env python3.12
"""
Dummy Discovery Worker - Testing Only

Consumes DHCP lease events from Redis queue.
Logs what actions WOULD be taken (without NetBox connection).
Useful for testing event flow without infrastructure dependencies.
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
import config


def process_dhcp_event(event, queue, logger, action_log):
    """
    Process a DHCP lease event (dummy mode).

    Args:
        event: DHCP event dictionary
        queue: Redis queue instance
        logger: Logger instance
        action_log: File handle for action log
    """
    data = event.get('data', {})
    ip = data.get('ip')
    mac = data.get('mac')
    hostname = data.get('hostname', '')

    logger.info(f"Processing DHCP lease: ip={ip}, mac={mac}, hostname={hostname}")

    try:
        timestamp = datetime.utcnow().isoformat() + 'Z'

        # Action 1: Would lookup interface by MAC in NetBox
        action = {
            'timestamp': timestamp,
            'action': 'LOOKUP_INTERFACE_BY_MAC',
            'details': {
                'mac_address': mac,
                'result': 'SIMULATED: Found interface on device srv001',
                'interface_id': 'dummy-123',
                'device_id': 'dummy-456',
                'device_name': f'server-{mac.replace(":", "")[-6:]}'
            }
        }
        action_log.write(json.dumps(action) + '\n')
        action_log.flush()
        logger.info(f"Action logged: {action['action']}")

        # Action 2: Would assign IP to interface
        action = {
            'timestamp': timestamp,
            'action': 'ASSIGN_IP_TO_INTERFACE',
            'details': {
                'interface_id': 'dummy-123',
                'ip_address': f'{ip}/24',
                'result': 'SIMULATED: IP assigned successfully'
            }
        }
        action_log.write(json.dumps(action) + '\n')
        action_log.flush()
        logger.info(f"Action logged: {action['action']}")

        # Action 3: Would update device state to 'discovered'
        device_name = f'server-{mac.replace(":", "")[-6:]}'
        action = {
            'timestamp': timestamp,
            'action': 'UPDATE_DEVICE_STATE',
            'details': {
                'device_id': 'dummy-456',
                'device_name': device_name,
                'old_state': 'racked',
                'new_state': 'discovered',
                'result': 'SIMULATED: State updated successfully'
            }
        }
        action_log.write(json.dumps(action) + '\n')
        action_log.flush()
        logger.info(f"Action logged: {action['action']}")

        log_event(logger, 'device_discovered_simulated', device_id=device_name, data={
            'device_name': device_name,
            'ip': ip,
            'mac': mac
        })

        # Action 4: Would publish device_discovered event
        discovered_event = {
            'event_type': 'device_discovered',
            'timestamp': timestamp,
            'data': {
                'device_id': 'dummy-456',
                'device_name': device_name,
                'ip': ip,
                'mac': mac
            }
        }

        action = {
            'timestamp': timestamp,
            'action': 'PUBLISH_DEVICE_DISCOVERED_EVENT',
            'details': {
                'queue': config.QUEUE_DEVICE_DISCOVERED,
                'event': discovered_event,
                'result': 'SIMULATED: Would publish to Redis'
            }
        }
        action_log.write(json.dumps(action) + '\n')
        action_log.flush()
        logger.info(f"Action logged: {action['action']}")

        # Actually publish to Redis so next worker can test
        success = queue.publish(config.QUEUE_DEVICE_DISCOVERED, discovered_event)
        if success:
            logger.info(f"Published device_discovered event for {device_name}")
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
    log_dir = os.getenv('LOG_DIR', 'log/bm')
    logger = setup_logger(
        'dummy-discovery-worker',
        log_file=os.path.join(log_dir, 'dummy_discovery_worker.log')
    )

    logger.info("Dummy Discovery Worker starting...")
    logger.info("*** TESTING MODE: No NetBox connection ***")

    # Initialize Redis queue with authentication
    queue = Queue(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', '6379')),
        db=int(os.getenv('REDIS_DB', '0')),
        password=os.getenv('REDIS_PASSWORD'),  # Support authentication
        use_tls=os.getenv('REDIS_USE_TLS', 'false').lower() == 'true',
        tls_cert=os.getenv('REDIS_TLS_CERT'),
        tls_key=os.getenv('REDIS_TLS_KEY'),
        tls_ca=os.getenv('REDIS_TLS_CA')
    )

    # Test Redis connection
    if not queue.ping():
        logger.error("Failed to connect to Redis")
        sys.exit(1)

    logger.info(f"Connected to Redis at {os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}")
    logger.info(f"Listening on queue: {config.QUEUE_DHCP_LEASE}")

    # Open action log file
    action_log_path = os.path.join(log_dir, 'discovery_actions.log')
    logger.info(f"Writing actions to: {action_log_path}")

    with open(action_log_path, 'a') as action_log:
        # Main event loop
        try:
            while True:
                # Block and wait for events
                event = queue.consume(config.QUEUE_DHCP_LEASE, timeout=5)

                if event:
                    process_dhcp_event(event, queue, logger, action_log)

        except KeyboardInterrupt:
            logger.info("Dummy Discovery Worker stopped by user")
        except Exception as e:
            log_error(logger, e)
            sys.exit(1)


if __name__ == '__main__':
    main()
