#!/usr/bin/env python3
"""
Callback API Service

Receives validation reports from PXE-booted servers.
Updates NetBox with hardware info and LLDP data.
Publishes validation_completed event.
"""
import sys
import os
import ssl
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify
import redis as redis_lib

# Add parent directory to path for imports
_poc_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_poc_dir))                              # poc/ — for lib/
sys.path.insert(0, str(_poc_dir.parent / 'config'))            # ../config/ — for config module

from lib.logger import setup_logger, log_event, log_error
from lib.queue import Queue
from lib.netbox_client import NetBoxClient
import config

# Initialize Flask app
app = Flask(__name__)

# Global variables (initialized in main)
logger = None
netbox = None
queue = None


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'}), 200


@app.route('/api/v1/validation/report', methods=['POST'])
def validation_report():
    """
    Receive validation report from server.

    Expected JSON payload:
    {
        "device_id": "123",
        "timestamp": "2026-02-11T10:00:00Z",
        "hardware": {
            "manufacturer": "HPE",
            "model": "ProLiant DL360 Gen10",
            "serial": "ABC123"
        },
        "lldp": {...},
        "interfaces": [...]
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        device_id = data.get('device_id')
        hardware = data.get('hardware', {})
        lldp_data = data.get('lldp', {})
        interfaces = data.get('interfaces', [])

        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400

        logger.info(f"Received validation report for device: {device_id}")

        # Step 1: Get device from NetBox
        try:
            device = netbox.get_device(int(device_id))
            device_name = device['name']
        except Exception as e:
            logger.error(f"Device {device_id} not found in NetBox: {e}")
            return jsonify({'error': f'Device not found: {device_id}'}), 404

        log_event(logger, 'validation_report_received', device_id=device_name, data={
            'hardware': hardware,
            'interface_count': len(interfaces)
        })

        # Step 2: Update hardware model in NetBox (if provided)
        if hardware.get('model'):
            logger.info(f"Updating hardware model: {hardware['model']}")
            # Note: Updating device_type requires the type to exist in NetBox
            # For PoC, we'll store in custom fields or comments
            # In production, you'd create/lookup device type
            netbox.update_device(device_id, {
                'comments': f"Hardware: {hardware.get('manufacturer', '')} {hardware.get('model', '')} "
                           f"(Serial: {hardware.get('serial', '')})"
            })

        # Step 3: Update interfaces with MAC addresses
        for iface in interfaces:
            iface_name = iface.get('name')
            mac_address = iface.get('mac')

            if not iface_name or not mac_address:
                continue

            # Skip BMC/iLO interfaces
            if 'ilo' in iface_name.lower() or 'bmc' in iface_name.lower():
                continue

            logger.info(f"Updating interface: {iface_name} with MAC: {mac_address}")
            try:
                netbox.create_or_update_interface(
                    device_id=device_id,
                    name=iface_name,
                    mac_address=mac_address,
                    interface_type='25gbase-x-sfp28'  # Assuming 25GbE, adjust as needed
                )
            except Exception as e:
                logger.warning(f"Failed to update interface {iface_name}: {e}")

        # Step 4: Process LLDP data and create cable connections
        # Parse LLDP data and create cables (simplified for PoC)
        # Full implementation would parse LLDP JSON and create cables
        # For now, we'll log it
        if lldp_data:
            logger.info(f"LLDP data received (not fully processed in PoC): {len(str(lldp_data))} bytes")
            # TODO: Parse LLDP, find switch in NetBox, create cable

        # Step 5: Update device state to 'validated'
        timestamp = datetime.utcnow().isoformat() + 'Z'
        logger.info(f"Updating device {device_id} state to 'validated'")
        netbox.set_device_state(device_id, config.STATE_VALIDATED)

        log_event(logger, 'device_state_updated', device_id=device_name, data={
            'state': config.STATE_VALIDATED,
            'timestamp': timestamp
        })

        # Step 6: Publish validation_completed event
        validation_event = {
            'event_type': 'validation_completed',
            'timestamp': timestamp,
            'data': {
                'device_id': device_id,
                'device_name': device_name
            }
        }

        success = queue.publish(config.QUEUE_VALIDATION_COMPLETED, validation_event)

        if success:
            log_event(logger, 'validation_completed', device_id=device_name)
        else:
            logger.error("Failed to publish validation_completed event")

        return jsonify({
            'status': 'success',
            'device_id': device_id,
            'device_name': device_name,
            'message': 'Validation data processed'
        }), 200

    except Exception as e:
        log_error(logger, e, context={'endpoint': 'validation_report'})
        return jsonify({'error': str(e)}), 500


def main():
    """Main service entry point."""
    global logger, netbox, queue

    # Setup logging
    logger = setup_logger(
        'callback-api',
        log_file=os.path.join(config.LOG_DIR, 'callback_api.log')
    )

    logger.info("Callback API starting...")

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

    tls_enabled = getattr(config, 'REDIS_USE_TLS', False)
    auth_enabled = bool(getattr(config, 'REDIS_PASSWORD', None))
    logger.info(
        f"Connecting to Redis — host={config.REDIS_HOST} port={config.REDIS_PORT} "
        f"db={config.REDIS_DB} tls={tls_enabled} auth={auth_enabled}"
    )
    if tls_enabled:
        logger.info(
            f"  TLS cert:  {getattr(config, 'REDIS_TLS_CERT', 'not set')}\n"
            f"  TLS key:   {getattr(config, 'REDIS_TLS_KEY', 'not set')}\n"
            f"  TLS CA:    {getattr(config, 'REDIS_TLS_CA', 'not set')}"
        )

    try:
        queue.client.ping()
    except redis_lib.AuthenticationError as e:
        logger.error(f"Redis authentication failed — check REDIS_PASSWORD: {e}")
        sys.exit(1)
    except redis_lib.ConnectionError as e:
        logger.error(
            f"Cannot reach Redis at {config.REDIS_HOST}:{config.REDIS_PORT} — {e}"
        )
        if tls_enabled:
            logger.error(
                "TLS is enabled — verify the server is listening for TLS, "
                "the CA cert is correct, and the client cert/key paths exist"
            )
        sys.exit(1)
    except ssl.SSLError as e:
        logger.error(f"TLS handshake failed connecting to Redis: {e}")
        logger.error(
            f"  cert: {getattr(config, 'REDIS_TLS_CERT', 'not set')} "
            f"  key: {getattr(config, 'REDIS_TLS_KEY', 'not set')} "
            f"  CA: {getattr(config, 'REDIS_TLS_CA', 'not set')}"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error connecting to Redis ({type(e).__name__}): {e}")
        sys.exit(1)

    logger.info(f"Connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")

    # Initialize NetBox client
    netbox = NetBoxClient(
        url=config.NETBOX_URL,
        token=config.NETBOX_TOKEN,
        verify_ssl=False  # For PoC
    )

    logger.info(f"Connected to NetBox at {config.NETBOX_URL}")
    logger.info(f"Starting API on {config.CALLBACK_API_HOST}:{config.CALLBACK_API_PORT}")

    ssl_context = None
    if config.API_USE_TLS:
        import ssl
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            certfile=config.API_TLS_CERT,
            keyfile=config.API_TLS_KEY
        )
        if config.API_REQUIRE_CLIENT_CERT:
            ssl_context.load_verify_locations(cafile=config.API_TLS_CA)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
        logger.info(f"TLS enabled (cert: {config.API_TLS_CERT}, client cert required: {config.API_REQUIRE_CLIENT_CERT})")
    else:
        logger.warning("TLS is disabled — running in plain HTTP mode")

    app.run(
        host=config.CALLBACK_API_HOST,
        port=config.CALLBACK_API_PORT,
        ssl_context=ssl_context,
        debug=False
    )

if __name__ == '__main__':
    main()
