# Pool "Last Temp" Sensor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-body temperature sensor that exposes IntelliCenter's `BODY.LSTTMP` ("last recorded temperature"), so users get a stable pool temperature that holds steady when the pump is off (issue #75).

**Architecture:** Reuse the existing `PoolSensor` class in `sensor.py`. Add one `BODY_TYPE` branch to `_build_entities` that creates a `TEMPERATURE` sensor bound to the `LSTTMP` attribute, named `"+ Last Temp"` (→ "Pool Last Temp" / "Spa Last Temp"), enabled by default. No coordinator, protocol, or `pyintellicenter` changes — `LSTTMP` is already tracked for bodies and push updates already flow.

**Tech Stack:** Python 3.13, Home Assistant custom integration, `pyintellicenter` (published), `pytest` + `pytest-homeassistant-custom-component`, `uv`, `ruff`, `mypy`.

## Global Constraints

- Package manager: **`uv` only** — never `pip`. Sync deps with `uv sync --frozen` (intellicenter repo), run tools via `uv run …`.
- **Never** disable linter rules (no `# noqa`, `# type: ignore`). Fix the root cause.
- Pre-commit gate (must pass before every commit): `uv run ruff check --fix` && `uv run ruff format` && `uv run mypy custom_components/intellicenter/ --ignore-missing-imports` && `uv run pytest`.
- Follow existing `sensor.py` patterns; do not restructure unrelated code.
- Entity naming: `"+ Last Temp"` produces `<body sname> + " Last Temp"` via `PoolEntity.name`. Use this exact string.
- Attribute: `LSTTMP_ATTR` (= `"LSTTMP"`). Object type: `BODY_TYPE`. Both imported from `pyintellicenter`.
- `unique_id` rule: `PoolEntity.unique_id` appends the attribute key only when it differs from `STATUS_ATTR`. The last-temp sensor's key is `LSTTMP`, so its id is `<entry_id>_<objnam>LSTTMP` — distinct from the body switch's `<entry_id>_<objnam>`.

---

### Task 1: Add the body "Last Temp" sensor

**Files:**
- Modify: `custom_components/intellicenter/sensor.py` (add `BODY_TYPE`, `LSTTMP_ATTR` to the `pyintellicenter` import block; add a `BODY_TYPE` branch in `_build_entities`)
- Test: `tests/test_sensor.py` (add 3 new tests; update 1 existing test)

**Interfaces:**
- Consumes (already exists):
  - `PoolSensor(coordinator, pool_object, *, device_class, attribute_key, name=None, enabled_by_default=True, ...)` — existing class in `sensor.py`.
  - `PoolEntity.name` — prepends `pool_object.sname` when `name` starts with `"+"`.
  - `PoolEntity.unique_id` → `f"{entry_id}_{objnam}"` plus `attribute_key` suffix when `attribute_key != STATUS_ATTR`.
  - Fixtures in `tests/conftest.py`: `mock_coordinator` (entry_id `"test_entry"`, `system_info.uses_metric is False`), `pool_model` (contains bodies `POOL1`/"Pool"/`LSTTMP="78"` and `SPA01`/"Spa"/`LSTTMP="102"`).
  - Fixture in `tests/test_sensor.py`: `pool_object_body` (`POOL1`, `SNAME="Pool"`, `LSTTMP="78"`, `LOTMP="72"`).
- Produces: a `PoolSensor` per body with `attribute_key=LSTTMP_ATTR`, `name="+ Last Temp"`, `device_class=TEMPERATURE`, enabled by default.

- [ ] **Step 1: Sync dependencies**

Run: `uv sync --frozen`
Expected: environment resolves with no errors (no lockfile drift).

- [ ] **Step 2: Write the failing tests**

Add these three tests to `tests/test_sensor.py`. `BODY_TYPE`, `SensorDeviceClass`, `SensorStateClass`, `UnitOfTemperature`, `PoolObject`, `PoolModel`, `MagicMock`, `HomeAssistant`, and `PoolSensor` are already imported at the top of the file.

