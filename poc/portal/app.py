#!/usr/bin/env python3
"""
Baremetal Services Chatbot Portal
===================================
Flask app that serves an AI-powered chatbot answering sales/availability
questions about baremetal hosting. Claude queries NetBox live via tool_use.
"""

import os
import json
import requests
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

NETBOX_URL = os.environ.get("NETBOX_URL", "http://localhost:8000").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

NETBOX_HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# NetBox helpers
# ---------------------------------------------------------------------------

def nb_get(path, params=None):
    """GET from NetBox API, return parsed JSON or raise."""
    resp = requests.get(
        f"{NETBOX_URL}/api/{path.lstrip('/')}",
        headers=NETBOX_HEADERS,
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_sites_overview():
    """Return all sites with device counts by status."""
    sites_data = nb_get("dcim/sites/", {"limit": 100})
    sites = sites_data.get("results", [])

    result = []
    for site in sites:
        slug = site["slug"]
        counts = {}
        for st in ("active", "planned", "staged", "offline", "inventory", "decommissioning"):
            count_data = nb_get(
                "dcim/devices/",
                {"site": slug, "status": st, "limit": 1},
            )
            counts[st] = count_data.get("count", 0)
        # "available" = planned (procured, not yet deployed) + active (live)
        available = counts.get("planned", 0) + counts.get("active", 0)
        result.append(
            {
                "id": site["id"],
                "name": site["name"],
                "slug": slug,
                "description": site.get("description", ""),
                "device_counts": counts,
                "ready_count": available,
            }
        )
    return result


def get_available_servers(site_slug=None):
    """Return planned/active servers, optionally filtered to one site."""
    params = {"limit": 100}
    if site_slug:
        params["site"] = site_slug
    # Fetch planned (in stock, not yet deployed) and active (live) devices
    servers = []
    total = 0
    for st in ("planned", "active"):
        p = dict(params, status=st)
        data = nb_get("dcim/devices/", p)
        total += data.get("count", 0)
        for d in data.get("results", []):
            servers.append(
                {
                    "name": d["name"],
                    "site": d.get("site", {}).get("name", "Unknown"),
                    "device_type": d.get("device_type", {}).get("display", "Unknown"),
                    "manufacturer": (
                        d.get("device_type", {}).get("manufacturer", {}).get("name", "Unknown")
                    ),
                    "status": d.get("status", {}).get("label", "Unknown"),
                    "rack": d.get("rack", {}).get("name") if d.get("rack") else None,
                    "primary_ip": (
                        d.get("primary_ip", {}).get("address") if d.get("primary_ip") else None
                    ),
                }
            )
    return {"total": total, "servers": servers}



    data = nb_get("dcim/devices/", params)
    devices = data.get("results", [])

    servers = []
    for d in devices:
        servers.append(
            {
                "name": d["name"],
                "site": d.get("site", {}).get("name", "Unknown"),
                "device_type": d.get("device_type", {}).get("display", "Unknown"),
                "manufacturer": (
                    d.get("device_type", {}).get("manufacturer", {}).get("name", "Unknown")
                ),
                "status": d.get("status", {}).get("label", "Unknown"),
                "rack": d.get("rack", {}).get("name") if d.get("rack") else None,
                "primary_ip": (
                    d.get("primary_ip", {}).get("address") if d.get("primary_ip") else None
                ),
            }
        )
    return {"total": data.get("count", 0), "servers": servers}


def get_site_capacity(site_slug):
    """Return rack count and utilization for a site."""
    racks_data = nb_get("dcim/racks/", {"site": site_slug, "limit": 100})
    racks = racks_data.get("results", [])

    rack_list = []
    total_units = 0
    used_units = 0

    for rack in racks:
        rack_id = rack["id"]
        util_data = nb_get(f"dcim/racks/{rack_id}/elevation/", {"limit": 1})
        # elevation returns units; count used from device query instead
        devices_in_rack = nb_get(
            "dcim/devices/", {"rack_id": rack_id, "limit": 1}
        )
        rack_u = rack.get("u_height", 42)
        # approximate used units from device count (rough)
        device_count = devices_in_rack.get("count", 0)

        rack_list.append(
            {
                "name": rack["name"],
                "u_height": rack_u,
                "device_count": device_count,
            }
        )
        total_units += rack_u

    return {
        "site": site_slug,
        "rack_count": len(racks),
        "total_rack_units": total_units,
        "racks": rack_list,
    }


def get_power_capacity(site_slug=None):
    """Return power capacity and utilization from NetBox power feeds."""
    import math

    params = {"limit": 100}
    if site_slug:
        params["site"] = site_slug

    feeds_data = nb_get("dcim/power-feeds/", params)
    feeds = feeds_data.get("results", [])

    def feed_kw(feed):
        v = feed.get("voltage", 0)
        a = feed.get("amperage", 0)
        phase = feed.get("phase", {}).get("value", "single-phase")
        factor = 1.732 if phase == "three-phase" else 1.0
        return round(v * a * factor / 1000, 2)

    # Aggregate by site
    by_site = {}
    for feed in feeds:
        site_name = feed["power_panel"]["name"].split("-", 2)[-1]  # "MDP-A-DC-East" → "DC-East"
        # Get site name from rack if available, fallback to panel name parse
        rack = feed.get("rack")
        s_key = site_name

        if s_key not in by_site:
            by_site[s_key] = {
                "site": s_key,
                "total_feeds": 0,
                "total_kw_rated": 0.0,
                "total_kw_derated": 0.0,
                "racks": {},
                "panels": set(),
            }

        kw = feed_kw(feed)
        max_util = feed.get("max_utilization", 80) / 100
        by_site[s_key]["total_feeds"] += 1
        by_site[s_key]["total_kw_rated"] += kw
        by_site[s_key]["total_kw_derated"] += round(kw * max_util, 2)
        by_site[s_key]["panels"].add(feed["power_panel"]["name"])

        if rack:
            rname = rack["name"]
            if rname not in by_site[s_key]["racks"]:
                by_site[s_key]["racks"][rname] = {"feeds": 0, "kw_rated": 0.0, "kw_derated": 0.0}
            by_site[s_key]["racks"][rname]["feeds"] += 1
            by_site[s_key]["racks"][rname]["kw_rated"] += kw
            by_site[s_key]["racks"][rname]["kw_derated"] += round(kw * max_util, 2)

    # Serialize and round
    result = []
    for site_data in by_site.values():
        racks_list = [
            {
                "rack": k,
                "feeds": v["feeds"],
                "kw_rated": round(v["kw_rated"], 1),
                "kw_derated": round(v["kw_derated"], 1),
            }
            for k, v in sorted(site_data["racks"].items())
        ]
        result.append({
            "site": site_data["site"],
            "panels": sorted(site_data["panels"]),
            "total_feeds": site_data["total_feeds"],
            "total_kw_rated": round(site_data["total_kw_rated"], 1),
            "total_kw_derated": round(site_data["total_kw_derated"], 1),
            "rack_count": len(racks_list),
            "kw_per_rack_rated": round(site_data["total_kw_rated"] / len(racks_list), 1) if racks_list else 0,
            "kw_per_rack_derated": round(site_data["total_kw_derated"] / len(racks_list), 1) if racks_list else 0,
            "racks": racks_list,
        })

    return {
        "sites": result,
        "total_sites": len(result),
        "grand_total_kw_rated": round(sum(s["total_kw_rated"] for s in result), 1),
        "grand_total_kw_derated": round(sum(s["total_kw_derated"] for s in result), 1),
    }


def get_server_types(manufacturer=None):
    """Return available device types (server models), optionally filtered by manufacturer."""
    params = {"limit": 100}
    if manufacturer:
        params["manufacturer"] = manufacturer

    data = nb_get("dcim/device-types/", params)
    types = data.get("results", [])

    result = []
    for dt in types:
        # Get count of available (planned) devices of this type
        count_data = nb_get(
            "dcim/devices/",
            {"device_type_id": dt["id"], "status": "planned", "limit": 1},
        )
        result.append(
            {
                "model": dt["model"],
                "manufacturer": dt.get("manufacturer", {}).get("name", "Unknown"),
                "part_number": dt.get("part_number", ""),
                "u_height": dt.get("u_height", 1),
                "ready_count": count_data.get("count", 0),
            }
        )
    return {"total_types": len(result), "device_types": result}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_sites_overview",
        "description": (
            "Get an overview of all datacenters/sites with device counts by status "
            "(ready, active, staged, offline, failed). Use this to answer questions "
            "about which sites have available capacity, or to list all datacenters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_available_servers",
        "description": (
            "Get the list of servers currently in 'ready' state (available for immediate "
            "deployment). Optionally filter by site slug (e.g. 'dc-toronto'). Returns server "
            "names, types, manufacturers, and locations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_slug": {
                    "type": "string",
                    "description": "Site slug to filter by (e.g. 'dc-toronto', 'dc-vancouver'). Omit for all sites.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_site_capacity",
        "description": (
            "Get rack inventory and capacity details for a specific datacenter. "
            "Use this to answer questions about rack space availability, total rack count, "
            "or how much room is left in a specific site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_slug": {
                    "type": "string",
                    "description": "Site slug (e.g. 'dc-toronto', 'dc-vancouver', 'dc-calgary').",
                }
            },
            "required": ["site_slug"],
        },
    },
    {
        "name": "get_power_capacity",
        "description": (
            "Get power infrastructure capacity from NetBox power feeds. "
            "Returns rated kW, derated (usable) kW, feed count, and per-rack breakdown. "
            "Use this for questions about power availability, how much power is left, "
            "rack power budget, or total datacenter power capacity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site_slug": {
                    "type": "string",
                    "description": "Filter to a specific site (e.g. 'dc-toronto'). Omit for all sites.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_server_types",
        "description": (
            "Get the catalog of server models we stock, with counts of how many are "
            "currently ready/available. Optionally filter by manufacturer name "
            "(e.g. 'HPE', 'Dell'). Use this to answer questions about server specs, "
            "form factors, or 'do you have any 2U servers?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manufacturer": {
                    "type": "string",
                    "description": "Filter by manufacturer name, e.g. 'HPE' or 'Dell'.",
                }
            },
            "required": [],
        },
    },
]


def dispatch_tool(name, tool_input):
    """Execute a tool call and return the result as a string."""
    try:
        if name == "get_sites_overview":
            result = get_sites_overview()
        elif name == "get_available_servers":
            result = get_available_servers(site_slug=tool_input.get("site_slug"))
        elif name == "get_site_capacity":
            result = get_site_capacity(site_slug=tool_input["site_slug"])
        elif name == "get_power_capacity":
            result = get_power_capacity(site_slug=tool_input.get("site_slug"))
        elif name == "get_server_types":
            result = get_server_types(manufacturer=tool_input.get("manufacturer"))
        else:
            result = {"error": f"Unknown tool: {name}"}
        return json.dumps(result)
    except requests.HTTPError as e:
        return json.dumps({"error": f"NetBox API error: {e.response.status_code} {e.response.text[:200]}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful sales and technical assistant for a baremetal server hosting company.
You answer questions about server availability, datacenter capacity, pricing context, and service capabilities.

COMPANY OVERVIEW:
- We provide baremetal (dedicated physical server) hosting — no virtualization, no shared resources
- We operate 6 datacenters across Canada: DC-Toronto, DC-Vancouver, DC-Calgary, DC-Montreal, DC-Edmonton, DC-Ottawa
- We exclusively procure and support HPE ProLiant and Dell PowerEdge servers
- All servers are rack-mounted and connected to enterprise top-of-rack switches

WHAT WE PROVIDE:
- Dedicated baremetal servers (HPE and Dell only)
- Remote BMC access via HPE iLO or Dell iDRAC
- Redfish API telemetry (CPU, memory, power, temperature monitoring)
- Firmware lifecycle management (we keep servers patched)
- BMC hardening via Ansible (security baselines applied before delivery)
- No OS is installed — clients receive raw hardware access via BMC
- Tenant portal showing real-time resource usage from Redfish/Prometheus

WHAT WE DO NOT OFFER:
- Virtualization or VMs (we are baremetal only)
- OS installation or managed OS services
- GPU servers (not in current catalog)
- Networking equipment rental (we cable to our ToR switches; customer uses their own uplinks)

DELIVERY SLA:
- In-stock (ready state) servers: delivered same week after contract signing
- Custom orders (not in stock): 4–6 weeks including procurement, racking, testing, hardening

SERVER LIFECYCLE STATES (in NetBox):
- offline: physically present but not powered on yet
- discovered: BMC detected on network for first time
- staged: being provisioned (firmware updates, hardening in progress)
- active: deployed to a tenant
- ready: fully hardened and available for new tenant assignment
- failed: hardware issue detected, under repair

ALWAYS call the appropriate tool(s) to fetch live data from NetBox before answering
any questions about availability, capacity, or specific server models.

For general service questions (SLAs, capabilities, what we offer), answer from your knowledge above.
Be concise, professional, and helpful. If you don't know something, say so honestly."""


def build_system_with_filter(site_filter=None):
    """Append site filter context to system prompt if provided."""
    if not site_filter:
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + f"\n\nCURRENT CONTEXT: The user has filtered to site '{site_filter}'. "
        "Focus your answers on that specific datacenter unless asked otherwise."
    )


# ---------------------------------------------------------------------------
# Content block serializer (anthropic SDK objects → plain dicts)
# ---------------------------------------------------------------------------

def serialize_content(content):
    """Convert a list of content blocks (SDK objects or dicts) to plain dicts."""
    result = []
    for block in content:
        if isinstance(block, dict):
            result.append(block)
        elif hasattr(block, "type"):
            if block.type == "text":
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
            else:
                result.append({"type": block.type})
        else:
            result.append({"type": "unknown"})
    return result


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sites")
def api_sites():
    """Return sites that have at least one ready server (for sidebar)."""
    try:
        sites = get_sites_overview()
        available = [s for s in sites if s["ready_count"] > 0]
        total_ready = sum(s["ready_count"] for s in sites)
        return jsonify(
            {
                "sites": available,
                "total_ready": total_ready,
                "total_sites": len(sites),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "sites": [], "total_ready": 0, "total_sites": 0}), 200


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Agentic chat loop with Claude tool_use.
    Request body: { messages: [...], site_filter: "dc-toronto" | null }
    Response: { reply: "...", messages: [...] }
    """
    body = request.get_json(force=True)
    messages = body.get("messages", [])
    site_filter = body.get("site_filter") or None

    system = build_system_with_filter(site_filter)

    # Agentic loop: keep calling Claude until stop_reason == "end_turn"
    for _ in range(10):  # safety limit
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Serialize content blocks to plain dicts
        content_blocks = serialize_content(response.content)

        # Append assistant turn to messages
        messages = messages + [{"role": "assistant", "content": content_blocks}]

        if response.stop_reason == "end_turn":
            # Extract final text reply
            reply_text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    reply_text += block["text"]
            return jsonify({"reply": reply_text, "messages": messages})

        if response.stop_reason == "tool_use":
            # Execute all tool calls
            tool_results = []
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    tool_output = dispatch_tool(block["name"], block.get("input", {}))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": tool_output,
                        }
                    )
            # Append user turn with tool results
            messages = messages + [{"role": "user", "content": tool_results}]
            continue

        # Unexpected stop reason
        break

    return jsonify({"reply": "I encountered an issue. Please try again.", "messages": messages})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
