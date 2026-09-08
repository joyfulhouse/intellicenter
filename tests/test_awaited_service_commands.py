"""Regression tests for awaited IntelliCenter service commands (issue #133)."""

import asyncio
from collections.abc import Awaitable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    BODY_TYPE,
    EXTINSTR_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HITMP_ATTR,
    NORMAL_ATTR,
    PMPCIRC_TYPE,
    POSIT_ATTR,
    SELECT_ATTR,
    SPEED_ATTR,
    STATUS_ATTR,
    ICCommandError,
    ICConnectionError,
    ICTimeoutError,
    PoolObject,
)
import pytest

from custom_components.intellicenter.climate import PoolClimate
from custom_components.intellicenter.cover import PoolCover
from custom_components.intellicenter.number import PoolNumber, PumpSpeedNumber
from custom_components.intellicenter.select import PumpModeSelect
from custom_components.intellicenter.switch import PoolCircuit

pytestmark = pytest.mark.asyncio


class _HeaterModel(dict[str, PoolObject]):
    """Provide PoolModel enumeration while retaining real dict lookups."""

    def get_by_type(self, _obj_type: str) -> list[PoolObject]:
        return []


def _block_controller_request(
    mock_coordinator: MagicMock,
) -> tuple[asyncio.Event, asyncio.Event]:
    """Block request_changes until the test models a panel acknowledgement."""
    started = asyncio.Event()
    acknowledged = asyncio.Event()

    async def wait_for_panel(*_args: Any) -> None:
        started.set()
        await acknowledged.wait()

    mock_coordinator.controller.request_changes.side_effect = wait_for_panel
    return started, acknowledged


async def _assert_service_is_pending(task: asyncio.Task[None]) -> None:
    """Assert a service call cannot return while its panel command is pending."""
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=0.01)


async def test_switch_service_waits_while_optimistic_state_renders(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """The optimistic switch state renders without completing the service call."""
    started, acknowledged = _block_controller_request(mock_coordinator)
    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass

    service_task = asyncio.create_task(switch.async_turn_on())
    await asyncio.wait_for(started.wait(), timeout=0.5)
    try:
        assert switch.is_on is True
        assert mock_write_ha_state.called
        await _assert_service_is_pending(service_task)
    finally:
        acknowledged.set()
        await service_task
        await hass.async_block_till_done()


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(ICConnectionError("connection lost"), id="connection-lost"),
        pytest.param(ICTimeoutError("request timed out"), id="protocol-timeout"),
        pytest.param(ICCommandError("command rejected"), id="command-rejected"),
    ],
)
async def test_switch_failure_reaches_caller_and_reverts_optimistic_state(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    failure: Exception,
) -> None:
    """Known panel failures become actionable HA errors and restore real state."""
    mock_coordinator.controller.request_changes.side_effect = failure
    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass

    with pytest.raises(HomeAssistantError) as raised:
        await switch.async_turn_on()

    assert raised.value.translation_domain == "intellicenter"
    assert raised.value.translation_key == "command_failed"
    assert raised.value.__cause__ is failure
    assert switch._optimistic_state is None
    assert switch.is_on is False
    assert mock_write_ha_state.call_count == 2


