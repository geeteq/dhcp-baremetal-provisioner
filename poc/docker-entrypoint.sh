#!/bin/bash
#
# Docker Entrypoint Script
# Runs one or more workers based on WORKER_TYPE environment variable
#

set -e

# Default to running all workers if not specified
WORKER_TYPE="${WORKER_TYPE:-all}"

echo "======================================"
echo "Baremetal Automation Workers"
echo "Worker Type: $WORKER_TYPE"
echo "======================================"

# Function to run a worker in background
run_worker() {
    local worker_name=$1
    local worker_script=$2

    echo "Starting $worker_name..."
    python3 "$worker_script" &
    echo "$worker_name started (PID: $!)"
}

# Run workers based on type
case "$WORKER_TYPE" in
    "dhcp-tailer")
        echo "Running DHCP Tailer only"
        exec python3 /app/services/dhcp_tailer.py
        ;;

    "discovery")
        echo "Running Discovery Worker only"
        exec python3 /app/services/discovery_worker.py
        ;;

    "provisioning")
        echo "Running Provisioning Worker only"
        exec python3 /app/services/provisioning_worker.py
        ;;

    "callback-api")
        echo "Running Callback API only"
        exec python3 /app/services/callback_api.py
        ;;

    "hardening")
        echo "Running Hardening Worker only"
        exec python3 /app/services/hardening_worker.py
        ;;

    "monitoring")
        echo "Running Monitoring Worker only"
        exec python3 /app/services/monitoring_worker.py
        ;;

    "all")
        echo "Running all workers in single container"
        echo "======================================"

        # Start all workers in background
        run_worker "DHCP Tailer" /app/services/dhcp_tailer.py
        run_worker "Discovery Worker" /app/services/discovery_worker.py
        run_worker "Provisioning Worker" /app/services/provisioning_worker.py
        run_worker "Callback API" /app/services/callback_api.py
        run_worker "Hardening Worker" /app/services/hardening_worker.py
        run_worker "Monitoring Worker" /app/services/monitoring_worker.py

        echo "======================================"
        echo "All workers started!"
        echo "======================================"

        # Wait for all background processes
        wait
        ;;

    *)
        echo "Error: Unknown WORKER_TYPE: $WORKER_TYPE"
        echo "Valid options: dhcp-tailer, discovery, provisioning, callback-api, hardening, monitoring, all"
        exit 1
        ;;
esac
