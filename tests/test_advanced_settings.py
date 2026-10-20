"""Advanced settings use panel readback, not inferred firmware capabilities.

Objects here are purpose-built model fixtures, not captured hardware results.
The MANOVR encoding is anchored in app function 83088 (0x203-0x21e).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    BODY_TYPE,
    CIRCGRP_TYPE,
    HEATER_TYPE,
    SYSTEM_TYPE,
    SYSTIM_TYPE,
    ICCommandError,
    ICConnectionError,
    ICTimeoutError,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.advanced_settings import (
    CONFIGURATION_SETTINGS,
    MANOVR_ATTR,
)
from custom_components.intellicenter.coordinator import (
    DEFAULT_ATTRIBUTES_MAP,
    IntelliCenterCoordinator,
)
from custom_components.intellicenter.sensor import (
    ConfigurationSensor,
    _build_entities as build_sensors,
)
from custom_components.intellicenter.switch import (
    ManualHeatSwitch,
    ManualPrioritySwitch,
    _build_entities as build_switches,
    async_setup_entry as setup_switches,
)


def _owner(model: PoolModel, raw: object = "OFF") -> PoolObject:
    """Use a distinct tracked owner; do not assert an unverified fixed wire ID."""
    obj = model.add_object(
        "ADVERTISED_OWNER", {"OBJTYP": SYSTIM_TYPE, MANOVR_ATTR: raw}
    )
    assert obj is not None
    return obj


def _priority_switches(
    coordinator: IntelliCenterCoordinator,
) -> list[ManualPrioritySwitch]:
    return [
        entity
        for entity in build_switches(coordinator, list(coordinator.model))
        if isinstance(entity, ManualPrioritySwitch)
    ]


def test_tracking_does_not_change_heater_activity_contract() -> None:
    """The latest-main heater activity fix remains untouched by setting discovery."""
    assert "COOL" in DEFAULT_ATTRIBUTES_MAP[HEATER_TYPE]
    assert "HEATING" not in DEFAULT_ATTRIBUTES_MAP[HEATER_TYPE]
    assert "HEATING" in DEFAULT_ATTRIBUTES_MAP[SYSTEM_TYPE]
    assert all(
        MANOVR_ATTR in attrs
        for objtype, attrs in DEFAULT_ATTRIBUTES_MAP.items()
        if objtype != CIRCGRP_TYPE
    )
    assert MANOVR_ATTR not in DEFAULT_ATTRIBUTES_MAP[CIRCGRP_TYPE]


def test_manual_heat_identity_and_priority_owner_are_independent(
    mock_coordinator,
) -> None:
    """MANOVR never aliases MANHT, including when the two have opposite states."""
    system = mock_coordinator.model["SYS01"]
    system.update({"MANHT": "ON"})
    owner = _owner(mock_coordinator.model)
    entities = build_switches(mock_coordinator, list(mock_coordinator.model))
    heat = next(e for e in entities if isinstance(e, ManualHeatSwitch))
    priority = next(e for e in entities if isinstance(e, ManualPrioritySwitch))
    assert heat.unique_id == "test_entry_SYS01MANHT"
    assert heat.name == "Spa Manual Heat"
    assert priority.unique_id == "test_entry_ADVERTISED_OWNERMANOVR"
    assert heat.is_on is True
    assert priority.is_on is False
    owner.update({MANOVR_ATTR: "ON"})
    system.update({"MANHT": "OFF"})
    assert heat.is_on is False
    assert priority.is_on is True


@pytest.mark.parametrize("firmware", ["1.047", "2.029", "3.008", None])
@pytest.mark.parametrize("raw", [None, "MANOVR", "UNKNOWN", "on", "", 0, False, [], {}])
def test_unknown_firmware_and_malformed_state_do_not_grant_control(
    mock_coordinator, firmware, raw
) -> None:
    """A version string and an unknown-key echo are not write capabilities."""
    mock_coordinator.model["SYS01"].update({"VER": firmware})
    _owner(mock_coordinator.model, raw)
    assert _priority_switches(mock_coordinator) == []


@pytest.mark.parametrize("value,expected", [("ON", True), ("OFF", False)])
def test_priority_known_state(mock_coordinator, value, expected) -> None:
    _owner(mock_coordinator.model, value)
    switch = _priority_switches(mock_coordinator)[0]
    assert switch.is_on is expected
    assert switch.available


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_on,value", [(True, "ON"), (False, "OFF")])
async def test_priority_targets_advertised_owner_and_awaits_ack_without_optimism(
    mock_coordinator, turn_on, value
) -> None:
    owner = _owner(mock_coordinator.model, "OFF" if turn_on else "ON")
    switch = _priority_switches(mock_coordinator)[0]
    started, release = asyncio.Event(), asyncio.Event()

    async def pending(*_args):
        started.set()
        await release.wait()

    mock_coordinator.controller.request_changes.side_effect = pending
    call = switch.async_turn_on if turn_on else switch.async_turn_off
    task = asyncio.create_task(call())
    await asyncio.wait_for(started.wait(), 1)
    try:
        assert not task.done()
        assert switch.is_on is not turn_on
    finally:
        release.set()
        await task
    mock_coordinator.controller.request_changes.assert_awaited_once_with(
        owner.objnam, {MANOVR_ATTR: value}
    )
    assert switch.is_on is not turn_on  # acknowledgement alone is not readback
    owner.update({MANOVR_ATTR: value})
    assert switch.is_on is turn_on
    assert mock_coordinator.model["SYS01"]["MANHT"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [ICCommandError("rejected"), ICConnectionError("lost"), ICTimeoutError("late")],
)
async def test_priority_failures_propagate_without_changing_readback(
    mock_coordinator, failure
) -> None:
    _owner(mock_coordinator.model)
    switch = _priority_switches(mock_coordinator)[0]
    mock_coordinator.controller.request_changes.side_effect = failure
    with pytest.raises(HomeAssistantError) as error:
        await switch.async_turn_on()
    assert error.value.translation_key == "command_failed"
    assert error.value.__cause__ is failure
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_priority_cancel_does_not_publish_requested_value(
    mock_coordinator,
) -> None:
    _owner(mock_coordinator.model)
    switch = _priority_switches(mock_coordinator)[0]
    started = asyncio.Event()

    async def pending(*_args):
        started.set()
        await asyncio.Event().wait()

    mock_coordinator.controller.request_changes.side_effect = pending
    task = asyncio.create_task(switch.async_turn_on())
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert switch.is_on is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["missing", "malformed", "ambiguous", "disconnected", "removed"]
)
async def test_stale_or_ambiguous_capability_blocks_direct_service_calls(
    mock_coordinator, change
) -> None:
    owner = _owner(mock_coordinator.model)
    switch = _priority_switches(mock_coordinator)[0]
    if change == "ambiguous":
        mock_coordinator.model.add_object(
            "OTHER", {"OBJTYP": BODY_TYPE, MANOVR_ATTR: "ON"}
        )
    elif change == "disconnected":
        mock_coordinator.connected = False
    elif change == "removed":
        mock_coordinator.model.remove_object(owner.objnam)
    else:
        owner.update({MANOVR_ATTR: None if change == "missing" else "INVALID"})
    assert not switch.available
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()
    mock_coordinator.controller.request_changes.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_initial_readback_recovers_via_real_coordinator_backfill(
    hass: HomeAssistant,
) -> None:
    """Truthy malformed/echoed values must not consume the deferred builder retry."""
    entry = MagicMock()
    entry.entry_id = "advanced"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    coordinator._started = True
    owner = _owner(coordinator.model, "MANOVR")
    coordinator._known_objnams = {owner.objnam}
    coordinator._seed_redispatch_bookkeeping(owner)
    entry.runtime_data = coordinator
    added = []
    await setup_switches(hass, entry, added.extend)
    assert not any(isinstance(e, ManualPrioritySwitch) for e in added)
    for value in ("INVALID", "OFF", "ON"):
        coordinator.async_set_updated_data(
            {owner.objnam: owner.update({MANOVR_ATTR: value})}
        )
    assert len([e for e in added if isinstance(e, ManualPrioritySwitch)]) == 1


@pytest.mark.asyncio
async def test_disconnect_requires_fresh_readback_before_reenabling_priority(
    hass: HomeAssistant,
) -> None:
    """Reconnect does not restore a stale capability when the panel omits its key."""
    entry = MagicMock()
    entry.entry_id = "advanced"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    owner = _owner(coordinator.model, "ON")
    coordinator._handler._is_connected = True
    switch = _priority_switches(coordinator)[0]
    assert switch.is_on is True
    coordinator._handler._is_connected = False
    coordinator.async_set_connection_state(False)
    assert owner[MANOVR_ATTR] is None
    assert switch.is_on is None
    coordinator._handler._is_connected = True
    coordinator.async_set_connection_state(True)
    assert not switch.available
    owner.update({MANOVR_ATTR: "OFF"})
    coordinator.async_set_updated_data({owner.objnam: {MANOVR_ATTR: "OFF"}})
    assert switch.available
    assert switch.is_on is False


@pytest.mark.parametrize(
    "setting", CONFIGURATION_SETTINGS, ids=lambda s: s.key + s.object_type
)
@pytest.mark.parametrize("raw", [None, [], {}, 0, False, "", "NaN", "Infinity"])
def test_configuration_unknown_never_becomes_off(setting, raw) -> None:
    if setting.key == "SOURCE" and isinstance(raw, str) and raw:
        return  # SOURCE tokens are opaque; this test does not invent an enumeration.
    assert setting.state(raw) is None
    assert setting.state(setting.key) is None


def test_clock_source_is_on_its_own_object_and_formats_are_bounded(
    mock_coordinator,
) -> None:
    model = mock_coordinator.model
    model.add_object("SOURCE", {"OBJTYP": SYSTIM_TYPE, "SOURCE": "URL"})
    clock = model.add_object(
        "CLOCK", {"OBJTYP": SYSTIM_TYPE, "CLK24A": "HR24", "DLSTIM": "OFF"}
    )
    model["SYS01"].update({"TIMZON": "-5.5", "SOURCE": "UNRELATED"})
    sensors = [
        e
        for e in build_sensors(mock_coordinator, list(model))
        if isinstance(e, ConfigurationSensor)
    ]
    by_key = {(s._pool_object.objnam, s._attribute_key): s for s in sensors}
    assert by_key[("SOURCE", "SOURCE")].native_value == "URL"
    assert ("SYS01", "SOURCE") not in by_key
    assert by_key[("CLOCK", "CLK24A")].native_value == "HR24"
    assert by_key[("SYS01", "TIMZON")].native_value == "-5.5"
    assert by_key[("SYS01", "TIMZON")].native_unit_of_measurement is None
    clock.update({"CLK24A": "24h"})
    assert by_key[("CLOCK", "CLK24A")].native_value is None
    clock.update({"CLK24A": "AMPM", "DLSTIM": "ON"})
    assert by_key[("CLOCK", "CLK24A")].native_value == "AMPM"
    assert by_key[("CLOCK", "DLSTIM")].native_value == "ON"
    # A DST setting transition does not synthesize a time-zone or timestamp change.
    assert by_key[("SYS01", "TIMZON")].native_value == "-5.5"


@pytest.mark.parametrize(
    "topology", [[], [BODY_TYPE], [BODY_TYPE, BODY_TYPE, HEATER_TYPE]]
)
def test_delay_and_solar_visibility_does_not_enable_commissioning(
    mock_coordinator, topology
) -> None:
    model = mock_coordinator.model
    model["SYS01"].update(
        {"VALVE": "OFF", "HEATING": "ON", "SASHP": "ON", "SASHP2": "INVALID"}
    )
    for index, objtype in enumerate(topology):
        model.add_object(f"TOPOLOGY{index}", {"OBJTYP": objtype})
    settings = [
        e
        for e in build_sensors(mock_coordinator, list(model))
        if isinstance(e, ConfigurationSensor)
    ]
    assert {e._attribute_key: e.native_value for e in settings} == {
        "VALVE": "OFF",
        "HEATING": "ON",
        "SASHP": "ON",
        "SASHP2": None,
    }
    assert all(e.entity_registry_enabled_default is False for e in settings)
    assert all(e.state_class is None for e in settings)
    assert not any(
        e._attribute_key in {"VALVE", "HEATING", "SASHP", "SASHP2"}
        for e in build_switches(mock_coordinator, list(model))
    )
    mock_coordinator.controller.request_changes.assert_not_called()


@pytest.mark.asyncio
async def test_priority_owner_changes_use_targeted_dispatch(
    hass: HomeAssistant, mock_write_ha_state
) -> None:
    """A competing owner's update must invalidate the original entity in HA."""
    entry = MagicMock()
    entry.entry_id = "advanced"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    coordinator._handler._is_connected = True
    coordinator._started = True
    owner = _owner(coordinator.model, "OFF")
    other = coordinator.model.add_object(
        "OTHER", {"OBJTYP": BODY_TYPE, MANOVR_ATTR: "INVALID"}
    )
    coordinator._known_objnams = {owner.objnam, other.objnam}
    switch = _priority_switches(coordinator)[0]
    switch.hass = hass
    await switch.async_added_to_hass()
    try:
        for value, available in (("ON", False), ("INVALID", True)):
            mock_write_ha_state.reset_mock()
            coordinator.async_set_updated_data(
                {other.objnam: other.update({MANOVR_ATTR: value})}
            )
            mock_write_ha_state.assert_called_once()
            assert switch.available is available
        mock_write_ha_state.reset_mock()
        coordinator.async_set_updated_data(
            {owner.objnam: owner.update({MANOVR_ATTR: "ON"})}
        )
        mock_write_ha_state.assert_called_once()
        assert switch.is_on is True
    finally:
        await switch.async_will_remove_from_hass()


@pytest.mark.asyncio
async def test_diagnostic_configuration_does_not_reuse_pre_disconnect_state(
    hass: HomeAssistant,
) -> None:
    entry = MagicMock()
    entry.entry_id = "advanced"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    system = coordinator.model.add_object(
        "SYSTEM", {"OBJTYP": SYSTEM_TYPE, "VALVE": "OFF"}
    )
    sensor = next(
        e
        for e in build_sensors(coordinator, list(coordinator.model))
        if isinstance(e, ConfigurationSensor)
    )
    assert sensor.native_value == "OFF"
    coordinator.async_set_connection_state(False)
    coordinator.async_set_connection_state(True)
    assert sensor.native_value is None
    system.update({"VALVE": "ON"})
    assert sensor.native_value == "ON"


def test_relationship_rows_never_become_manual_priority_owners(
    mock_coordinator,
) -> None:
    """Membership-row fields must not expand the equipment control surface."""
    mock_coordinator.model.add_object(
        "ROW", {"OBJTYP": CIRCGRP_TYPE, MANOVR_ATTR: "ON"}
    )
    assert _priority_switches(mock_coordinator) == []
    _owner(mock_coordinator.model)
    assert _priority_switches(mock_coordinator)[0].available
