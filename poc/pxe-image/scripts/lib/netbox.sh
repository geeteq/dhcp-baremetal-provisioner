#!/bin/bash
# NetBox API helpers — read-only queries + journal entry writes only.
# Never PATCHes or PUTs existing objects.

# Load site config if present (test/dev); production gets vars from kernel cmdline via main.sh
[[ -f /etc/bm-validate.conf ]] && source /etc/bm-validate.conf

NETBOX_URL="${NETBOX_URL:-http://10.0.0.1:8000}"
NETBOX_TOKEN="${NETBOX_TOKEN:-}"

# GET /api/<path>  → raw JSON
nb_get() {
    curl -sf --max-time 15 \
        -H "Authorization: Token ${NETBOX_TOKEN}" \
        -H "Accept: application/json" \
        "${NETBOX_URL}/api${1}"
}

# POST /api/<path> with JSON body → raw JSON
nb_post() {
    curl -sf --max-time 15 \
        -X POST \
        -H "Authorization: Token ${NETBOX_TOKEN}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d "${2}" \
        "${NETBOX_URL}/api${1}"
}

# Add a journal entry to a device (the ONLY write operation used).
# Usage: nb_journal <device_id> <kind> <message>
# kind: info | success | warning | danger
nb_journal() {
    local device_id="$1" kind="$2" msg="$3"
    local payload
    payload=$(python3 -c "
import json, sys
print(json.dumps({
    'assigned_object_type': 'dcim.device',
    'assigned_object_id': int(sys.argv[1]),
    'kind': sys.argv[2],
    'comments': sys.argv[3],
}))" "$device_id" "$kind" "$msg")
    nb_post "/extras/journal-entries/" "$payload" > /dev/null
}

# Resolve device from NetBox by system serial number (dmidecode).
# Sets globals: DEVICE_ID, DEVICE_NAME, DEVICE_SITE
# Returns 0 on found, 1 on not found or empty serial.
nb_find_device_by_serial() {
    local serial="$1"
    [[ -z "$serial" || "$serial" == "Not Specified" || "$serial" == "To Be Filled By O.E.M." ]] && return 1

    local result count
    result=$(nb_get "/dcim/devices/?serial=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$serial")&limit=1")
    count=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)

    if [[ "${count}" -gt 0 ]]; then
        DEVICE_ID=$(echo "$result"   | python3 -c "import json,sys; print(json.load(sys.stdin)['results'][0]['id'])")
        DEVICE_NAME=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin)['results'][0]['name'])")
        DEVICE_SITE=$(echo "$result" | python3 -c "
import json,sys
d=json.load(sys.stdin)['results'][0]
print((d.get('site') or {}).get('name','unknown'))")
        export DEVICE_ID DEVICE_NAME DEVICE_SITE
        return 0
    fi
    return 1
}

# Resolve device ID from any of this host's MAC addresses (fallback).
# Sets globals: DEVICE_ID, DEVICE_NAME, DEVICE_SITE
nb_find_device_by_mac() {
    for iface_path in /sys/class/net/*; do
        local iface mac result count
        iface=$(basename "$iface_path")
        mac=$(cat "${iface_path}/address" 2>/dev/null | tr '[:lower:]' '[:upper:]')
        [[ "$mac" == "00:00:00:00:00:00" ]] && continue
        [[ "$iface" == "lo" ]] && continue

        result=$(nb_get "/dcim/interfaces/?mac_address=${mac}&limit=1")
        count=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)

        if [[ "${count}" -gt 0 ]]; then
            DEVICE_ID=$(echo "$result" | python3 -c "
import json,sys
d=json.load(sys.stdin)['results'][0]['device']
print(d['id'])")
            DEVICE_NAME=$(echo "$result" | python3 -c "
import json,sys
d=json.load(sys.stdin)['results'][0]['device']
print(d['name'])")
            DEVICE_SITE=$(nb_get "/dcim/devices/${DEVICE_ID}/" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print((d.get('site') or {}).get('name','unknown'))")
            export DEVICE_ID DEVICE_NAME DEVICE_SITE
            return 0
        fi
    done
    return 1
}
