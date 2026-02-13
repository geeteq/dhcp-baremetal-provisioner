"""
Central configuration for baremetal automation PoC.
All settings can be overridden via environment variables.
"""
import os

# NetBox Configuration
NETBOX_URL = os.getenv('NETBOX_URL', 'http://netbox.example.com')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN')  # Required
NETBOX_TENANT = os.getenv('NETBOX_TENANT', 'baremetal-staging')

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')  # Optional password for authentication
REDIS_USE_TLS = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'

# Redis TLS Configuration (optional)
REDIS_TLS_CERT = os.getenv('REDIS_TLS_CERT')
REDIS_TLS_KEY = os.getenv('REDIS_TLS_KEY')
REDIS_TLS_CA = os.getenv('REDIS_TLS_CA')

# Queue Names
QUEUE_DHCP_LEASE = 'bm:events:dhcp_lease'
QUEUE_DEVICE_DISCOVERED = 'bm:events:device_discovered'
QUEUE_PXE_BOOT_INITIATED = 'bm:events:pxe_boot_initiated'
QUEUE_VALIDATION_COMPLETED = 'bm:events:validation_completed'
QUEUE_HARDENING_COMPLETED = 'bm:events:hardening_completed'

# iLO/BMC Configuration
ILO_DEFAULT_USER = os.getenv('ILO_DEFAULT_USER', 'Administrator')
ILO_DEFAULT_PASSWORD = os.getenv('ILO_DEFAULT_PASSWORD')  # Required
ILO_VERIFY_SSL = os.getenv('ILO_VERIFY_SSL', 'false').lower() == 'true'

# Callback API Configuration
CALLBACK_API_HOST = os.getenv('CALLBACK_API_HOST', '0.0.0.0')
CALLBACK_API_PORT = int(os.getenv('CALLBACK_API_PORT', '5000'))
CALLBACK_API_URL = os.getenv('CALLBACK_API_URL', 'http://10.1.100.5:5000')

# Paths
LOG_DIR = os.getenv('LOG_DIR', '/var/log/bm')
DHCP_EVENT_LOG = os.path.join(LOG_DIR, 'dhcp_events.log')
ERROR_LOG = os.path.join(LOG_DIR, 'errors.log')
METRICS_DIR = os.path.join(LOG_DIR, 'metrics')

# Ansible Configuration
ANSIBLE_PLAYBOOK_DIR = os.getenv('ANSIBLE_PLAYBOOK_DIR', '/opt/bm/ansible')
ANSIBLE_BMC_HARDENING_PLAYBOOK = os.path.join(ANSIBLE_PLAYBOOK_DIR, 'bmc_hardening.yml')

# Monitoring Configuration
MONITORING_INTERVAL_SECONDS = int(os.getenv('MONITORING_INTERVAL_SECONDS', '300'))  # 5 minutes

# Timeouts
REDFISH_TIMEOUT_SECONDS = int(os.getenv('REDFISH_TIMEOUT_SECONDS', '30'))
VALIDATION_TIMEOUT_SECONDS = int(os.getenv('VALIDATION_TIMEOUT_SECONDS', '900'))  # 15 minutes

# NetBox Custom Fields
NETBOX_FIELD_LIFECYCLE_STATE = 'lifecycle_state'
NETBOX_FIELD_DISCOVERED_AT = 'discovered_at'
NETBOX_FIELD_PXE_BOOT_INITIATED_AT = 'pxe_boot_initiated_at'
NETBOX_FIELD_HARDENED_AT = 'hardened_at'
NETBOX_FIELD_LAST_MONITORED_AT = 'last_monitored_at'
NETBOX_FIELD_LAST_POWER_WATTS = 'last_power_watts'

# Lifecycle States
STATE_OFFLINE = 'offline'
STATE_PLANNED = 'planned'
STATE_VALIDATING = 'validating'
STATE_VALIDATED = 'validated'
STATE_HARDENING = 'hardening'
STATE_STAGED = 'staged'
STATE_READY = 'ready'
STATE_MONITORED = 'monitored'
STATE_ERROR = 'error'

def validate_config():
    """Validate required configuration is present."""
    errors = []

    if not NETBOX_TOKEN:
        errors.append("NETBOX_TOKEN environment variable is required")

    if not ILO_DEFAULT_PASSWORD:
        errors.append("ILO_DEFAULT_PASSWORD environment variable is required")

    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    return True