```python
async def test_body_last_temp_sensor_properties(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """The body last-temp sensor exposes LSTTMP, named '<body> Last Temp'."""
    sensor = PoolSensor(
        mock_coordinator,
        pool_object_body,
        device_class=SensorDeviceClass.TEMPERATURE,
        attribute_key="LSTTMP",
        name="+ Last Temp",
    )

    assert sensor.name == "Pool Last Temp"
    assert sensor.unique_id == "test_entry_POOL1LSTTMP"
    assert sensor.native_value == 78
    assert sensor.native_unit_of_measurement == str(UnitOfTemperature.FAHRENHEIT)
    assert sensor._attr_device_class == SensorDeviceClass.TEMPERATURE
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    # Enabled by default: distinct, primary value (issue #75).
    assert sensor.entity_registry_enabled_default is True


async def test_body_last_temp_unique_id_distinct_from_body_switch(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """The last-temp sensor must not collide with the body switch's unique_id."""
    from custom_components.intellicenter.switch import PoolBody

    sensor = PoolSensor(
        mock_coordinator,
        pool_object_body,
        device_class=SensorDeviceClass.TEMPERATURE,
        attribute_key="LSTTMP",
        name="+ Last Temp",
    )
    body_switch = PoolBody(mock_coordinator, pool_object_body)

    assert body_switch.unique_id == "test_entry_POOL1"
    assert sensor.unique_id == "test_entry_POOL1LSTTMP"
    assert sensor.unique_id != body_switch.unique_id


async def test_setup_creates_body_last_temp_sensors(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Platform setup creates a Last Temp sensor for each body (Pool + Spa)."""
    mock_coordinator.model = pool_model

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added: list = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.sensor import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    names = [e.name for e in entities_added]
    assert "Pool Last Temp" in names
    assert "Spa Last Temp" in names
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_sensor.py::test_body_last_temp_sensor_properties tests/test_sensor.py::test_body_last_temp_unique_id_distinct_from_body_switch tests/test_sensor.py::test_setup_creates_body_last_temp_sensors -v`
Expected: FAIL. `test_setup_creates_body_last_temp_sensors` fails on the missing `"Pool Last Temp"` name; the property test fails because no body branch builds the sensor (and `entities_added` from setup lacks it). The standalone property/unique_id tests construct `PoolSensor` directly, so they may pass already — that is fine; the setup test is the one that proves the feature is wired.

- [ ] **Step 4: Add the imports in `sensor.py`**

In the `from pyintellicenter import (...)` block in `custom_components/intellicenter/sensor.py`, add `BODY_TYPE` and `LSTTMP_ATTR` in alphabetical position. The block currently starts:

```python
from pyintellicenter import (
    CHEM_TYPE,
    GPM_ATTR,
```

Change it to begin:

```python
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    GPM_ATTR,
```

and add `LSTTMP_ATTR` in alphabetical order (between `GPM_ATTR` and `MAX_ATTR`):

```python
    GPM_ATTR,
    LSTTMP_ATTR,
    MAX_ATTR,
```

- [ ] **Step 5: Add the `BODY_TYPE` branch in `_build_entities`**

In `custom_components/intellicenter/sensor.py`, the loop in `_build_entities` begins with `if obj.objtype == SENSE_TYPE:`. Insert a new branch immediately **after** the `SENSE_TYPE` block and **before** `elif obj.objtype == PUMP_TYPE:`:

```python
        elif obj.objtype == BODY_TYPE:
            # "Last Temp" = the body's last recorded (latched) temperature.
            # Unlike the physical SENSE water probe (which cools in an
            # above-ground pipe when the pump stops), LSTTMP holds the last
            # circulating temperature, so it stays accurate when idle (#75).
            if LSTTMP_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=SensorDeviceClass.TEMPERATURE,
                        attribute_key=LSTTMP_ATTR,
                        name="+ Last Temp",
                    )
                )
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_sensor.py::test_body_last_temp_sensor_properties tests/test_sensor.py::test_body_last_temp_unique_id_distinct_from_body_switch tests/test_sensor.py::test_setup_creates_body_last_temp_sensors -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Update the stale comment/assertion in `test_sensor_setup_creates_entities`**

In `tests/test_sensor.py`, `test_sensor_setup_creates_entities` contains:

```python
    # Should create sensors for:
    # - SENSE1 (air temp)
    # - PUMP1 (power, RPM, GPM = 3)
    # - CHEM1 (pH, ORP, pH tank, ORP tank = 4)
    # Note: Body temps (POOL1/SPA01) are in water_heater, not sensors
    assert len(entities_added) >= 8
```

Replace that comment block (the `# Note:` line is now wrong) with:

