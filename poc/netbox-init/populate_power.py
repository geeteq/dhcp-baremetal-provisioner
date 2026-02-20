#!/usr/bin/env python3
"""
Populate NetBox with power infrastructure.

Architecture per datacenter (1MW total, PUE 1.4 → ~715kW IT load):
  - 2× Main Distribution Panels (MDP-A, MDP-B) at 500kW each
  - Per rack: 2× power feeds (A+B redundancy)
    - 208V 3-phase, 34A each → 12.2kW per feed → 24.4kW per rack
  - 12 racks × 24kW = 288kW IT load (40% of 715kW capacity)

Run:
  NETBOX_URL=http://localhost:8000 NETBOX_TOKEN=<token> python3 populate_power.py
"""

import os
import sys
import json
import requests

NETBOX_URL = os.environ.get("NETBOX_URL", "http://localhost:8000").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "0fedf27ad8bab4f4a3b5fda94a663d4f0bc6c065")

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# 208V 3-phase 34A = ~12.2kW per feed; 2 feeds per rack = ~24.4kW
FEED_VOLTAGE    = 208
FEED_AMPERAGE   = 34       # amps
FEED_PHASE      = "three-phase"
FEED_SUPPLY     = "ac"
FEED_MAX_UTIL   = 80       # % — derate to 80% = ~9.8kW usable per feed → ~19.6kW, headroom for bursts
PANEL_KW        = 500      # kW per main panel (A and B = 1MW total)


def nb_get(path, params=None):
    r = requests.get(f"{NETBOX_URL}/api/{path.lstrip('/')}", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()


def nb_post(path, data):
    r = requests.post(f"{NETBOX_URL}/api/{path.lstrip('/')}", headers=HEADERS, json=data)
    if r.status_code == 400:
        # May already exist — return None so caller can skip
        print(f"    SKIP (already exists or bad request): {r.text[:120]}")
        return None
    r.raise_for_status()
    return r.json()


def get_all(path, params=None):
    results = []
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    p = dict(params or {}, limit=100, offset=0)
    while url:
        r = requests.get(url, headers=HEADERS, params=p)
        r.raise_for_status()
        d = r.json()
        results.extend(d["results"])
        url = d["next"]
        p = None  # next URL already has params
    return results


def ensure_power_panel(site_id, site_name, label):
    """Create a power panel if it doesn't exist; return its id."""
    name = f"{label}"
    existing = nb_get("dcim/power-panels/", {"site_id": site_id, "q": name})
    for p in existing.get("results", []):
        if p["name"] == name:
            print(f"    Panel exists: {name} (id={p['id']})")
            return p["id"]

    result = nb_post("dcim/power-panels/", {
        "site": site_id,
        "name": name,
        "comments": f"Main Distribution Panel — {PANEL_KW}kW, {site_name}",
    })
    if result:
        print(f"    Created panel: {name} (id={result['id']})")
        return result["id"]
    return None


def ensure_power_feed(rack_id, rack_name, panel_id, feed_label):
    """Create a power feed for a rack if it doesn't exist."""
    name = f"{rack_name}-{feed_label}"
    existing = nb_get("dcim/power-feeds/", {"rack_id": rack_id, "q": name})
    for f in existing.get("results", []):
        if f["name"] == name:
            print(f"      Feed exists: {name}")
            return f["id"]

    result = nb_post("dcim/power-feeds/", {
        "power_panel": panel_id,
        "rack": rack_id,
        "name": name,
        "supply": FEED_SUPPLY,
        "phase": FEED_PHASE,
        "voltage": FEED_VOLTAGE,
        "amperage": FEED_AMPERAGE,
        "max_utilization": FEED_MAX_UTIL,
        "status": "active",
        "comments": (
            f"Feed {feed_label} to {rack_name} — "
            f"{FEED_VOLTAGE}V {FEED_PHASE} {FEED_AMPERAGE}A "
            f"(~{round(FEED_VOLTAGE * FEED_AMPERAGE * 1.732 / 1000, 1)}kW)"
        ),
    })
    if result:
        kw = round(FEED_VOLTAGE * FEED_AMPERAGE * 1.732 / 1000, 1)
        print(f"      Created feed: {name}  [{FEED_VOLTAGE}V 3φ {FEED_AMPERAGE}A = {kw}kW]")
        return result["id"]
    return None


def main():
    print("=" * 60)
    print("NetBox Power Infrastructure Population")
    print(f"  {FEED_VOLTAGE}V 3-phase {FEED_AMPERAGE}A per feed")
    kw_per_feed = round(FEED_VOLTAGE * FEED_AMPERAGE * 1.732 / 1000, 1)
    print(f"  {kw_per_feed}kW per feed × 2 feeds = {kw_per_feed*2}kW per rack")
    print(f"  Panel capacity: {PANEL_KW}kW each (A+B = {PANEL_KW*2}kW total)")
    print("=" * 60)

    # Get all sites
    sites = get_all("dcim/sites/")
    print(f"\nFound {len(sites)} sites")

    # Get all racks grouped by site
    racks = get_all("dcim/racks/")
    from collections import defaultdict
    racks_by_site = defaultdict(list)
    for rack in racks:
        racks_by_site[rack["site"]["id"]].append(rack)

    for site in sorted(sites, key=lambda s: s["name"]):
        site_id   = site["id"]
        site_name = site["name"]
        site_racks = racks_by_site.get(site_id, [])

        print(f"\n{'─'*60}")
        print(f"Site: {site_name}  ({len(site_racks)} racks)")

        # Create MDP-A and MDP-B
        print(f"  Creating power panels...")
        panel_a_id = ensure_power_panel(site_id, site_name, f"MDP-A-{site_name}")
        panel_b_id = ensure_power_panel(site_id, site_name, f"MDP-B-{site_name}")

        if not site_racks:
            print(f"  No racks — skipping feeds")
            continue

        print(f"  Creating power feeds ({len(site_racks)} racks × 2 feeds)...")
        for rack in sorted(site_racks, key=lambda r: r["name"]):
            rack_id   = rack["id"]
            rack_name = rack["name"]
            ensure_power_feed(rack_id, rack_name, panel_a_id, "FEED-A")
            ensure_power_feed(rack_id, rack_name, panel_b_id, "FEED-B")

    # Summary
    print(f"\n{'='*60}")
    total_feeds = nb_get("dcim/power-feeds/", {"limit": 1}).get("count", 0)
    total_panels = nb_get("dcim/power-panels/", {"limit": 1}).get("count", 0)
    print(f"Done.")
    print(f"  Power panels : {total_panels}")
    print(f"  Power feeds  : {total_feeds}")
    print(f"  Per-rack kW  : {kw_per_feed*2}kW ({kw_per_feed}kW A + {kw_per_feed}kW B)")
    rack_count = len(racks)
    print(f"  Total IT load: {rack_count} racks × {kw_per_feed*2}kW = {rack_count * kw_per_feed*2:.0f}kW")
    print(f"  Site budget  : {PANEL_KW*2}kW (1MW) — PUE 1.4 → {round(PANEL_KW*2/1.4)}kW IT")
    print("=" * 60)


if __name__ == "__main__":
    main()
