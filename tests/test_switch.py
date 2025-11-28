"""Test the Pentair IntelliCenter switch platform."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pyintellicenter import (
    STATUS_ATTR,
    VACFLO_ATTR,
    VALVE_TYPE,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.switch import PoolBody, PoolCircuit

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


async def test_valve_switch_properties(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test valve switch properties."""
    valve_switch = PoolCircuit(
        mock_coordinator,
        pool_object_valve,
        icon="mdi:pipe-valve",
    )

    assert valve_switch.is_on is False
    assert valve_switch.name == "Spillover Valve"
    assert valve_switch.unique_id == "test_entry_VAL01"


async def test_valve_switch_turn_on(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a valve switch."""
    valve_switch = PoolCircuit(
        mock_coordinator,
        pool_object_valve,
        icon="mdi:pipe-valve",
    )
    valve_switch.hass = hass

    await hass.async_block_till_done()
    await valve_switch.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "VAL01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_valve_switch_turn_off(
    hass: HomeAssistant,
    pool_object_valve: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning off a valve switch."""
    pool_object_valve.update({STATUS_ATTR: "ON"})

    valve_switch = PoolCircuit(
        mock_coordinator,
        pool_object_valve,
        icon="mdi:pipe-valve",
    )
    valve_switch.hass = hass

    assert valve_switch.is_on is True

    await hass.async_block_till_done()
    await valve_switch.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "VAL01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_valve_switch_setup_creates_entity(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test that valve switches are created during setup."""
    mock_coordinator.model = pool_model

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Find valve switches
    valve_switches = [
        e
        for e in entities_added
        if hasattr(e, "_pool_object") and e._pool_object.objtype == VALVE_TYPE
    ]
    assert len(valve_switches) == 1
    assert valve_switches[0]._pool_object.objnam == "VAL01"
