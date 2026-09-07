"""Regression tests for object-targeted coordinator dispatch (issue #136)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from pyintellicenter import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    PUMP_TYPE,
    SENSE_TYPE,
    PoolObject,
)
import pytest

from custom_components.intellicenter import PoolEntity
from custom_components.intellicenter.climate import PoolClimate
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator
from custom_components.intellicenter.sensor import async_setup_entry as setup_sensors

pytestmark = pytest.mark.asyncio


def _make_coordinator(hass: HomeAssistant) -> IntelliCenterCoordinator:
    """Return a coordinator whose current model is the known connected snapshot."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100"}
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.168.1.100")
    coordinator._handler._is_connected = True
    return coordinator


def _mark_started(coordinator: IntelliCenterCoordinator) -> None:
    """Seed dynamic-object bookkeeping as async_start does after connecting."""
    coordinator._known_objnams = {obj.objnam for obj in coordinator.model}
    coordinator._started = True


class _CountingPoolEntity(PoolEntity):
    """Pool entity that counts coordinator callbacks and state writes."""

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        attribute_key: str = "STATUS",
    ) -> None:
        self.update_invocations = 0
        self.state_writes = 0
        super().__init__(coordinator, pool_object, attribute_key=attribute_key)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.update_invocations += 1
        super()._handle_coordinator_update()

    @callback
    def async_write_ha_state(self) -> None:
        self.state_writes += 1


class _CountingClimate(PoolClimate):
    """Climate entity that counts coordinator callbacks and state writes."""

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        heater_list: list[str],
    ) -> None:
        self.update_invocations = 0
        self.state_writes = 0
        super().__init__(coordinator, pool_object, heater_list)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.update_invocations += 1
        super()._handle_coordinator_update()

    @callback
    def async_write_ha_state(self) -> None:
        self.state_writes += 1


async def _register(hass: HomeAssistant, *entities: PoolEntity) -> None:
    """Register entity coordinator listeners without an entity platform."""
    for entity in entities:
        entity.hass = hass
        await entity.async_added_to_hass()


@pytest.mark.parametrize("unrelated_count", [10, 100, 1000])
async def test_selective_dispatch_scaling(
    hass: HomeAssistant, unrelated_count: int
) -> None:
    """One pump telemetry push invokes one listener regardless of entity count."""
    coordinator = _make_coordinator(hass)
    pump = coordinator.model.add_object(
        "PUMP1",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VSF",
            "SNAME": "Pool Pump",
            "STATUS": "10",
            "RPM": "2400",
        },
    )
    assert pump is not None
    interested = _CountingPoolEntity(coordinator, pump, attribute_key="RPM")

    unrelated: list[_CountingPoolEntity] = []
    for index in range(unrelated_count):
        obj = coordinator.model.add_object(
            f"C{index:04d}",
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GENERIC",
                "SNAME": f"Circuit {index}",
                "STATUS": "OFF",
            },
        )
        assert obj is not None
        unrelated.append(_CountingPoolEntity(coordinator, obj))

    _mark_started(coordinator)
    await _register(hass, interested, *unrelated)

    pump.update({"RPM": "2600"})
    coordinator.async_set_updated_data({"PUMP1": {"RPM": "2600"}})

    assert interested.update_invocations == 1
    assert sum(entity.update_invocations for entity in unrelated) == 0


async def test_heater_cool_routes_only_to_dependent_climate(
    hass: HomeAssistant,
) -> None:
    """A heater COOL push refreshes its climate without touching an unrelated entity."""
    coordinator = _make_coordinator(hass)
    body = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "LSTTMP": "80",
            "LOTMP": "82",
            "HITMP": "86",
        },
    )
    heater = coordinator.model.add_object(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "ULTRA",
            "SNAME": "UltraTemp",
            "BODY": "POOL1",
            "COOL": "OFF",
        },
    )
    circuit = coordinator.model.add_object(
        "C0001",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Unrelated",
            "STATUS": "OFF",
        },
    )
    assert body is not None and heater is not None and circuit is not None
    climate = _CountingClimate(coordinator, body, ["HTR01"])
    unrelated = _CountingPoolEntity(coordinator, circuit)
    _mark_started(coordinator)
    await _register(hass, climate, unrelated)

    heater.update({"COOL": "ON"})
    coordinator.async_set_updated_data({"HTR01": {"COOL": "ON"}})

    assert climate.update_invocations == 1
    assert climate.state_writes == 1
    assert unrelated.update_invocations == 0


