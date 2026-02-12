"""
Simple NetBox API client using requests library.
No external dependencies beyond requests.
"""
import requests
from typing import Optional, Dict, List, Any
from datetime import datetime


class NetBoxClient:
    """Minimal NetBox API client."""

    def __init__(self, url: str, token: str, verify_ssl: bool = True):
        """
        Initialize NetBox client.

        Args:
            url: NetBox URL (e.g., http://netbox.example.com)
            token: API token
            verify_ssl: Verify SSL certificates
        """
        self.url = url.rstrip('/')
        self.headers = {
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.verify_ssl = verify_ssl

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to NetBox API."""
        url = f'{self.url}/api/{endpoint.lstrip("/")}'
        response = requests.get(
            url,
            headers=self.headers,
            params=params,
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Dict) -> Dict:
        """Make POST request to NetBox API."""
        url = f'{self.url}/api/{endpoint.lstrip("/")}'
        response = requests.post(
            url,
            headers=self.headers,
            json=data,
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _patch(self, endpoint: str, data: Dict) -> Dict:
        """Make PATCH request to NetBox API."""
        url = f'{self.url}/api/{endpoint.lstrip("/")}'
        response = requests.patch(
            url,
            headers=self.headers,
            json=data,
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def find_interface_by_mac(self, mac_address: str) -> Optional[Dict]:
        """
        Find an interface by MAC address.

        Args:
            mac_address: MAC address to search for

        Returns:
            Interface dictionary or None if not found
        """
        result = self._get('dcim/interfaces/', {'mac_address': mac_address})
        results = result.get('results', [])
        return results[0] if results else None

    def get_device(self, device_id: int) -> Dict:
        """
        Get device by ID.

        Args:
            device_id: Device ID

        Returns:
            Device dictionary
        """
        return self._get(f'dcim/devices/{device_id}/')

    def update_device(self, device_id: int, data: Dict) -> Dict:
        """
        Update device.

        Args:
            device_id: Device ID
            data: Fields to update

        Returns:
            Updated device dictionary
        """
        return self._patch(f'dcim/devices/{device_id}/', data)

    def set_device_custom_field(self, device_id: int, field_name: str, value: Any) -> Dict:
        """
        Set a custom field on a device.

        Args:
            device_id: Device ID
            field_name: Custom field name
            value: Field value

        Returns:
            Updated device dictionary
        """
        return self.update_device(device_id, {
            'custom_fields': {field_name: value}
        })

    def set_device_state(self, device_id: int, state: str) -> Dict:
        """
        Set device lifecycle state.

        Args:
            device_id: Device ID
            state: Lifecycle state

        Returns:
            Updated device dictionary
        """
        return self.set_device_custom_field(device_id, 'lifecycle_state', state)

    def assign_ip_to_interface(self, interface_id: int, ip_address: str) -> Dict:
        """
        Assign IP address to an interface.

        Args:
            interface_id: Interface ID
            ip_address: IP address with mask (e.g., "10.1.100.50/24")

        Returns:
            Created IP address dictionary
        """
        data = {
            'address': ip_address,
            'status': 'active',
            'assigned_object_type': 'dcim.interface',
            'assigned_object_id': interface_id
        }
        return self._post('ipam/ip-addresses/', data)

    def create_or_update_interface(self, device_id: int, name: str,
                                   mac_address: Optional[str] = None,
                                   interface_type: str = '25gbase-x-sfp28') -> Dict:
        """
        Create or update an interface.

        Args:
            device_id: Device ID
            name: Interface name
            mac_address: MAC address
            interface_type: Interface type slug

        Returns:
            Interface dictionary
        """
        # Try to find existing interface
        result = self._get('dcim/interfaces/', {
            'device_id': device_id,
            'name': name
        })
        interfaces = result.get('results', [])

        data = {
            'device': device_id,
            'name': name,
            'type': interface_type,
            'enabled': True
        }

        if mac_address:
            data['mac_address'] = mac_address

        if interfaces:
            # Update existing
            interface_id = interfaces[0]['id']
            return self._patch(f'dcim/interfaces/{interface_id}/', data)
        else:
            # Create new
            return self._post('dcim/interfaces/', data)

    def create_cable(self, interface_a_id: int, interface_b_id: int) -> Dict:
        """
        Create a cable connection between two interfaces.

        Args:
            interface_a_id: First interface ID
            interface_b_id: Second interface ID

        Returns:
            Created cable dictionary
        """
        data = {
            'a_terminations': [{
                'object_type': 'dcim.interface',
                'object_id': interface_a_id
            }],
            'b_terminations': [{
                'object_type': 'dcim.interface',
                'object_id': interface_b_id
            }],
            'status': 'connected'
        }
        return self._post('dcim/cables/', data)

    def find_device_by_name(self, name: str) -> Optional[Dict]:
        """
        Find device by name.

        Args:
            name: Device name

        Returns:
            Device dictionary or None if not found
        """
        result = self._get('dcim/devices/', {'name': name})
        results = result.get('results', [])
        return results[0] if results else None

    def find_interface_by_device_and_name(self, device_id: int, interface_name: str) -> Optional[Dict]:
        """
        Find interface by device ID and interface name.

        Args:
            device_id: Device ID
            interface_name: Interface name

        Returns:
            Interface dictionary or None if not found
        """
        result = self._get('dcim/interfaces/', {
            'device_id': device_id,
            'name': interface_name
        })
        results = result.get('results', [])
        return results[0] if results else None

    def get_devices_by_state(self, state: str, tenant: Optional[str] = None) -> List[Dict]:
        """
        Get devices by lifecycle state.

        Args:
            state: Lifecycle state
            tenant: Optional tenant name filter

        Returns:
            List of device dictionaries
        """
        params = {'cf_lifecycle_state': state}
        if tenant:
            params['tenant'] = tenant

        result = self._get('dcim/devices/', params)
        return result.get('results', [])
