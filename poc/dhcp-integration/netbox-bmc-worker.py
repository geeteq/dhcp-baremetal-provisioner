#!/usr/bin/env python3
"""
NetBox BMC Discovery Worker
============================
Consumes BMC DHCP lease events from Redis and updates NetBox device states.

Workflow:
1. Listen to Redis queue for BMC DHCP lease events
2. Extract MAC address from event
3. Query NetBox for device with matching BMC MAC address
4. Update device lifecycle state: offline → discovered
5. Assign IP address to BMC interface in NetBox
6. Log all actions for audit trail

Usage:
    python netbox-bmc-worker.py

Environment Variables:
    REDIS_HOST          - Redis server hostname (default: localhost)
    REDIS_PORT          - Redis server port (default: 6379)
    REDIS_QUEUE         - Redis queue name (default: netbox:bmc:discovered)
    NETBOX_URL          - NetBox API URL (default: http://localhost:8000)
    NETBOX_TOKEN        - NetBox API token
    LOG_LEVEL           - Logging level (default: INFO)
"""

import os
import sys
import json
import time
import logging
import redis
import requests
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parent.parent.parent / 'config' / '.env'
    if _env.exists():
        load_dotenv(_env, override=False)
except ImportError:
    pass

from netbox_utils import NetBoxJournalMixin

# Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or None
REDIS_QUEUE = os.getenv('REDIS_QUEUE', 'netbox:bmc:discovered')
REDIS_USE_TLS = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'
REDIS_TLS_CERT = os.getenv('REDIS_TLS_CERT')
REDIS_TLS_KEY = os.getenv('REDIS_TLS_KEY')
REDIS_TLS_CA = os.getenv('REDIS_TLS_CA')
NETBOX_URL = os.getenv('NETBOX_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '0123456789abcdef0123456789abcdef01234567')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', '/var/log/bm')

os.makedirs(LOG_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, 'netbox-bmc-worker.log'))
    ]
)
logger = logging.getLogger('netbox-bmc-worker')


