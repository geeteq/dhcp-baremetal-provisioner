#!/usr/bin/env python3
"""
DHCP Log Tailer Service

Tails the DHCP events log file and publishes events to Redis queue.
Handles log rotation and ensures no events are lost.
"""
import sys
import time
import json
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
import config


def tail_file(file_path, callback, poll_interval=1.0):
    """
    Tail a file and call callback for each new line.

    Args:
        file_path: Path to file to tail
        callback: Function to call with each line
        poll_interval: Polling interval in seconds
    """
    # Ensure file exists
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).touch(exist_ok=True)

    with open(file_path, 'r') as f:
        # Start at end of file
        f.seek(0, 2)

        while True:
            line = f.readline()
            if line:
                callback(line.strip())
            else:
                time.sleep(poll_interval)


def process_dhcp_event(line, queue, logger):
    """
    Process a DHCP event line and publish to Redis.

    Args:
        line: JSON event line
        queue: Redis queue instance
        logger: Logger instance
    """
    try:
        # Parse JSON
        event = json.loads(line)

        # Extract event data
        event_type = event.get('event_type')
        data = event.get('data', {})
        ip = data.get('ip')
        mac = data.get('mac')

        if not ip or not mac:
            log_error(logger, f"Invalid event: missing IP or MAC", {'event': event})
            return

        # Log event
        log_event(logger, 'dhcp_event_received', data={
            'ip': ip,
            'mac': mac,
            'hostname': data.get('hostname', '')
        })

        # Publish to Redis queue
        success = queue.publish(config.QUEUE_DHCP_LEASE, event)

        if success:
            log_event(logger, 'dhcp_event_published', data={'ip': ip, 'mac': mac})
        else:
            log_error(logger, 'Failed to publish to Redis', {'event': event})

    except json.JSONDecodeError as e:
        log_error(logger, f"Invalid JSON in DHCP log: {line}", {'error': str(e)})
    except Exception as e:
        log_error(logger, e, {'line': line})


def main():
    """Main service loop."""
    # Setup logging
    logger = setup_logger(
        'dhcp-tailer',
        log_file=os.path.join(config.LOG_DIR, 'dhcp_tailer.log')
    )

    logger.info("DHCP Tailer starting...")

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
    logger.info(f"Tailing DHCP event log: {config.DHCP_EVENT_LOG}")

    # Tail DHCP event log
    try:
        tail_file(
            config.DHCP_EVENT_LOG,
            lambda line: process_dhcp_event(line, queue, logger)
        )
    except KeyboardInterrupt:
        logger.info("DHCP Tailer stopped by user")
    except Exception as e:
        log_error(logger, e)
        sys.exit(1)


if __name__ == '__main__':
    main()
