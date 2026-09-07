"""Regression tests for deferred entity builders after attribute backfill."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import PUMP_TYPE, PoolModel, PoolObject

from custom_components.intellicenter.coordinator import (
    DEFAULT_ATTRIBUTES_MAP,
    IntelliCenterCoordinator,
)
from custom_components.intellicenter.sensor import (
    _build_entities,
    async_setup_entry,
)

PUMP_OBJNAM = "PUMP134"
SPARSE_PUMP = {
    "OBJTYP": PUMP_TYPE,
    "SUBTYP": "SPEED",
    "SNAME": "Backfill Pump",
    "STATUS": "10",
}


def _make_coordinator(hass: HomeAssistant) -> IntelliCenterCoordinator:
    """Build a started coordinator with an initially empty real pool model."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "issue_134"
    entry.data = {CONF_HOST: "192.0.2.134"}

    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.134")
    coordinator._model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    coordinator._known_objnams = set()
    coordinator._started = True
    return coordinator


async def _setup_sensor_platform(
    hass: HomeAssistant, coordinator: IntelliCenterCoordinator
) -> list[Any]:
    """Set up the actual sensor builder and return dynamically added entities."""
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()
    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)
    return added


def _discover_sparse_pump(coordinator: IntelliCenterCoordinator) -> PoolObject:
    """Apply the sparse notification that introduces a runtime pump."""
    pump = coordinator.model.add_object(PUMP_OBJNAM, dict(SPARSE_PUMP))
    assert pump is not None
    coordinator.async_set_updated_data({PUMP_OBJNAM: dict(SPARSE_PUMP)})
    return pump


def _apply_update(
    coordinator: IntelliCenterCoordinator,
    pump: PoolObject,
    attributes: Mapping[str, str],
) -> None:
    """Apply an update to the real model before dispatching its changed payload."""
    changed = pump.update(dict(attributes))
    assert changed
    coordinator.async_set_updated_data({PUMP_OBJNAM: changed})


def _telemetry_keys(added: list[Any]) -> list[str]:
    """Return telemetry keys in entity-registration order."""
    return [
        entity._attribute_key
        for entity in added
        if entity._pool_object.objnam == PUMP_OBJNAM
        and entity._attribute_key in {"PWR", "RPM"}
    ]


async def test_status_notifications_do_not_consume_backfill_retry(
    hass: HomeAssistant,
) -> None:
    """STATUS races before backfill still create PWR and RPM exactly once."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)

    pump = _discover_sparse_pump(coordinator)
    assert _telemetry_keys(added) == []
    assert PUMP_OBJNAM in coordinator._pending_redispatch

    _apply_update(coordinator, pump, {"STATUS": "4"})
    _apply_update(coordinator, pump, {"STATUS": "10"})
    assert _telemetry_keys(added) == []
    assert PUMP_OBJNAM in coordinator._pending_redispatch

    _apply_update(coordinator, pump, {"PWR": "850", "RPM": "2400"})
    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]
    assert _telemetry_keys(added).count("PWR") == 1
    assert _telemetry_keys(added).count("RPM") == 1
    assert PUMP_OBJNAM not in coordinator._pending_redispatch


async def test_partial_reordered_backfill_builds_eligible_sensors(
    hass: HomeAssistant,
) -> None:
    """A partial, reordered backfill builds eligible sensors without a reload."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)

    # Real devices need not return every tracked key (notably GPM). The response
    # order is immaterial and a partial response must still count as backfill,
    # even when an ordinary notification was delivered first.
    _apply_update(coordinator, pump, {"STATUS": "4"})
    _apply_update(coordinator, pump, {"RPM": "2400", "PWR": "850"})

    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]
    assert PUMP_OBJNAM not in coordinator._pending_redispatch
    assert sum(1 for _obj in coordinator.model) == 1


async def test_telemetry_after_backfill_does_not_rebuild_sensor_model(
    hass: HomeAssistant,
) -> None:
    """Value-only telemetry after completion does not invoke the builder again."""
    coordinator = _make_coordinator(hass)

    with patch(
        "custom_components.intellicenter.sensor._build_entities",
        wraps=_build_entities,
    ) as builder:
        added = await _setup_sensor_platform(hass, coordinator)
        pump = _discover_sparse_pump(coordinator)
        _apply_update(coordinator, pump, {"STATUS": "4"})
        _apply_update(coordinator, pump, {"PWR": "850", "RPM": "2400"})
        calls_after_backfill = builder.call_count

        _apply_update(coordinator, pump, {"RPM": "2600"})
        _apply_update(coordinator, pump, {"PWR": "875"})

    assert calls_after_backfill == 3
    assert builder.call_count == calls_after_backfill
    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]


async def test_removal_clears_outstanding_backfill_state(
    hass: HomeAssistant,
) -> None:
    """Removing a sparse object clears its deferred-builder bookkeeping."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)
    assert PUMP_OBJNAM in coordinator._pending_redispatch

    _apply_update(coordinator, pump, {"STATUS": "4"})
    assert PUMP_OBJNAM in coordinator._pending_redispatch

    coordinator.model.remove_object(PUMP_OBJNAM)
    coordinator.async_set_updated_data({PUMP_OBJNAM: None})

    assert not coordinator._pending_redispatch
    assert PUMP_OBJNAM not in coordinator._known_objnams
    assert coordinator.model[PUMP_OBJNAM] is None
    assert _telemetry_keys(added) == []
