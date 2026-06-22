# Design: Pool "Last Temp" Sensor (Issue #75)

**Date:** 2026-06-22
**Branch:** `feature/issue-75-pool-last-temp-entity`
**Issue:** [#75 — Pool last temp entity](https://github.com/joyfulhouse/intellicenter/issues/75)

## Problem

The user (migrating from the `dwradcliffe` integration) reports that the water
temperature entity reads ~10°F colder in the evening when the pump is not
running. The entity they currently see is IntelliCenter's **physical water
sensor** — the `SENSE` object's `SOURCE` attribute — which is a live probe
mounted in an above-ground pipe. When circulation stops, the probe cools to
ambient and the reading drops, even though the actual body of water has not.

The `dwradcliffe` integration exposed a separate **"last temp" entity** that did
not exhibit this drop. That entity reflected the IntelliCenter controller's
`BODY.LSTTMP` ("last recorded temperature") attribute, which latches the last
temperature recorded while circulating and holds steady when the pump is off.

## Current State

Two distinct, device-provided values exist:

| | Physical Water Sensor | Body "last temp" |
|---|---|---|
| Object / attribute | `SENSE` → `SOURCE` | `BODY` → `LSTTMP` |
| Meaning | Raw probe reading, live | Last recorded (latched) temperature |
| Behavior when pump off | Drops toward ambient | Holds last good value |
| Exposed today as | A standalone temperature sensor (enabled) | **Not** a sensor — only the `current_temperature` *attribute* of the climate / water_heater entities |

`LSTTMP` is already tracked by the coordinator
(`DEFAULT_ATTRIBUTES_MAP[BODY_TYPE]` includes `LSTTMP_ATTR`) and is already used
as `current_temperature` by `climate.py` and `water_heater.py`. It is **not**
available as a first-class, history-graphable sensor entity. That standalone
sensor is the gap this design fills.

`LSTTMP` is **not** a duplicate of the physical Water Sensor — it comes from a
different object and behaves differently. The only existing overlap is the
control entities' `current_temperature` attribute, which is not a standalone
sensor and is not guaranteed to exist (a body without a heater gets no
climate/water_heater entity, but always reports `LSTTMP`).

## Goal

Add a per-body temperature **sensor** entity that exposes `BODY.LSTTMP`,
matching the `dwradcliffe` "last temp" entity. Enabled by default.

## Non-Goals

- No change to the existing physical `SENSE` "Water Sensor" entity (purely
  additive).
- No change to `climate.py` / `water_heater.py` (they keep using `LSTTMP` as
  `current_temperature`).
- No `pyintellicenter` / protocol changes.
- No coordinator changes (`LSTTMP` is already tracked for bodies).

## Design

Reuse the existing `PoolSensor` class. In `sensor.py`'s `_build_entities`, add a
branch for `BODY_TYPE` objects that report `LSTTMP`:

```python
elif obj.objtype == BODY_TYPE:
    if LSTTMP_ATTR in obj.attribute_keys:
        sensors.append(
            PoolSensor(
                coordinator,
                obj,
                device_class=SensorDeviceClass.TEMPERATURE,
                attribute_key=LSTTMP_ATTR,
                name="+ Last Temp",   # -> "Pool Last Temp" / "Spa Last Temp"
                # enabled by default (PoolSensor default)
            )
        )
```

- **Imports:** add `BODY_TYPE` and `LSTTMP_ATTR` to the `pyintellicenter` import
  block in `sensor.py`.
- **Entity name:** `"+ Last Temp"`. `PoolEntity.name` prepends the body's
  `sname`, producing `"Pool Last Temp"`, `"Spa Last Temp"`, etc.
- **Device class:** `SensorDeviceClass.TEMPERATURE` →
  `native_unit_of_measurement` resolves automatically via
  `pentairTemperatureSettings()` (°F / °C per system mode), and the default
  `MEASUREMENT` state class enables history graphing.
- **Created for every body** that reports `LSTTMP` (guarded by the
  `attribute_key` check), so both Pool and Spa get one.
- **Enabled by default** (the `PoolSensor` / `PoolEntity` default).

### Why no collision with the body switch

`PoolEntity.unique_id` appends the attribute key **only when it differs from
`STATUS_ATTR`**:

- Body switch (`PoolBody`) uses `attribute_key=STATUS_ATTR` → `unique_id` =
  `<entry_id><objnam>` (no suffix).
- New sensor uses `attribute_key=LSTTMP` → `unique_id` =
  `<entry_id><objnam>LSTTMP`.

These are distinct, so the two entities coexist on the same `BODY` object.

### Update propagation

`LSTTMP` is already in `DEFAULT_ATTRIBUTES_MAP[BODY_TYPE]`, so push updates
already arrive. `PoolEntity._handle_coordinator_update` writes new state when the
entity's `_attribute_key` (`LSTTMP`) appears in the update set — so the sensor
updates in real time with no coordinator changes.

## Testing (`tests/test_sensor.py`)

Add tests asserting:

1. A `Pool Last Temp` sensor is created for a `BODY` object that reports
   `LSTTMP`.
2. The sensor is **enabled by default**
   (`entity_registry_enabled_default is True`).
3. `native_value` reflects the body's `LSTTMP` value, and
   `native_unit_of_measurement` is the system temperature unit (°F/°C).
4. The sensor's `unique_id` is distinct from the body switch's `unique_id`
   (regression guard for the `STATUS_ATTR`-suffix rule).
5. (If practical) a body without `LSTTMP` produces no last-temp sensor.

## Documentation

- `README`: note the per-body "Last Temp" sensor in the entity list and explain
  it holds the last circulating temperature (vs the live Water Sensor that
  cools when the pump is off).
- `CLAUDE.md`: extend the "Bodies of Water" entity-creation bullet to mention
  the `LSTTMP` last-temp sensor.

## Scope

~6 lines of production code in `sensor.py` (one branch + two imports), plus
tests and docs. Additive, low risk.
