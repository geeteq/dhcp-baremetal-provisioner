# Quick Start Guide - 5 Minutes to Running

Get the baremetal automation PoC running in 5 minutes with Docker.

## Prerequisites

- Docker and Docker Compose installed
- NetBox instance with API access
- HPE iLO Gen10 server (for testing)

## Steps

### 1. Configure (2 minutes)

```bash
cd /Users/gabe/ai/bm/poc

# Copy environment template
cp .env.example .env

# Edit with your values
nano .env
```

**Required values**:
```bash
NETBOX_URL=http://your-netbox.example.com
NETBOX_TOKEN=your-api-token-here
ILO_DEFAULT_PASSWORD=your-ilo-password
CALLBACK_API_URL=http://your-docker-host-ip:5000
```

### 2. Start (1 minute)

```bash
# Build and start all workers
docker-compose --profile all-in-one up -d

# Check status
docker-compose ps
```

Expected output:
```
NAME            STATUS    PORTS
bm-redis        running   6379/tcp
bm-workers-all  running   0.0.0.0:5000->5000/tcp
```

### 3. Verify (1 minute)

```bash
# Check logs
docker-compose logs -f

# Test callback API
curl http://localhost:5000/health

# Check Redis
docker exec bm-redis redis-cli ping
```

### 4. Test (1 minute)

```bash
# Simulate DHCP event
docker exec bm-workers-all /app/scripts/dhcp_hook.sh 10.1.100.50 94:40:c9:5e:7a:b0

# Check DHCP events log
docker exec bm-workers-all cat /var/log/bm/dhcp_events.log

# Watch discovery worker logs
docker-compose logs -f workers-all | grep discovery
```

## What's Running?

Inside the `bm-workers-all` container:
- ✅ DHCP Tailer (listening for DHCP events)
- ✅ Discovery Worker (watching for devices)
- ✅ Provisioning Worker (ready to trigger PXE boot)
- ✅ Callback API (listening on port 5000)
- ✅ Hardening Worker (ready to run Ansible)
- ✅ Monitoring Worker (polling every 5 minutes)

## Next Steps

### Test with Real Hardware

1. **Setup NetBox**:
   - Create device with BMC interface
   - Set MAC address on BMC interface
   - Set device state to `racked`

2. **Configure DHCP Server**:
   ```bash
   # Add to /etc/dhcp/dhcpd.conf
   on commit {
       set clientIP = binary-to-ascii(10, 8, ".", leased-address);
       set clientMAC = binary-to-ascii(16, 8, ":", substring(hardware, 1, 6));
       execute("/path/to/dhcp_hook.sh", clientIP, clientMAC);
   }
   ```

3. **Power On Server**:
   - Power on server BMC
   - Watch logs: `docker-compose logs -f`
   - Check NetBox for state changes

### View Logs

```bash
# All logs
docker-compose logs -f

# Specific worker
docker-compose logs -f workers-all | grep discovery
docker-compose logs -f workers-all | grep provisioning

# On host filesystem
tail -f poc/logs/discovery_worker.log
tail -f poc/logs/provisioning_worker.log
```

### View Metrics

```bash
# List collected metrics
ls -lh poc/metrics/

# View specific metric file
cat poc/metrics/srv001-20260211-100000.json | jq .
```

### Stop

```bash
# Stop all containers
docker-compose down

# Stop but keep data
docker-compose stop

# Restart
docker-compose up -d
```

## Troubleshooting

### Workers Not Starting

```bash
# Check logs for errors
docker-compose logs workers-all

# Check environment variables
docker exec bm-workers-all env | grep NETBOX
```

### NetBox Connection Failed

```bash
# Test NetBox API from container
docker exec bm-workers-all curl -k $NETBOX_URL/api/

# Validate config
docker exec bm-workers-all python3 -c "import config; config.validate_config()"
```

### Can't Access Callback API

```bash
# Check port mapping
docker-compose ps

# Test from host
curl http://localhost:5000/health

# Check from network
curl http://your-host-ip:5000/health
```

## Advanced Options

### Run Workers Separately

```bash
# Stop all-in-one
docker-compose --profile all-in-one down

# Start separate workers
docker-compose --profile separate up -d

# Scale discovery workers
docker-compose --profile separate up -d --scale discovery=3
```

### Access Container Shell

```bash
# Get shell in workers container
docker exec -it bm-workers-all bash

# Check running processes
docker exec bm-workers-all ps aux

# View logs inside container
docker exec bm-workers-all tail -f /var/log/bm/discovery_worker.log
```

### Update Code

```bash
# Rebuild after code changes
docker-compose build

# Restart with new image
docker-compose up -d
```

## Production Deployment

For production use:

1. **Use separate worker containers** for better scaling:
   ```bash
   docker-compose --profile separate up -d
   ```

2. **Add resource limits** in `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1'
         memory: 1G
   ```

3. **Configure persistent logging**:
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

4. **Use external Redis** for durability:
   ```bash
   REDIS_HOST=external-redis.example.com docker-compose up -d
   ```

5. **Deploy with orchestration** (Kubernetes, Docker Swarm)

See [DOCKER.md](poc/DOCKER.md) for complete documentation.

---

## Summary

**Time to Deploy**: ~5 minutes
**Containers**: 2 (Redis + All Workers)
**Memory**: ~500MB
**Disk**: ~250MB image + logs/metrics

**What You Get**:
✅ Complete event-driven automation pipeline
✅ Ready for testing with real hardware
✅ All workers running and monitored
✅ Logs accessible from host
✅ Easy to stop/start/restart

**Ready for**: Development, Testing, PoC Demonstration

---

Need help? Check:
- [DOCKER.md](poc/DOCKER.md) - Complete Docker guide
- [README.md](poc/README.md) - Full documentation
- [POC_COMPLETE.md](POC_COMPLETE.md) - Implementation summary
