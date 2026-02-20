#!/bin/bash
#
# Database Snapshot Save
# ======================
# Saves current NetBox PostgreSQL database to a snapshot file.
#
# Usage:
#   ./snapshot-save.sh <phase>
#
# Arguments:
#   phase   Phase number (0, 1, or 2)
#
# Examples:
#   # Save current state as Phase 0
#   ./snapshot-save.sh 0
#
#   # Save current state as Phase 1
#   ./snapshot-save.sh 1
#
# The snapshot will be saved to:
#   snapshots/phase-<phase>-<timestamp>.sql
#   snapshots/phase-<phase>-latest.sql (symlink)
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
    echo "Usage: $0 <phase>"
    echo "Example: $0 1"
    exit 1
fi

PHASE=$1

if [[ ! "$PHASE" =~ ^[0-2]$ ]]; then
    echo -e "${RED}✗ Error: Invalid phase: $PHASE${NC}"
    echo "Valid phases: 0, 1, 2"
    exit 1
fi

# Ensure snapshot directory exists
mkdir -p "$SNAPSHOT_DIR"

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Snapshot file paths
SNAPSHOT_FILE="${SNAPSHOT_DIR}/phase-${PHASE}-${TIMESTAMP}.sql"
LATEST_LINK="${SNAPSHOT_DIR}/phase-${PHASE}-latest.sql"

echo "======================================================================"
echo "DATABASE SNAPSHOT SAVE"
echo "======================================================================"
echo ""
echo "Phase:           $PHASE"
echo "Container:       $CONTAINER_NAME"
echo "Database:        $DB_NAME"
echo "Snapshot file:   $(basename $SNAPSHOT_FILE)"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}✗ Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Start the container first: docker-compose up -d"
    exit 1
fi

echo "✓ Container is running"

# Create database dump
echo "✓ Creating database dump..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" > "$SNAPSHOT_FILE"

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Error: Failed to create database dump${NC}"
    rm -f "$SNAPSHOT_FILE"
    exit 1
fi

# Check file size
FILE_SIZE=$(du -h "$SNAPSHOT_FILE" | cut -f1)
echo "✓ Dump created: $FILE_SIZE"

# Update latest symlink
rm -f "$LATEST_LINK"
ln -s "$(basename $SNAPSHOT_FILE)" "$LATEST_LINK"
echo "✓ Updated latest symlink: phase-${PHASE}-latest.sql"

# List all snapshots for this phase
echo ""
echo "======================================================================"
echo "SNAPSHOTS FOR PHASE $PHASE"
echo "======================================================================"
ls -lh "${SNAPSHOT_DIR}/phase-${PHASE}-"*.sql 2>/dev/null | awk '{print $9, "(" $5 ")"}'

echo ""
echo -e "${GREEN}✓ Snapshot saved successfully${NC}"
echo ""
echo "To restore this snapshot:"
echo "  ./snapshot-restore.sh $PHASE"
echo "======================================================================"
