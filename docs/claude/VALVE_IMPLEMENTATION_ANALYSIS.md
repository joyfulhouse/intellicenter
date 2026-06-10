# Valve Control Implementation Analysis

## Executive Summary

**YES, valve control is feasible!** The IntelliCenter integration already has VALVE object type definitions and attributes in the codebase. Based on my analysis of the JSON protocol and existing code patterns, implementing valve control is straightforward.

## Current State

### VALVE Object Type Already Defined

The integration already has comprehensive VALVE definitions in `custom_components/intellicenter/pyintellicenter/attributes.py`:

```python
VALVE_ATTRIBUTES = {
    "ASSIGN",  # 'NONE', 'INTAKE' or 'RETURN'
    CIRCUIT_ATTR,  # I've only seen '00000'
    DLY_ATTR,  # (ON/OFF)
    HNAME_ATTR,  # same as objnam
    PARENT_ATTR,  # (objnam) parent (a module)
    SNAME_ATTR,  # friendly name
    STATIC_ATTR,  # (ON/OFF) I've only seen 'OFF'
    SUBTYP_ATTR,  # I've only seen 'LEGACY'
}
```

The VALVE type is already registered in `ALL_ATTRIBUTES_BY_TYPE` (line 454).

### Key Valve Attributes

1. **ASSIGN**: Controls valve position with three possible values:
   - `'NONE'` - Valve is in neutral/off position
   - `'INTAKE'` - Valve is set to intake position
   - `'RETURN'` - Valve is set to return position

2. **SNAME**: Friendly name for the valve
3. **DLY**: Delay setting (ON/OFF)
4. **PARENT**: Reference to parent module
5. **SUBTYP**: Valve subtype (currently only 'LEGACY' observed)

## Implementation Approach

### Option 1: Select Entity (RECOMMENDED)

Valves are best represented as **Select entities** in Home Assistant since they have 3 discrete states (NONE, INTAKE, RETURN).

**Benefits:**
- Natural UI representation (dropdown with 3 options)
- Matches the discrete state model of the ASSIGN attribute
- Follows HA design patterns for multi-state controls

**Implementation Pattern:**

```python
# custom_components/intellicenter/select.py

from homeassistant.components.select import SelectEntity

VALVE_POSITIONS = ["NONE", "INTAKE", "RETURN"]

class PoolValve(PoolEntity, SelectEntity):
    """Representation of a Pentair pool valve."""

    def __init__(self, entry, controller, poolObject):
        super().__init__(
            entry,
            controller,
            poolObject,
            attribute_key="ASSIGN",
            extraStateAttributes={"DLY"},
            icon="mdi:valve"
        )
        self._attr_options = VALVE_POSITIONS

    @property
    def current_option(self) -> str | None:
        """Return the current valve position."""
        return self._poolObject.get("ASSIGN", "NONE")

    async def async_select_option(self, option: str) -> None:
        """Change the valve position."""
        if option in VALVE_POSITIONS:
            self.requestChanges({"ASSIGN": option})
```

**Setup in async_setup_entry:**

```python
async def async_setup_entry(hass, entry, async_add_entities):
    controller = hass.data[DOMAIN][entry.entry_id].controller

    valves = []
    for obj in controller.model.objectList:
        if obj.objtype == "VALVE":
            valves.append(PoolValve(entry, controller, obj))

    async_add_entities(valves)
```

### Option 2: Switch Entities (Alternative)

If valves only toggle between two positions (e.g., INTAKE vs RETURN), could use switches:

```python
class PoolValveSwitch(PoolEntity, SwitchEntity):
    """Valve as switch (OFF=INTAKE, ON=RETURN)."""

    @property
    def is_on(self) -> bool:
        return self._poolObject.get("ASSIGN") == "RETURN"

    def turn_on(self):
        self.requestChanges({"ASSIGN": "RETURN"})

    def turn_off(self):
        self.requestChanges({"ASSIGN": "INTAKE"})
```

**Drawback:** Loses the NONE state unless you add separate buttons.

## Required Code Changes

