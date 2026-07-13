"""Test the Pentair IntelliCenter switch platform."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    CIRCGRP_TYPE,
    STATUS_ATTR,
    VACFLO_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.switch import PoolBody, PoolCircuit, PoolVacation

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


async def test_true_plain_circuit_group_creates_enabled_switch(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """A true CIRCGRP without color members creates an enabled group switch."""
    group = pool_model.add_object(
        "WATER_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "Water Features",
            "STATUS": "OFF",
            "CIRCUIT": "CIRC01 CIRC02",
        },
    )
    assert group is not None
    mock_coordinator.model = pool_model
    mock_entry = MagicMock()
    mock_entry.runtime_data = mock_coordinator
    entities_added: list[PoolCircuit] = []

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, mock_entry, entities_added.extend)

    group_switches = [
        entity
        for entity in entities_added
        if entity._pool_object.objnam == "WATER_GROUP"
    ]
    assert len(group_switches) == 1
    assert group_switches[0].entity_registry_enabled_default is True


async def test_true_color_circuit_group_does_not_create_switch(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """A true CIRCGRP containing a color light is left to the light platform."""
    group = pool_model.add_object(
        "LIGHT_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "All Pool Lights",
            "STATUS": "OFF",
            "CIRCUIT": "LIGHT1 LIGHT2",
        },
    )
    assert group is not None
    mock_coordinator.model = pool_model
    mock_entry = MagicMock()
    mock_entry.runtime_data = mock_coordinator
    entities_added: list[PoolCircuit] = []

    from custom_components.intellicenter.switch import async_setup_entry

    await async_setup_entry(hass, mock_entry, entities_added.extend)

    assert all(entity._pool_object.objnam != "LIGHT_GROUP" for entity in entities_added)


def make_group_switch(
    mock_coordinator: MagicMock, status: object = "OFF"
) -> PoolCircuit:
    """Create a plain circuit-group switch for focused unit tests."""
    group = PoolObject(
        "WATER_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "Water Features",
            "STATUS": status,
            "CIRCUIT": "CIRC01 CIRC02",
        },
    )
    mock_coordinator.controller.get_circuits_in_group.side_effect = None
    mock_coordinator.controller.get_circuits_in_group.return_value = [
        mock_coordinator.model["CIRC01"],
        mock_coordinator.model["CIRC02"],
    ]
    from custom_components.intellicenter.switch import PoolCircuitGroup

    return PoolCircuitGroup(mock_coordinator, group)


@pytest.mark.parametrize(
    ("method_name", "state"), [("async_turn_on", True), ("async_turn_off", False)]
)
async def test_true_circuit_group_atomically_controls_members(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    method_name: str,
    state: bool,
) -> None:
    """Group on/off uses one set_multiple_circuit_states helper call."""
    switch = make_group_switch(mock_coordinator)
    switch.hass = hass

    await getattr(switch, method_name)()

    mock_coordinator.controller.set_multiple_circuit_states.assert_awaited_once_with(
        ["CIRC01", "CIRC02"], state
    )
    mock_coordinator.controller.request_changes.assert_not_awaited()


@pytest.mark.parametrize("status", [None, "", "READY", 1])
async def test_true_circuit_group_malformed_status_is_unknown(
    mock_coordinator: MagicMock,
    status: object,
) -> None:
    """A group without a valid ON/OFF status does not fabricate an off state."""
    assert make_group_switch(mock_coordinator, status).is_on is None


async def test_true_circuit_group_without_members_refuses_control(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """A partially synchronized group cannot silently issue an empty batch."""
    switch = make_group_switch(mock_coordinator)
    switch.hass = hass
    mock_coordinator.controller.get_circuits_in_group.return_value = []
    mock_coordinator.controller.get_circuits_in_group.side_effect = None

    with pytest.raises(HomeAssistantError) as err:
        await switch.async_turn_on()

    assert err.value.translation_key == "circuit_group_members_missing"
    mock_coordinator.controller.set_multiple_circuit_states.assert_not_awaited()


async def test_true_circuit_group_command_failure_reverts_optimistic_state(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """A failed atomic group write raises cleanly and drops optimistic state."""
    from pyintellicenter import ICConnectionError

    mock_coordinator.controller.set_multiple_circuit_states.side_effect = (
        ICConnectionError("Not connected")
    )
    switch = make_group_switch(mock_coordinator)
    switch.hass = hass

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    assert switch._optimistic_state is None
    assert mock_write_ha_state.call_count == 2
