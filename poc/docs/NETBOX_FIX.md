# NetBox Error Fix - 'NoneType' object has no attribute 'choices'

## Problem

When accessing NetBox devices page (http://localhost:8000/dcim/devices/), you encountered this error:

```
AttributeError: 'NoneType' object has no attribute 'choices'
```

**Root Cause:**
The `lifecycle_state` custom field was created as a `select` type field, but in NetBox 3.7.3, select fields require a separate `CustomFieldChoiceSet` object to define the available choices. The initialization script was trying to set choices directly on the CustomField, which didn't work properly and left `choice_set = None`.

## Solution

### 1. Updated the Initialization Script

**File:** `/Users/gabe/ai/bm/poc/netbox/netbox-init/init_data.py`

**Changes:**
- Added import for `CustomFieldChoiceSet` model
- Created a separate `CustomFieldChoiceSet` object with lifecycle state choices
- Linked the CustomField to the ChoiceSet using the `choice_set` field
- Changed choice format from strings to `[value, label]` pairs as required by NetBox 3.7.3

### 2. Fixed Existing Custom Field

Created and ran a fix script (`fix_lifecycle_field.py`) that:
- Found the existing broken `lifecycle_state` custom field
- Linked it to the newly created `CustomFieldChoiceSet`

## Verification

After the fix, the following now work correctly:

1. **API Access:**
   ```bash
   curl http://localhost:8000/api/dcim/devices/ \
     -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
   ```

2. **Custom Field Query:**
   ```bash
   curl "http://localhost:8000/api/extras/custom-fields/?name=lifecycle_state" \
     -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
   ```

3. **Web Interface:** The devices page should now load without errors

## Lifecycle States Defined

The following lifecycle states are now properly configured:
- `offline` - Initial state (default)
- `planned` - Server planned for deployment
- `validating` - Configuration validation in progress
- `validated` - Configuration validated
- `hardening` - Security hardening in progress
- `staged` - In staging environment
- `ready` - Ready for tenant assignment
- `monitored` - Active monitoring enabled
- `error` - Error state requiring attention

## Prevention

For future NetBox custom field creation with choices:

1. **Always create the ChoiceSet first:**
   ```python
   choice_set = CustomFieldChoiceSet.objects.create(
       name='My Choices',
       extra_choices=[
           ['value1', 'Label 1'],
           ['value2', 'Label 2'],
       ]
   )
   ```

2. **Then link it to the CustomField:**
   ```python
   field = CustomField.objects.create(
       name='my_field',
       type='select',
       choice_set=choice_set,
       ...
   )
   ```

## Files Modified

1. `/Users/gabe/ai/bm/poc/netbox/netbox-init/init_data.py` - Updated initialization script
2. `/Users/gabe/ai/bm/poc/netbox/netbox-init/fix_lifecycle_field.py` - One-time fix script (can be deleted)

## Testing

All custom fields are now working:
```bash
# View all custom fields
curl "http://localhost:8000/api/extras/custom-fields/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"

# View a device with custom fields
curl "http://localhost:8000/api/dcim/devices/1/" \
  -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567"
```

## Status

✅ **RESOLVED** - NetBox is now fully functional with all custom fields properly configured.
