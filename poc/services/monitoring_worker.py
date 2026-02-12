#!/usr/bin/env python3
"""
Monitoring Worker Service

Periodically polls devices in 'ready' state.
Collects metrics via Redfish API (CPU, memory, power, thermal).
Stores metrics to JSON files.
Updates NetBox with last monitored timestamp.
"""
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logger import setup_logger, log_event, log_error
from lib.netbox_client import NetBoxClient
from lib.redfish_client import RedfishClient
import config


def collect_metrics(device, netbox, logger):
    """
    Collect metrics from a device.

    Args:
        device: NetBox device dictionary
        netbox: NetBox client instance
        logger: Logger instance
    """
    device_id = device['id']
    device_name = device['name']

    logger.info(f"Collecting metrics for device: {device_name}")

    try:
        # Get device BMC IP
        device_ip = None
        if device.get('primary_ip4'):
            device_ip = device['primary_ip4']['address'].split('/')[0]

        if not device_ip:
            logger.warning(f"No IP address for device {device_name}, skipping")
            return

        # Connect to iLO
        ilo = RedfishClient(
            host=device_ip,
            username=config.ILO_DEFAULT_USER,
            password=config.ILO_DEFAULT_PASSWORD,
            verify_ssl=config.ILO_VERIFY_SSL
        )

        # Collect all metrics
        logger.info(f"Querying Redfish API at {device_ip}")
        metrics = ilo.get_all_metrics()

        # Prepare metrics document
        timestamp = datetime.utcnow().isoformat() + 'Z'
        metrics_doc = {
            'device_id': device_id,
            'device_name': device_name,
            'timestamp': timestamp,
            'metrics': {
                'cpu': metrics.get('cpu', {}),
                'memory': metrics.get('memory', {}),
                'power': metrics.get('power', {}),
                'thermal': metrics.get('thermal', {})
            }
        }

        # Save to file
        metrics_dir = Path(config.METRICS_DIR)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{device_name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
        filepath = metrics_dir / filename

        with open(filepath, 'w') as f:
            json.dump(metrics_doc, f, indent=2)

        log_event(logger, 'metrics_collected', device_id=device_name, data={
            'file': str(filepath),
            'cpu_count': metrics_doc['metrics']['cpu'].get('count', 0),
            'memory_gb': metrics_doc['metrics']['memory'].get('total_gb', 0),
            'power_watts': metrics_doc['metrics']['power'].get('consumed_watts', 0)
        })

        # Update NetBox with last monitored timestamp and power reading
        try:
            netbox.update_device(device_id, {
                'custom_fields': {
                    config.NETBOX_FIELD_LAST_MONITORED_AT: timestamp,
                    config.NETBOX_FIELD_LAST_POWER_WATTS: metrics_doc['metrics']['power'].get('consumed_watts', 0)
                }
            })
        except Exception as e:
            logger.warning(f"Failed to update NetBox: {e}")

    except Exception as e:
        log_error(logger, e, context={
            'device_id': device_id,
            'device_name': device_name,
            'event': 'metrics_collection'
        })


def monitoring_loop(netbox, logger):
    """
    Main monitoring loop.

    Args:
        netbox: NetBox client instance
        logger: Logger instance
    """
    while True:
        try:
            # Get all devices in 'ready' state
            logger.info(f"Querying devices in state: {config.STATE_READY}")
            devices = netbox.get_devices_by_state(
                state=config.STATE_READY,
                tenant=config.NETBOX_TENANT
            )

            logger.info(f"Found {len(devices)} devices to monitor")

            # Collect metrics from each device
            for device in devices:
                collect_metrics(device, netbox, logger)

            # Wait for next interval
            logger.info(f"Sleeping for {config.MONITORING_INTERVAL_SECONDS} seconds")
            time.sleep(config.MONITORING_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            log_error(logger, e, context={'event': 'monitoring_loop'})
            # Sleep a bit before retrying
            time.sleep(60)


def main():
    """Main service entry point."""
    # Setup logging
    logger = setup_logger(
        'monitoring-worker',
        log_file=os.path.join(config.LOG_DIR, 'monitoring_worker.log')
    )

    logger.info("Monitoring Worker starting...")

    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Initialize NetBox client
    netbox = NetBoxClient(
        url=config.NETBOX_URL,
        token=config.NETBOX_TOKEN,
        verify_ssl=False  # For PoC
    )

    logger.info(f"Connected to NetBox at {config.NETBOX_URL}")
    logger.info(f"Monitoring interval: {config.MONITORING_INTERVAL_SECONDS} seconds")
    logger.info(f"Metrics directory: {config.METRICS_DIR}")

    # Start monitoring loop
    try:
        monitoring_loop(netbox, logger)
    except KeyboardInterrupt:
        logger.info("Monitoring Worker stopped by user")
    except Exception as e:
        log_error(logger, e)
        sys.exit(1)


if __name__ == '__main__':
    main()