async def test_switch_acknowledgement_completes_then_push_reconciles(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """A panel acknowledgement completes service before its push echo reconciles."""
    started, acknowledged = _block_controller_request(mock_coordinator)
    mock_coordinator.model = {pool_object_switch.objnam: pool_object_switch}
    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass

    service_task = asyncio.create_task(switch.async_turn_on())
    await asyncio.wait_for(started.wait(), timeout=0.5)
    try:
        await _assert_service_is_pending(service_task)
    finally:
        acknowledged.set()
        await service_task
        await hass.async_block_till_done()

    assert switch._optimistic_state is True
    assert pool_object_switch[STATUS_ATTR] == "OFF"

    pool_object_switch.update({STATUS_ATTR: "ON"})
    mock_coordinator.data = {pool_object_switch.objnam: {STATUS_ATTR: "ON"}}
    switch._handle_coordinator_update()

    assert switch._optimistic_state is None
    assert switch.is_on is True
    assert mock_write_ha_state.call_count == 2


async def test_switch_cancellation_reverts_optimistic_state(
    hass: HomeAssistant,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Cancellation restores real state when a queued command never completes."""
    started = asyncio.Event()
    dispatch_allowed = asyncio.Event()
    completed_wire_dispatches = 0

    async def wait_for_dispatch(*_args: Any) -> None:
        nonlocal completed_wire_dispatches
        started.set()
        await dispatch_allowed.wait()
        completed_wire_dispatches += 1

    mock_coordinator.controller.request_changes.side_effect = wait_for_dispatch
    switch = PoolCircuit(mock_coordinator, pool_object_switch)
    switch.hass = hass

    service_task = asyncio.create_task(switch.async_turn_on())
    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert switch.is_on is True

    service_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await service_task

    assert completed_wire_dispatches == 0
    assert switch._optimistic_state is None
    assert switch.is_on is False
    assert mock_write_ha_state.call_count == 2


def _make_platform_service(
    platform: str,
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> Awaitable[None]:
    """Create one representative service command for each affected platform."""
    if platform == "cover":
        pool_object = PoolObject(
            "COVER1",
            {
                "OBJTYP": EXTINSTR_TYPE,
                "SUBTYP": "COVER",
                "SNAME": "Pool Cover",
                POSIT_ATTR: "OFF",
                NORMAL_ATTR: "ON",
            },
        )
        entity = PoolCover(mock_coordinator, pool_object)
        entity.hass = hass
        return entity.async_open_cover()

    if platform == "climate":
        pool_object = PoolObject(
            "POOL1",
            {
                "OBJTYP": BODY_TYPE,
                "SNAME": "Pool",
                STATUS_ATTR: "ON",
                HEATER_ATTR: "HTR01",
            },
        )
        entity = PoolClimate(mock_coordinator, pool_object, ["HTR01"])
        entity.hass = hass
        return entity.async_set_hvac_mode(HVACMode.OFF)

    if platform == "climate-preset":
        pool_object = PoolObject(
            "POOL1",
            {
                "OBJTYP": BODY_TYPE,
                "SNAME": "Pool",
                STATUS_ATTR: "ON",
                HEATER_ATTR: "HTR01",
            },
        )
        heater = PoolObject("HTR01", {"OBJTYP": HEATER_TYPE, "SNAME": "UltraTemp"})
        mock_coordinator.model = _HeaterModel({heater.objnam: heater})
        entity = PoolClimate(mock_coordinator, pool_object, [heater.objnam])
        entity.hass = hass
        return entity.async_set_preset_mode("UltraTemp")

    if platform == "climate-heat-no-heater":
        pool_object = PoolObject(
            "POOL1",
            {
                "OBJTYP": BODY_TYPE,
                "SNAME": "Pool",
                STATUS_ATTR: "ON",
                HEATER_ATTR: "",
            },
        )
        entity = PoolClimate(mock_coordinator, pool_object, ["HTR01"])
        entity.hass = hass
        return entity.async_set_hvac_mode(HVACMode.HEAT)

    if platform == "number":
        pool_object = PoolObject(
            "POOL1",
            {
                "OBJTYP": BODY_TYPE,
                "SNAME": "Pool",
                HITMP_ATTR: "85",
            },
        )
        entity = PoolNumber(
            mock_coordinator,
            pool_object,
            attribute_key=HITMP_ATTR,
        )
        entity.hass = hass
        return entity.async_set_native_value(86)

    pool_object = PoolObject(
        "PMPCIRC01",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "SNAME": "Pool Pump Circuit",
            SELECT_ATTR: "GPM",
            SPEED_ATTR: "80",
        },
    )
    if platform == "pump-speed-number":
        entity = PumpSpeedNumber(
            mock_coordinator,
            pool_object,
            pump_name="Pool Pump",
            circuit_name="Pool",
            rpm_min=450,
            rpm_max=3450,
            gpm_min=15,
            gpm_max=140,
        )
        entity.hass = hass
        return entity.async_set_native_value(90)

    entity = PumpModeSelect(
        mock_coordinator,
        pool_object,
        pump_name="Pool Pump",
        circuit_name="Pool",
    )
    entity.hass = hass
    return entity.async_select_option("RPM")


@pytest.mark.parametrize(
    "platform",
    [
        "cover",
        "climate",
        "climate-preset",
        "climate-heat-no-heater",
        "number",
        "pump-speed-number",
        "select",
    ],
)
async def test_platform_service_waits_for_panel_acknowledgement(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    platform: str,
) -> None:
    """Every remaining request-changes handler awaits the panel response."""
    started, acknowledged = _block_controller_request(mock_coordinator)
    mock_coordinator.controller.refresh_pump_circuit_speed = AsyncMock()

    service_task = asyncio.create_task(
        _make_platform_service(platform, hass, mock_coordinator)
    )
    await asyncio.wait_for(started.wait(), timeout=0.5)
    try:
        await _assert_service_is_pending(service_task)
    finally:
        acknowledged.set()
        await service_task
        await hass.async_block_till_done()

    if platform == "select":
        mock_coordinator.controller.refresh_pump_circuit_speed.assert_awaited_once_with(
            "PMPCIRC01"
        )


async def test_select_refresh_timeout_after_write_does_not_fail_service(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A display-only refresh timeout cannot fail an acknowledged mode write."""
    mock_coordinator.controller.refresh_pump_circuit_speed = AsyncMock(
        side_effect=ICTimeoutError("speed refresh timed out")
    )

    await _make_platform_service("select", hass, mock_coordinator)

    mock_coordinator.controller.request_changes.assert_awaited_once_with(
        "PMPCIRC01", {SELECT_ATTR: "RPM"}
    )
    mock_coordinator.controller.refresh_pump_circuit_speed.assert_awaited_once_with(
        "PMPCIRC01"
    )


@pytest.mark.parametrize(
    "platform", ["cover", "climate", "number", "select", "pump-speed-number"]
)
async def test_platform_failure_is_translated(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    platform: str,
) -> None:
    """Representative platform writes translate library connection failures."""
    mock_coordinator.controller.request_changes.side_effect = ICConnectionError(
        "panel disconnected"
    )
    if platform == "select":
        mock_coordinator.controller.refresh_pump_circuit_speed = AsyncMock()

    with pytest.raises(HomeAssistantError) as raised:
        await _make_platform_service(platform, hass, mock_coordinator)

    assert raised.value.translation_domain == "intellicenter"
    assert raised.value.translation_key == "command_failed"
    if platform == "select":
        mock_coordinator.controller.refresh_pump_circuit_speed.assert_not_awaited()
