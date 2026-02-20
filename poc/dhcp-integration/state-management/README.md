# PoC State Management System

Fast and reliable state management for baremetal automation PoC workflows.

## Overview

This system allows you to save and restore consistent states for your PoC, enabling:
- Demo the workflow from any phase
- Test phases independently
- Reset to known states for debugging
- Replay automation sequences

## Available Phases

### Phase 0: Clean Slate
- **Status**: All servers offline
- **IPs**: No BMC IPs assigned
- **Redis**: Queue cleared
- **Use case**: Fresh start, reset everything

### Phase 1: BMC Discovery Complete
- **Status**: Servers set to 'planned'
- **IPs**: BMC IPs allocated and assigned
- **Redis**: Discovery events processed
- **Use case**: Test cable validation, skip initial discovery

### Phase 2: Cable Validation Complete
- **Status**: Servers set to 'failed'
- **Cables**: Production NICs inverted (misconfigured)
- **Journal**: Failure details logged
- **Use case**: Test remediation workflows, demonstrate failure handling

## Quick Start

### API-Based State Restoration (Recommended)

Fast, portable, easy to modify:

```bash
cd dhcp-integration/state-management

# Reset to Phase 0 (clean slate)
python state-restore.py 0

# Advance to Phase 1 (BMC discovery)
python state-restore.py 1

# Advance to Phase 2 (cable validation failures)
python state-restore.py 2

# Process only 10 servers
python state-restore.py 1 --limit 10

# Dry run to see what would happen
python state-restore.py 1 --dry-run
```

### Database Snapshots (Instant Restore)

Fastest method for demos - instant rollback:

```bash
cd dhcp-integration/state-management

# Save current state as Phase 1 snapshot
./snapshot-save.sh 1

# Later... restore Phase 1 instantly
./snapshot-restore.sh 1

# Restore specific snapshot by timestamp
./snapshot-restore.sh 1 --timestamp 20240215-143022
```

## Performance

| Operation | Time (601 servers) |
|-----------|-------------------|
| Phase 0 Reset | < 30 seconds |
| Phase 1 Advance | ~2 minutes |
| Phase 2 Advance | ~5 minutes |
| Snapshot Save | ~5 seconds |
| Snapshot Restore | ~10 seconds |

## Individual Phase Scripts

You can also run phase scripts directly:

```bash
# Phase 0: Reset to clean slate
python state-phase0.py [--dry-run]

# Phase 1: Run BMC discovery
python state-phase1.py [--limit N] [--dry-run]

# Phase 2: Invert cables and mark failed
python state-phase2.py [--limit N] [--dry-run]
```

## Verification

After each phase transition, the scripts automatically verify the state:

### Phase 0 Verification
```bash
# Check all servers are offline
curl -s http://localhost:8000/api/dcim/devices/?limit=2000 | \
  jq -r '.results[] | select(.role.name | contains("Server")) | .status.value' | \
  sort | uniq -c

# Expected: All "offline"
```

### Phase 1 Verification
```bash
# Count servers in 'planned' status
curl -s http://localhost:8000/api/dcim/devices/?status=planned | \
  jq '.count'

# Check BMC IP assignments
curl -s http://localhost:8000/api/ipam/ip-addresses/?limit=2000 | \
  jq -r '.results[] | select(.assigned_object.name == "bmc") | .address' | \
  wc -l
```

### Phase 2 Verification
```bash
# Count servers in 'failed' status
curl -s http://localhost:8000/api/dcim/devices/?status=failed | \
  jq '.count'

# Check for cable inversion journal entries
curl -s http://localhost:8000/api/extras/journal-entries/ | \
  jq -r '.results[] | select(.comments | contains("Cable Inversion")) | .assigned_object.name' | \
  wc -l
```

## Workflow Examples

### Demo Preparation

```bash
# 1. Advance to Phase 1
python state-restore.py 1

# 2. Save snapshot for quick demos
./snapshot-save.sh 1

# 3. During demo, if you need to restart:
./snapshot-restore.sh 1  # Instant reset to Phase 1
```

