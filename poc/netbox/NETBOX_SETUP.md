# NetBox 3.7.3 Docker Setup for Testing

Complete Docker-based NetBox installation for testing the baremetal provisioning system.

## Quick Start

```bash
# Navigate to netbox directory
cd poc/netbox

# Start NetBox
docker-compose -f docker-compose.netbox.yml up -d

# Wait for NetBox to initialize (2-3 minutes)
docker-compose -f docker-compose.netbox.yml logs -f netbox

# Initialize test data
docker exec -it netbox python /opt/netbox-init/init_data.py

# Access NetBox
# URL: http://localhost:8000
# Username: admin
# Password: admin
# API Token: 0123456789abcdef0123456789abcdef01234567
```

## What's Included

### Services

- **NetBox 3.7.3** - Main DCIM application
- **PostgreSQL 15** - Database backend
- **Redis 7** - Cache and task queue
- **NetBox Worker** - Background task processor
- **NetBox Housekeeping** - Cleanup tasks

### Test Data

The initialization script creates:

- ✅ **Custom Fields** - Lifecycle tracking fields
  - `lifecycle_state` (offline, planned, validating, validated, hardening, staged, ready, monitored, error)
  - `discovered_at`, `pxe_boot_initiated_at`, `hardened_at`
  - `last_monitored_at`, `last_power_watts`

- ✅ **Manufacturers** - HPE and Dell

- ✅ **Device Types**
  - HPE ProLiant DL360 Gen10 (1U)
  - HPE ProLiant DL380 Gen10 (2U)
  - Dell PowerEdge R640 (1U)
  - Dell PowerEdge R740 (2U)

- ✅ **Sites**
  - DC-Chicago
  - DC-NewYork
  - DC-LosAngeles

- ✅ **Racks**
  - CHI-R01, CHI-R02 (Chicago)
  - NYC-R01 (New York)

- ✅ **Tenants**
  - Baremetal Staging (for new devices)
  - Customer A, Customer B (for assigned devices)

- ✅ **Test Devices** - 3 pre-configured servers with iLO interfaces

## Detailed Setup

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

### Step 1: Start NetBox Stack

```bash
# Start all services
docker-compose -f docker-compose.netbox.yml up -d

# Check service status
docker-compose -f docker-compose.netbox.yml ps

# Expected output:
# NAME                 STATUS              PORTS
# netbox               running (healthy)   0.0.0.0:8000->8080/tcp
# netbox-postgres      running (healthy)   5432/tcp
# netbox-redis         running (healthy)   6379/tcp
# netbox-redis-cache   running (healthy)   6379/tcp
# netbox-worker        running
# netbox-housekeeping  running
```

### Step 2: Wait for Initialization

NetBox takes 2-3 minutes to initialize on first start:

```bash
# Follow logs
docker-compose -f docker-compose.netbox.yml logs -f netbox

# Look for:
# netbox | Performing database migrations...
# netbox | Creating superuser account...
# netbox | Superuser created successfully
# netbox | Application startup complete
```

### Step 3: Initialize Test Data

```bash
# Run initialization script
docker exec -it netbox python /opt/netbox-init/init_data.py

# Expected output:
# ============================================================
# NetBox Initialization for Baremetal Provisioning
# ============================================================
# Creating custom fields...
#   ✓ Created custom field: lifecycle_state
#   ✓ Created custom field: discovered_at
#   ...
# ✓ NetBox initialization completed successfully!
```

### Step 4: Verify Installation

```bash
# Test API access
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  http://localhost:8000/api/dcim/devices/

# Expected: JSON response with devices

# Test web interface
# Open browser: http://localhost:8000
# Login: admin / admin
```

## Configuration

### Environment Variables

Edit `.env.netbox` to customize:

```bash
# Superuser
NETBOX_SUPERUSER_NAME=admin
NETBOX_SUPERUSER_EMAIL=admin@example.com
NETBOX_SUPERUSER_PASSWORD=admin

# API Token
NETBOX_API_TOKEN=0123456789abcdef0123456789abcdef01234567

# Database
DB_NAME=netbox
DB_USER=netbox
DB_PASSWORD=netbox_password

# Settings
TIME_ZONE=UTC
DEBUG=False
ALLOWED_HOSTS=*
```

### Custom Configuration

Edit `netbox-config/configuration.py` for advanced settings:

```python
# Enable debug mode
DEBUG = True

# Configure logging
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}

# Configure webhooks
WEBHOOKS_ENABLED = True

# Configure CORS
CORS_ORIGIN_WHITELIST = [
    'http://localhost:3000',
    'http://localhost:5000',
]
```

## Integration with Baremetal Provisioning

### Update Project Configuration

Edit `poc/.env`:

```bash
# NetBox Configuration
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
NETBOX_TENANT=baremetal-staging
```

### Test Connection

```python
from lib.netbox_client import NetBoxClient

# Create client
netbox = NetBoxClient(
    url='http://localhost:8000',
    token='0123456789abcdef0123456789abcdef01234567',
    verify_ssl=False
)

# Test API
devices = netbox.get_devices_by_state('offline')
print(f"Found {len(devices)} offline devices")

# Update device state
device = devices[0]
netbox.set_device_state(device['id'], 'planned')
print(f"Updated device {device['name']} to 'planned'")
```

## Management Commands

### View Logs