### 1. Add VALVE_TYPE constant to exports

**File:** `custom_components/intellicenter/pyintellicenter/__init__.py`

Add to exports:
```python
VALVE_TYPE = "VALVE"
```

### 2. Add ASSIGN_ATTR constant

**File:** `custom_components/intellicenter/pyintellicenter/attributes.py`

```python
ASSIGN_ATTR = "ASSIGN"
```

Export in `__init__.py`:
```python
ASSIGN_ATTR,
```

### 3. Track VALVE objects in PoolModel

**File:** `custom_components/intellicenter/__init__.py`

Add to `attributes_map` in `async_setup_entry`:

```python
attributes_map = {
    # ... existing mappings ...
    "VALVE": {SNAME_ATTR, "ASSIGN", DLY_ATTR},
}
```

### 4. Create select.py platform

**File:** `custom_components/intellicenter/select.py` (NEW FILE)

Create the select platform implementation as shown in Option 1 above.

### 5. Add select platform to PLATFORMS list

**File:** `custom_components/intellicenter/__init__.py`

```python
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN

PLATFORMS = [
    LIGHT_DOMAIN,
    SENSOR_DOMAIN,
    SWITCH_DOMAIN,
    BINARY_SENSOR_DOMAIN,
    WATER_HEATER_DOMAIN,
    NUMBER_DOMAIN,
    COVER_DOMAIN,
    SELECT_DOMAIN,  # ADD THIS
]
```

### 6. Update manifest.json

**File:** `custom_components/intellicenter/manifest.json`

No changes needed - select domain will be auto-discovered.

### 7. Add translations (optional but recommended)

**File:** `custom_components/intellicenter/strings.json`

```json
{
  "entity": {
    "select": {
      "valve_position": {
        "name": "Valve Position",
        "state": {
          "none": "None",
          "intake": "Intake",
          "return": "Return"
        }
      }
    }
  }
}
```

## Testing Approach

### Unit Tests

**File:** `tests/test_select.py` (NEW)

```python
"""Tests for select entities."""

import pytest
from custom_components.intellicenter.select import PoolValve

async def test_valve_current_position(hass, pool_object_valve):
    """Test reading valve position."""
    mock_controller = MagicMock()
    valve = PoolValve(entry, mock_controller, pool_object_valve)

    assert valve.current_option == "INTAKE"
    assert valve.options == ["NONE", "INTAKE", "RETURN"]

async def test_valve_select_option(hass, pool_object_valve):
    """Test changing valve position."""
    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    valve = PoolValve(entry, mock_controller, pool_object_valve)
    await valve.async_select_option("RETURN")

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "VALVE1"
    assert args[1]["ASSIGN"] == "RETURN"
```

**Fixture in conftest.py:**

```python
@pytest.fixture
def pool_object_valve() -> PoolObject:
    """Return a PoolObject representing a valve."""
    return PoolObject(
        "VALVE1",
        {
            "OBJTYP": "VALVE",
            "SUBTYP": "LEGACY",
            "SNAME": "Pool Valve",
            "ASSIGN": "INTAKE",
            "DLY": "OFF",
        },
    )
```

### Integration Testing

1. **Mock Protocol Testing**: Verify requestChanges sends correct JSON
2. **Hardware Testing**: Test with actual IntelliCenter system to confirm:
   - Valve objects are discovered
   - Position changes work correctly
   - State updates are received
   - Delay functionality works as expected

## JSON Protocol Examples

### ✅ CONFIRMED: Live System Data from 10.100.11.60

**Found 4 VALVE objects in live IntelliCenter system:**

#### Valve 1 - Intake Position
```json
{
  "objnam": "VAL03",
  "params": {
    "OBJTYP": "VALVE",
    "SUBTYP": "LEGACY",
    "SNAME": "Intake",
    "ASSIGN": "INTAKE",
    "DLY": "OFF",
    "PARENT": "M0102",
    "CIRCUIT": "00000",
    "STATIC": "OFF",
    "HNAME": "VAL03"
  }
}
```

