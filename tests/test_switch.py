"""Test the Pentair IntelliCenter switch platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
import pytest

from custom_components.intellicenter import DOMAIN
from custom_components.intellicenter.pyintellicenter import (
    STATUS_ATTR,
    VACFLO_ATTR,
    PoolModel,
    PoolObject,
)
from custom_components.intellicenter.switch import PoolBody, PoolCircuit

pytestmark = pytest.mark.asyncio


async def test_switch_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """Test switch platform creates entities for circuits and bodies."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100"}

    mock_handler = MagicMock()
    mock_controller = MagicMock()
    mock_controller.model = pool_model
    mock_handler.controller = mock_controller

    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, entry, capture_entities)

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
) -> None:
    """Test PoolCircuit switch properties."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    switch = PoolCircuit(entry, mock_controller, pool_object_switch)

    assert switch.is_on is False
    assert switch.name == "Pool Cleaner"
    assert switch.unique_id == "test_entry_CIRC01"


async def test_circuit_switch_turn_on(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
) -> None:
    """Test turning on a circuit switch."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    switch = PoolCircuit(entry, mock_controller, pool_object_switch)

    await hass.async_block_till_done()
    await switch.async_turn_on()

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "CIRC01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_circuit_switch_turn_off(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
) -> None:
    """Test turning off a circuit switch."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    # Set switch to ON initially
    pool_object_switch.update({STATUS_ATTR: "ON"})

    switch = PoolCircuit(entry, mock_controller, pool_object_switch)

    assert switch.is_on is True

    await hass.async_block_till_done()
    await switch.async_turn_off()

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "CIRC01"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_body_switch_properties(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
) -> None:
    """Test PoolBody switch properties."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    body_switch = PoolBody(entry, mock_controller, pool_object_body)

    assert body_switch.is_on is True  # STATUS is "ON" in fixture
    assert body_switch.name == "Pool"
    assert body_switch.unique_id == "test_entry_POOL1"


async def test_body_switch_turn_on(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
) -> None:
    """Test turning on a body switch."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    # Set body to OFF initially
    pool_object_body.update({STATUS_ATTR: "OFF"})

    body_switch = PoolBody(entry, mock_controller, pool_object_body)

    await hass.async_block_till_done()
    await body_switch.async_turn_on()

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "POOL1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_body_switch_turn_off(
    hass: HomeAssistant,
    pool_object_body: PoolObject,
) -> None:
    """Test turning off a body switch."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    body_switch = PoolBody(entry, mock_controller, pool_object_body)

    await hass.async_block_till_done()
    await body_switch.async_turn_off()

    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "POOL1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_vacation_mode_switch(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """Test vacation mode switch creation and properties."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    system_obj = pool_model["SYS01"]
    system_obj.update({VACFLO_ATTR: "OFF"})

    vacation_switch = PoolCircuit(
        entry,
        mock_controller,
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
) -> None:
    """Test switch state updates from IntelliCenter."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    switch = PoolCircuit(entry, mock_controller, pool_object_switch)

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
) -> None:
    """Test that non-featured circuits don't create switches."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_handler = MagicMock()
    mock_controller = MagicMock()
    mock_controller.model = pool_model
    mock_handler.controller = mock_controller

    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, entry, capture_entities)

    # CIRC02 is not featured, should not be in switches
    circ02_switches = [
        e
        for e in entities_added
        if hasattr(e, "_poolObject") and e._poolObject.objnam == "CIRC02"
    ]
    assert len(circ02_switches) == 0
