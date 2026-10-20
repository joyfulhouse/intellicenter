"""Reconnect regressions through the real handler/controller and synthetic transport."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import ICConnectionError
import pytest

from custom_components.intellicenter.coordinator import IntelliCenterCoordinator
from custom_components.intellicenter.sensor import (
    ConfigurationSensor,
    _build_entities as build_sensors,
)
from custom_components.intellicenter.switch import (
    ManualPrioritySwitch,
    _build_entities as build_switches,
)

# Synthetic settings, not a captured device schema or a firmware capability claim.
_ADVANCED = {
    "SYSTEM": {
        "VALVE": "OFF",
        "HEATING": "ON",
        "SASHP": "ON",
        "SASHP2": "OFF",
        "TIMZON": "-5.5",
    },
    "OWNER": {"MANOVR": "ON"},
    "CLOCK": {"CLK24A": "HR24", "DLSTIM": "OFF"},
    "SOURCE": {"SOURCE": "URL"},
}
_TYPES = {
    "SYSTEM": "SYSTEM",
    "OWNER": "SYSTIM",
    "CLOCK": "SYSTIM",
    "SOURCE": "SYSTIM",
    "SENSOR": "SENSE",
}


def _snapshot():
    return [
        {"objnam": objnam, "params": {"OBJTYP": objtype, "SNAME": objnam}}
        for objnam, objtype in _TYPES.items()
    ]


def _transport(*, advanced):
    """Fake only wire I/O; use real start, reconcile, subscription and dispatch."""
    connection = MagicMock()
    connection.connected = False

    async def connect():
        connection.connected = True

    async def disconnect():
        connection.connected = False

    async def send_request(command, **kwargs):
        if command == "GetParamList":
            if kwargs["condition"] == "OBJTYP=SYSTEM":
                return {
                    "objectList": [
                        {
                            "objnam": "SYSTEM",
                            "params": {
                                "PROPNAME": "Synthetic pool",
                                "VER": "1.064",
                                "MODE": "ENGLISH",
                                "SNAME": "SYSTEM",
                            },
                        }
                    ]
                }
            assert kwargs["condition"] == ""
            return {"objectList": _snapshot()}
        assert command == "RequestParamList"  # No setup/reconnect writes.
        return {
            "objectList": [
                {
                    "objnam": obj["objnam"],
                    "params": {
                        **(advanced.get(obj["objnam"], {})),
                        **({"MANHT": "ON"} if obj["objnam"] == "SYSTEM" else {}),
                        **(
                            {"CALIB": "2", "SOURCE": "70", "PROBE": "ON"}
                            if obj["objnam"] == "SENSOR"
                            else {}
                        ),
                    },
                }
                for obj in kwargs["objectList"]
            ]
        }

    connection.connect = AsyncMock(side_effect=connect)
    connection.disconnect = AsyncMock(side_effect=disconnect)
    connection.send_request = AsyncMock(side_effect=send_request)
    return connection


@pytest.mark.asyncio
@pytest.mark.parametrize("fresh_readback", [False, True], ids=["omitted", "fresh"])
async def test_fast_reconnect_retains_objects_without_retaining_advanced_state(
    hass: HomeAssistant,
    fresh_readback: bool,
) -> None:
    """Reconnection before debounce must require current-generation readback."""
    entry = MagicMock()
    entry.entry_id = "advanced_reconnect"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    handler = coordinator._handler
    handler._time_between_reconnects = 0
    handler._disconnect_debounce_time = 60
    first = _transport(advanced=_ADVANCED)
    second = _transport(advanced=_ADVANCED if fresh_readback else {})

    with (
        patch("pyintellicenter.controller.ICConnection", side_effect=[first, second]),
        patch.object(
            handler, "on_disconnected", wraps=handler.on_disconnected
        ) as debounced,
        patch.object(
            handler, "on_reconnected", wraps=handler.on_reconnected
        ) as reconnected,
    ):
        try:
            await coordinator.async_start()
            retained = {obj.objnam: obj for obj in coordinator.model}
            switch = next(
                e
                for e in build_switches(coordinator, list(coordinator.model))
                if isinstance(e, ManualPrioritySwitch)
            )
            sensors = [
                e
                for e in build_sensors(coordinator, list(coordinator.model))
                if isinstance(e, ConfigurationSensor)
            ]
            assert len(sensors) == 8
            assert switch.available and switch.is_on is True

            # Deliver the callback registered by the real controller, without
            # invoking the debounced coordinator callback ourselves.
            first.connected = False
            first.set_disconnect_callback.call_args.args[0](ICConnectionError("lost"))
            # The immediate hook must run synchronously before any reconnect
            # snapshot/backfill can arrive, regardless of the debounce callback.
            for objnam, params in _ADVANCED.items():
                assert all(retained[objnam][key] is None for key in params)
            assert switch.is_on is None
            assert not switch.available
            assert all(e.native_value is None for e in sensors)
            reconnect_task = handler._starter_task
            assert reconnect_task is not None
            await asyncio.wait_for(asyncio.shield(reconnect_task), timeout=2)
            assert coordinator.connected
            assert handler._disconnect_debounce_task is None
            reconnected.assert_called_once()
            debounced.assert_not_called()
            for objnam, obj in retained.items():
                assert coordinator.model[objnam] is obj
            assert retained["SYSTEM"]["MANHT"] == "ON"
            assert retained["SENSOR"]["CALIB"] == "2"

            if fresh_readback:
                # Even identical readback must survive the reconnect announcement.
                assert switch.available and switch.is_on is True
                assert all(e.native_value is not None for e in sensors)
            else:
                assert switch.is_on is None
                assert not switch.available
                assert all(e.native_value is None for e in sensors)
                for objnam, params in _ADVANCED.items():
                    assert all(retained[objnam][key] is None for key in params)
                with patch.object(
                    coordinator.controller, "request_changes", new_callable=AsyncMock
                ) as write:
                    with pytest.raises(HomeAssistantError):
                        await switch.async_turn_off()
                    write.assert_not_awaited()
                # Independent NotifyList readback restores the same entity.
                second.set_notification_callback.call_args.args[0](
                    {
                        "command": "NotifyList",
                        "objectList": [
                            {"objnam": objnam, "params": dict(params)}
                            for objnam, params in _ADVANCED.items()
                        ],
                    }
                )
                assert switch.available and switch.is_on is True
                assert all(e.native_value is not None for e in sensors)
        finally:
            await coordinator.async_stop()


@pytest.mark.asyncio
async def test_stopped_handler_ignores_disconnect_without_invalidating_settings(
    hass: HomeAssistant,
) -> None:
    """A callback after stop must neither invalidate state nor restart work."""
    entry = MagicMock()
    entry.entry_id = "advanced_stopped"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.186")
    owner = coordinator.model.add_object("OWNER", {"OBJTYP": "SYSTIM", "MANOVR": "ON"})
    coordinator._handler._stopped = True
    coordinator._handler._on_disconnect(coordinator.controller, None)
    assert owner["MANOVR"] == "ON"
    assert coordinator._handler._starter_task is None
    assert coordinator._handler._disconnect_debounce_task is None
