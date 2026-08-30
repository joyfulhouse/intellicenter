# Valve Control Implementation Guide

**Status:** ⚠️ Superseded — premise corrected (see below)
**Date:** 2025-01-15 (correction: 2026-07-11)
**Version:** 1.1
**Tested On:** Live IntelliCenter system (4 valves confirmed)

---

> ## ⚠️ Correction (2026-07-11)
>
> This document mischaracterizes the `ASSIGN` attribute as "current valve
> position." Live-hardware investigation (see the README's
> [Circulation Watchdog](../README.md#circulation-watchdog-stuck-valve-detection)
> section) established:
>
> - **`ASSIGN` is a static role assignment** — it declares which plumbing
>   function a valve output serves (`INTAKE`/`RETURN`/`NONE`). It is
>   configuration, not telemetry, and does not change when the valve turns.
> - **Valve actuators have no feedback path.** IntelliCenter drives them
>   blind over a 3-wire 24VAC interface; neither position nor mode (e.g. an
>   IntelliValve stuck in SERVICE) is ever reported back. `VALVE` objects
>   expose no `STATUS`/`MODE` attribute.
> - Writing `ASSIGN` therefore **re-configures the valve's role** in the
>   system; it does not command the actuator to rotate. Actual valve motion
>   is driven by IntelliCenter's body/circuit logic.
>
> The select-entity design below would build a configuration editor, not a
> valve control — it is retained for the (accurate) protocol captures, but
> the "position control" framing should not be implemented as designed.

## Executive Summary

~~Valve control is **fully feasible** and ready for implementation.~~ See the
correction above: what the protocol allows is editing a valve's *role
assignment*, not commanding or reading its *position*. The protocol captures
in this document remain accurate.

**Implementation Effort:** ~2 hours
**Risk Level:** Low (follows established patterns)
**Recommended Approach:** Home Assistant Select Entity

---

## Table of Contents

