# DHCP Baremetal Provisioner

An event-driven automation pipeline for baremetal server provisioning — from physical rack installation through tenant delivery. When a server BMC powers on and requests a DHCP lease, this system automatically discovers it, validates its physical configuration, hardens it, and transitions it through a full lifecycle tracked in NetBox.

## What It Does

```
Server Racked
     │
     ▼
BMC Powers On ──► DHCP Lease ──► Redis Event ──► NetBox Discovery
                                                        │
                                               lifecycle: offline
                                                        │
                                                        ▼
                                               lifecycle: discovered
                                                        │
                                               PXE Boot / Validation
                                               (LLDP, port mapping)
                                                        │
                                                        ▼
                                               lifecycle: provisioning
                                                        │
                                               Ansible BMC Hardening
                                               Firmware Updates
                                                        │
                                                        ▼
                                               lifecycle: ready
                                                        │
                                               Assign to Tenant
                                                        │
                                                        ▼
                                               lifecycle: active
```

No manual steps between rack and ready. Each stage is triggered automatically by the previous one via a Redis event bus.

## Business Context

This system supports a baremetal hosting operation across 5 datacenters. It handles:

- Procurement of HPE and Dell servers
- Physical installation and cabling documentation (NetBox DCIM)
- Automated discovery via DHCP BMC lease hooks
- Vendor tool provisioning (HPE OneView, Dell OpenManage)
- BMC hardening via Ansible
- Hardware monitoring via Redfish API → Prometheus → Grafana
- Tenant portal with per-server usage metrics
- Warranty tracking and hardware failure ticketing (Jira)
- Decommission planning with consolidation calculator

## Architecture

### Event Bus

Redis acts as the message broker. Each lifecycle stage publishes an event that triggers the next worker:

| Queue | Published by | Consumed by |
|-------|-------------|-------------|
| `netbox:bmc:discovered` | DHCP hook | BMC worker |
| `netbox:server:validated` | Validation callback | Hardening worker |
| `netbox:server:hardened` | Hardening worker | Monitoring worker |
| `netbox:server:ready` | Monitoring worker | Tenant assignment |

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| DHCP lease hook | `dhcp-integration/dhcp-lease-hook.sh` | Fires on DHCP commit, publishes BMC MAC + IP to Redis |
| BMC worker | `dhcp-integration/netbox-bmc-worker.py` | Looks up device by MAC, assigns IP, transitions state in NetBox |
| Status dashboard | `dhcp-integration/status-dashboard/` | Real-time web UI showing per-server lifecycle timeline |
| NetBox init scripts | `netbox-init/` | Populates infrastructure (sites, racks, devices, IP ranges) |
| Ansible hardening | `ansible/bmc_hardening.yml` | BMC security hardening playbook |
| Shared libs | `lib/` | NetBox client, Redfish client, Redis queue, JSON logger |
| Services | `services/` | Discovery, provisioning, callback API, hardening, monitoring workers |

### Tech Stack

- **Event bus**: Redis
- **DCIM**: NetBox 3.7.3
- **Automation**: Ansible
- **BMC APIs**: HPE iLO via Redfish, Dell iDRAC via Redfish
- **Vendor tools**: HPE OneView, Dell OpenManage
- **Provisioning**: Canonical MaaS (PXE)
- **Monitoring**: Prometheus + Grafana
- **Ticketing**: Jira
- **Language**: Python 3.11+
- **Containerization**: Docker / Docker Compose

## Repository Structure

