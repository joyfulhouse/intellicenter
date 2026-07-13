"""Test the Pentair IntelliCenter switch platform."""

from unittest.mock import MagicMock

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    SCHED_TYPE,
    STATUS_ATTR,
    VACFLO_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.const import MANHT_ATTR
from custom_components.intellicenter.switch import (
    ManualHeatSwitch,
    PoolBody,
    PoolCircuit,
    PoolSchedule,
    PoolVacation,
    _build_entities,
)

pytestmark = pytest.mark.asyncio


async def test_switch_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch platform creates entities for circuits and bodies."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create switches for:
    # - POOL1 (Pool body)
    # - SPA01 (Spa body)
    # - CIRC01 (Featured circuit - Pool Cleaner)
    # - SYS01 (Vacation mode)
    assert len(entities_added) >= 4

    # Verify we have body switches
    body_switches = [e for e in entities_added if isinstance(e, PoolBody)]
    assert len(body_switches) == 2

    # Verify we have circuit switches
    circuit_switches = [e for e in entities_added if isinstance(e, PoolCircuit)]
    assert len(circuit_switches) >= 2


async def test_manual_heat_created_only_for_spa_unconditionally(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """SPA bodies always get Manual Heat; pools do not, regardless of MANHT state."""
    spa = PoolObject(
        "SPA01",
        {"OBJTYP": BODY_TYPE, "SUBTYP": "SPA", "SNAME": "Spa"},
    )
    pool = PoolObject(
        "POOL1",
        {"OBJTYP": BODY_TYPE, "SUBTYP": "POOL", "SNAME": "Pool"},
    )

    switches = _build_entities(mock_coordinator, [spa, pool])

    manual_heat = [
        switch for switch in switches if isinstance(switch, ManualHeatSwitch)
    ]
    assert len(manual_heat) == 1
    assert manual_heat[0]._pool_object.objnam == "SPA01"
    assert manual_heat[0].name == "Spa Manual Heat"
    assert manual_heat[0].entity_category == EntityCategory.CONFIG
    assert manual_heat[0].entity_registry_enabled_default is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ON", True), ("OFF", False), (None, None), ("BAD", None)],
)
async def test_manual_heat_state_mapping(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    raw: str | None,
    expected: bool | None,
) -> None:
    """Manual Heat reports unknown for missing or malformed runtime state."""
    spa = PoolObject(
        "SPA01",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "SPA",
            "SNAME": "Spa",
            MANHT_ATTR: raw,
        },
    )
    switch = ManualHeatSwitch(mock_coordinator, spa)

    assert switch.is_on is expected


@pytest.mark.parametrize(("turn_on", "expected"), [(True, "ON"), (False, "OFF")])
async def test_manual_heat_write(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    turn_on: bool,
    expected: str,
) -> None:
    """Manual Heat writes MANHT directly on its SPA body."""
    spa = PoolObject(
        "SPA01",
        {"OBJTYP": BODY_TYPE, "SUBTYP": "SPA", "SNAME": "Spa"},
    )
    switch = ManualHeatSwitch(mock_coordinator, spa)

    if turn_on:
        await switch.async_turn_on()
    else:
        await switch.async_turn_off()

    mock_coordinator.controller.request_changes.assert_awaited_once_with(
        "SPA01", {MANHT_ATTR: expected}
    )