```bash
# All services
docker-compose -f docker-compose.netbox.yml logs -f

# Specific service
docker-compose -f docker-compose.netbox.yml logs -f netbox
docker-compose -f docker-compose.netbox.yml logs -f netbox-postgres
docker-compose -f docker-compose.netbox.yml logs -f netbox-worker
```

### Access NetBox Shell

```bash
# Django shell
docker exec -it netbox python /opt/netbox/netbox/manage.py shell

# Database shell
docker exec -it netbox-postgres psql -U netbox -d netbox

# Redis CLI
docker exec -it netbox-redis redis-cli
```

### Backup and Restore

```bash
# Backup database
docker exec netbox-postgres pg_dump -U netbox netbox > netbox_backup.sql

# Backup media files
docker cp netbox:/opt/netbox/netbox/media ./netbox_media_backup

# Restore database
docker exec -i netbox-postgres psql -U netbox netbox < netbox_backup.sql

# Restore media files
docker cp ./netbox_media_backup/. netbox:/opt/netbox/netbox/media/
```

### Reset NetBox

```bash
# Stop services
docker-compose -f docker-compose.netbox.yml down

# Remove volumes (WARNING: deletes all data)
docker volume rm netbox_postgres_data netbox_redis_data netbox_media

# Start fresh
docker-compose -f docker-compose.netbox.yml up -d

# Wait for initialization
sleep 120

# Re-initialize test data
docker exec -it netbox python /opt/netbox-init/init_data.py
```

## Troubleshooting

### Issue 1: NetBox Not Starting

```bash
# Check logs
docker-compose -f docker-compose.netbox.yml logs netbox

# Common issues:
# - Database not ready: Wait for postgres health check
# - Port conflict: Change port in docker-compose.yml
# - Permission issues: Check file permissions on volumes
```

### Issue 2: Database Connection Failed

```bash
# Test database connection
docker exec -it netbox-postgres psql -U netbox -d netbox -c "SELECT 1"

# Reset database password
docker exec -it netbox-postgres psql -U postgres -c \
  "ALTER USER netbox WITH PASSWORD 'netbox_password';"
```

### Issue 3: API Token Not Working

```bash
# Generate new token
docker exec -it netbox python /opt/netbox/netbox/manage.py shell
>>> from users.models import Token, User
>>> user = User.objects.get(username='admin')
>>> token = Token.objects.create(user=user)
>>> print(token.key)
```

### Issue 4: Initialization Script Fails

```bash
# Run with error details
docker exec -it netbox python -u /opt/netbox-init/init_data.py

# Check Django migrations
docker exec -it netbox python /opt/netbox/netbox/manage.py showmigrations

# Run migrations manually
docker exec -it netbox python /opt/netbox/netbox/manage.py migrate
```

### Issue 5: Can't Access Web Interface

```bash
# Check if port is listening
netstat -tlnp | grep 8000
# or
ss -tlnp | grep 8000

# Check firewall
sudo firewall-cmd --list-ports

# Check container health
docker inspect netbox | grep -A10 Health
```

## Performance Tuning

### For Development/Testing

```yaml
# In docker-compose.netbox.yml
environment:
  # Disable debug mode
  DEBUG: "False"

  # Increase workers (if you have CPU cores)
  # Add to netbox service:
  command: gunicorn --workers=4 --bind=0.0.0.0:8080 netbox.wsgi
```

### Database Optimization

```sql
-- Connect to database
docker exec -it netbox-postgres psql -U netbox -d netbox

-- Analyze tables
ANALYZE;

-- Vacuum database
VACUUM FULL;

-- Check database size
SELECT pg_size_pretty(pg_database_size('netbox'));
```

## Useful API Examples

### List Devices

```bash
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  "http://localhost:8000/api/dcim/devices/" | jq
```

### Get Device by Name

```bash
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  "http://localhost:8000/api/dcim/devices/?name=chi-server-001" | jq
```

### Update Custom Field

```bash
curl -X PATCH \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  -H "Content-Type: application/json" \
  -d '{"custom_fields": {"lifecycle_state": "planned"}}' \
  "http://localhost:8000/api/dcim/devices/1/"
```

### Create Device

```bash
curl -X POST \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-server-001",
    "device_type": 1,
    "role": 1,
    "site": 1,
    "status": "offline"
  }' \
  "http://localhost:8000/api/dcim/devices/"
```

## Security Notes

⚠️ **This is a TEST environment. Do NOT use in production without:**

1. Changing default passwords
2. Generating a new SECRET_KEY
3. Creating a new API token
4. Enabling HTTPS/TLS
5. Restricting ALLOWED_HOSTS
6. Configuring proper authentication
7. Setting up proper backups
8. Implementing monitoring

## Next Steps

1. ✅ Start NetBox
2. ✅ Initialize test data
3. ✅ Configure project to use NetBox
4. ✅ Test device lifecycle workflow
5. ✅ Set up webhooks (optional)
6. ✅ Integrate with monitoring

## Resources

- [NetBox Documentation](https://docs.netbox.dev/en/stable/)
- [NetBox Docker](https://github.com/netbox-community/netbox-docker)
- [REST API Guide](https://docs.netbox.dev/en/stable/integrations/rest-api/)
- [Python Client (pynetbox)](https://github.com/netbox-community/pynetbox)

---

**Version:** 3.7.3
**Last Updated:** 2026-02-12
**Tested On:** Docker Engine 24.0+, Docker Compose 2.20+