#### Valve 2 - Return Position
```json
{
  "objnam": "VAL04",
  "params": {
    "OBJTYP": "VALVE",
    "SUBTYP": "LEGACY",
    "SNAME": "Return",
    "ASSIGN": "RETURN",
    "DLY": "OFF",
    "PARENT": "M0102",
    "CIRCUIT": "00000",
    "STATIC": "OFF",
    "HNAME": "VAL04"
  }
}
```

#### Valve 3 - NONE Position
```json
{
  "objnam": "VAL01",
  "params": {
    "OBJTYP": "VALVE",
    "SUBTYP": "LEGACY",
    "SNAME": "Valve A",
    "ASSIGN": "NONE",
    "DLY": "OFF",
    "PARENT": "M0101",
    "CIRCUIT": "00000",
    "STATIC": "OFF",
    "HNAME": "VAL01"
  }
}
```

#### Valve 4 - NONE Position
```json
{
  "objnam": "VAL02",
  "params": {
    "OBJTYP": "VALVE",
    "SUBTYP": "LEGACY",
    "SNAME": "Valve B",
    "ASSIGN": "NONE",
    "DLY": "OFF",
    "PARENT": "M0101",
    "CIRCUIT": "00000",
    "STATIC": "OFF",
    "HNAME": "VAL02"
  }
}
```

**Key Findings:**
- ✅ All valves have `SUBTYP: "LEGACY"`
- ✅ ASSIGN values confirmed: `"INTAKE"`, `"RETURN"`, `"NONE"`
- ✅ All valves have `CIRCUIT: "00000"` (not linked to specific circuits)
- ✅ DLY is always `"OFF"` in this system
- ✅ STATIC is always `"OFF"` for valves
- ✅ PARENT references the module (M0101 or M0102)

### Request to Change Valve Position

```json
{
  "messageID": 123,
  "command": "RequestParamChange",
  "objectList": [
    {
      "objnam": "VALVE1",
      "params": {
        "ASSIGN": "RETURN"
      }
    }
  ]
}
```

### Expected Response

```json
{
  "messageID": 123,
  "response": "OK"
}
```

### NotifyList Update

```json
{
  "messageID": 0,
  "command": "NotifyList",
  "objectList": [
    {
      "objnam": "VALVE1",
      "params": {
        "ASSIGN": "RETURN"
      }
    }
  ]
}
```

## Implementation Risks & Considerations

### Low Risk Items
- ✅ VALVE type already defined in attributes.py
- ✅ Protocol pattern established (same as lights, switches)
- ✅ requestChanges method proven in other entities
- ✅ Testing framework in place

### Medium Risk Items
- ⚠️ **Hardware Availability**: Need actual IntelliCenter with valves to test
- ⚠️ **ASSIGN Values**: Only documented as 'NONE', 'INTAKE', 'RETURN' - need hardware confirmation
- ⚠️ **DLY Attribute**: Purpose unclear - might affect valve transition timing

### High Risk Items
- ❌ **None identified** - implementation follows established patterns

## Next Steps

1. **Add VALVE support to PoolModel tracking** (5 minutes)
2. **Create select.py platform** (30 minutes)
3. **Add unit tests** (30 minutes)
4. **Test with hardware** (requires physical IntelliCenter with valves)
5. **Document in README** (15 minutes)

**Total estimated development time: ~2 hours** (excluding hardware testing)

## References

- **Attributes Definition**: `custom_components/intellicenter/pyintellicenter/attributes.py:424-433`
- **Similar Implementation (Cover)**: `custom_components/intellicenter/cover.py`
- **Entity Base Class**: `custom_components/intellicenter/__init__.py:199-324`
- **Home Assistant Select Integration**: https://developers.home-assistant.io/docs/core/entity/select

## Conclusion

Valve control implementation is **highly feasible** with minimal risk. The VALVE object type is already defined, and we can leverage the existing entity patterns. The recommended approach is to use the **Select entity** platform to represent the three valve positions (NONE, INTAKE, RETURN).

The implementation follows the same proven patterns as lights, switches, and covers already in the codebase, making it a low-risk addition with clear testing paths.