1. [Live System Analysis](#live-system-analysis)
2. [Protocol Specification](#protocol-specification)
3. [Implementation Design](#implementation-design)
4. [Code Implementation](#code-implementation)
5. [Testing Strategy](#testing-strategy)
6. [Future Enhancements](#future-enhancements)

---

## Live System Analysis

### System Details

**IntelliCenter IP:** <intellicenter-ip>
**Protocol Port:** 6681
**Valves Found:** 4

### Discovered Valve Objects

#### VAL03 - Intake Valve
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

#### VAL04 - Return Valve
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

#### VAL01 - Valve A (Neutral)
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

#### VAL02 - Valve B (Neutral)
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

### Key Observations

| Attribute | Values Observed | Purpose |
|-----------|----------------|---------|
| OBJTYP | `"VALVE"` | Object type identifier |
| SUBTYP | `"LEGACY"` | Valve subtype (all valves) |
| SNAME | Various | Friendly name for display |
| ASSIGN | `"NONE"`, `"INTAKE"`, `"RETURN"` | **Valve role assignment** (configuration — not live position; see correction above) |
| DLY | `"OFF"` | Delay setting (unused in test system) |
| PARENT | `"M0101"`, `"M0102"` | Parent module reference |
| CIRCUIT | `"00000"` | Not linked to circuits |
| STATIC | `"OFF"` | Dynamic object (can be controlled) |
| HNAME | Matches objnam | Internal hardware name |

---

## Protocol Specification

### Existing Code Support

The VALVE type is **already defined** in the codebase:

**File:** `custom_components/intellicenter/pyintellicenter/attributes.py:424-433`

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

**Registration:** Already in `ALL_ATTRIBUTES_BY_TYPE` dictionary (line 454)

### Protocol Commands

#### Get All Valves
```json
{
  "messageID": "1",
  "command": "GetParamList",
  "condition": "",
  "objectList": [
    {
      "objnam": "INCR",
      "keys": ["OBJTYP", "SUBTYP", "SNAME", "ASSIGN", "DLY", "PARENT"]
    }
  ]
}
```

#### Change Valve Role Assignment (configuration write — does not rotate the actuator)
```json
{
  "messageID": "123",
  "command": "SETPARAMLIST",
  "objectList": [
    {
      "objnam": "VAL03",
      "params": {
        "ASSIGN": "RETURN"
      }
    }
  ]
}
```

#### Expected Response
```json
{
  "messageID": "123",
  "command": "SETPARAMLIST",
  "response": "200"
}
```

#### State Update Notification
```json
{
  "messageID": "0",
  "command": "NotifyList",
  "objectList": [
    {
      "objnam": "VAL03",
      "params": {
        "ASSIGN": "RETURN"
      }
    }
  ]
}
```

---

## Implementation Design

### Architecture Decision: Select Entity

**Recommended:** Home Assistant **Select Entity**

**Rationale:**
- Valves have 3 discrete states (NONE, INTAKE, RETURN)
- Select entity provides natural dropdown UI
- Matches the semantic model of the ASSIGN attribute
- Follows HA best practices for multi-state controls

**Alternative Considered:** Switch entities (rejected - loses NONE state)

### Component Architecture

```
custom_components/intellicenter/
├── select.py                    # NEW - Valve select platform
├── __init__.py                  # MODIFY - Add SELECT_DOMAIN to PLATFORMS
├── pyintellicenter/
│   ├── attributes.py            # EXISTS - VALVE_ATTRIBUTES already defined
│   └── __init__.py              # MODIFY - Export VALVE_TYPE, ASSIGN_ATTR
└── tests/
    ├── test_select.py           # NEW - Unit tests for valves
    └── conftest.py              # MODIFY - Add valve fixtures
```

### Entity Hierarchy

```
PoolEntity (base class)
    └── PoolValve (select.py)
            ├── current_option -> reads ASSIGN
            └── async_select_option -> writes ASSIGN
```

### State Management

```
ASSIGN Attribute Values:
┌────────────────────────────────┐
│  NONE    : Neutral/Off         │
│  INTAKE  : Intake position     │
│  RETURN  : Return position     │
└────────────────────────────────┘

State Flow:
User selects option in UI
    ↓
async_select_option("RETURN")
    ↓
requestChanges({"ASSIGN": "RETURN"})
    ↓
SETPARAMLIST command sent
    ↓
IntelliCenter responds with "200"
    ↓
NotifyList update received
    ↓
PoolModel updates valve object
    ↓
Dispatcher signals entity
    ↓
UI updates to show new position
```

---

## Code Implementation

### Step 1: Export Constants

**File:** `custom_components/intellicenter/pyintellicenter/attributes.py`

Add constant:
```python
ASSIGN_ATTR = "ASSIGN"
```

**File:** `custom_components/intellicenter/pyintellicenter/__init__.py`

Add to exports:
```python
from .attributes import (
    # ... existing exports ...
    ASSIGN_ATTR,
)

# Add VALVE_TYPE constant
VALVE_TYPE = "VALVE"
```

### Step 2: Track VALVE Objects

**File:** `custom_components/intellicenter/__init__.py`

Modify `async_setup_entry` function, add to `attributes_map`:

```python
attributes_map = {
    BODY_TYPE: {
        SNAME_ATTR,
        HEATER_ATTR,
        HTMODE_ATTR,
        LOTMP_ATTR,
        LSTTMP_ATTR,
        STATUS_ATTR,
        VOL_ATTR,
    },
    CIRCUIT_TYPE: {SNAME_ATTR, STATUS_ATTR, USE_ATTR, SUBTYP_ATTR, FEATR_ATTR},
    CIRCGRP_TYPE: {CIRCUIT_ATTR},
    CHEM_TYPE: {},
    HEATER_TYPE: {SNAME_ATTR, BODY_ATTR, LISTORD_ATTR},
    PUMP_TYPE: {SNAME_ATTR, STATUS_ATTR, PWR_ATTR, RPM_ATTR, GPM_ATTR},
    SENSE_TYPE: {SNAME_ATTR, SOURCE_ATTR},
    SCHED_TYPE: {SNAME_ATTR, ACT_ATTR, VACFLO_ATTR},
    SYSTEM_TYPE: {MODE_ATTR, VACFLO_ATTR},
    VALVE_TYPE: {SNAME_ATTR, ASSIGN_ATTR, DLY_ATTR, SUBTYP_ATTR},  # ADD THIS LINE
}
```

### Step 3: Add SELECT Platform

**File:** `custom_components/intellicenter/__init__.py`

Add import:
```python
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
```

Modify PLATFORMS list:
```python
PLATFORMS = [
    LIGHT_DOMAIN,
    SENSOR_DOMAIN,
    SWITCH_DOMAIN,
    BINARY_SENSOR_DOMAIN,
    WATER_HEATER_DOMAIN,
    NUMBER_DOMAIN,
    COVER_DOMAIN,
    SELECT_DOMAIN,  # ADD THIS LINE
]
```

### Step 4: Create Select Platform

**File:** `custom_components/intellicenter/select.py` (NEW)

```python
"""Pentair IntelliCenter select entities."""

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import (
    ASSIGN_ATTR,
    DLY_ATTR,
    VALVE_TYPE,
    ModelController,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

# Valve position options (matches IntelliCenter ASSIGN values)
VALVE_POSITIONS = ["NONE", "INTAKE", "RETURN"]

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Load Pentair valve select entities based on a config entry."""
    controller: ModelController = hass.data[DOMAIN][entry.entry_id].controller

    valves = []

    obj: PoolObject
    for obj in controller.model.objectList:
        if obj.objtype == VALVE_TYPE:
            valves.append(PoolValve(entry, controller, obj))

    async_add_entities(valves)


# -------------------------------------------------------------------------------------


class PoolValve(PoolEntity, SelectEntity):
    """Representation of a Pentair pool valve."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
    ):
        """Initialize the valve select entity."""
        super().__init__(
            entry,
            controller,
            poolObject,
            attribute_key=ASSIGN_ATTR,
            extraStateAttributes={DLY_ATTR},
            icon="mdi:valve",
        )
        self._attr_options = VALVE_POSITIONS

    @property
    def current_option(self) -> str | None:
        """Return the current valve position."""
        position = self._poolObject.get(ASSIGN_ATTR)
        # Ensure the position is one of the valid options
        if position in VALVE_POSITIONS:
            return position
        # Default to NONE if invalid
        _LOGGER.warning(
            f"Valve {self._poolObject.objnam} has invalid position: {position}"
        )
        return "NONE"

    async def async_select_option(self, option: str) -> None:
        """Change the valve position."""
        if option not in VALVE_POSITIONS:
            _LOGGER.error(f"Invalid valve position requested: {option}")
            return

        _LOGGER.debug(f"Setting valve {self._poolObject.objnam} to position {option}")
        self.requestChanges({ASSIGN_ATTR: option})
```

### Step 5: Add Unit Tests

**File:** `tests/conftest.py`

Add fixture:
```python
@pytest.fixture
def pool_object_valve() -> PoolObject:
    """Return a PoolObject representing a valve."""
    return PoolObject(
        "VAL01",
        {
            "OBJTYP": "VALVE",
            "SUBTYP": "LEGACY",
            "SNAME": "Pool Valve",
            "ASSIGN": "INTAKE",
            "DLY": "OFF",
            "PARENT": "M0101",
            "CIRCUIT": "00000",
            "STATIC": "OFF",
            "HNAME": "VAL01",
        },
    )


@pytest.fixture
def pool_model_data() -> list[dict[str, Any]]:
    """Return test data for a complete pool model."""
    return [
        # ... existing test data ...
        # Add valve to test data
        {
            "objnam": "VAL01",
            "params": {
                "OBJTYP": "VALVE",
                "SUBTYP": "LEGACY",
                "SNAME": "Pool Valve",
                "ASSIGN": "INTAKE",
                "DLY": "OFF",
                "PARENT": "M0101",
                "CIRCUIT": "00000",
                "STATIC": "OFF",
                "HNAME": "VAL01",
            },
        },
    ]
```

**File:** `tests/test_select.py` (NEW)

```python
"""Tests for select entities (valves)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.intellicenter.pyintellicenter import PoolObject
from custom_components.intellicenter.pyintellicenter.attributes import ASSIGN_ATTR
from custom_components.intellicenter.select import PoolValve, VALVE_POSITIONS


async def test_valve_properties(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test valve select entity properties."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    valve = PoolValve(entry, mock_controller, pool_object_valve)

    # Test initial state
    assert valve.current_option == "INTAKE"
    assert valve.options == VALVE_POSITIONS
    assert valve.name == "Pool Valve"
    assert valve.unique_id == "test_entry_VAL01ASSIGN"
    assert valve.icon == "mdi:valve"


async def test_valve_select_none(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test changing valve to NONE position."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    valve = PoolValve(entry, mock_controller, pool_object_valve)
    await valve.async_select_option("NONE")

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "VAL01"
    assert args[1][ASSIGN_ATTR] == "NONE"


async def test_valve_select_intake(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test changing valve to INTAKE position."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    # Start with valve at NONE
    pool_object_valve.update({ASSIGN_ATTR: "NONE"})

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    valve = PoolValve(entry, mock_controller, pool_object_valve)
    await valve.async_select_option("INTAKE")

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "VAL01"
    assert args[1][ASSIGN_ATTR] == "INTAKE"


async def test_valve_select_return(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test changing valve to RETURN position."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    valve = PoolValve(entry, mock_controller, pool_object_valve)
    await valve.async_select_option("RETURN")

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "VAL01"
    assert args[1][ASSIGN_ATTR] == "RETURN"


async def test_valve_state_update(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test valve state updates when ASSIGN changes."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    valve = PoolValve(entry, mock_controller, pool_object_valve)

    # Initial state
    assert valve.current_option == "INTAKE"

    # Update valve position
    pool_object_valve.update({ASSIGN_ATTR: "RETURN"})
    assert valve.current_option == "RETURN"

    # Update to NONE
    pool_object_valve.update({ASSIGN_ATTR: "NONE"})
    assert valve.current_option == "NONE"


async def test_valve_invalid_option(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test handling of invalid valve position."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    valve = PoolValve(entry, mock_controller, pool_object_valve)
    await valve.async_select_option("INVALID")

    # Should not call requestChanges for invalid option
    mock_controller.requestChanges.assert_not_called()


async def test_valve_extra_state_attributes(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
) -> None:
    """Test valve extra state attributes."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="intellicenter",
        title="Test",
        data={},
        source="test",
        entry_id="test_entry",
    )

    mock_controller = MagicMock()
    mock_controller.systemInfo = MagicMock()
    type(mock_controller.systemInfo).propName = property(lambda self: "Test Pool")
    type(mock_controller.systemInfo).swVersion = property(lambda self: "2.0.0")

    valve = PoolValve(entry, mock_controller, pool_object_valve)

    attrs = valve.extra_state_attributes
    assert attrs["OBJNAM"] == "VAL01"
    assert attrs["OBJTYPE"] == "VALVE/LEGACY"
    assert "DLY" in attrs
    assert attrs["DLY"] == "OFF"
```

### Step 6: Update Manifest (Optional)

**File:** `custom_components/intellicenter/manifest.json`

No changes needed - Home Assistant will auto-discover the select domain.

### Step 7: Add Translations (Optional but Recommended)

**File:** `custom_components/intellicenter/strings.json`

Add translations:
```json
{
  "config": {
    "...": "existing config entries..."
  },
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

**File:** `custom_components/intellicenter/translations/en.json`

Mirror the same structure as `strings.json`.

---

## Testing Strategy

### Unit Testing

**Run all tests:**
```bash
pytest tests/test_select.py -v
```

**Expected output:**
```
tests/test_select.py::test_valve_properties PASSED
tests/test_select.py::test_valve_select_none PASSED
tests/test_select.py::test_valve_select_intake PASSED
tests/test_select.py::test_valve_select_return PASSED
tests/test_select.py::test_valve_state_update PASSED
tests/test_select.py::test_valve_invalid_option PASSED
tests/test_select.py::test_valve_extra_state_attributes PASSED
```

**Coverage:**
```bash
pytest tests/test_select.py --cov=custom_components/intellicenter/select --cov-report=html
```

### Integration Testing

#### Phase 1: Discovery
1. Install integration in Home Assistant
2. Configure with IP: <intellicenter-ip>
3. Verify 4 valve entities are created:
   - `select.intellicenter_intake`
   - `select.intellicenter_return`
   - `select.intellicenter_valve_a`
   - `select.intellicenter_valve_b`

#### Phase 2: State Reading
1. Check each valve's current position
2. Verify positions match live system:
   - VAL03 should show "Intake"
   - VAL04 should show "Return"
   - VAL01 should show "None"
   - VAL02 should show "None"

#### Phase 3: State Changes
1. Select different position from dropdown
2. Verify IntelliCenter receives SETPARAMLIST command
3. Confirm valve physically moves (if observable)
4. Check NotifyList update received
5. Verify UI updates to new position

#### Phase 4: State Sync
1. Change valve position using IntelliCenter app/panel
2. Verify Home Assistant entity updates automatically
3. Test with multiple rapid changes
4. Confirm no race conditions

#### Phase 5: Automation Testing
1. Create automation to change valve on schedule
2. Test service calls:
   ```yaml
   service: select.select_option
   target:
     entity_id: select.intellicenter_intake
   data:
     option: RETURN
   ```
3. Verify automation triggers correctly

### Edge Case Testing

| Test Case | Expected Behavior |
|-----------|------------------|
| Invalid position received | Default to "NONE", log warning |
| Network disconnect during change | Request queued, sent on reconnect |
| Concurrent position changes | Last command wins, NotifyList resolves |
| DLY attribute changes | Extra state attribute updates |
| Parent module offline | Entity marked unavailable |
| Position unchanged | No unnecessary updates |

---

## Future Enhancements

### Phase 2 Features

#### 1. Delay Support
**Status:** DLY attribute exists but currently unused

**Enhancement:**
```python
class PoolValve(PoolEntity, SelectEntity):
    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        if self._poolObject.get(DLY_ATTR) == "ON":
            attrs["delay_enabled"] = True
        return attrs
```

**Use Case:** Some valves may need delay between position changes to prevent hydraulic shock.

#### 2. Valve Interlock
**Status:** Not implemented

**Enhancement:**
```python
# Prevent both intake and return from being NONE simultaneously
async def async_select_option(self, option: str):
    if option == "NONE":
        # Check if companion valve is also NONE
        companion = self._get_companion_valve()
        if companion and companion.current_option == "NONE":
            _LOGGER.warning("Cannot set both valves to NONE")
            return

    self.requestChanges({ASSIGN_ATTR: option})
```

**Use Case:** Safety feature to ensure water flow is always directed somewhere.

#### 3. Valve Groups
**Status:** Not implemented

**Enhancement:**
```yaml
# Home Assistant template to group intake/return valves
template:
  - select:
      - name: "Pool Valve Configuration"
        options:
          - "Pool Mode"
          - "Spa Mode"
          - "Backwash Mode"
        select_option:
          - service: select.select_option
            target:
              entity_id: select.intellicenter_intake
            data:
              option: >
                {% if option == 'Pool Mode' %}INTAKE
                {% elif option == 'Spa Mode' %}RETURN
                {% else %}NONE{% endif %}
```

**Use Case:** Simplified UI for common valve configurations.

#### 4. Position Feedback
**Status:** ASSIGN provides position, no separate sensor

**Enhancement:**
```python
# Add diagnostic sensors for valve health
class PoolValveStatusSensor(SensorEntity):
    """Report valve status and health."""

    @property
    def native_value(self):
        # Could track:
        # - Last position change timestamp
        # - Total position changes (cycles)
        # - Time in each position
        return "operational"
```

**Use Case:** Maintenance tracking and fault detection.

#### 5. Smart Valve Routing
**Status:** Not implemented

**Enhancement:**
```python
# Automation to optimize valve positions based on mode
automation:
  - alias: "Auto-configure valves for pool mode"
    trigger:
      - platform: state
        entity_id: switch.intellicenter_pool
        to: "on"
    action:
      - service: select.select_option
        target:
          entity_id: select.intellicenter_intake
        data:
          option: "INTAKE"
      - service: select.select_option
        target:
          entity_id: select.intellicenter_return
        data:
          option: "RETURN"
```

**Use Case:** Automatic valve configuration when switching between pool/spa modes.

### Phase 3 Features

#### 1. Advanced Diagnostics
- Valve cycle counter
- Position change history
- Estimated maintenance schedule
- Failure prediction based on patterns

#### 2. Energy Optimization
- Optimize valve positions for pump efficiency
- Reduce hydraulic resistance
- Coordinate with variable speed pump settings

#### 3. Multi-Valve Scenarios
- Support for 3-way valves
- Support for diverter valves
- Complex routing scenarios

---

## Reference Files

### Primary Implementation Files
- `custom_components/intellicenter/select.py` - Main valve implementation
- `custom_components/intellicenter/__init__.py` - Platform registration
- `custom_components/intellicenter/pyintellicenter/attributes.py` - Valve attributes
- `tests/test_select.py` - Unit tests

### Supporting Files
- `explore_valves.py` - Live system exploration script
- `valve_objects.json` - Raw JSON data from live system
- `docs/valve-control-implementation.md` - This document

### Related Code References
- `custom_components/intellicenter/switch.py` - Similar entity pattern
- `custom_components/intellicenter/cover.py` - Another 3-state entity
- `custom_components/intellicenter/pyintellicenter/controller.py` - requestChanges implementation
- `custom_components/intellicenter/pyintellicenter/protocol.py` - SETPARAMLIST command

---

## Troubleshooting

### Common Issues

#### Valves Not Discovered
**Symptom:** No valve entities appear after setup

**Solution:**
1. Check that VALVE_TYPE is in attributes_map
2. Verify SELECT_DOMAIN is in PLATFORMS list
3. Check Home Assistant logs for errors
4. Confirm valves exist on IntelliCenter (use explore_valves.py)

#### Position Not Changing
**Symptom:** UI shows change but valve doesn't move

**Solution:**
1. Check IntelliCenter logs for SETPARAMLIST errors
2. Verify ASSIGN attribute is writable (STATIC != "ON")
3. Check network connectivity
4. Confirm valve is not mechanically stuck
5. Look for permission errors in IntelliCenter

#### State Out of Sync
**Symptom:** HA shows different position than actual

**Solution:**
1. Reload integration to force full sync
2. Check NotifyList messages are being received
3. Verify ASSIGN is in tracked attributes
4. Check for network packet loss
5. Enable debug logging for protocol.py

#### Invalid Position Warning
**Symptom:** Warning about invalid position in logs

**Solution:**
1. Check live system for unexpected ASSIGN values
2. Update VALVE_POSITIONS list if new values found
3. Verify IntelliCenter firmware version compatibility

### Debug Logging

**Enable debug logs in configuration.yaml:**
```yaml
logger:
  default: info
  logs:
    custom_components.intellicenter: debug
    custom_components.intellicenter.select: debug
    custom_components.intellicenter.pyintellicenter.protocol: debug
    custom_components.intellicenter.pyintellicenter.controller: debug
```

**Look for:**
- `Setting valve VAL01 to position RETURN` - Command sent
- `PROTOCOL: writing to transport: {"command":"SETPARAMLIST"...` - Network activity
- `received update for 1 pool objects` - State update received
- `receivedNotifyList` - IntelliCenter pushing updates

---

## Appendix

### A. Valve Position State Machine

```
┌──────────────────────────────────────────────┐
│                                              │
│                 VALVE STATES                 │
│                                              │
│    ┌──────┐         ┌──────┐         ┌──────┐    │
│    │      │         │      │         │      │    │
│    │ NONE │◄───────►│INTAKE│◄───────►│RETURN│    │
│    │      │         │      │         │      │    │
│    └──────┘         └──────┘         └──────┘    │
│       ▲                ▲                ▲        │
│       │                │                │        │
│       └────────────────┴────────────────┘        │
│          Any position can transition             │
│          directly to any other position          │
│                                              │
└──────────────────────────────────────────────┘
```

### B. Protocol Message Flow

```
Home Assistant                IntelliCenter              Physical Valve
      │                             │                         │
      │  User selects "RETURN"      │                         │
      ├─────────────────────────────►                         │
      │  SETPARAMLIST               │                         │
      │  {"ASSIGN": "RETURN"}       │                         │
      │                             │                         │
      │◄─────────────────────────────                         │
      │  Response: 200 OK           │                         │
      │                             │                         │
      │                             ├────────────────────────►│
      │                             │  Actuate valve motor    │
      │                             │                         │
      │                             │◄────────────────────────│
      │                             │  Position confirmed     │
      │                             │                         │
      │◄─────────────────────────────                         │
      │  NotifyList                 │                         │
      │  {"ASSIGN": "RETURN"}       │                         │
      │                             │                         │
      │  UI updates                 │                         │
      │                             │                         │
```

### C. Integration with Existing Systems

#### Pool/Spa Mode Automation
```yaml
automation:
  - alias: "Switch to Spa Mode"
    trigger:
      - platform: state
        entity_id: switch.intellicenter_spa
        to: "on"
    action:
      # Configure valves for spa
      - service: select.select_option
        target:
          entity_id: select.intellicenter_intake
        data:
          option: "RETURN"
      # Wait for valve to actuate
      - delay: "00:00:05"
      # Then start spa pump
      - service: switch.turn_on
        target:
          entity_id: switch.intellicenter_spa_pump
```

#### Backwash Automation
```yaml
automation:
  - alias: "Weekly Backwash"
    trigger:
      - platform: time
        at: "02:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      # Set valves to backwash position
      - service: select.select_option
        target:
          entity_id:
            - select.intellicenter_intake
            - select.intellicenter_return
        data:
          option: "NONE"
      - delay: "00:10:00"
      # Return to normal operation
      - service: select.select_option
        target:
          entity_id: select.intellicenter_intake
        data:
          option: "INTAKE"
      - service: select.select_option
        target:
          entity_id: select.intellicenter_return
        data:
          option: "RETURN"
```

### D. Performance Considerations

| Metric | Expected Value | Notes |
|--------|---------------|-------|
| Command latency | < 500ms | Local network |
| State update delay | < 1s | Via NotifyList |
| Valve actuation time | 5-30s | Mechanical limitation |
| Concurrent commands | Queued | One-at-a-time protocol |
| Network overhead | ~200 bytes | Per position change |

### E. Security Considerations

- **Authentication:** IntelliCenter does not require auth on local network
- **Network Access:** Ensure IntelliCenter is on trusted LAN segment
- **Firewall:** Block external access to port 6681
- **Physical Security:** Valve control requires physical access to pool equipment
- **Fail-Safe:** Valves default to last position on power loss

---

## Changelog

### Version 1.0 (2025-01-15)
- Initial documentation
- Live system analysis completed (<intellicenter-ip>)
- 4 valves discovered and documented
- Full implementation guide created
- Testing strategy defined
- Future enhancements outlined

---

## Contributors

- **Analysis:** Claude Code (Anthropic)
- **Live System:** IntelliCenter @ <intellicenter-ip>
- **Integration Base:** dwradcliffe/intellicenter (original)
- **Repository:** joyfulhouse/intellicenter

---

## License

This implementation guide is part of the joyfulhouse/intellicenter integration and follows the same license as the main project.

---

**End of Document**
