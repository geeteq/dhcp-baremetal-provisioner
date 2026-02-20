#!/usr/bin/env python3
"""
NetBox Utilities Module
=======================
Shared utilities for NetBox API operations including journal logging.

This module provides:
- Journal entry creation for audit trail
- Common NetBox API operations
- Error handling and logging

Usage:
    from netbox_utils import add_journal_entry, NetBoxJournalMixin
"""

import requests
from datetime import datetime


class NetBoxJournalMixin:
    """Mixin class to add journal logging capabilities to NetBox clients."""

    def add_journal_entry(self, device_id, message, kind='info'):
        """
        Add a journal entry to a device in NetBox.

        Args:
            device_id: NetBox device ID
            message: Journal entry text
            kind: Entry type - 'info', 'success', 'warning', or 'danger'

        Returns:
            dict: Journal entry object if successful, None otherwise
        """
        valid_kinds = ['info', 'success', 'warning', 'danger']
        if kind not in valid_kinds:
            kind = 'info'

        timestamp = datetime.utcnow().isoformat() + 'Z'

        try:
            response = requests.post(
                f"{self.url}/api/extras/journal-entries/",
                headers=self.headers,
                json={
                    'assigned_object_type': 'dcim.device',
                    'assigned_object_id': device_id,
                    'kind': kind,
                    'comments': f"[{timestamp}] {message}"
                }
            )

            if response.status_code == 201:
                if hasattr(self, 'logger'):
                    self.logger.info(f"✓ Journal entry added to device {device_id}: {message}")
                return response.json()
            else:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"Failed to add journal entry: {response.status_code} - {response.text}")
                return None

        except requests.RequestException as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error adding journal entry: {e}")
            return None

    def add_journal_state_change(self, device_id, device_name, old_state, new_state):
        """
        Add a journal entry for a state transition.

        Args:
            device_id: NetBox device ID
            device_name: Device name for logging
            old_state: Previous lifecycle state
            new_state: New lifecycle state
        """
        message = f"Lifecycle state changed: {old_state} → {new_state}"
        return self.add_journal_entry(device_id, message, kind='success')

    def add_journal_ip_assignment(self, device_id, device_name, interface_name, ip_address):
        """
        Add a journal entry for IP address assignment.

        Args:
            device_id: NetBox device ID
            device_name: Device name for logging
            interface_name: Interface name
            ip_address: Assigned IP address
        """
        message = f"IP address {ip_address} assigned to interface {interface_name}"
        return self.add_journal_entry(device_id, message, kind='info')

    def add_journal_discovery(self, device_id, device_name, discovery_type, mac_address, ip_address):
        """
        Add a journal entry for device discovery via DHCP.

        Args:
            device_id: NetBox device ID
            device_name: Device name for logging
            discovery_type: Type of discovery (BMC, Management, etc.)
            mac_address: MAC address that triggered discovery
            ip_address: IP address assigned
        """
        message = f"{discovery_type} discovered via DHCP - MAC: {mac_address}, IP: {ip_address}"
        return self.add_journal_entry(device_id, message, kind='success')

    def add_journal_error(self, device_id, device_name, error_message):
        """
        Add a journal entry for an error condition.

        Args:
            device_id: NetBox device ID
            device_name: Device name for logging
            error_message: Error description
        """
        message = f"ERROR: {error_message}"
        return self.add_journal_entry(device_id, message, kind='danger')


def add_journal_entry_django(device, message, kind='info'):
    """
    Add a journal entry using Django ORM (for use inside NetBox container).

    Args:
        device: Device Django model instance
        message: Journal entry text
        kind: Entry type - 'info', 'success', 'warning', or 'danger'

    Returns:
        JournalEntry instance if successful, None otherwise
    """
    try:
        from extras.models import JournalEntry
        from django.contrib.contenttypes.models import ContentType

        device_ct = ContentType.objects.get_for_model(device)
        timestamp = datetime.utcnow().isoformat() + 'Z'

        entry = JournalEntry.objects.create(
            assigned_object_type=device_ct,
            assigned_object_id=device.id,
            kind=kind,
            comments=f"[{timestamp}] {message}"
        )

        print(f"  ✓ Journal: {message}")
        return entry

    except Exception as e:
        print(f"  ⚠ Failed to add journal entry: {e}")
        return None


def add_journal_state_change_django(device, old_state, new_state):
    """
    Add a state change journal entry using Django ORM.

    Args:
        device: Device Django model instance
        old_state: Previous lifecycle state
        new_state: New lifecycle state
    """
    message = f"Lifecycle state changed: {old_state} → {new_state}"
    return add_journal_entry_django(device, message, kind='success')


def add_journal_ip_assignment_django(device, interface_name, ip_address):
    """
    Add an IP assignment journal entry using Django ORM.

    Args:
        device: Device Django model instance
        interface_name: Interface name
        ip_address: Assigned IP address
    """
    message = f"IP address {ip_address} assigned to interface {interface_name}"
    return add_journal_entry_django(device, message, kind='info')


def add_journal_discovery_django(device, discovery_type, mac_address, ip_address):
    """
    Add a discovery journal entry using Django ORM.

    Args:
        device: Device Django model instance
        discovery_type: Type of discovery (BMC, Management, etc.)
        mac_address: MAC address that triggered discovery
        ip_address: IP address assigned
    """
    message = f"{discovery_type} discovered via DHCP - MAC: {mac_address}, IP: {ip_address}"
    return add_journal_entry_django(device, message, kind='success')


def add_journal_error_django(device, error_message):
    """
    Add an error journal entry using Django ORM.

    Args:
        device: Device Django model instance
        error_message: Error description
    """
    message = f"ERROR: {error_message}"
    return add_journal_entry_django(device, message, kind='danger')
