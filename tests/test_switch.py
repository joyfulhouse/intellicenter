"""Test the Pentair IntelliCenter switch platform."""

from unittest.mock import MagicMock

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    BODY_TYPE,
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


async def test_non_featured_circuit_not_created(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test that non-featured circuits don't create switches."""
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

    # CIRC02 is not featured, should not be in switches
    circ02_switches = [
        e
        for e in entities_added
        if hasattr(e, "_pool_object") and e._pool_object.objnam == "CIRC02"
    ]
    assert len(circ02_switches) == 0


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
