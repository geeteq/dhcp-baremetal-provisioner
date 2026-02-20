#!/usr/bin/env python3
"""
Baremetal Server Lifecycle Simulator
=====================================
Simulates the full provisioning pipeline for 100 servers per DC across
3 datacenters (East/West/Central).

Usage:
  python simulate_lifecycle.py --reset          # Reset all to ordered (planned/offline)
  python simulate_lifecycle.py --phase 1        # Show ordered state
  python simulate_lifecycle.py --phase 2        # Receive & rack (staged/discovered)
  python simulate_lifecycle.py --phase 3        # Staging (staged/provisioning)
  python simulate_lifecycle.py --phase 4        # Available (active/ready)
  python simulate_lifecycle.py --phase all      # Run all phases sequentially
"""

import os
import sys
import time
import random
import string
import argparse
from datetime import date, timedelta

import requests

# ─── Config ────────────────────────────────────────────────────────────────

NETBOX_URL   = os.getenv("NETBOX_URL",   "http://localhost:8000").rstrip("/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "0fedf27ad8bab4f4a3b5fda94a663d4f0bc6c065")
HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}

SERVERS_PER_DC = 100

DCS = [
    {"name": "DC-Toronto",   "slug": "dc-toronto",   "prefix": "EAST", "bmc_prefix": "10.55.3", "tenant": "baremetal-staging"},
    {"name": "DC-Vancouver", "slug": "dc-vancouver",  "prefix": "WEST", "bmc_prefix": "10.55.6", "tenant": "baremetal-staging"},
    {"name": "DC-Calgary",   "slug": "dc-calgary",   "prefix": "CENT", "bmc_prefix": "10.55.1", "tenant": "baremetal-staging"},
]

# ─── Colour helpers ────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
CYAN   = "\033[36m"
RED    = "\033[31m"
GREY   = "\033[90m"

def banner(text, colour=BOLD):
    width = 60
    print(f"\n{colour}{'═' * width}{RESET}")
    print(f"{colour}  {text}{RESET}")
    print(f"{colour}{'═' * width}{RESET}")

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def info(msg): print(f"  {BLUE}ℹ{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def step(msg): print(f"\n{CYAN}{BOLD}{msg}{RESET}")

# ─── NetBox helpers ────────────────────────────────────────────────────────

def get(path, params=None):
    r = requests.get(f"{NETBOX_URL}/api{path}", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def patch(path, data):
    r = requests.patch(f"{NETBOX_URL}/api{path}", headers=HEADERS, json=data)
    r.raise_for_status()
    return r.json()

def post(path, data):
    r = requests.post(f"{NETBOX_URL}/api{path}", headers=HEADERS, json=data)
    r.raise_for_status()
    return r.json()

def get_tenant_id(slug):
    result = get("/tenancy/tenants/", {"slug": slug})
    if result["results"]:
        return result["results"][0]["id"]
    return None

def get_servers(site_slug, limit=200):
    """Return servers for a site, sorted by name, limited to SERVERS_PER_DC."""
    result = get("/dcim/devices/", {
        "site":        site_slug,
        "device_type": "hpe-dl360-gen11",
        "limit":       limit,
    })
    servers = sorted(result["results"], key=lambda d: d["name"])
    return servers[:SERVERS_PER_DC]

# ─── Serial / asset generation ─────────────────────────────────────────────

def make_serial(prefix="HPE"):
    """Generate a realistic HPE server serial number."""
    chars = string.ascii_uppercase + string.digits
    return prefix + "".join(random.choices(chars, k=10))

def make_asset_tag(dc_prefix, index):
    return f"BM-{dc_prefix}-{index:04d}"

def make_mac():
    """Generate a random MAC address."""
    return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))

# ─── Phase 1: Order ────────────────────────────────────────────────────────

def phase_1_order():
    banner("PHASE 1 — ORDER", BLUE)
    print(f"\n  Status: {BOLD}planned{RESET}  |  Lifecycle: {BOLD}offline{RESET}")
    print(f"  Servers have been ordered from HPE.")
    print(f"  Awaiting delivery to datacenter.")
    print()
    total = 0
    for dc in DCS:
        servers = get_servers(dc["slug"])
        ordered  = [s for s in servers if s["status"]["value"] == "planned"]
        received = [s for s in servers if s["status"]["value"] != "planned"]
        info(f"{dc['name']:15s} {len(servers):3d} servers  "
             f"({YELLOW}{len(ordered)} ordered{RESET}  "
             f"{GREEN}{len(received)} in-house{RESET})")
        total += len(servers)
    print()
    info(f"Total batch: {total} servers across {len(DCS)} datacenters")