async def test_connection_transitions_broadcast_after_targeted_update(
    hass: HomeAssistant,
) -> None:
    """Ordinary updates are targeted, but loss and recovery reach every entity."""
    coordinator = _make_coordinator(hass)
    entities: list[_CountingPoolEntity] = []
    for index in range(3):
        obj = coordinator.model.add_object(
            f"C{index:04d}",
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GENERIC",
                "SNAME": f"Circuit {index}",
                "STATUS": "OFF",
            },
        )
        assert obj is not None
        entities.append(_CountingPoolEntity(coordinator, obj))
    _mark_started(coordinator)
    await _register(hass, *entities)

    coordinator.async_set_updated_data({"C0000": {"STATUS": "ON"}})
    assert [entity.update_invocations for entity in entities] == [1, 0, 0]

    for entity in entities:
        entity.update_invocations = 0
    coordinator._handler._is_connected = False
    coordinator.async_set_connection_state(False)
    assert [entity.update_invocations for entity in entities] == [1, 1, 1]
    assert all(not entity.available for entity in entities)

    for entity in entities:
        entity.update_invocations = 0
    coordinator._handler._is_connected = True
    coordinator.async_set_connection_state(True)
    assert [entity.update_invocations for entity in entities] == [1, 1, 1]
    assert all(entity.available for entity in entities)


async def test_runtime_add_remove_and_reconnect_reconciliation(
    hass: HomeAssistant,
) -> None:
    """Changed IDs build/retire equipment; reconnect still performs a full scan."""
    coordinator = _make_coordinator(hass)
    _mark_started(coordinator)
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()
    added: list[PoolEntity] = []
    await setup_sensors(hass, entry, added.extend)
    added.clear()

    sensor = coordinator.model.add_object(
        "SENSE2",
        {
            "OBJTYP": SENSE_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Water Temp",
            "SOURCE": "80",
        },
    )
    assert sensor is not None
    with patch.object(
        coordinator,
        "_async_detect_new_objects",
        wraps=coordinator._async_detect_new_objects,
    ) as detect:
        coordinator.async_set_updated_data({"SENSE2": {"SOURCE": "80"}})
        detect.assert_called_once_with({"SENSE2"})
    sensor_entities = [
        entity for entity in added if entity._pool_object.objnam == "SENSE2"
    ]
    assert sensor_entities

    target = sensor_entities[0]
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        "sensor", "intellicenter", target.unique_id
    )
    target.entity_id = registry_entry.entity_id
    target.hass = hass

    coordinator.model.remove_object("SENSE2")
    coordinator.async_set_updated_data({"SENSE2": None})
    assert registry.async_get(registry_entry.entity_id) is None

    added.clear()
    sensor = coordinator.model.add_object(
        "SENSE2",
        {
            "OBJTYP": SENSE_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Water Temp",
            "SOURCE": "81",
        },
    )
    assert sensor is not None
    with patch.object(
        coordinator,
        "_async_detect_new_objects",
        wraps=coordinator._async_detect_new_objects,
    ) as detect:
        coordinator.async_set_connection_state(True)
        detect.assert_called_once_with()
    assert [entity for entity in added if entity._pool_object.objnam == "SENSE2"]


async def test_incomplete_runtime_object_redispatches_on_backfill(
    hass: HomeAssistant,
) -> None:
    """Changed-ID detection keeps #134's one-shot incomplete-object redispatch."""
    coordinator = _make_coordinator(hass)
    _mark_started(coordinator)
    dispatched: list[list[str]] = []
    coordinator.async_add_new_objects_listener(
        lambda objects: dispatched.append([obj.objnam for obj in objects])
    )

    pump = coordinator.model.add_object(
        "PUMP3",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "SPEED",
            "SNAME": "Booster Pump",
            "STATUS": "10",
        },
    )
    assert pump is not None
    with patch.object(
        coordinator,
        "_async_detect_new_objects",
        wraps=coordinator._async_detect_new_objects,
    ) as detect:
        coordinator.async_set_updated_data({"PUMP3": {"STATUS": "10"}})
        detect.assert_called_once_with({"PUMP3"})
    assert dispatched == [["PUMP3"]]
    assert coordinator._pending_redispatch == {"PUMP3"}

    pump.update({"PWR": "850", "RPM": "2400", "MIN": "450", "MAX": "3450"})
    coordinator.async_set_updated_data(
        {"PUMP3": {"PWR": "850", "RPM": "2400", "MIN": "450", "MAX": "3450"}}
    )

    assert dispatched == [["PUMP3"], ["PUMP3"]]
    assert coordinator._pending_redispatch == set()
