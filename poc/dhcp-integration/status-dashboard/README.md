# Server Lifecycle Status Dashboard

Real-time web UI for monitoring baremetal server automation workflow.

## Features

✨ **Real-time Monitoring**
- Auto-refreshes every 5 seconds
- Live queue status from Redis
- Device state transitions

📊 **Visual Timeline**
- Interactive lifecycle state progression
- Color-coded status indicators
- Progress bar for each server

🔍 **Filtering & Search**
- Filter by site
- Filter by lifecycle state
- Search by device name

📈 **Statistics Dashboard**
- Total device count
- State distribution
- Queue depth monitoring

## Quick Start

```bash
cd status-dashboard

# Build and start the dashboard
docker-compose up -d

# Check logs
docker-compose logs -f dashboard
```

**Access the dashboard:**
```
http://localhost:5000
```

## Architecture

```
┌──────────────┐
│   Browser    │
│  (Port 5000) │
└──────┬───────┘
       │ HTTP
       ▼
┌──────────────┐
│   Flask App  │
│  Dashboard   │
└──┬────────┬──┘
   │        │
   │        └─────────────┐
   │                      │
   ▼                      ▼
┌──────────┐      ┌──────────────┐
│  Redis   │      │    NetBox    │
│  Queue   │      │     API      │
└──────────┘      └──────────────┘
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard UI |
| `GET /api/devices` | List all devices with states |
| `GET /api/device/<id>/timeline` | Device journal timeline |
| `GET /api/queue` | Redis queue status |
| `GET /api/stats` | Overall statistics |

## Configuration

Edit `app.py` to configure:

```python
REDIS_HOST = 'bmc-redis'
REDIS_PORT = 6379
NETBOX_URL = 'http://host.docker.internal:8000'
NETBOX_TOKEN = 'your-token-here'
```

## Lifecycle States

The dashboard tracks these states:

| State | Icon | Color | Description |
|-------|------|-------|-------------|
| offline | ⏸ | Gray | Server powered off or not detected |
| discovered | 🔍 | Cyan | BMC detected via DHCP |
| provisioning | ⚙️ | Yellow | Firmware updates, configuration |
| ready | ✓ | Green | Ready for tenant assignment |
| active | ▶ | Blue | In production use |
| maintenance | 🔧 | Orange | Under maintenance |
| failed | ✗ | Red | Hardware failure detected |

## Screenshots

### Main Dashboard
Shows all servers with timeline visualization of their current lifecycle state.

### Statistics
Real-time counts of servers in each state.

### Queue Monitor
Shows pending events in Redis queue waiting to be processed.

## Troubleshooting

### Dashboard won't start

```bash
# Check if containers are running
docker-compose ps

# Check logs for errors
docker-compose logs dashboard

# Rebuild if needed
docker-compose up -d --build
```

### Can't connect to NetBox

```bash
# Test NetBox API from dashboard container
docker exec lifecycle-dashboard curl http://host.docker.internal:8000/api/

# Check NETBOX_TOKEN is correct
```

### Can't connect to Redis

```bash
# Test Redis connection
docker exec lifecycle-dashboard redis-cli -h bmc-redis ping

# Should return: PONG
```

### No devices showing

```bash
# Check NetBox has devices
curl http://localhost:8000/api/dcim/devices/ \
  -H "Authorization: Token YOUR_TOKEN"

# Check devices have 'server' role
```

## Development

Run locally without Docker:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REDIS_HOST=localhost
export REDIS_PORT=6380
export NETBOX_URL=http://localhost:8000
export NETBOX_TOKEN=your-token

# Run
python app.py
```

Access at: http://localhost:5000

## Performance

- **Polling Interval:** 5 seconds
- **Device Limit:** 100 devices per page (configurable)
- **Journal History:** Last 10 entries per device
- **Queue Preview:** Last 10 pending events

For production with thousands of devices, consider:
- Pagination
- Caching layer (Redis)
- WebSocket instead of polling

## License

Part of the baremetal server automation project.

---

**Version:** 1.0
**Last Updated:** 2026-02-13