# ─── Phase 2: Receive & Rack ───────────────────────────────────────────────

def phase_2_receive():
    banner("PHASE 2 — RECEIVE & RACK", YELLOW)
    print(f"\n  Status: {BOLD}planned → staged{RESET}  |  Lifecycle: {BOLD}offline → discovered{RESET}")
    print(f"  Onsite tech receives hardware, racks servers,")
    print(f"  powers them on, and verifies BMC connectivity.\n")

    today = date.today()
    staging_tenant_id = get_tenant_id("baremetal-staging")

    for dc in DCS:
        step(f"Processing {dc['name']}…")
        servers = get_servers(dc["slug"])
        planned = [s for s in servers if s["status"]["value"] == "planned"]

        if not planned:
            warn(f"No planned servers in {dc['name']} — already received?")
            continue

        for i, srv in enumerate(planned, start=1):
            idx = int(srv["name"].split("-")[-1])
            serial = make_serial()
            asset  = make_asset_tag(dc["prefix"], idx)

            patch(f"/dcim/devices/{srv['id']}/", {
                "status":     "staged",
                "serial":     serial,
                "asset_tag":  asset,
                "tenant":     staging_tenant_id,
                "custom_fields": {
                    "lifecycle_state": "discovered",
                    "discovered_at":   str(today),
                },
            })

            if i <= 3 or i == len(planned):
                ok(f"{srv['name']:18s}  serial={serial}  asset={asset}")
            elif i == 4:
                print(f"  {GREY}  … ({len(planned) - 3} more){RESET}")

        ok(f"  {dc['name']}: {len(planned)} servers received and racked")

# ─── Phase 3: Stage ────────────────────────────────────────────────────────

def phase_3_stage():
    banner("PHASE 3 — STAGING", CYAN)
    print(f"\n  Status: {BOLD}staged{RESET}  |  Lifecycle: {BOLD}discovered → provisioning{RESET}")
    print(f"  DHCP triggers PXE boot. LLDP validates switch connectivity.")
    print(f"  Firmware updates applied. Ansible BMC hardening runs.\n")

    today      = date.today()
    discovered = "discovered"

    for dc in DCS:
        step(f"Processing {dc['name']}…")
        servers = get_servers(dc["slug"])
        to_stage = [
            s for s in servers
            if s["status"]["value"] == "staged"
            and s["custom_fields"].get("lifecycle_state") == discovered
        ]

        if not to_stage:
            warn(f"No discovered/staged servers in {dc['name']} — run phase 2 first?")
            continue

        for i, srv in enumerate(to_stage, start=1):
            patch(f"/dcim/devices/{srv['id']}/", {
                "custom_fields": {
                    "lifecycle_state":       "provisioning",
                    "pxe_boot_initiated_at": str(today),
                },
            })

            if i <= 3 or i == len(to_stage):
                ok(f"{srv['name']:18s}  PXE booted  firmware updated  BMC hardened")
            elif i == 4:
                print(f"  {GREY}  … ({len(to_stage) - 3} more){RESET}")

        ok(f"  {dc['name']}: {len(to_stage)} servers staged")

# ─── Phase 4: Available ────────────────────────────────────────────────────

