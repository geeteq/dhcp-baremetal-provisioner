# Dashboard Fix Summary

## Issue
The web dashboard on port 5001 was failing with the error:
```
TypeError: Object of type Undefined is not JSON serializable
```

## Root Cause
There were two mismatches between the Flask app (`app.py`) and the HTML template (`templates/index.html`):

1. **Template variable name mismatch**:
   - Template expected: `lifecycle_states`
   - App was passing: `device_statuses`
   - This caused Jinja2 `Undefined` objects to be serialized to JSON

2. **Missing field in API response**:
   - Template JavaScript expected: `device.lifecycle_state`
   - API was only returning: `device.status`
   - This caused JavaScript errors when filtering and rendering devices

## Fixes Applied

### Fix 1: Corrected template variable name
**File**: `app.py` (line 131)

**Before**:
```python
return render_template('index.html', device_statuses=DEVICE_STATUSES)
```

**After**:
```python
return render_template('index.html', lifecycle_states=DEVICE_STATUSES)
```

### Fix 2: Added lifecycle_state to API response
**File**: `app.py` (lines 136-160)

**Before**:
```python
device_data = {
    'id': device['id'],
    'name': device['name'],
    'site': device['site']['name'] if device.get('site') else 'Unknown',
    'status': status,
    'primary_ip': device.get('primary_ip4', {}).get('address', None) if device.get('primary_ip4') else None,
}
```

**After**:
```python
lifecycle_state = device.get('custom_fields', {}).get('lifecycle_state', status)

device_data = {
    'id': device['id'],
    'name': device['name'],
    'site': device['site']['name'] if device.get('site') else 'Unknown',
    'status': status,
    'lifecycle_state': lifecycle_state or status,
    'primary_ip': device.get('primary_ip4', {}).get('address', None) if device.get('primary_ip4') else None,
}
```

## Verification

All dashboard endpoints are now working correctly:

1. **Main Page**: `http://localhost:5001/` ✓
2. **Devices API**: `http://localhost:5001/api/devices` ✓
3. **Stats API**: `http://localhost:5001/api/stats` ✓
4. **Queue API**: `http://localhost:5001/api/queue` ✓

## Dashboard Features

The dashboard now provides:

- **Real-time server monitoring**: Auto-refreshes every 5 seconds
- **Timeline visualization**: Shows device lifecycle progression
- **Filtering**: By site, state, or device name
- **Statistics**: Total devices, queue length, counts by state
- **Queue monitoring**: Shows pending events in Redis queue

## Access

Open in your browser:
```
http://localhost:5001/
```

## Running the Dashboard

### Option 1: Direct Python
```bash
cd dhcp-integration/status-dashboard
python3 app.py
```

### Option 2: Docker Compose
```bash
cd dhcp-integration/status-dashboard
docker-compose up -d
```

## Current Status

✓ Dashboard is running and functional
✓ All API endpoints returning HTTP 200
✓ Auto-refresh working (5-second intervals)
✓ Device data includes both `status` and `lifecycle_state` fields
✓ Template rendering correctly with lifecycle states

## Notes

- The dashboard monitors the NetBox device status field
- Lifecycle states come from the `lifecycle_state` custom field in NetBox
- If `lifecycle_state` is not set, it falls back to the device `status`
- The dashboard filters for devices with "server" in their role name
