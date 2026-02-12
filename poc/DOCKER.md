# Docker Deployment Guide

Run all baremetal automation workers in Docker containers.

## Quick Start

### 1. Configure Environment

```bash
cd /Users/gabe/ai/bm/poc

# Copy environment template
cp .env.example .env

# Edit with your values
vi .env
```

Required values in `.env`:
- `NETBOX_URL` - Your NetBox URL
- `NETBOX_TOKEN` - NetBox API token
- `ILO_DEFAULT_PASSWORD` - Default iLO password
- `CALLBACK_API_URL` - URL accessible from PXE-booted servers

### 2. Run All Workers in Single Container

```bash
# Build and start
docker-compose --profile all-in-one up -d

# View logs
docker-compose --profile all-in-one logs -f

# Stop
docker-compose --profile all-in-one down
```

### 3. OR: Run Workers Separately

```bash
# Build and start
docker-compose --profile separate up -d

# View logs for specific worker
docker-compose --profile separate logs -f discovery

# View all logs
docker-compose --profile separate logs -f

# Stop
docker-compose --profile separate down
```

## Architecture

### All-in-One Mode (Default)
```
┌─────────────────────────────────────┐
│     bm-workers-all container        │
│  ┌───────────────────────────────┐  │
│  │ DHCP Tailer                   │  │
│  │ Discovery Worker              │  │
│  │ Provisioning Worker           │  │
│  │ Callback API (port 5000)      │  │
│  │ Hardening Worker              │  │
│  │ Monitoring Worker             │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│     bm-redis container              │
│          (port 6379)                │
└─────────────────────────────────────┘
```

**Pros**: Simple, single container, less overhead
**Cons**: All workers restart together, harder to scale

### Separate Mode
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ dhcp-tailer  │  │  discovery   │  │ provisioning │
└──────────────┘  └──────────────┘  └──────────────┘
       ↕                 ↕                  ↕
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ callback-api │  │  hardening   │  │  monitoring  │
└──────────────┘  └──────────────┘  └──────────────┘
       ↕                 ↕                  ↕
┌─────────────────────────────────────────────────┐
│              bm-redis container                 │
└─────────────────────────────────────────────────┘
```

**Pros**: Independent scaling, isolated failures
**Cons**: More containers to manage

## Docker Commands

### Build

```bash
# Build image
docker-compose build

# Rebuild without cache
docker-compose build --no-cache
```

### Run

```bash
# All-in-one mode
docker-compose --profile all-in-one up -d

# Separate mode
docker-compose --profile separate up -d

# Run specific worker only
docker-compose up -d redis discovery
```

### Logs

```bash
# All logs
docker-compose logs -f

# Specific service
docker-compose logs -f workers-all
docker-compose logs -f discovery

# Last 100 lines
docker-compose logs --tail=100 workers-all
```

### Status

```bash
# Check running containers
docker-compose ps

# Check resource usage
docker stats

# Inspect container
docker inspect bm-workers-all
```

### Stop/Restart

```bash
# Stop all
docker-compose down

# Stop but keep data
docker-compose stop

# Restart
docker-compose restart

# Restart specific service
docker-compose restart discovery
```

### Shell Access

```bash
# Exec into running container
docker exec -it bm-workers-all bash

# Run Python shell
docker exec -it bm-workers-all python3

# Check logs inside container
docker exec -it bm-workers-all tail -f /var/log/bm/discovery_worker.log
```

## Volumes

### Log Files
```bash
# Logs are mounted to host
./logs/

# View logs from host
tail -f logs/discovery_worker.log
```

### Metrics Files
```bash
# Metrics are mounted to host
./metrics/

# View metrics from host
ls -lh metrics/
cat metrics/srv001-20260211-100000.json | jq .
```

### Redis Data
```bash
# Redis data persists in Docker volume
docker volume ls | grep redis

# Backup Redis data
docker exec bm-redis redis-cli SAVE
docker cp bm-redis:/data/dump.rdb ./backup/
```

## Environment Variables

Override any config in `docker-compose.yml`:

```bash
# Run with custom monitoring interval
MONITORING_INTERVAL_SECONDS=60 docker-compose up -d

# Run with different Redis
REDIS_HOST=external-redis.example.com docker-compose up -d
```

## Networking

### Access from Host

```bash
# Callback API
curl http://localhost:5000/health

# Redis
redis-cli -h localhost -p 6379 ping
```

### Access from PXE-booted Servers

Ensure `CALLBACK_API_URL` in `.env` points to IP accessible from your network:

```bash
# If Docker host is 10.1.100.5
CALLBACK_API_URL=http://10.1.100.5:5000
```

### Custom Network

```yaml
# In docker-compose.yml, add:
networks:
  default:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

## Production Deployment

### Use Docker Swarm or Kubernetes

Docker Compose is great for development. For production:

**Docker Swarm**:
```bash
docker stack deploy -c docker-compose.yml bm
```

**Kubernetes**:
- Use Kompose to convert: `kompose convert -f docker-compose.yml`
- Or write Kubernetes manifests manually

### Health Checks

All workers have health checks in Dockerfile:
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python3 -c "import redis; redis.Redis(host='redis').ping()" || exit 1
```

### Resource Limits

Add to `docker-compose.yml`:
```yaml
services:
  workers-all:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Logging

Configure logging driver:
```yaml
services:
  workers-all:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Or use centralized logging (ELK, Loki):
```yaml
services:
  workers-all:
    logging:
      driver: "gelf"
      options:
        gelf-address: "udp://logstash:12201"
```

## Troubleshooting

### Workers Not Starting

```bash
# Check logs
docker-compose logs workers-all

# Check environment
docker exec bm-workers-all env | grep NETBOX

# Verify Redis connectivity
docker exec bm-workers-all redis-cli -h redis ping
```

### NetBox Connection Failed

```bash
# Test from container
docker exec bm-workers-all curl -k $NETBOX_URL/api/

# Check token
docker exec bm-workers-all python3 -c "import config; config.validate_config()"
```

### iLO Connection Failed

```bash
# Test from container
docker exec bm-workers-all curl -k -u Administrator:password https://ilo-ip/redfish/v1/

# Check network access
docker exec bm-workers-all ping ilo-ip
```

### Redis Connection Failed

```bash
# Check Redis is running
docker-compose ps redis

# Check Redis logs
docker-compose logs redis

# Test Redis connection
docker exec bm-workers-all redis-cli -h redis ping
```

### Callback API Not Reachable

```bash
# Check port mapping
docker-compose ps | grep 5000

# Test from host
curl http://localhost:5000/health

# Test from network
curl http://docker-host-ip:5000/health
```

## Migration from Native to Docker

1. Stop native services
2. Configure `.env` file
3. Start Docker containers
4. Point DHCP hook to Docker host
5. Update `CALLBACK_API_URL` for PXE servers

## Cleanup

```bash
# Stop and remove containers
docker-compose down

# Remove volumes too (deletes Redis data!)
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Full cleanup
docker system prune -a --volumes
```

---

**Image Size**: ~250MB
**Container Count**: 1 (all-in-one) or 7 (separate)
**Memory Usage**: ~500MB (all-in-one) or ~1GB (separate)
**CPU Usage**: Minimal (event-driven, mostly idle)