```python
    # Should create sensors for:
    # - SENSE1 (air temp)
    # - PUMP1 (power, RPM, GPM = 3)
    # - CHEM1 (pH, ORP, pH tank, ORP tank = 4)
    # - POOL1/SPA01 bodies (Last Temp = LSTTMP, one per body)
    assert len(entities_added) >= 8
```

- [ ] **Step 8: Run the full sensor test file**

Run: `uv run pytest tests/test_sensor.py -v`
Expected: PASS (all existing tests plus the 3 new ones).

- [ ] **Step 9: Run the pre-commit quality gate**

Run: `uv run ruff check --fix && uv run ruff format && uv run mypy custom_components/intellicenter/ --ignore-missing-imports && uv run pytest`
Expected: ruff clean, format clean, mypy reports no new errors, full test suite passes.

- [ ] **Step 10: Commit**

```bash
git add custom_components/intellicenter/sensor.py tests/test_sensor.py
git commit -m "feat(sensor): add per-body Last Temp sensor (LSTTMP) for #75

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Document the new sensor

**Files:**
- Modify: `README` (entity list / equipment section)
- Modify: `CLAUDE.md` (the "Bodies of Water" entity-creation bullet under "Entity Creation Logic")

**Interfaces:**
- Consumes: the entity from Task 1 (name "Pool Last Temp" / "Spa Last Temp", attribute `LSTTMP`, enabled by default).
- Produces: documentation only (no code, no tests).

- [ ] **Step 1: Locate the README entity documentation**

Run: `grep -rn "Water Sensor\|Bodies of Water\|water_heater\|temperature" README* 2>/dev/null | head -20`
Expected: shows the README file name (e.g. `README.md`) and the section listing per-equipment entities. Note the file name and the body/temperature section for the next step.

- [ ] **Step 2: Add a README note about the Last Temp sensor**

In the README section that lists body/temperature entities, add a bullet (match the surrounding markdown style):

```markdown
- **Last Temp** (`sensor`, one per body, e.g. "Pool Last Temp"): the body's last
  recorded water temperature (`LSTTMP`). Unlike the physical Water Sensor — whose
  probe sits in an above-ground pipe and reads colder when the pump is off — the
  Last Temp value latches the last circulating temperature, so it stays accurate
  while the pump is idle.
```

- [ ] **Step 3: Update the "Bodies of Water" bullet in `CLAUDE.md`**

In `CLAUDE.md`, under "### Entity Creation Logic", the bullet currently reads:

```markdown
- **Bodies of Water**: Create switch, temperature sensors, and water heater entities
```

Replace it with:

```markdown
- **Bodies of Water**: Create a switch, a "Last Temp" temperature sensor (the body's `LSTTMP` last-recorded temperature, enabled by default — holds steady when the pump is off, unlike the physical Water Sensor), and water heater entities
```

- [ ] **Step 4: Commit**

```bash
git add README* CLAUDE.md
git commit -m "docs: document per-body Last Temp sensor (#75)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- "Add a per-body `LSTTMP` sensor, reuse `PoolSensor`, name `+ Last Temp`, enabled by default, created for every body with `LSTTMP`" → Task 1, Steps 4–5. ✅
- "Imports `BODY_TYPE`, `LSTTMP_ATTR`" → Task 1, Step 4. ✅
- "No coordinator/protocol/pyintellicenter changes" → respected; only `sensor.py` + tests touched. ✅
- "No collision with body switch unique_id" → Task 1, Step 2 (`test_body_last_temp_unique_id_distinct_from_body_switch`). ✅
- Testing: created (`test_setup_creates_body_last_temp_sensors`), enabled-by-default + value + unit (`test_body_last_temp_sensor_properties`), distinct unique_id (dedicated test). ✅ The spec's optional "body without LSTTMP produces no sensor" is implicitly covered by the `if LSTTMP_ATTR in obj.attribute_keys` guard; not separately tested (YAGNI — no such body exists in fixtures).
- Docs: README + CLAUDE.md → Task 2. ✅

**2. Placeholder scan:** No TBD/TODO/"add error handling"/"similar to" — every code and command step is concrete. ✅

**3. Type consistency:** `attribute_key="LSTTMP"` (string literal in tests) equals `LSTTMP_ATTR` (= `"LSTTMP"`) used in production — consistent. `name="+ Last Temp"` identical across spec, production, and tests. `unique_id` strings (`test_entry_POOL1LSTTMP`, `test_entry_POOL1`) match the `PoolEntity.unique_id` rule. Sensor constructor keyword args match the existing `PoolSensor.__init__` signature. ✅
