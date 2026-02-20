# State Management Quick Start

## TL;DR

```bash
cd dhcp-integration/state-management

# Reset everything
python state-restore.py 0

# Jump to Phase 1 (BMC discovery done)
python state-restore.py 1

# Jump to Phase 2 (cable failures)
python state-restore.py 2
```

## Common Commands

### Reset to Clean Slate (Phase 0)
```bash
python state-restore.py 0
```
**Result**: All servers offline, no IPs, Redis cleared

### Advance to Phase 1 (BMC Discovery)
```bash
python state-restore.py 1
```
**Result**: Servers have BMC IPs, status='planned'

**Time**: ~2 minutes for 601 servers

### Advance to Phase 2 (Cable Failures)
```bash
python state-restore.py 2
```
**Result**: Servers failed, cables inverted, journal entries added

**Time**: ~5 minutes for 601 servers

## Testing with Limited Servers

```bash
# Test with only 10 servers
python state-restore.py 1 --limit 10

# Test with 50 servers
python state-restore.py 2 --limit 50
```

## Snapshots (Fast Demo Reset)

```bash
# Save current state as Phase 1
./snapshot-save.sh 1

# Later: instantly restore Phase 1
./snapshot-restore.sh 1
```
**Time**: ~10 seconds to restore

## Preview Changes (Dry Run)

```bash
# See what would happen without making changes
python state-restore.py 1 --dry-run
python state-restore.py 2 --dry-run
```

## Workflow for Demos

1. **Prepare snapshots**:
   ```bash
   python state-restore.py 1 && ./snapshot-save.sh 1
   python state-restore.py 2 && ./snapshot-save.sh 2
   ```

2. **During demo**:
   ```bash
   # Show Phase 1 (instant)
   ./snapshot-restore.sh 1

   # Show Phase 2 (instant)
   ./snapshot-restore.sh 2

   # Reset to Phase 1 (instant)
   ./snapshot-restore.sh 1
   ```

## Verification

### Check Current State
```bash
# Count by status
curl -s http://localhost:8000/api/dcim/devices/?limit=2000 | \
  jq -r '.results[] | select(.role.name | contains("Server")) | .status.value' | \
  sort | uniq -c

# Count BMC IPs
curl -s http://localhost:8000/api/ipam/ip-addresses/?limit=2000 | \
  jq -r '.results[] | select(.assigned_object.name == "bmc") | .address' | wc -l
```

### Monitor Progress
```bash
# Watch Redis queue
watch -n 1 'redis-cli -p 6380 llen netbox:bmc:discovered'

# Watch worker logs
docker-compose logs -f bmc-worker
```

## Troubleshooting

### Connection refused
```bash
# Check services are running
docker-compose ps
curl http://localhost:8000/api/
redis-cli -p 6380 ping
```

### No servers discovered
```bash
# Check worker is running
docker-compose logs bmc-worker

# Check Redis queue
redis-cli -p 6380 llen netbox:bmc:discovered
```

### Snapshot restore fails
```bash
# Ensure PostgreSQL is running
docker ps | grep postgres
docker-compose up -d netbox-postgres
```

## Performance

| Operation | Time (601 servers) |
|-----------|-------------------|
| Phase 0 | < 30s |
| Phase 1 | ~2 min |
| Phase 2 | ~5 min |
| Snapshot restore | ~10s |

## Next Steps

See [README.md](README.md) for complete documentation.