def phase_4_available():
    banner("PHASE 4 — AVAILABLE", GREEN)
    print(f"\n  Status: {BOLD}staged → active{RESET}  |  Lifecycle: {BOLD}provisioning → ready{RESET}")
    print(f"  All checks passed. Servers marked active and")
    print(f"  ready for tenant assignment.\n")

    today = date.today()

    for dc in DCS:
        step(f"Processing {dc['name']}…")
        servers = get_servers(dc["slug"])
        to_activate = [
            s for s in servers
            if s["status"]["value"] == "staged"
            and s["custom_fields"].get("lifecycle_state") == "provisioning"
        ]

        if not to_activate:
            warn(f"No provisioning servers in {dc['name']} — run phase 3 first?")
            continue

        for i, srv in enumerate(to_activate, start=1):
            patch(f"/dcim/devices/{srv['id']}/", {
                "status": "active",
                "custom_fields": {
                    "lifecycle_state": "ready",
                    "hardened_at":     str(today),
                },
            })

            if i <= 3 or i == len(to_activate):
                ok(f"{srv['name']:18s}  {GREEN}ACTIVE — ready for tenant{RESET}")
            elif i == 4:
                print(f"  {GREY}  … ({len(to_activate) - 3} more){RESET}")

        ok(f"  {dc['name']}: {len(to_activate)} servers now ACTIVE")

    print()
    banner("SIMULATION COMPLETE", GREEN)
    total = sum(
        len([s for s in get_servers(dc["slug"]) if s["status"]["value"] == "active"])
        for dc in DCS
    )
    print(f"\n  {GREEN}{BOLD}{total} servers available across {len(DCS)} Canadian datacenters{RESET}")
    print(f"  Tenants can now be assigned via NetBox or the chatbot portal.\n")

# ─── Reset ─────────────────────────────────────────────────────────────────

def reset_all():
    banner("RESET — Returning servers to ORDERED state", RED)
    print(f"\n  Status: → {BOLD}planned{RESET}  |  Lifecycle: → {BOLD}offline{RESET}")
    print(f"  Clears: serial, asset_tag, tenant, lifecycle dates\n")

    for dc in DCS:
        step(f"Resetting {dc['name']}…")
        servers = get_servers(dc["slug"])

        for srv in servers:
            patch(f"/dcim/devices/{srv['id']}/", {
                "status":     "planned",
                "serial":     "",
                "asset_tag":  None,
                "tenant":     None,
                "custom_fields": {
                    "lifecycle_state":       "offline",
                    "discovered_at":         None,
                    "pxe_boot_initiated_at": None,
                    "hardened_at":           None,
                    "last_monitored_at":     None,
                    "last_power_watts":      None,
                },
            })

        ok(f"{dc['name']}: {len(servers)} servers reset to planned/offline")

# ─── Summary ───────────────────────────────────────────────────────────────

def show_summary():
    banner("CURRENT STATE SUMMARY", BOLD)
    print()
    for dc in DCS:
        servers = get_servers(dc["slug"])
        by_status = {}
        by_lc = {}
        for s in servers:
            st = s["status"]["value"]
            lc = s["custom_fields"].get("lifecycle_state") or "offline"
            by_status[st] = by_status.get(st, 0) + 1
            by_lc[lc] = by_lc.get(lc, 0) + 1
        print(f"  {BOLD}{dc['name']:15s}{RESET}  {len(servers)} servers")
        for st, n in sorted(by_status.items()):
            print(f"    NetBox status: {st:10s} × {n}")
        for lc, n in sorted(by_lc.items()):
            print(f"    Lifecycle:     {lc:12s} × {n}")
        print()

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Baremetal server lifecycle simulator")
    ap.add_argument("--phase",  choices=["1", "2", "3", "4", "all"], help="Lifecycle phase to run")
    ap.add_argument("--reset",  action="store_true",                  help="Reset servers to ordered state")
    ap.add_argument("--status", action="store_true",                  help="Show current state summary")
    args = ap.parse_args()

    if args.reset:
        reset_all()
        show_summary()
    elif args.status:
        show_summary()
    elif args.phase == "1":
        phase_1_order()
    elif args.phase == "2":
        phase_2_receive()
        show_summary()
    elif args.phase == "3":
        phase_3_stage()
        show_summary()
    elif args.phase == "4":
        phase_4_available()
    elif args.phase == "all":
        print(f"\n{BOLD}Running full lifecycle simulation…{RESET}")
        phase_1_order()
        input(f"\n  {YELLOW}Press Enter to advance to Phase 2 (Receive & Rack)…{RESET}")
        phase_2_receive()
        input(f"\n  {YELLOW}Press Enter to advance to Phase 3 (Staging)…{RESET}")
        phase_3_stage()
        input(f"\n  {YELLOW}Press Enter to advance to Phase 4 (Available)…{RESET}")
        phase_4_available()
    else:
        ap.print_help()
        print()
        show_summary()


if __name__ == "__main__":
    main()
