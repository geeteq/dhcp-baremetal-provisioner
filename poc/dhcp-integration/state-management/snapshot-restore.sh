#!/bin/bash
#
# Database Snapshot Restore
# ==========================
# Restores NetBox PostgreSQL database from a snapshot file.
#
# Usage:
#   ./snapshot-restore.sh <phase> [--timestamp TIMESTAMP]
#
# Arguments:
#   phase      Phase number (0, 1, or 2)
#
# Options:
#   --timestamp TIMESTAMP   Restore specific timestamp (default: latest)
#
# Examples:
#   # Restore latest Phase 1 snapshot
#   ./snapshot-restore.sh 1
#
#   # Restore specific snapshot
#   ./snapshot-restore.sh 1 --timestamp 20240215-143022
#
# WARNING: This will REPLACE the current database!
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_DIR="${SCRIPT_DIR}/snapshots"
CONTAINER_NAME="${NETBOX_CONTAINER:-netbox-postgres}"
DB_NAME="${NETBOX_DB:-netbox}"
DB_USER="${NETBOX_USER:-netbox}"

# Parse arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}✗ Error: Phase number required${NC}"
    echo "Usage: $0 <phase> [--timestamp TIMESTAMP]"
    echo "Example: $0 1"
    exit 1
fi

PHASE=$1
shift

TIMESTAMP=""

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --timestamp)
            TIMESTAMP="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}✗ Error: Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

if [[ ! "$PHASE" =~ ^[0-2]$ ]]; then
    echo -e "${RED}✗ Error: Invalid phase: $PHASE${NC}"
    echo "Valid phases: 0, 1, 2"
    exit 1
fi

# Determine snapshot file
if [ -n "$TIMESTAMP" ]; then
    SNAPSHOT_FILE="${SNAPSHOT_DIR}/phase-${PHASE}-${TIMESTAMP}.sql"
else
    # Use latest
    LATEST_LINK="${SNAPSHOT_DIR}/phase-${PHASE}-latest.sql"

    if [ ! -L "$LATEST_LINK" ]; then
        echo -e "${RED}✗ Error: No snapshot found for Phase $PHASE${NC}"
        echo "Available snapshots:"
        ls -1 "${SNAPSHOT_DIR}/phase-${PHASE}-"*.sql 2>/dev/null || echo "  (none)"
        exit 1
    fi

    SNAPSHOT_FILE=$(readlink -f "$LATEST_LINK")
fi

if [ ! -f "$SNAPSHOT_FILE" ]; then
    echo -e "${RED}✗ Error: Snapshot file not found: $SNAPSHOT_FILE${NC}"
    exit 1
fi

FILE_SIZE=$(du -h "$SNAPSHOT_FILE" | cut -f1)

echo "======================================================================"
echo "DATABASE SNAPSHOT RESTORE"
echo "======================================================================"
echo ""
echo "Phase:           $PHASE"
echo "Container:       $CONTAINER_NAME"
echo "Database:        $DB_NAME"
echo "Snapshot:        $(basename $SNAPSHOT_FILE)"
echo "Size:            $FILE_SIZE"
echo ""
echo -e "${YELLOW}⚠ WARNING: This will REPLACE the current database!${NC}"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}✗ Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Start the container first: docker-compose up -d"
    exit 1
fi

echo "✓ Container is running"

# Ask for confirmation
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 0
fi

echo ""
echo "✓ Terminating active database connections..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
    > /dev/null 2>&1 || true

echo "✓ Dropping existing database..."
docker exec "$CONTAINER_NAME" dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true

echo "✓ Creating new database..."
docker exec "$CONTAINER_NAME" createdb -U "$DB_USER" "$DB_NAME"

echo "✓ Restoring database from snapshot..."
cat "$SNAPSHOT_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" > /dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Error: Failed to restore database${NC}"
    exit 1
fi

echo "✓ Database restored successfully"

# Restart NetBox to pick up changes
echo "✓ Restarting NetBox container..."
NETBOX_CONTAINER="${NETBOX_WEB_CONTAINER:-netbox}"
docker restart "$NETBOX_CONTAINER" > /dev/null 2>&1 || true

echo ""
echo "======================================================================"
echo -e "${GREEN}✓ RESTORE COMPLETE${NC}"
echo "======================================================================"
echo ""
echo "Restored Phase $PHASE from $(basename $SNAPSHOT_FILE)"
echo ""
echo "NetBox should be available at: http://localhost:8000"
echo "======================================================================"
