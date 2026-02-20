#!/usr/bin/env python3
"""
Unit Test: DHCP Lifecycle State Transition
===========================================
Tests the complete DHCP discovery workflow and state transitions.

Test Flow:
1. Reset server to 'offline' state and clear DHCP IP
2. Simulate DHCP request via dummy service
3. Verify worker processes the event
4. Verify IP assignment
5. Verify state transition: offline → provisioning

Usage:
    python test-dhcp-lifecycle.py <SERVER_NAME> <SITE>

Example:
    python test-dhcp-lifecycle.py EAST-SRV-001 dc-east
"""

import os
import sys
import time
import json
import redis
import subprocess
from datetime import datetime


class DHCPLifecycleTest:
    """Test harness for DHCP lifecycle state transitions."""

    def __init__(self, server_name, site):
        self.server_name = server_name
        self.site = site
        self.test_results = {
            'reset_state': False,
            'get_mac': False,
            'dhcp_request': False,
            'worker_processing': False,
            'ip_assigned': False,
            'state_transition': False,
        }
        self.mac_address = None
        self.allocated_ip = None
        self.initial_state = None
        self.final_state = None

    def print_header(self, title):
        """Print section header."""
        print(f"\n{'='*70}")
        print(f"{title}")
        print(f"{'='*70}\n")

    def run_docker_command(self, command, capture_output=True):
        """Execute docker command and return output."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=capture_output,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def test_1_reset_state(self):
        """Test 1: Reset server to offline state."""
        self.print_header("TEST 1: Reset Server to Offline State")

        # First, get current state (before reset)
        cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device
try:
    server = Device.objects.get(name='{self.server_name}')
    print(server.custom_field_data.get('lifecycle_state', 'unknown'), end='')
except:
    print('error', end='')
" 2>/dev/null"""

        success, stdout, _ = self.run_docker_command(cmd)
        if success and 'error' not in stdout:
            before_reset = stdout.strip().split('\n')[-1]
            print(f"  State before reset: {before_reset}")
        else:
            print(f"  ✗ Could not get state")
            return False

        # Copy reset script to container
        success, _, _ = self.run_docker_command(
            "docker cp reset-server-state.py netbox:/tmp/"
        )
        if not success:
            print(f"  ✗ Failed to copy reset script")
            return False

        # Run reset script
        cmd = f"docker exec netbox python /tmp/reset-server-state.py {self.server_name} 2>/dev/null"
        success, stdout, stderr = self.run_docker_command(cmd)

        if success and "RESET COMPLETE" in stdout:
            print(f"  ✓ Server reset to offline")

            # Get state after reset - this becomes our initial_state for the test
            time.sleep(0.5)
            cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device
server = Device.objects.get(name='{self.server_name}')
print(server.custom_field_data.get('lifecycle_state', 'unknown'), end='')
" 2>/dev/null"""

            success, stdout, _ = self.run_docker_command(cmd)
            if success:
                self.initial_state = stdout.strip().split('\n')[-1]
                print(f"  State after reset: {self.initial_state}")

            self.test_results['reset_state'] = True
            return True
        else:
            print(f"  ✗ Reset failed")
            print(f"  Error: {stderr}")
            return False

    def test_2_get_mac_address(self):
        """Test 2: Get server's management MAC address."""
        self.print_header("TEST 2: Get Management Interface MAC")

        cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device, Interface
try:
    server = Device.objects.get(name='{self.server_name}')
    mgmt = Interface.objects.get(device=server, name='mgmt0')
    print(mgmt.mac_address, end='')
except:
    print('error', end='')
" 2>/dev/null"""

        success, stdout, _ = self.run_docker_command(cmd)
        if success and 'error' not in stdout:
            self.mac_address = stdout.strip().split('\n')[-1]
            print(f"  Server: {self.server_name}")
            print(f"  MAC Address: {self.mac_address}")
            print(f"  Site: {self.site}")
            print(f"  ✓ MAC address retrieved")
            self.test_results['get_mac'] = True
            return True
        else:
            print(f"  ✗ Failed to get MAC address")
            return False

    def test_3_dhcp_request(self):
        """Test 3: Simulate DHCP request."""
        self.print_header("TEST 3: Simulate DHCP Request")

        cmd = f"python dummy-dhcp-service.py {self.mac_address} {self.site}"
        success, stdout, stderr = self.run_docker_command(cmd)

        if success and "LEASE COMPLETED" in stdout:
            # Extract allocated IP from output
            for line in stdout.split('\n'):
                if 'Allocated IP:' in line:
                    self.allocated_ip = line.split('Allocated IP:')[1].strip()
                    break

            print(f"  ✓ DHCP request completed")
            print(f"  Allocated IP: {self.allocated_ip}")
            print(f"  Event published to Redis")
            self.test_results['dhcp_request'] = True
            return True
        else:
            print(f"  ✗ DHCP request failed")
            print(f"  Error: {stderr}")
            return False

    def test_4_worker_processing(self):
        """Test 4: Wait for worker to process event."""
        self.print_header("TEST 4: Wait for Worker Processing")

        print(f"  Waiting for worker to process event...")

        # Wait up to 10 seconds for state change
        for i in range(10):
            time.sleep(1)

            # Check if state changed
            cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device
