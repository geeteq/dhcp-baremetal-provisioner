"""
Simple Redfish API client using requests library.
Supports HPE iLO Gen10 operations.
"""
import requests
import urllib3
from typing import Dict, Optional

# Disable SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RedfishClient:
    """Minimal Redfish API client for HPE iLO."""

    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False):
        """
        Initialize Redfish client.

        Args:
            host: iLO hostname or IP address
            username: iLO username
            password: iLO password
            verify_ssl: Verify SSL certificates
        """
        self.base_url = f'https://{host}'
        self.auth = (username, password)
        self.verify_ssl = verify_ssl
        self.headers = {
            'Content-Type': 'application/json'
        }

    def _get(self, path: str) -> Dict:
        """Make GET request to Redfish API."""
        url = f'{self.base_url}{path}'
        response = requests.get(
            url,
            auth=self.auth,
            headers=self.headers,
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, data: Dict) -> Dict:
        """Make PATCH request to Redfish API."""
        url = f'{self.base_url}{path}'
        response = requests.patch(
            url,
            auth=self.auth,
            headers=self.headers,
            json=data,
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, data: Optional[Dict] = None) -> Dict:
        """Make POST request to Redfish API."""
        url = f'{self.base_url}{path}'
        response = requests.post(
            url,
            auth=self.auth,
            headers=self.headers,
            json=data or {},
            verify=self.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def get_system_info(self) -> Dict:
        """
        Get system information.

        Returns:
            System info dictionary
        """
        return self._get('/redfish/v1/Systems/1')

    def get_power_state(self) -> str:
        """
        Get current power state.

        Returns:
            Power state string (e.g., 'On', 'Off')
        """
        info = self.get_system_info()
        return info.get('PowerState', 'Unknown')

    def set_one_time_pxe_boot(self) -> Dict:
        """
        Configure one-time PXE boot.

        Returns:
            Response dictionary
        """
        data = {
            'Boot': {
                'BootSourceOverrideTarget': 'Pxe',
                'BootSourceOverrideEnabled': 'Once'
            }
        }
        return self._patch('/redfish/v1/Systems/1', data)

    def power_on(self) -> Dict:
        """
        Power on the system.

        Returns:
            Response dictionary
        """
        data = {'ResetType': 'On'}
        return self._post('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset', data)

    def power_off(self) -> Dict:
        """
        Power off the system (graceful).

        Returns:
            Response dictionary
        """
        data = {'ResetType': 'GracefulShutdown'}
        return self._post('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset', data)

    def force_restart(self) -> Dict:
        """
        Force restart the system.

        Returns:
            Response dictionary
        """
        data = {'ResetType': 'ForceRestart'}
        return self._post('/redfish/v1/Systems/1/Actions/ComputerSystem.Reset', data)

    def get_cpu_info(self) -> Dict:
        """
        Get CPU information.

        Returns:
            Dictionary with CPU count and health status
        """
        info = self.get_system_info()
        proc_summary = info.get('ProcessorSummary', {})
        return {
            'count': proc_summary.get('Count', 0),
            'model': proc_summary.get('Model', 'Unknown'),
            'health': proc_summary.get('Status', {}).get('Health', 'Unknown')
        }

    def get_memory_info(self) -> Dict:
        """
        Get memory information.

        Returns:
            Dictionary with memory size and health status
        """
        info = self.get_system_info()
        mem_summary = info.get('MemorySummary', {})
        return {
            'total_gb': mem_summary.get('TotalSystemMemoryGiB', 0),
            'health': mem_summary.get('Status', {}).get('Health', 'Unknown')
        }

    def get_power_metrics(self) -> Dict:
        """
        Get power consumption metrics.

        Returns:
            Dictionary with power consumption data
        """
        try:
            data = self._get('/redfish/v1/Chassis/1/Power')
            power_control = data.get('PowerControl', [{}])[0]
            power_supplies = data.get('PowerSupplies', [])

            return {
                'consumed_watts': power_control.get('PowerConsumedWatts', 0),
                'capacity_watts': power_control.get('PowerCapacityWatts', 0),
                'power_supplies': [{
                    'name': ps.get('Name', ''),
                    'health': ps.get('Status', {}).get('Health', 'Unknown')
                } for ps in power_supplies]
            }
        except Exception:
            return {'consumed_watts': 0, 'capacity_watts': 0, 'power_supplies': []}

    def get_thermal_metrics(self) -> Dict:
        """
        Get thermal metrics.

        Returns:
            Dictionary with temperature data
        """
        try:
            data = self._get('/redfish/v1/Chassis/1/Thermal')
            temperatures = data.get('Temperatures', [])
            fans = data.get('Fans', [])

            temp_readings = [t.get('ReadingCelsius', 0) for t in temperatures
                           if t.get('ReadingCelsius') is not None]

            return {
                'avg_temp_celsius': sum(temp_readings) / len(temp_readings) if temp_readings else 0,
                'max_temp_celsius': max(temp_readings) if temp_readings else 0,
                'sensors': [{
                    'name': t.get('Name', ''),
                    'reading': t.get('ReadingCelsius', 0),
                    'health': t.get('Status', {}).get('Health', 'Unknown')
                } for t in temperatures],
                'fans': [{
                    'name': f.get('Name', ''),
                    'reading_rpm': f.get('Reading', 0),
                    'health': f.get('Status', {}).get('Health', 'Unknown')
                } for f in fans]
            }
        except Exception:
            return {
                'avg_temp_celsius': 0,
                'max_temp_celsius': 0,
                'sensors': [],
                'fans': []
            }

    def get_all_metrics(self) -> Dict:
        """
        Get all system metrics.

        Returns:
            Combined metrics dictionary
        """
        return {
            'system': self.get_system_info(),
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'power': self.get_power_metrics(),
            'thermal': self.get_thermal_metrics()
        }
