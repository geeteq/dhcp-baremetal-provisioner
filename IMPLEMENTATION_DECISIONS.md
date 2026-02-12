# Implementation Decisions for PoC

**Date**: 2026-02-11
**Status**: Ready to implement

---

## Core Principles

1. **Modular**: Each component is independent and replaceable
2. **Simple**: Use standard library where possible, minimal dependencies
3. **Elegant**: Clean code, clear separation of concerns
4. **Minimal Dependencies**: Avoid heavy frameworks and libraries

---

## Key Decisions

### 1. DHCP Hook Approach ✅
**Decision**: File-based queue for maximum reliability

```
DHCP Hook → /var/log/bm/dhcp_events.log (append-only)
           ↓
Log Tailer → Redis queue (bm:events:dhcp_lease)
```

**Rationale**:
- DHCP daemon never blocks
- Events never lost even if Redis is down
- Simple and battle-tested

### 2. MAC Address Not Found ✅
**Decision**: Log error and skip, no complex fallback

```
MAC not found → Log to /var/log/bm/errors.log → Continue
```

**Rationale**:
- Keeps PoC focused and simple
- Manual intervention acceptable for edge cases
- Easy to enhance later if needed

### 3. Minimal Dependencies ✅
**Decision**: Use Python stdlib where possible

**Only Required Packages**:
```
redis==5.0.1        # Event queue
requests==2.31.0    # HTTP client (NetBox, Redfish)
flask==3.0.0        # Callback API
ansible==9.0.0      # BMC hardening
```

**Avoided**:
- ~~pynetbox~~ → Use `requests` directly
- ~~redfish library~~ → Use `requests` directly
- ~~FastAPI~~ → Use `flask` (lighter)
- ~~APScheduler~~ → Use simple while loop
- ~~RQ/Celery~~ → Use simple queue consumer loops

### 4. Modular Architecture ✅
**Decision**: Each worker is standalone Python script

```
/opt/bm/
├── scripts/
│   ├── dhcp_hook.sh           # Bash script
│   └── validate_server.sh     # Runs in ISO
├── services/
│   ├── dhcp_tailer.py         # Standalone worker
│   ├── discovery_worker.py    # Standalone worker
│   ├── provisioning_worker.py # Standalone worker
│   ├── callback_api.py        # Standalone Flask app
│   ├── hardening_worker.py    # Standalone worker
│   └── monitoring_worker.py   # Standalone worker
├── lib/
│   ├── netbox_client.py       # Shared NetBox helper
│   ├── redfish_client.py      # Shared Redfish helper
│   ├── queue.py               # Shared Redis helper
│   └── logger.py              # Shared logging config
└── config.py                   # Central configuration
```

### 5. Configuration Management ✅
**Decision**: Single Python config file with environment variable overrides

```python
# config.py
import os

# NetBox
NETBOX_URL = os.getenv('NETBOX_URL', 'http://netbox.example.com')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', 'required')

# Redis
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

# iLO
ILO_DEFAULT_USER = os.getenv('ILO_DEFAULT_USER', 'Administrator')
ILO_DEFAULT_PASSWORD = os.getenv('ILO_DEFAULT_PASSWORD', 'required')

# Paths
LOG_DIR = '/var/log/bm'
DHCP_EVENT_LOG = f'{LOG_DIR}/dhcp_events.log'
ERROR_LOG = f'{LOG_DIR}/errors.log'
```

### 6. Logging Strategy ✅
**Decision**: Simple file-based logging, JSON format

```python
# All logs go to /var/log/bm/
# Format: JSON lines for easy parsing
{
  "timestamp": "2026-02-11T10:00:00Z",
  "level": "INFO",
  "service": "discovery-worker",
  "device_id": "uuid",
  "event": "device_discovered",
  "data": {...}
}
```

### 7. Error Handling ✅
**Decision**: Log and continue, no complex retry logic for PoC

```python
try:
    process_event(event)
except Exception as e:
    log_error(e, event)
    # Continue processing next event
```

**Rationale**: Keep it simple, iterate based on real failure modes

### 8. State Machine ✅
**Decision**: NetBox custom fields track state

**States**:
- `racked` → Initial state (manually set)
- `discovered` → After MAC/IP assignment
- `validating` → During PXE boot
- `validated` → After successful validation
- `hardening` → During Ansible execution
- `ready` → Available for assignment
- `monitored` → Actively monitored

### 9. Testing Approach ✅
**Decision**: Manual testing for PoC, add automated tests later

**Test Each Component**:
```bash
# Test DHCP hook
echo "test" >> /var/log/bm/dhcp_events.log

# Test discovery worker
redis-cli LPUSH bm:events:dhcp_lease '{"ip":"10.1.100.50","mac":"aa:bb:cc:dd:ee:ff"}'

# Test API
curl -X POST http://localhost:5000/api/v1/validation/report -d @test_data.json
```

---

## Implementation Order

1. **Setup** (30 min)
   - Create directory structure
   - Install dependencies
   - Create config.py

2. **Shared Libraries** (1 hour)
   - lib/logger.py
   - lib/queue.py
   - lib/netbox_client.py
   - lib/redfish_client.py

3. **DHCP Hook** (1 hour)
   - scripts/dhcp_hook.sh
   - services/dhcp_tailer.py
   - Test manually

4. **Discovery Worker** (2 hours)
   - services/discovery_worker.py
   - Test with mock events

5. **Provisioning Worker** (2 hours)
   - services/provisioning_worker.py
   - Test with real iLO

6. **Callback API** (2 hours)
   - services/callback_api.py
   - Test with curl

7. **Validation ISO** (4 hours)
   - scripts/validate_server.sh
   - Build custom ISO
   - Test PXE boot

8. **Hardening Worker** (2 hours)
   - ansible/bmc_hardening.yml
   - services/hardening_worker.py
   - Test playbook

9. **Monitoring Worker** (2 hours)
   - services/monitoring_worker.py
   - Test metrics collection

10. **Integration Testing** (4 hours)
    - End-to-end test
    - Document issues
    - Iterate

**Total Estimate**: 20-25 hours (3-4 days full-time, 1-2 weeks part-time)

---

## Success Criteria

✅ Server powers on → automatically discovered in NetBox
✅ IP address assigned without manual intervention
✅ PXE boot triggered via Redfish API
✅ Validation data collected and reported
✅ NetBox interfaces updated with LLDP data
✅ Ansible hardening playbook executes successfully
✅ Metrics collected every 5 minutes
✅ Complete audit trail in logs
✅ Zero hardcoded credentials (all from env vars)
✅ All code committed to git

---

## Next Steps

1. Create directory structure
2. Create shared libraries
3. Create workers (one at a time)
4. Test each component individually
5. Integration test
6. Commit to git after each working component

**Ready to start coding!**
