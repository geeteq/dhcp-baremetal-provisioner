#!/usr/bin/env python3
"""
Server Status Dashboard
========================
Web UI for monitoring baremetal server automation workflow.

Provides:
- Real-time server status monitoring (NetBox device status)
- Timeline visualization of device statuses
- Redis queue monitoring
- Event history with journal entries
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import redis
import requests
import json
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6380
REDIS_QUEUE = 'netbox:bmc:discovered'
NETBOX_URL = 'http://localhost:8000'
NETBOX_TOKEN = '0123456789abcdef0123456789abcdef01234567'

# Initialize Redis client
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# NetBox device status definitions
DEVICE_STATUSES = [
    {'name': 'offline', 'color': '#6c757d', 'icon': '⏸'},
    {'name': 'planned', 'color': '#17a2b8', 'icon': '📋'},
    {'name': 'discovered', 'color': '#3b82f6', 'icon': '🔍'},
    {'name': 'staged', 'color': '#ffc107', 'icon': '📦'},
    {'name': 'active', 'color': '#28a745', 'icon': '✓'},
    {'name': 'failed', 'color': '#dc3545', 'icon': '✗'},
    {'name': 'inventory', 'color': '#6c757d', 'icon': '📊'},
    {'name': 'decommissioning', 'color': '#fd7e14', 'icon': '🔧'},
]

STATE_ORDER = {state['name']: i for i, state in enumerate(DEVICE_STATUSES)}


def get_netbox_devices(limit=1000):
    """Fetch devices from NetBox API."""
    try:
        # Fetch enough devices to include all servers
        # (need to account for switches and other devices)
        response = requests.get(
            f"{NETBOX_URL}/api/dcim/devices/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={
                'limit': limit
            },
            timeout=10
        )
        response.raise_for_status()

        # Filter for devices with 'server' in role name (client-side)
        all_devices = response.json()['results']
        devices = [d for d in all_devices if d.get('role') and 'server' in d['role']['name'].lower()]

        return devices
    except Exception as e:
        print(f"Error fetching NetBox devices: {e}")
        return []


def get_device_journals(device_id):
    """Fetch journal entries for a device."""
    try:
        response = requests.get(
            f"{NETBOX_URL}/api/extras/journal-entries/",
            headers={
                'Authorization': f'Token {NETBOX_TOKEN}',
                'Accept': 'application/json'
            },
            params={
                'assigned_object_type': 'dcim.device',
                'assigned_object_id': device_id,
                'limit': 10
            },
            timeout=5
        )
        response.raise_for_status()
        return response.json()['results']
    except Exception as e:
        print(f"Error fetching journals for device {device_id}: {e}")
        return []


def get_redis_queue_status():
    """Get Redis queue statistics."""
    try:
        queue_length = redis_client.llen(REDIS_QUEUE)

        # Get recent events from queue (without removing them)
        recent_events = []
        events = redis_client.lrange(REDIS_QUEUE, 0, 9)  # Get last 10

        for event_data in events:
            try:
                event = json.loads(event_data)
                recent_events.append(event)
            except json.JSONDecodeError:
                continue

        return {
            'queue_length': queue_length,
            'recent_events': recent_events
        }
    except Exception as e:
        print(f"Error fetching Redis queue status: {e}")
        return {
            'queue_length': 0,
            'recent_events': []
        }


@app.route('/')
def index():
    """Render main dashboard page."""
    return render_template('index.html', lifecycle_states=DEVICE_STATUSES)


@app.route('/api/devices')
def api_devices():
    """API endpoint for device list with current states."""
    devices = get_netbox_devices(limit=2000)

    # Transform device data
    device_list = []
    for device in devices:
        status = device.get('status', {}).get('value', 'unknown')

        device_data = {
            'id': device['id'],
            'name': device['name'],
            'site': device['site']['name'] if device.get('site') else 'Unknown',
            'status': status,
            'primary_ip': device.get('primary_ip4', {}).get('address', None) if device.get('primary_ip4') else None,
        }

        device_list.append(device_data)

    # Sort by status
    device_list.sort(key=lambda d: (
        STATE_ORDER.get(d['status'], 999),
        d['name']
    ))

    return jsonify(device_list)


@app.route('/api/device/<int:device_id>/timeline')
def api_device_timeline(device_id):
    """API endpoint for device timeline (journal entries)."""
    journals = get_device_journals(device_id)

    timeline = []
    for journal in journals:
        timeline.append({
            'timestamp': journal['created'],
            'kind': journal['kind']['value'],
            'comments': journal['comments'],
        })

    return jsonify(timeline)


@app.route('/api/queue')
def api_queue():
    """API endpoint for Redis queue status."""
    return jsonify(get_redis_queue_status())


@app.route('/api/stats')
def api_stats():
    """API endpoint for overall statistics."""
    devices = get_netbox_devices(limit=2000)

    # Count devices by status
    state_counts = defaultdict(int)
    for device in devices:
        status = device.get('status', {}).get('value', 'unknown')
        state_counts[status] += 1

    queue_status = get_redis_queue_status()

    return jsonify({
        'total_devices': len(devices),
        'state_counts': dict(state_counts),
        'queue_length': queue_status['queue_length'],
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
