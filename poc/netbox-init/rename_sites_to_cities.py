#!/usr/bin/env python3
"""
Rename NetBox sites so name and slug match the assigned Canadian city.
"""

import os
import json
import requests

NETBOX_URL   = os.environ.get("NETBOX_URL",   "http://localhost:8000").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "0fedf27ad8bab4f4a3b5fda94a663d4f0bc6c065")
HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}

# old slug → new name/slug/city
RENAMES = {
    "dc-east":       {"name": "DC-Toronto",   "slug": "dc-toronto",   "city": "Toronto"},
    "dc-west":       {"name": "DC-Vancouver", "slug": "dc-vancouver", "city": "Vancouver"},
    "dc-center":     {"name": "DC-Calgary",   "slug": "dc-calgary",   "city": "Calgary"},
    "dc-chicago":    {"name": "DC-Montreal",  "slug": "dc-montreal",  "city": "Montreal"},
    "dc-losangeles": {"name": "DC-Edmonton",  "slug": "dc-edmonton",  "city": "Edmonton"},
    "dc-newyork":    {"name": "DC-Ottawa",    "slug": "dc-ottawa",    "city": "Ottawa"},
}

def main():
    r = requests.get(f"{NETBOX_URL}/api/dcim/sites/?limit=50", headers=HEADERS)
    r.raise_for_status()
    sites = r.json()["results"]

    print("=" * 55)
    print("Renaming NetBox sites to match Canadian cities")
    print("=" * 55)

    mapping = []  # (old_slug, new_slug, new_name) for DC_COORDS update

    for site in sorted(sites, key=lambda s: s["name"]):
        old_slug = site["slug"]
        rename   = RENAMES.get(old_slug)
        if not rename:
            print(f"  SKIP  {site['name']} — not in rename map")
            continue

        resp = requests.patch(
            f"{NETBOX_URL}/api/dcim/sites/{site['id']}/",
            headers=HEADERS,
            json={"name": rename["name"], "slug": rename["slug"]},
        )
        resp.raise_for_status()
        print(f"  ✓  {site['name']:20s} → {rename['name']}  (slug: {rename['slug']})")
        mapping.append((old_slug, rename["slug"], rename["name"], rename["city"]))

    # Print updated DC_COORDS block for portal/templates/index.html
    print("\n" + "=" * 55)
    print("Updated DC_COORDS — paste into index.html:")
    print("=" * 55)

    # Keep city/coord data from the previous run (hardcoded here for convenience)
    coords = {
        "dc-toronto":   {"lat": 43.6452, "lng": -79.3806,  "city": "Toronto, ON"},
        "dc-vancouver": {"lat": 49.2827, "lng": -123.1207, "city": "Vancouver, BC"},
        "dc-calgary":   {"lat": 51.0447, "lng": -114.0719, "city": "Calgary, AB"},
        "dc-montreal":  {"lat": 45.4972, "lng": -73.5679,  "city": "Montréal, QC"},
        "dc-edmonton":  {"lat": 53.5461, "lng": -113.4938, "city": "Edmonton, AB"},
        "dc-ottawa":    {"lat": 45.4215, "lng": -75.6972,  "city": "Ottawa, ON"},
    }

    print("  const DC_COORDS = {")
    for _, new_slug, new_name, _ in sorted(mapping, key=lambda x: x[1]):
        c = coords[new_slug]
        pad = 16 - len(new_slug)
        print(
            f"    '{new_slug}':{' '*pad}"
            f"{{ lat: {c['lat']}, lng: {c['lng']}, "
            f"city: '{c['city']}', name: '{new_name}' }},"
        )
    print("  };")
    print("=" * 55)


if __name__ == "__main__":
    main()