server = Device.objects.get(name='{self.server_name}')
print(server.custom_field_data.get('lifecycle_state', 'unknown'), end='')
" 2>/dev/null"""

            success, stdout, _ = self.run_docker_command(cmd)
            if success:
                current_state = stdout.strip().split('\n')[-1]
                if current_state == 'provisioning':
                    print(f"  ✓ Worker processed event (after {i+1}s)")
                    self.test_results['worker_processing'] = True
                    return True

            print(f"  {'.' * (i + 1)}", end='\r')

        print(f"\n  ✗ Worker did not process event in time")
        return False

    def test_5_verify_ip_assignment(self):
        """Test 5: Verify IP was assigned."""
        self.print_header("TEST 5: Verify IP Assignment")

        cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device, Interface
from ipam.models import IPAddress
server = Device.objects.get(name='{self.server_name}')
mgmt = Interface.objects.get(device=server, name='mgmt0')
ips = IPAddress.objects.filter(
    assigned_object_type__model='interface',
    assigned_object_id=mgmt.id
)
if ips.exists():
    ip = ips.first()
    print(f'{{ip.address}}|{{ip.description}}', end='')
else:
    print('none', end='')
" 2>/dev/null"""

        success, stdout, _ = self.run_docker_command(cmd)
        if success and 'none' not in stdout.lower():
            output = stdout.strip().split('\n')[-1]
            if '|' in output:
                assigned_ip, description = output.split('|', 1)
                expected_ip = f"{self.allocated_ip}/24"

                if assigned_ip == expected_ip:
                    print(f"  ✓ IP correctly assigned")
                    print(f"  Expected: {expected_ip}")
                    print(f"  Actual: {assigned_ip}")
                    print(f"  Description: {description}")
                    self.test_results['ip_assigned'] = True
                    return True
                else:
                    print(f"  ✗ IP mismatch")
                    print(f"  Expected: {expected_ip}")
                    print(f"  Actual: {assigned_ip}")
                    return False

        print(f"  ✗ No IP assigned")
        return False

    def test_6_verify_state_transition(self):
        """Test 6: Verify state transition."""
        self.print_header("TEST 6: Verify State Transition")

        cmd = f"""docker exec netbox python -c "
import os, sys, django
sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()
from dcim.models import Device
server = Device.objects.get(name='{self.server_name}')
print(server.custom_field_data.get('lifecycle_state', 'unknown'), end='')
" 2>/dev/null"""

        success, stdout, _ = self.run_docker_command(cmd)
        if success:
            self.final_state = stdout.strip().split('\n')[-1]

            print(f"  Initial State: {self.initial_state}")
            print(f"  Final State: {self.final_state}")

            if self.initial_state == 'offline' and self.final_state == 'provisioning':
                print(f"  ✓ State transition successful: offline → provisioning")
                self.test_results['state_transition'] = True
                return True
            else:
                print(f"  ✗ Unexpected state transition")
                return False

        print(f"  ✗ Could not verify state")
        return False

    def print_results(self):
        """Print final test results."""
        self.print_header("TEST RESULTS SUMMARY")

        all_passed = True

        print(f"Server: {self.server_name}")
        print(f"Site: {self.site}")
        print(f"MAC Address: {self.mac_address}")
        print(f"Allocated IP: {self.allocated_ip}")
        print(f"\nTest Results:")

        tests = [
            ("1. Reset State to Offline", 'reset_state'),
            ("2. Get MAC Address", 'get_mac'),
            ("3. DHCP Request", 'dhcp_request'),
            ("4. Worker Processing", 'worker_processing'),
            ("5. IP Assignment", 'ip_assigned'),
            ("6. State Transition", 'state_transition'),
        ]

        for test_name, test_key in tests:
            result = self.test_results[test_key]
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  {status}  {test_name}")
            if not result:
                all_passed = False

        print(f"\n{'='*70}")
        if all_passed:
            print("✓ ALL TESTS PASSED")
            print("="*70)
            print("\nThe DHCP lifecycle workflow is functioning correctly:")
            print(f"  • Server reset to offline state")
            print(f"  • DHCP request simulated successfully")
            print(f"  • Worker processed event from Redis")
            print(f"  • IP assigned: {self.allocated_ip}/24")
            print(f"  • State transitioned: offline → provisioning")
        else:
            print("✗ SOME TESTS FAILED")
            print("="*70)
            print("\nCheck the test output above for details.")

        print("="*70)

        return all_passed

    def run_all_tests(self):
        """Run all tests in sequence."""
        print("\n" + "="*70)
        print("DHCP LIFECYCLE STATE TRANSITION UNIT TEST")
        print("="*70)
        print(f"\nTarget Server: {self.server_name}")
        print(f"Site: {self.site}")
        print(f"Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run tests in sequence
        tests = [
            self.test_1_reset_state,
            self.test_2_get_mac_address,
            self.test_3_dhcp_request,
            self.test_4_worker_processing,
            self.test_5_verify_ip_assignment,
            self.test_6_verify_state_transition,
        ]

        for test in tests:
            if not test():
                # Stop on first failure
                break
            time.sleep(0.5)

        # Print final results
        return self.print_results()


def main():
    """Main execution."""
    if len(sys.argv) < 3:
        print("Usage: python test-dhcp-lifecycle.py <SERVER_NAME> <SITE>")
        print("\nExample:")
        print("  python test-dhcp-lifecycle.py EAST-SRV-001 dc-east")
        sys.exit(1)

    server_name = sys.argv[1]
    site = sys.argv[2]

    # Create test instance
    test = DHCPLifecycleTest(server_name, site)

    # Run all tests
    success = test.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
