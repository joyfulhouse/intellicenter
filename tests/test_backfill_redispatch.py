"""Regression tests for deferred entity builders after attribute backfill."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import PMPCIRC_TYPE, PUMP_TYPE, PoolModel, PoolObject
import pytest

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
    "SUBTYP": "VSF",
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


async def _start_with_initial_pump(
    hass: HomeAssistant, telemetry: Mapping[str, str]
) -> tuple[IntelliCenterCoordinator, PoolObject, list[Any]]:
    """Start a coordinator whose first connect discovers an existing pump."""
    coordinator = _make_coordinator(hass)
    coordinator._started = False
    initial = {**SPARSE_PUMP, **telemetry}
    pump = coordinator.model.add_object(PUMP_OBJNAM, initial)
    assert pump is not None
    with patch.object(coordinator._handler, "start"):
        await coordinator.async_start()
    added = await _setup_sensor_platform(hass, coordinator)
    return coordinator, pump, added


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
        and entity._attribute_key in {"PWR", "RPM", "GPM"}
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
    assert {"PWR", "RPM"} <= coordinator._pending_redispatch[PUMP_OBJNAM]


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [("RPM", "PWR"), ("PWR", "RPM")],
)
async def test_separate_reordered_backfill_builds_each_eligible_sensor_once(
    hass: HomeAssistant,
    first_key: str,
    second_key: str,
) -> None:
    """Separate telemetry deliveries build both sensors in either order."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)

    _apply_update(coordinator, pump, {"STATUS": "4"})
    values = {"PWR": "850", "RPM": "2400"}
    _apply_update(coordinator, pump, {first_key: values[first_key]})
    assert _telemetry_keys(added) == [first_key]

    _apply_update(coordinator, pump, {second_key: values[second_key]})

    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]
    assert _telemetry_keys(added).count("PWR") == 1
    assert _telemetry_keys(added).count("RPM") == 1
    assert {"PWR", "RPM"} <= coordinator._pending_redispatch[PUMP_OBJNAM]
    assert sum(1 for _obj in coordinator.model) == 1


async def test_later_gpm_key_builds_sensor_after_partial_backfill(
    hass: HomeAssistant,
) -> None:
    """A GPM key omitted from backfill can create its sensor when it arrives."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)

    _apply_update(coordinator, pump, {"PWR": "850", "RPM": "2400"})
    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]

    _apply_update(coordinator, pump, {"GPM": "60"})

    assert sorted(_telemetry_keys(added)) == ["GPM", "PWR", "RPM"]
    assert _telemetry_keys(added).count("GPM") == 1
    assert {"GPM", "PWR", "RPM"} <= coordinator._pending_redispatch[PUMP_OBJNAM]


async def test_falsy_initial_power_redispatches_when_truthy(
    hass: HomeAssistant,
) -> None:
    """A pump power sensor is built when its initially empty value becomes usable."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    initial = {**SPARSE_PUMP, "PWR": ""}
    pump = coordinator.model.add_object(PUMP_OBJNAM, initial)
    assert pump is not None

    coordinator.async_set_updated_data({PUMP_OBJNAM: initial})
    assert _telemetry_keys(added) == []

    _apply_update(coordinator, pump, {"PWR": "850"})

    assert _telemetry_keys(added) == ["PWR"]


async def test_initial_setup_falsy_power_redispatches_when_truthy(
    hass: HomeAssistant,
) -> None:
    """An initially deferred pump sensor is built without reloading the entry."""
    coordinator, pump, added = await _start_with_initial_pump(hass, {"PWR": ""})

    assert _telemetry_keys(added) == []

    _apply_update(coordinator, pump, {"PWR": "250"})

    assert _telemetry_keys(added) == ["PWR"]


@pytest.mark.parametrize(
    (
        "initial_telemetry",
        "updates",
        "expected_initial",
        "expected_after_updates",
        "expected_builder_calls",
    ),
    [
        pytest.param(
            {"PWR": "250"},
            [{"PWR": "275"}],
            ["PWR"],
            [["PWR"]],
            [1],
            id="truthy-at-setup-does-not-rebuild-on-churn",
        ),
        pytest.param(
            {"PWR": ""},
            [{"PWR": "250"}],
            [],
            [["PWR"]],
            [2],
            id="falsy-at-setup-builds-on-truthy-transition",
        ),
        pytest.param(
            {"PWR": "", "RPM": ""},
            [{"PWR": "250"}, {"RPM": "2400"}],
            [],
            [["PWR"], ["PWR", "RPM"]],
            [2, 3],
            id="second-tracked-key-rebuilds-after-first-resolves",
        ),
        pytest.param(
            {"PWR": ""},
            [{"PWR": "250"}, {"PWR": "275"}],
            [],
            [["PWR"], ["PWR"]],
            [2, 2],
            id="usable-key-does-not-rebuild-on-later-churn",
        ),
    ],
)
async def test_initial_setup_redispatch_transitions(
    hass: HomeAssistant,
    initial_telemetry: Mapping[str, str],
    updates: list[Mapping[str, str]],
    expected_initial: list[str],
    expected_after_updates: list[list[str]],
    expected_builder_calls: list[int],
) -> None:
    """Initial objects rebuild only when a tracked attribute becomes usable."""
    with patch(
        "custom_components.intellicenter.sensor._build_entities",
        wraps=_build_entities,
    ) as builder:
        coordinator, pump, added = await _start_with_initial_pump(
            hass, initial_telemetry
        )
        assert _telemetry_keys(added) == expected_initial
        assert builder.call_count == 1

        for attributes, expected_keys, expected_calls in zip(
            updates,
            expected_after_updates,
            expected_builder_calls,
            strict=True,
        ):
            _apply_update(coordinator, pump, attributes)
            assert _telemetry_keys(added) == expected_keys
            assert builder.call_count == expected_calls


