#!/bin/bash
#
# NetBox Quick Start Script
# Starts NetBox 3.7.3 Docker environment and initializes test data
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "NetBox 3.7.3 Quick Start"
echo "=========================================="
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    echo "Please start Docker and try again"
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose not found"
    echo "Please install docker-compose and try again"
    exit 1
fi

echo "✓ Docker is running"
echo

# Start NetBox stack
echo "Starting NetBox services..."
docker-compose -f docker-compose.netbox.yml up -d

echo
echo "Waiting for services to become healthy..."
echo "This may take 2-3 minutes on first start..."
echo

# Wait for NetBox to be healthy
for i in {1..60}; do
    if docker inspect netbox --format='{{.State.Health.Status}}' 2>/dev/null | grep -q "healthy"; then
        echo "✓ NetBox is healthy"
        break
    fi

    if [ $i -eq 60 ]; then
        echo "❌ Timeout waiting for NetBox to become healthy"
        echo "Check logs with: docker-compose -f docker-compose.netbox.yml logs netbox"
        exit 1
    fi

    echo -n "."
    sleep 3
done

echo
echo "Initializing test data..."
docker exec -it netbox python /opt/netbox-init/init_data.py

echo
echo "=========================================="
echo "✓ NetBox is ready!"
echo "=========================================="
echo
echo "Access NetBox at: http://localhost:8000"
echo "Username: admin"
echo "Password: admin"
echo "API Token: 0123456789abcdef0123456789abcdef01234567"
echo
echo "Next steps:"
echo "  1. Update poc/.env with NetBox URL and token"
echo "  2. Test connection: python -c 'from lib.netbox_client import NetBoxClient; nb = NetBoxClient(\"http://localhost:8000\", \"0123456789abcdef0123456789abcdef01234567\", False); print(nb.get_devices_by_state(\"offline\"))'"
echo
echo "Useful commands:"
echo "  Stop:    docker-compose -f docker-compose.netbox.yml stop"
echo "  Start:   docker-compose -f docker-compose.netbox.yml start"
echo "  Logs:    docker-compose -f docker-compose.netbox.yml logs -f netbox"
echo "  Restart: docker-compose -f docker-compose.netbox.yml restart netbox"
echo "  Clean:   docker-compose -f docker-compose.netbox.yml down -v"
echo "=========================================="