class NetBoxClient(NetBoxJournalMixin):
    """NetBox API client with journal logging support."""

    def __init__(self, url, token, logger=None):
        self.url = url.rstrip('/')
        self.token = token
        self.logger = logger
        self.headers = {
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def find_device_by_bmc_mac(self, mac_address):
        """Find device by BMC interface MAC address."""
        mac_normalized = mac_address.upper().replace('-', ':')

        logger.info(f"Searching for device with BMC MAC: {mac_normalized}")

        # Search for interface with this MAC
        response = requests.get(
            f"{self.url}/api/dcim/interfaces/",
            headers=self.headers,
            params={
                'mac_address': mac_normalized,
                'name': 'bmc',  # BMC interface name
            }
        )
        response.raise_for_status()

        data = response.json()
        if data['count'] == 0:
            logger.warning(f"No device found with BMC MAC: {mac_normalized}")
            return None

        interface = data['results'][0]
        device_id = interface['device']['id']

        # Get full device details
        response = requests.get(
            f"{self.url}/api/dcim/devices/{device_id}/",
            headers=self.headers
        )
        response.raise_for_status()

        device = response.json()
        logger.info(f"Found device: {device['name']} (ID: {device_id})")

        return device, interface

    def update_device_state(self, device_id, new_state):
        """Update device status."""
        logger.info(f"Updating device {device_id} to state: {new_state}")

        response = requests.patch(
            f"{self.url}/api/dcim/devices/{device_id}/",
            headers=self.headers,
            json={
                'status': new_state
            }
        )
        response.raise_for_status()

        logger.info(f"Device {device_id} state updated to: {new_state}")
        return response.json()

    def assign_ip_to_interface(self, interface_id, ip_address):
        """Assign IP address to BMC interface."""
        logger.info(f"Assigning IP {ip_address} to interface {interface_id}")

        # Create IP address in NetBox
        response = requests.post(
            f"{self.url}/api/ipam/ip-addresses/",
            headers=self.headers,
            json={
                'address': f"{ip_address}/24",  # Adjust subnet as needed
                'assigned_object_type': 'dcim.interface',
                'assigned_object_id': interface_id,
                'status': 'active',
                'description': f'Auto-assigned by DHCP on {datetime.utcnow().isoformat()}'
            }
        )

        # IP might already exist, that's OK
        if response.status_code == 400:
            logger.warning(f"IP {ip_address} may already exist, skipping")
            return None

        response.raise_for_status()
        logger.info(f"IP {ip_address} assigned to interface {interface_id}")
        return response.json()

    def update_bmc_ip(self, interface_id, ip_address):
        """Update the IP address already assigned to the BMC interface."""
        # Find existing IP on this interface
        response = requests.get(
            f"{self.url}/api/ipam/ip-addresses/",
            headers=self.headers,
            params={
                'assigned_object_type': 'dcim.interface',
                'assigned_object_id': interface_id,
            }
        )
        response.raise_for_status()
        results = response.json().get('results', [])

        if not results:
            # No IP yet — fall back to creating one
            return self.assign_ip_to_interface(interface_id, ip_address)

        ip_id = results[0]['id']
        response = requests.patch(
            f"{self.url}/api/ipam/ip-addresses/{ip_id}/",
            headers=self.headers,
            json={
                'address': f"{ip_address}/24",
                'description': f'Auto-updated by DHCP on {datetime.utcnow().isoformat()}'
            }
        )
        response.raise_for_status()
        logger.info(f"BMC IP updated to {ip_address} on interface {interface_id}")
        return response.json()

    def get_device_state(self, device):
        """Get current status of device."""
        return device.get('status', {}).get('value', 'unknown')


class BMCDiscoveryWorker:
    """Worker that processes BMC discovery events."""

    def __init__(self, redis_client, netbox_client):
        self.redis = redis_client
        self.netbox = netbox_client
        self.running = False

    def process_event(self, event_data):
        """Process a single BMC discovery event."""
        try:
            event = json.loads(event_data)
            logger.info(f"Processing event: {event['event_type']}")
            logger.debug(f"Event data: {json.dumps(event, indent=2)}")

            mac_address = event['mac_address']
            ip_address = event['ip_address']
            timestamp = event['timestamp']

            # Find device in NetBox
            result = self.netbox.find_device_by_bmc_mac(mac_address)
            if not result:
                logger.error(f"Device not found in NetBox for MAC {mac_address}")
                # Cannot log to device journal since device not found
                return False

            device, bmc_interface = result
            device_id = device['id']
            device_name = device['name']
            interface_id = bmc_interface['id']

            # Get current state
            current_state = self.netbox.get_device_state(device)
            logger.info(f"Device {device_name} current state: {current_state}")

            # Add discovery journal entry
            self.netbox.add_journal_discovery(
                device_id, device_name, 'BMC', mac_address, ip_address
            )

            # State transition logic
            if current_state == 'active':
                # Device is live — only update the BMC IP, touch nothing else
                logger.info(f"Device {device_name} is active (live); updating BMC IP only")
                ip_result = self.netbox.update_bmc_ip(interface_id, ip_address)
                if ip_result:
                    self.netbox.add_journal_ip_assignment(
                        device_id, device_name, 'bmc', ip_address
                    )
                logger.info(f"✓ BMC IP refreshed for live device {device_name}")
                return True
            elif current_state == 'offline':
                # Transition: offline → discovered
                self.netbox.update_device_state(device_id, 'discovered')
                self.netbox.add_journal_state_change(
                    device_id, device_name, current_state, 'discovered'
                )
                logger.info(f"✓ State transition: {device_name} offline → discovered")
            elif current_state == 'discovered':
                logger.info(f"Device {device_name} already in discovered state")
            else:
                logger.warning(f"Device {device_name} in unexpected state: {current_state}")
                self.netbox.add_journal_entry(
                    device_id,
                    f"BMC discovery attempted but device in unexpected state: {current_state}",
                    kind='warning'
                )

            # Assign IP address to BMC interface
            ip_result = self.netbox.assign_ip_to_interface(interface_id, ip_address)
            if ip_result:
                self.netbox.add_journal_ip_assignment(
                    device_id, device_name, 'bmc', ip_address
                )

            logger.info(f"✓ Successfully processed BMC discovery for {device_name}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in event: {e}")
            return False
        except requests.HTTPError as e:
            logger.error(f"NetBox API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error processing event: {e}", exc_info=True)
            return False

    def run(self):
        """Main worker loop - blocks and processes events from Redis."""
        self.running = True
        logger.info("=" * 70)
        logger.info("NetBox BMC Discovery Worker Started")
        logger.info("=" * 70)
        logger.info(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
        logger.info(f"Queue: {REDIS_QUEUE}")
        logger.info(f"NetBox: {NETBOX_URL}")
        logger.info("Waiting for BMC discovery events...")
        logger.info("=" * 70)

        while self.running:
            try:
                # Blocking pop with 1 second timeout
                result = self.redis.brpop(REDIS_QUEUE, timeout=1)

                if result:
                    queue_name, event_data = result
                    event_data = event_data.decode('utf-8')

                    logger.info("-" * 70)
                    success = self.process_event(event_data)
                    if success:
                        logger.info("Event processed successfully")
                    else:
                        logger.error("Event processing failed")
                    logger.info("-" * 70)

            except redis.RedisError as e:
                logger.error(f"Redis error: {e}")
                time.sleep(5)  # Wait before retry
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.stop()
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(1)

        logger.info("Worker stopped")

    def stop(self):
        """Stop the worker."""
        self.running = False


def main():
    """Main entry point."""
    # Connect to Redis
    try:
        tls_kwargs = {}
        if REDIS_USE_TLS:
            tls_kwargs = dict(
                ssl=True,
                ssl_certfile=REDIS_TLS_CERT,
                ssl_keyfile=REDIS_TLS_KEY,
                ssl_ca_certs=REDIS_TLS_CA,
                ssl_check_hostname=False,  # cert CN is redis-server, not host.docker.internal
            )
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=False,
            **tls_kwargs
        )
        redis_client.ping()
        logger.info(f"✓ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    except redis.RedisError as e:
        logger.error(f"✗ Failed to connect to Redis: {e}")
        sys.exit(1)

    # Initialize NetBox client
    netbox_client = NetBoxClient(NETBOX_URL, NETBOX_TOKEN, logger=logger)
    logger.info(f"✓ NetBox client initialized: {NETBOX_URL}")

    # Create and run worker
    worker = BMCDiscoveryWorker(redis_client, netbox_client)
    worker.run()


if __name__ == '__main__':
    main()