### Testing Phase 2 Remediation

```bash
# 1. Advance to Phase 2 (creates failures)
python state-restore.py 2

# 2. Test your remediation script
./my-remediation-script.sh

# 3. Verify fixes worked
python verify-cables.py

# 4. Reset and test again
python state-restore.py 2  # Back to Phase 2 failures
```

### Iterative Development

```bash
# Test with small subset first
python state-restore.py 1 --limit 10

# Verify your changes work
# ... test code here ...

# Scale up to full dataset
python state-restore.py 1  # All 601 servers
```

## Architecture

### Two-Tier Approach

**Tier 1: API-Based Scripts**
- Primary method for state management
- Uses NetBox REST API
- Portable and easy to modify
- Reuses existing automation scripts

**Tier 2: Database Snapshots**
- Quick restore for demos
- Exact state preservation
- PostgreSQL dumps
- Instant rollback capability

### Dependencies

Each phase builds on the previous:
- **Phase 1** → Runs Phase 0 first (clean slate)
- **Phase 2** → Runs Phase 1 first (ensures discovery complete)

This ensures consistent state transitions.

## Files

```
state-management/
├── state-phase0.py          # Reset to offline, clear IPs
├── state-phase1.py          # Run Phase 1 automation
├── state-phase2.py          # Run Phase 2 automation
├── state-restore.py         # Universal CLI interface
├── snapshot-save.sh         # Save database snapshot
├── snapshot-restore.sh      # Restore database snapshot
├── snapshots/               # Stored .sql dumps
│   ├── phase-0-*.sql
│   ├── phase-1-*.sql
│   └── phase-2-*.sql
└── README.md                # This file
```

## Environment Variables

The scripts use these environment variables (with defaults):

```bash
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_QUEUE=netbox:bmc:discovered
```

Override if needed:
```bash
export NETBOX_URL=http://netbox.example.com
python state-restore.py 1
```

## Troubleshooting

### Scripts fail with connection errors

Check NetBox and Redis are running:
```bash
docker-compose ps
curl http://localhost:8000/api/
redis-cli -p 6380 ping
```

### Phase 1 shows 0 servers discovered

Check BMC worker is running:
```bash
docker-compose logs -f bmc-worker
```

### Snapshot restore fails

Ensure PostgreSQL container is running:
```bash
docker ps | grep postgres
docker-compose up -d netbox-postgres
```

### State verification shows unexpected results

Wait for workers to process events:
```bash
# Check Redis queue depth
redis-cli -p 6380 llen netbox:bmc:discovered

# Watch worker logs
docker-compose logs -f bmc-worker
```

## Best Practices

1. **Always use snapshots for demos** - Instant reset, no waiting
2. **Test with --limit first** - Verify changes with small subset
3. **Save snapshots before experiments** - Easy rollback if needed
4. **Use --dry-run** - Preview changes before applying
5. **Monitor worker logs** - Catch issues early during state transitions

## Success Criteria

- ✅ Can reset to Phase 0 in < 30 seconds
- ✅ Can advance to Phase 1 in < 2 minutes (601 servers)
- ✅ Can advance to Phase 2 in < 5 minutes (601 servers)
- ✅ Database snapshot restore in < 10 seconds
- ✅ All phase transitions are idempotent (safe to re-run)
- ✅ Clear console output showing state changes

## Next Steps

1. **Create baseline snapshots**:
   ```bash
   python state-restore.py 0 && ./snapshot-save.sh 0
   python state-restore.py 1 && ./snapshot-save.sh 1
   python state-restore.py 2 && ./snapshot-save.sh 2
   ```

2. **Test your workflow**:
   - Use snapshots to quickly jump between phases
   - Develop remediation scripts
   - Test automation sequences

3. **Scale up**:
   - Test with --limit 10, 50, 100
   - Validate performance at full scale (601 servers)
   - Monitor resource usage during transitions