async def test_initial_setup_skips_complete_truthy_object_bookkeeping(
    hass: HomeAssistant,
) -> None:
    """A complete usable initial object does not occupy deferred state."""
    coordinator = _make_coordinator(hass)
    coordinator._started = False
    non_slotted_tracked = DEFAULT_ATTRIBUTES_MAP[PUMP_TYPE] - {"OBJTYP", "SUBTYP"}
    initial = {
        "OBJTYP": PUMP_TYPE,
        "SUBTYP": "VSF",
        **dict.fromkeys(non_slotted_tracked, "1"),
    }
    assert coordinator.model.add_object(PUMP_OBJNAM, initial) is not None

    with patch.object(coordinator._handler, "start"):
        await coordinator.async_start()

    assert PUMP_OBJNAM not in coordinator._pending_redispatch
    assert PUMP_OBJNAM not in coordinator._pending_truthy_redispatch


async def test_initial_setup_prunes_resolved_bookkeeping(
    hass: HomeAssistant,
) -> None:
    """The last deferred tracked value removes the object's pending state."""
    coordinator = _make_coordinator(hass)
    coordinator._started = False
    non_slotted_tracked = DEFAULT_ATTRIBUTES_MAP[PUMP_TYPE] - {"OBJTYP", "SUBTYP"}
    initial = {
        "OBJTYP": PUMP_TYPE,
        "SUBTYP": "VSF",
        **dict.fromkeys(non_slotted_tracked, "1"),
        "PWR": "",
    }
    obj = coordinator.model.add_object(PUMP_OBJNAM, initial)
    assert obj is not None

    with patch.object(coordinator._handler, "start"):
        await coordinator.async_start()
    assert PUMP_OBJNAM in coordinator._pending_redispatch

    changed = obj.update({"PWR": "250"})
    assert changed
    coordinator.async_set_updated_data({PUMP_OBJNAM: changed})

    assert PUMP_OBJNAM not in coordinator._pending_redispatch
    assert PUMP_OBJNAM not in coordinator._pending_truthy_redispatch


async def test_non_telemetry_key_does_not_consume_later_sensor_retries(
    hass: HomeAssistant,
) -> None:
    """An earlier tracked configuration key does not block telemetry builders."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)

    _apply_update(coordinator, pump, {"PRIMTIM": "5"})
    assert _telemetry_keys(added) == []

    _apply_update(coordinator, pump, {"RPM": "2400"})
    _apply_update(coordinator, pump, {"PWR": "850"})

    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]
    assert _telemetry_keys(added).count("PWR") == 1
    assert _telemetry_keys(added).count("RPM") == 1


async def test_delayed_parent_limits_redispatch_pmpcirc_dependent(
    hass: HomeAssistant,
) -> None:
    """Separate parent limit keys eventually build its PMPCIRC mode select."""
    from custom_components.intellicenter.select import async_setup_entry as setup_select

    coordinator = _make_coordinator(hass)
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()
    added: list[Any] = []
    await setup_select(hass, entry, added.extend)

    child_params = {
        "OBJTYP": PMPCIRC_TYPE,
        "PARENT": PUMP_OBJNAM,
        "CIRCUIT": "SPA134",
        "SELECT": "RPM",
        "SPEED": "2400",
        "GPM": "60",
    }
    child = coordinator.model.add_object("PMPCIRC134", child_params)
    assert child is not None
    coordinator.async_set_updated_data({"PMPCIRC134": child_params})
    pump = _discover_sparse_pump(coordinator)

    _apply_update(coordinator, pump, {"MAX": "3450"})
    assert [e for e in added if e._pool_object.objnam == "PMPCIRC134"] == []

    _apply_update(coordinator, pump, {"MAXF": "140"})

    child_entities = [e for e in added if e._pool_object.objnam == "PMPCIRC134"]
    assert len(child_entities) == 1
    assert child_entities[0].unique_id.endswith("_PMPCIRC134_SELECT")


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
        assert builder.call_count == 2
        _apply_update(coordinator, pump, {"STATUS": "4"})
        assert builder.call_count == 2
        _apply_update(coordinator, pump, {"RPM": "2400"})
        assert builder.call_count == 3
        _apply_update(coordinator, pump, {"PWR": "850"})
        calls_after_backfill = builder.call_count

        _apply_update(coordinator, pump, {"RPM": "2600"})
        _apply_update(coordinator, pump, {"PWR": "875"})

    assert calls_after_backfill == 4
    assert builder.call_count == calls_after_backfill
    assert sorted(_telemetry_keys(added)) == ["PWR", "RPM"]


async def test_removal_clears_outstanding_backfill_state(
    hass: HomeAssistant,
) -> None:
    """Removing a sparse object clears its deferred-builder bookkeeping."""
    coordinator = _make_coordinator(hass)
    added = await _setup_sensor_platform(hass, coordinator)
    pump = _discover_sparse_pump(coordinator)
    _apply_update(coordinator, pump, {"PRIMTIM": "5"})
    assert "PRIMTIM" in coordinator._pending_redispatch[PUMP_OBJNAM]

    coordinator.model.remove_object(PUMP_OBJNAM)
    coordinator.async_set_updated_data({PUMP_OBJNAM: None})

    assert PUMP_OBJNAM not in coordinator._pending_redispatch
    assert PUMP_OBJNAM not in coordinator._known_objnams
    assert coordinator.model[PUMP_OBJNAM] is None
    assert _telemetry_keys(added) == []
