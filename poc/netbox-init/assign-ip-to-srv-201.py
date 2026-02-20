#!/usr/bin/env python3
"""Assign BMC IP to WEST-SRV-201"""
import os, sys, django

sys.path.insert(0, '/opt/netbox/netbox')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
django.setup()

from dcim.models import Device, Interface
from ipam.models import IPAddress
import ipaddress

# Get WEST-SRV-201
server = Device.objects.get(name='WEST-SRV-201')
bmc_interface = Interface.objects.get(device=server, name='bmc')

# Find available IP in 10.22.2.0/23 (West BMC subnet)
network = ipaddress.ip_network('10.22.2.0/23')
for ip in network.hosts():
    ip_str = str(ip)
    last_octet = int(ip_str.split('.')[-1])
    if last_octet < 10 or last_octet > 250:
        continue

    # Check if IP exists
    if not IPAddress.objects.filter(address=f"{ip_str}/24").exists():
        # Create and assign IP
        ip_obj = IPAddress.objects.create(
            address=f"{ip_str}/24",
            status='active',
            dns_name='west-srv-201-bmc',
            description='BMC for WEST-SRV-201 - Manually assigned'
        )
        ip_obj.assigned_object = bmc_interface
        ip_obj.save()

        print(f"✓ Assigned {ip_str}/24 to {server.name}/bmc")
        break