```
.
├── dhcp-integration/          # DHCP-triggered BMC discovery pipeline
│   ├── dhcp-lease-hook.sh     # DHCP server hook (fires on lease commit)
│   ├── netbox-bmc-worker.py   # Redis consumer → NetBox updater
│   ├── status-dashboard/      # Real-time lifecycle timeline UI
│   ├── state-management/      # Lifecycle state transition logic
│   ├── docker-compose.yml     # Worker + Redis stack
│   ├── QUICKSTART.md
│   └── PHASE1-GUIDE.md
│
├── netbox/                    # NetBox Docker setup
│   ├── docker-compose.netbox.yml
│   ├── netbox-config/
│   └── netbox-init/           # Data initialization scripts
│
├── netbox-init/               # Infrastructure population scripts
│   ├── populate_infrastructure.py
│   ├── create_infrastructure_final.py
│   └── export_mac_addresses.py
│
├── services/                  # Python worker services
│   ├── dhcp_tailer.py         # Tails DHCP log → Redis
│   ├── discovery_worker.py    # Device discovery
│   ├── provisioning_worker.py # PXE boot trigger
│   ├── callback_api.py        # Validation result receiver
│   ├── hardening_worker.py    # Ansible BMC hardening
│   └── monitoring_worker.py   # Redfish metrics collection
│
├── lib/                       # Shared libraries
│   ├── netbox_client.py       # NetBox REST API wrapper
│   ├── redfish_client.py      # HPE iLO / Dell iDRAC Redfish client
│   ├── queue.py               # Redis queue wrapper
│   └── logger.py              # Structured JSON logger
│
├── ansible/
│   └── bmc_hardening.yml      # BMC security hardening playbook
│
├── pki/                       # mTLS certificates (keys excluded from repo)
├── scripts/                   # Shell utilities
├── docs/                      # Additional documentation
├── config.py                  # Central configuration
├── docker-compose.yml         # Full stack compose file
└── PHASES.md                  # Implementation phases and roadmap
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- NetBox 3.7.3+ (see `netbox/NETBOX_SETUP.md`)
- Redis 5.0+
- ISC DHCP server or dnsmasq (on your network)
- NetBox API token

### Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your NetBox URL, token, and iLO credentials

# 2. Start NetBox (if not already running)
cd netbox
docker compose -f docker-compose.netbox.yml up -d

# 3. Populate infrastructure data
python3 netbox-init/populate_infrastructure.py

# 4. Start the DHCP integration stack
cd dhcp-integration
docker compose up -d

# 5. Watch the logs
docker compose logs -f bmc-worker
```

See `dhcp-integration/QUICKSTART.md` for a full walkthrough including test simulation.

### Simulate a Server Discovery (no real hardware needed)

```bash
cd dhcp-integration

# Inject a fake DHCP event into Redis
./test-bmc-discovery.sh A0:36:9F:01:00:00 10.0.100.50

# Watch the worker process it
docker compose logs -f bmc-worker
```

## Lifecycle States

| State | Meaning |
|-------|---------|
| `offline` | Exists in NetBox, not yet seen on network |
| `discovered` | BMC detected via DHCP lease |
| `provisioning` | PXE validation and firmware updates in progress |
| `ready` | Hardened and validated, available for tenant assignment |
| `active` | Assigned to a tenant, in production |

All transitions are logged as journal entries in NetBox for a full audit trail.

## Supported Hardware

| Vendor | BMC | OUI Prefix |
|--------|-----|-----------|
| HPE ProLiant | iLO | `A0:36:9F` |
| Dell PowerEdge | iDRAC | `D0:67:E5`, `14:18:77` |
| Supermicro | IPMI | `18:FB:7B` |

## Roadmap

See `PHASES.md` for the detailed implementation plan.

- **Phase 0** — Reset server to initial state
- **Phase 1** — DHCP discovery, NetBox state transition, journal logging *(complete)*
- **Phase 2** — PXE boot, LLDP validation, port assignment
- **Phase 3** — Firmware updates via HPE OneView / Dell OpenManage
- **Phase 4** — Ansible BMC hardening
- **Phase 5** — Prometheus metrics via Redfish, Grafana dashboards
- **Phase 6** — Tenant portal, warranty tracking, Jira integration
- **Phase 7** — Decommission workflow and consolidation calculator

## Documentation

- `dhcp-integration/PHASE1-GUIDE.md` — Phase 1 detailed guide and journal logging
- `dhcp-integration/QUICKSTART.md` — Quick start for DHCP integration
- `netbox/NETBOX_SETUP.md` — NetBox installation and configuration
- `docs/PKI.md` — mTLS certificate setup
- `docs/redis_install.md` — Redis installation guide
- `DOCKER.md` — Docker deployment guide