async def test_manual_heat_write_error_is_translated(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A failed MANHT write surfaces a translated service error."""
    from pyintellicenter import ICConnectionError

    spa = PoolObject(
        "SPA01",
        {"OBJTYP": BODY_TYPE, "SUBTYP": "SPA", "SNAME": "Spa"},
    )
    mock_coordinator.controller.request_changes.side_effect = ICConnectionError(
        "offline"
    )
    switch = ManualHeatSwitch(mock_coordinator, spa)

    with pytest.raises(HomeAssistantError) as err:
        await switch.async_turn_on()

    assert err.value.translation_domain == "intellicenter"
    assert err.value.translation_key == "command_failed"


async def test_circuit_switch_properties(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolCircuit switch properties."""
    switch = PoolCircuit(mock_coordinator, pool_object_switch)

    assert switch.is_on is False
    assert switch.name == "Pool Cleaner"
    assert switch.unique_id == "test_entry_CIRC01"


async def test_circuit_switch_turn_on(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a circuit switch."""
    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await switch.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "CIRC01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"
    # Verify optimistic update was called
    mock_write_ha_state.assert_called()


async def test_circuit_switch_turn_off(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning off a circuit switch."""
    # Set switch to ON initially
    pool_object_switch.update({STATUS_ATTR: "ON"})

    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass  # Required for async_create_task

    assert switch.is_on is True

    await hass.async_block_till_done()
    await switch.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "CIRC01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_body_switch_properties(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolBody switch properties."""
    body_switch = PoolBody(mock_coordinator, pool_object_body)

    assert body_switch.is_on is True  # STATUS is "ON" in fixture
    assert body_switch.name == "Pool"
    assert body_switch.unique_id == "test_entry_POOL1"


async def test_body_switch_turn_on(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a body switch."""
    # Set body to OFF initially
    pool_object_body.update({STATUS_ATTR: "OFF"})

    body_switch = PoolBody(mock_coordinator, pool_object_body)
    body_switch.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await body_switch.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_body_switch_turn_off(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning off a body switch."""
    body_switch = PoolBody(mock_coordinator, pool_object_body)
    body_switch.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await body_switch.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_vacation_mode_switch(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test vacation mode switch creation and properties."""
    system_obj = pool_model["SYS01"]
    system_obj.update({VACFLO_ATTR: "OFF"})

    vacation_switch = PoolCircuit(
        mock_coordinator,
        system_obj,
        VACFLO_ATTR,
        name="Vacation mode",
        icon="mdi:palm-tree",
        enabled_by_default=False,
    )

    assert vacation_switch.is_on is False
    assert vacation_switch.name == "Vacation mode"
    assert vacation_switch.entity_registry_enabled_default is False


async def test_switch_state_updates(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test switch state updates from IntelliCenter."""
    switch = PoolCircuit(mock_coordinator, pool_object_switch)

    # Simulate update from IntelliCenter
    updates = {
        "CIRC01": {
            STATUS_ATTR: "ON",
        }
    }

    assert switch.isUpdated(updates) is True

    # Apply the update
    pool_object_switch.update(updates["CIRC01"])

    # Verify state changed
    assert switch.is_on is True


async def test_non_featured_circuit_created_disabled_by_default(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Non-featured user circuits create opt-in switches."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # CIRC02 is not featured, but remains available as an opt-in switch.
    circ02_switches = [
        e
        for e in entities_added
        if hasattr(e, "_pool_object")
        and e._pool_object.objnam == "CIRC02"
        and e._attribute_key == STATUS_ATTR
    ]
    assert len(circ02_switches) == 1
    assert circ02_switches[0].entity_registry_enabled_default is False


async def test_featured_circuit_switch_remains_enabled_with_stable_unique_id(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Featured switches retain their enabled default and existing unique ID."""
    switch = PoolCircuit(mock_coordinator, pool_object_switch)

    assert switch.entity_registry_enabled_default is True
    assert switch.unique_id == "test_entry_CIRC01"


@pytest.mark.parametrize(
    "subtype",
    ["LIGHT", "INTELLI", "GLOW", "GLOWT", "DIMMER", "MAGIC2", "LITSHO"],
)
async def test_light_circuits_do_not_create_status_switches(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    subtype: str,
) -> None:
    """Every light subtype, including LITSHO, is excluded from switch status."""
    from custom_components.intellicenter.switch import _build_entities

    light = PoolObject(
        f"LIGHT_{subtype}",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": subtype,
            "SNAME": subtype,
            "STATUS": "OFF",
            "FEATR": "OFF",
        },
    )

    status_switches = [
        entity
        for entity in _build_entities(mock_coordinator, [light])
        if entity._attribute_key == STATUS_ATTR
    ]
    assert status_switches == []


async def test_schedule_switch_creation_state_and_defaults(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Every schedule creates a normal-category, disabled-by-default switch."""
    from custom_components.intellicenter.switch import _build_entities

    schedule = PoolObject(
        "SCHED2",
        {"OBJTYP": SCHED_TYPE, "SNAME": "Spa", "STATUS": "ON"},
    )
    mock_coordinator.controller.is_schedule_enabled.return_value = True

    entities = _build_entities(mock_coordinator, [schedule])

    assert len(entities) == 1
    switch = entities[0]
    assert isinstance(switch, PoolSchedule)
    assert switch.name == "Schedule (Spa)"
    assert switch.unique_id == "test_entry_SCHED2"
    assert switch.entity_registry_enabled_default is False
    assert switch.entity_category is None
    assert switch.is_on is True
    mock_coordinator.controller.is_schedule_enabled.assert_called_once_with("SCHED2")


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [("OFF", False), (None, None), ("INVALID", None)],
)
async def test_schedule_switch_state_mapping(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    raw_status: str | None,
    expected: bool | None,
) -> None:
    """Missing or malformed schedule status is unknown, never falsely disabled."""
    schedule = PoolObject(
        "SCHED2",
        {"OBJTYP": SCHED_TYPE, "SNAME": "Spa", "STATUS": raw_status},
    )
    mock_coordinator.controller.is_schedule_enabled.return_value = False

    switch = PoolSchedule(mock_coordinator, schedule)

    assert switch.is_on is expected


async def test_schedule_switch_write_paths(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Schedule enable and disable write STATUS ON/OFF to the schedule object."""
    schedule = PoolObject(
        "SCHED2",
        {"OBJTYP": SCHED_TYPE, "SNAME": "Spa", "STATUS": "OFF"},
    )
    switch = PoolSchedule(mock_coordinator, schedule)
    switch.hass = hass

    await switch.async_turn_on()
    await hass.async_block_till_done()
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "SCHED2", {STATUS_ATTR: "ON"}
    )

    mock_coordinator.controller.request_changes.reset_mock()
    await switch.async_turn_off()
    await hass.async_block_till_done()
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "SCHED2", {STATUS_ATTR: "OFF"}
    )


async def test_dont_stop_switch_creation_state_and_writes(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Each user circuit gets a disabled CONFIG Don't Stop switch."""
    from custom_components.intellicenter.switch import _build_entities

    circuit = PoolObject(
        "AUX4",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "AUX 4",
            "STATUS": "OFF",
            "FEATR": "OFF",
            "DNTSTP": "ON",
        },
    )

    entities = _build_entities(mock_coordinator, [circuit])
    dont_stop = next(
        entity for entity in entities if entity.unique_id.endswith("DNTSTP")
    )
    assert dont_stop.name == "AUX 4 Don't Stop"
    assert dont_stop.entity_registry_enabled_default is False
    assert dont_stop.entity_category == EntityCategory.CONFIG
    assert dont_stop.is_on is True

    dont_stop.hass = hass
    await dont_stop.async_turn_off()
    await hass.async_block_till_done()
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "AUX4", {"DNTSTP": "OFF"}
    )


@pytest.mark.parametrize("raw_value", [None, "INVALID"])
async def test_dont_stop_switch_unknown_state(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    raw_value: str | None,
) -> None:
    """Missing and malformed Don't Stop values map to unknown."""
    circuit = PoolObject(
        "AUX4",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "AUX 4",
            "DNTSTP": raw_value,
        },
    )
    switch = PoolCircuit(
        mock_coordinator,
        circuit,
        attribute_key="DNTSTP",
        name="+ Don't Stop",
    )

    assert switch.is_on is None


async def test_switch_device_class(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that switches have the correct device class."""
    from homeassistant.components.switch import SwitchDeviceClass

    circuit = PoolCircuit(mock_coordinator, pool_object_switch)

    assert circuit.device_class == SwitchDeviceClass.SWITCH


async def test_circuit_failed_command_reverts_optimistic_state(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Regression: a failed fire-and-forget command must drop optimistic state.

    The write task swallowed every exception while the optimistic state could
    only be cleared by a push echo - which never arrives when the command
    failed - so the UI showed the wrong on/off state indefinitely.
    """
    from pyintellicenter import ICConnectionError

    mock_coordinator.controller.request_changes.side_effect = ICConnectionError(
        "Not connected"
    )

    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass

    await switch.async_turn_on()
    # The eagerly-started write task fails and reverts the optimistic state.
    await hass.async_block_till_done()
    assert switch._optimistic_state is None
    assert mock_write_ha_state.call_count >= 2  # optimistic write + revert


async def test_vacation_failed_command_raises_and_reverts(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """A failed vacation-mode write raises HomeAssistantError and reverts."""
    from pyintellicenter import ICConnectionError

    mock_coordinator.controller.set_vacation_mode.side_effect = ICConnectionError(
        "Not connected"
    )

    system_obj = pool_model["SYS01"]
    vacation = PoolVacation(mock_coordinator, system_obj)
    vacation.hass = hass

    with pytest.raises(HomeAssistantError):
        await vacation.async_turn_on()

    assert vacation._optimistic_state is None
