#!/usr/bin/env python3
"""
Update NetBox datacenter sites with Canadian city locations and addresses.
Also prints updated DC_COORDS block to paste into portal/templates/index.html.
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

# Random major Canadian cities assigned to each site
SITE_DATA = {
    "dc-east": {
        "city":             "Toronto, ON",
        "physical_address": "151 Front Street West\nToronto, ON  M5J 2N1\nCanada",
        "description":      "East Region — Toronto, Ontario",
        "latitude":         43.6452,
        "longitude":        -79.3806,
        "time_zone":        "America/Toronto",
    },
    "dc-west": {
        "city":             "Vancouver, BC",
        "physical_address": "555 West Hastings Street\nVancouver, BC  V6B 4N6\nCanada",
        "description":      "West Region — Vancouver, British Columbia",
        "latitude":         49.2827,
        "longitude":        -123.1207,
        "time_zone":        "America/Vancouver",
    },
    "dc-center": {
        "city":             "Calgary, AB",
        "physical_address": "225 11 Avenue SE\nCalgary, AB  T2G 0Y1\nCanada",
        "description":      "Central Region — Calgary, Alberta",
        "latitude":         51.0447,
        "longitude":        -114.0719,
        "time_zone":        "America/Edmonton",
    },
    "dc-chicago": {
        "city":             "Montréal, QC",
        "physical_address": "1000 De La Gauchetière Street West\nMontréal, QC  H3B 4W5\nCanada",
        "description":      "East-Central Region — Montréal, Québec",
        "latitude":         45.4972,
        "longitude":        -73.5679,
        "time_zone":        "America/Toronto",
    },
    "dc-losangeles": {
        "city":             "Edmonton, AB",
        "physical_address": "10020 100 Street NW\nEdmonton, AB  T5J 0N3\nCanada",
        "description":      "Northwest Region — Edmonton, Alberta",
        "latitude":         53.5461,
        "longitude":        -113.4938,
        "time_zone":        "America/Edmonton",
    },
    "dc-newyork": {
        "city":             "Ottawa, ON",
        "physical_address": "100 Queen Street\nOttawa, ON  K1P 1J9\nCanada",
        "description":      "Capital Region — Ottawa, Ontario",
        "latitude":         45.4215,
        "longitude":        -75.6972,
        "time_zone":        "America/Toronto",
    },
}


def get_sites():
    r = requests.get(f"{NETBOX_URL}/api/dcim/sites/?limit=50", headers=HEADERS)
    r.raise_for_status()
    return r.json()["results"]


def update_site(site_id, payload):
    r = requests.patch(
        f"{NETBOX_URL}/api/dcim/sites/{site_id}/",
        headers=HEADERS,
        json=payload,
    )
    r.raise_for_status()
    return r.json()


def main():
    print("=" * 60)
    print("Setting Canadian datacenter locations in NetBox")
    print("=" * 60)

    sites = get_sites()
    updated = []

    for site in sorted(sites, key=lambda s: s["name"]):
        slug = site["slug"]
        data = SITE_DATA.get(slug)
        if not data:
            print(f"  SKIP {site['name']} — no location data defined")
            continue

        payload = {
            "physical_address": data["physical_address"],
            "description":      data["description"],
            "latitude":         data["latitude"],
            "longitude":        data["longitude"],
            "time_zone":        data["time_zone"],
        }

        result = update_site(site["id"], payload)
        print(f"  ✓  {site['name']:20s} → {data['city']}  ({data['latitude']}, {data['longitude']})")
        updated.append((slug, site["name"], data))

    # Print DC_COORDS block for easy copy-paste into index.html
    print("\n" + "=" * 60)
    print("Updated DC_COORDS for portal/templates/index.html:")
    print("=" * 60)
    print("  const DC_COORDS = {")
    for slug, name, data in sorted(updated):
        js_name = name.replace("'", "\\'")
        print(
            f"    '{slug}':{' '*(15-len(slug))}"
            f"{{ lat: {data['latitude']}, lng: {data['longitude']}, "
            f"city: '{data['city']}', name: '{js_name}' }},"
        )
    print("  };")
    print("=" * 60)


if __name__ == "__main__":
    main()
