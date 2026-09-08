"""Regression tests for object-targeted coordinator dispatch (issue #136)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from pyintellicenter import (
    BODY_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    LIGHT_EFFECTS,
    PMPCIRC_TYPE,
    PUMP_TYPE,
    SENSE_TYPE,
    SYSTEM_TYPE,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter import PoolEntity
from custom_components.intellicenter.climate import PoolClimate
from custom_components.intellicenter.const import LIMIT_ATTR
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator
from custom_components.intellicenter.light import PoolLight
from custom_components.intellicenter.number import PumpSpeedNumber
from custom_components.intellicenter.select import PumpModeSelect
from custom_components.intellicenter.sensor import async_setup_entry as setup_sensors
from custom_components.intellicenter.water_heater import PoolWaterHeater

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


class _CountingWaterHeater(PoolWaterHeater):
    """Water-heater entity that counts coordinator callbacks and state writes."""

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


class _CountingLight(PoolLight):
    """Light entity that counts coordinator callbacks and state writes."""

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        self.update_invocations = 0
        self.state_writes = 0
        super().__init__(coordinator, pool_object)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.update_invocations += 1
        super()._handle_coordinator_update()

    @callback
    def async_write_ha_state(self) -> None:
        self.state_writes += 1


class _AttributeDependencyEntity(_CountingPoolEntity):
    """Entity with one attribute-scoped cross-object dependency."""

    dependency_calls = 0

    def coordinator_update_dependencies(self) -> dict[str, set[str] | None]:
        """Depend only on DEP.RELEVANT."""
        self.dependency_calls += 1
        return {"DEP": {"RELEVANT"}}


class _FlakyDependencyClimate(_CountingClimate):
    """Climate entity whose dependency resolver can fail and recover."""

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        self.dependency_calls = 0
        self.fail_dependency_resolution = True
        super().__init__(coordinator, pool_object, [])

    def coordinator_update_dependencies(self) -> dict[str, set[str] | None]:
        """Raise until the test enables successful dependency resolution."""
        self.dependency_calls += 1
        if self.fail_dependency_resolution:
            raise RuntimeError("dependency resolution failed")
        return {"DEP": {"RELEVANT"}}


class _FailingDependencyWaterHeater(_CountingWaterHeater):
    """Water heater whose dependency resolver remains in broadcast fallback."""

    def coordinator_update_dependencies(self) -> dict[str, set[str] | None]:
        """Simulate a dependency resolver failure."""
        raise RuntimeError("dependency resolution failed")


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
    model_iterations = 0
    model_type_lookups = 0
    original_iter = PoolModel.__iter__
    original_get_by_type = PoolModel.get_by_type

    def _count_model_iterations(model: PoolModel):
        nonlocal model_iterations
        model_iterations += 1
        return original_iter(model)

    def _count_model_type_lookups(
        model: PoolModel, obj_type: str, subtype: str | None = None
    ) -> list[PoolObject]:
        nonlocal model_type_lookups
        model_type_lookups += 1
        return original_get_by_type(model, obj_type, subtype)

    with (
        patch.object(PoolModel, "__iter__", _count_model_iterations),
        patch.object(PoolModel, "get_by_type", _count_model_type_lookups),
    ):
        coordinator.async_set_updated_data({"PUMP1": {"RPM": "2600"}})

    assert interested.update_invocations == 1
    assert sum(entity.update_invocations for entity in unrelated) == 0
    assert model_iterations == 0
    assert model_type_lookups == 0


async def test_dependency_attributes_are_filtered_from_cached_map(
    hass: HomeAssistant,
) -> None:
    """Dependency callbacks render only relevant attrs without re-resolving maps."""
    coordinator = _make_coordinator(hass)
    owner = coordinator.model.add_object(
        "OWNER",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Owner",
            "STATUS": "OFF",
        },
    )
    dependency = coordinator.model.add_object(
        "DEP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Dependency",
            "STATUS": "OFF",
        },
    )
    pump = coordinator.model.add_object(
        "PUMP1",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VSF",
            "SNAME": "Pump",
            "MIN": "450",
            "MAX": "3450",
            "MINF": "15",
            "MAXF": "140",
        },
    )
    pump_circuit = coordinator.model.add_object(
        "PMPCIRC1",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "PARENT": "PUMP1",
            "CIRCUIT": "OWNER",
            "SELECT": "RPM",
            "SPEED": "2000",
        },
    )
    assert all(obj is not None for obj in (owner, dependency, pump, pump_circuit))
    assert owner is not None and pump_circuit is not None
    entity = _AttributeDependencyEntity(coordinator, owner)
    speed = PumpSpeedNumber(
        coordinator,
        pump_circuit,
        pump_name="Pump",
        circuit_name="Owner",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )
    mode = PumpModeSelect(coordinator, pump_circuit, "Pump", "Owner")
    _mark_started(coordinator)
    await _register(hass, entity)

    assert entity.dependency_calls == 1
    assert speed.coordinator_update_dependencies() == {
        "PUMP1": {"MIN", "MAX", "MINF", "MAXF"}
    }
    assert mode.coordinator_update_dependencies() == {}

    coordinator.async_set_updated_data({"DEP": {"STATUS": "ON"}})
    assert entity.update_invocations == 1
    assert entity.state_writes == 0
    assert entity.dependency_calls == 2

    coordinator.async_set_updated_data({"DEP": {"RELEVANT": "changed"}})
    assert entity.update_invocations == 2
    assert entity.state_writes == 1
    assert entity.dependency_calls == 2


async def test_pump_limit_updates_refresh_speed_number(
    hass: HomeAssistant,
) -> None:
    """Parent limits refresh pump speed without routing unrelated telemetry."""
    coordinator = _make_coordinator(hass)
    pump = coordinator.model.add_object(
        "PUMP1",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VSF",
            "SNAME": "Pump",
            "MIN": "450",
            "MAX": "3450",
            "MINF": "15",
            "MAXF": "140",
        },
    )
    pump_circuit = coordinator.model.add_object(
        "PMPCIRC1",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "PARENT": "PUMP1",
            "CIRCUIT": "C0001",
            "SELECT": "RPM",
            "SPEED": "2000",
        },
    )
    assert pump is not None and pump_circuit is not None
    entity = PumpSpeedNumber(
        coordinator,
        pump_circuit,
        pump_name="Pump",
        circuit_name="Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )
    _mark_started(coordinator)

    with (
        patch.object(
            entity,
            "_handle_coordinator_update",
            wraps=entity._handle_coordinator_update,
        ) as handle_update,
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        await _register(hass, entity)
        assert entity.native_value == 2000

        pump.update({"MIN": "2100"})
        coordinator.async_set_updated_data({"PUMP1": {"MIN": "2100"}})
        assert handle_update.call_count == 1
        write_state.assert_called_once_with()
        assert entity.native_value is None

        pump.update({"STATUS": "10"})
        coordinator.async_set_updated_data({"PUMP1": {"STATUS": "10"}})
        assert handle_update.call_count == 2
        write_state.assert_called_once_with()


async def test_heater_cool_routes_only_to_dependent_climate(
    hass: HomeAssistant,
) -> None:
    """A heater COOL push refreshes dependents without touching unrelated entities."""
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
    water_heater = _CountingWaterHeater(coordinator, body, ["HTR01"])
    unrelated = _CountingPoolEntity(coordinator, circuit)
    _mark_started(coordinator)
    await _register(hass, climate, water_heater, unrelated)

    heater.update({"COOL": "ON"})
    coordinator.async_set_updated_data({"HTR01": {"COOL": "ON"}})

    assert climate.update_invocations == 1
    assert climate.state_writes == 1
    assert water_heater.update_invocations == 1
    assert water_heater.state_writes == 1
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


async def test_removal_only_update_broadcasts_to_every_entity(
    hass: HomeAssistant,
) -> None:
    """Removal-only structural updates retain a global entity callback fan-out."""
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
    removed = coordinator.model.add_object(
        "REMOVED",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Removed",
            "STATUS": "OFF",
        },
    )
    assert removed is not None
    _mark_started(coordinator)
    await _register(hass, *entities)

    coordinator.async_set_updated_data({"C0000": {"STATUS": "ON"}})
    assert [entity.update_invocations for entity in entities] == [1, 0, 0]

    for entity in entities:
        entity.update_invocations = 0
    coordinator.model.remove_object("REMOVED")
    coordinator.async_set_updated_data({"REMOVED": None})
    assert [entity.update_invocations for entity in entities] == [1, 1, 1]


async def test_dependency_edge_change_broadcasts_and_reindexes(
    hass: HomeAssistant,
) -> None:
    """A heater rewire broadcasts once and targets its new climate afterward."""
    coordinator = _make_coordinator(hass)
    pool = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )
    spa = coordinator.model.add_object(
        "SPA1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "SPA",
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
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
    assert all(obj is not None for obj in (pool, spa, heater, circuit))
    assert pool is not None and spa is not None and heater is not None
    assert circuit is not None
    pool_climate = _CountingClimate(coordinator, pool, [])
    spa_climate = _CountingClimate(coordinator, spa, [])
    unrelated = _CountingPoolEntity(coordinator, circuit)
    _mark_started(coordinator)
    await _register(hass, pool_climate, spa_climate, unrelated)

    heater.update({"BODY": "SPA1"})
    coordinator.async_set_updated_data({"HTR01": {"BODY": "SPA1"}})
    assert [
        pool_climate.update_invocations,
        spa_climate.update_invocations,
        unrelated.update_invocations,
    ] == [1, 1, 1]
    assert [
        pool_climate.state_writes,
        spa_climate.state_writes,
        unrelated.state_writes,
    ] == [1, 1, 1]

    for entity in (pool_climate, spa_climate, unrelated):
        entity.update_invocations = 0
        entity.state_writes = 0
    heater.update({"COOL": "ON"})
    coordinator.async_set_updated_data({"HTR01": {"COOL": "ON"}})
    assert [
        pool_climate.update_invocations,
        spa_climate.update_invocations,
        unrelated.update_invocations,
    ] == [0, 1, 0]
    assert [
        pool_climate.state_writes,
        spa_climate.state_writes,
        unrelated.state_writes,
    ] == [0, 1, 0]


async def test_structural_batch_preserves_water_heater_memory(
    hass: HomeAssistant,
) -> None:
    """A structural batch still lets the water heater capture its live update."""
    coordinator = _make_coordinator(hass)
    body = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "00000",
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "78",
        },
    )
    heater = coordinator.model.add_object(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GAS",
            "SNAME": "Gas Heater",
            "BODY": "POOL1",
            "LISTORD": "1",
        },
    )
    assert body is not None and heater is not None
    entity = _CountingWaterHeater(coordinator, body, ["HTR01"])
    _mark_started(coordinator)
    await _register(hass, entity)
    added = coordinator.model.add_object(
        "C_NEW",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "New Circuit",
            "STATUS": "OFF",
        },
    )
    assert added is not None

    body.update({"HEATER": "HTR01", "HTMODE": "1", "LOTMP": "88"})
    coordinator.async_set_updated_data(
        {
            "POOL1": {"HEATER": "HTR01", "HTMODE": "1", "LOTMP": "88"},
            "C_NEW": {"STATUS": "OFF"},
        }
    )

    assert entity._last_operation == "Gas Heater"
    assert entity._last_setpoint == 88.0
    assert entity.state_writes == 1


async def test_structural_refresh_preserves_optimistic_state(
    hass: HomeAssistant,
) -> None:
    """Structural refreshes preserve unrelated optimism but honor own echoes."""
    coordinator = _make_coordinator(hass)
    owner = coordinator.model.add_object(
        "OWNER",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Owner",
            "STATUS": "OFF",
        },
    )
    assert owner is not None
    entity = _CountingPoolEntity(coordinator, owner)
    _mark_started(coordinator)
    await _register(hass, entity)
    added = coordinator.model.add_object(
        "C_NEW",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "New Circuit",
            "STATUS": "OFF",
        },
    )
    assert added is not None

    entity._optimistic_state = True
    coordinator.async_set_updated_data({"C_NEW": {"STATUS": "OFF"}})
    assert entity._optimistic_state is True
    assert entity.state_writes == 1

    coordinator.model.remove_object("C_NEW")
    entity._optimistic_state = False
    coordinator.async_set_updated_data({"C_NEW": None})
    assert entity._optimistic_state is False
    assert entity.state_writes == 2

    added = coordinator.model.add_object(
        "C_ECHO",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Echo Circuit",
            "STATUS": "OFF",
        },
    )
    assert added is not None
    owner.update({"STATUS": "ON"})
    entity._optimistic_state = True
    coordinator.async_set_updated_data(
        {"OWNER": {"STATUS": "ON"}, "C_ECHO": {"STATUS": "OFF"}}
    )
    assert entity._optimistic_state is None
    assert entity.state_writes == 3

    entity._optimistic_state = True
    coordinator.async_set_connection_state(False)
    assert entity._optimistic_state is None
    assert entity.state_writes == 4


async def test_light_group_structural_refresh_clears_only_own_echo(
    hass: HomeAssistant,
) -> None:
    """Group capability changes preserve optimism until its STATUS echo arrives."""
    coordinator = _make_coordinator(hass)
    group = coordinator.model.add_object(
        "GROUP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "LITSHO",
            "SNAME": "Color Group",
            "STATUS": "OFF",
            "USE": "WHITER",
        },
    )
    for objnam in ("GLOW1", "GLOW2"):
        child = coordinator.model.add_object(
            objnam,
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GLOW",
                "SNAME": objnam,
                "STATUS": "OFF",
                "USE": "WHITER",
            },
        )
        assert child is not None
    row1 = coordinator.model.add_object(
        "GROUP_ROW_1",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "PARENT": "GROUP",
            "CIRCUIT": "GLOW1",
            "LISTORD": "1",
        },
    )
    row2 = coordinator.model.add_object(
        "GROUP_ROW_2",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "PARENT": "GROUP",
            "CIRCUIT": "MISSING",
            "LISTORD": "2",
        },
    )
    assert group is not None and row1 is not None and row2 is not None
    entity = _CountingLight(coordinator, group)
    _mark_started(coordinator)
    await _register(hass, entity)
    assert entity.effect_list is None

    row2.update({"CIRCUIT": "GLOW2"})
    entity._optimistic_state = True
    coordinator.async_set_updated_data({"GROUP_ROW_2": {"CIRCUIT": "GLOW2"}})
    assert entity.effect_list == list(LIGHT_EFFECTS.values())
    assert entity._optimistic_state is True

    added = coordinator.model.add_object(
        "C_NEW",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "New Circuit",
            "STATUS": "OFF",
        },
    )
    assert added is not None
    group.update({"STATUS": "ON"})
    coordinator.async_set_updated_data(
        {"GROUP": {"STATUS": "ON"}, "C_NEW": {"STATUS": "OFF"}}
    )
    assert entity._optimistic_state is None


async def test_dependency_refresh_preserves_optimism_until_own_echo(
    hass: HomeAssistant,
) -> None:
    """An ordinary dependency refresh writes state without clearing optimism."""
    coordinator = _make_coordinator(hass)
    group = coordinator.model.add_object(
        "GROUP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "LITSHO",
            "SNAME": "Color Group",
            "STATUS": "OFF",
            "USE": "WHITER",
        },
    )
    system = coordinator.model.add_object(
        "SYS",
        {
            "OBJTYP": SYSTEM_TYPE,
            "SNAME": "System",
            "VER": "1.064",
        },
    )
    assert group is not None and system is not None
    entity = _CountingLight(coordinator, group)
    _mark_started(coordinator)
    await _register(hass, entity)

    entity._optimistic_state = True
    system.update({"VER": "1.065"})
    coordinator.async_set_updated_data({"SYS": {"VER": "1.065"}})
    assert entity._optimistic_state is True
    assert entity.state_writes == 1

    group.update({"STATUS": "ON"})
    coordinator.async_set_updated_data({"GROUP": {"STATUS": "ON"}})
    assert entity._optimistic_state is None
    assert entity.state_writes == 2


async def test_dimmer_limit_echo_clears_status_keyed_optimistic_state(
    hass: HomeAssistant,
) -> None:
    """A LIMIT-only dimmer echo reconciles its optimistic on state."""
    coordinator = _make_coordinator(hass)
    dimmer = coordinator.model.add_object(
        "DIMMER1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "DIMMER",
            "SNAME": "Patio Dimmer",
            "STATUS": "ON",
            LIMIT_ATTR: "50",
        },
    )
    assert dimmer is not None
    entity = _CountingLight(coordinator, dimmer)
    _mark_started(coordinator)
    await _register(hass, entity)

    entity._optimistic_state = True
    dimmer.update({LIMIT_ATTR: "75"})
    coordinator.async_set_updated_data({"DIMMER1": {LIMIT_ATTR: "75"}})

    assert entity._optimistic_state is None
    assert entity.state_writes == 1


async def test_backfill_update_broadcasts_to_every_entity(
    hass: HomeAssistant,
) -> None:
    """A pending object backfill retains a global entity callback fan-out."""
    coordinator = _make_coordinator(hass)
    entities: list[_CountingPoolEntity] = []
    for index in range(2):
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
    coordinator.async_set_updated_data({"PUMP3": {"STATUS": "10"}})
    for entity in entities:
        entity.update_invocations = 0
        entity.state_writes = 0

    pump.update({"PWR": "850", "RPM": "2400"})
    coordinator.async_set_updated_data({"PUMP3": {"PWR": "850", "RPM": "2400"}})
    assert [entity.update_invocations for entity in entities] == [1, 1]
    assert [entity.state_writes for entity in entities] == [1, 1]

    for entity in entities:
        entity.update_invocations = 0
        entity.state_writes = 0
    coordinator.async_set_updated_data({"PUMP3": {"RPM": "2500"}})
    assert [entity.update_invocations for entity in entities] == [0, 0]
    assert [entity.state_writes for entity in entities] == [0, 0]


async def test_dependency_resolver_failure_falls_back_once_and_recovers(
    hass: HomeAssistant,
) -> None:
    """Resolver failures broadcast safely, log once, and later recover targeting."""
    coordinator = _make_coordinator(hass)
    body = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "00000",
            "HTMODE": "0",
        },
    )
    dependency = coordinator.model.add_object(
        "DEP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Dependency",
            "STATUS": "OFF",
        },
    )
    other = coordinator.model.add_object(
        "OTHER",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Other",
            "STATUS": "OFF",
        },
    )
    assert body is not None and dependency is not None and other is not None
    entity = _FlakyDependencyClimate(coordinator, body)
    _mark_started(coordinator)

    with patch(
        "custom_components.intellicenter.coordinator._LOGGER.exception"
    ) as log_exception:
        await _register(hass, entity)
        coordinator._async_refresh_object_listener_index()
        coordinator._async_refresh_object_listener_index()
        assert log_exception.call_count == 1

        coordinator.async_set_updated_data({"OTHER": {"STATUS": "ON"}})
        assert entity.update_invocations == 1
        assert entity.state_writes == 1
        assert log_exception.call_count == 1

        entity.fail_dependency_resolution = False
        entity.update_invocations = 0
        entity.state_writes = 0
        coordinator.async_set_updated_data({"OTHER": {"STATUS": "OFF"}})
        assert entity.update_invocations == 0

        coordinator.async_set_updated_data({"DEP": {"RELEVANT": "changed"}})
        assert entity.update_invocations == 1
        assert entity.state_writes == 1
        assert log_exception.call_count == 1


async def test_water_heater_fallback_still_captures_operation_memory(
    hass: HomeAssistant,
) -> None:
    """Resolver fallback still runs water-heater update side effects."""
    coordinator = _make_coordinator(hass)
    body = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "00000",
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "78",
        },
    )
    heater = coordinator.model.add_object(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GAS",
            "SNAME": "Gas Heater",
            "BODY": "POOL1",
            "LISTORD": "1",
        },
    )
    assert body is not None and heater is not None
    entity = _FailingDependencyWaterHeater(coordinator, body, ["HTR01"])
    _mark_started(coordinator)
    await _register(hass, entity)

    body.update({"HEATER": "HTR01", "HTMODE": "1", "LOTMP": "88"})
    coordinator.async_set_updated_data(
        {"POOL1": {"HEATER": "HTR01", "HTMODE": "1", "LOTMP": "88"}}
    )

    assert entity._last_operation == "Gas Heater"
    assert entity._last_setpoint == 88.0
    assert entity.state_writes == 1


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
    dispatched: list[list[str]] = []
    await setup_sensors(hass, entry, added.extend)
    coordinator.async_add_new_objects_listener(
        lambda objects: dispatched.append([obj.objnam for obj in objects])
    )
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
    pending = coordinator.model.add_object(
        "C_PENDING",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Pending Circuit",
            "STATUS": "OFF",
        },
    )
    assert pending is not None
    coordinator.async_set_updated_data({"SENSE2": {"SOURCE": "80"}})
    sensor_entities = [
        entity for entity in added if entity._pool_object.objnam == "SENSE2"
    ]
    assert sensor_entities
    assert {entity._pool_object.objnam for entity in added} == {"SENSE2"}
    assert dispatched == [["SENSE2"]]

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
    model_iterations = 0
    original_iter = PoolModel.__iter__

    def _count_model_iterations(model: PoolModel):
        nonlocal model_iterations
        model_iterations += 1
        return original_iter(model)

    with patch.object(PoolModel, "__iter__", _count_model_iterations):
        coordinator.async_set_connection_state(True)
    assert [entity for entity in added if entity._pool_object.objnam == "SENSE2"]
    assert model_iterations > 0


async def test_incomplete_runtime_object_redispatches_on_backfill(
    hass: HomeAssistant,
) -> None:
    """Changed-ID detection keeps #134's tracked-key backfill redispatch."""
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
    coordinator.async_set_updated_data({"PUMP3": {"STATUS": "10"}})
    assert dispatched == [["PUMP3"]]
    assert set(coordinator._pending_redispatch) == {"PUMP3"}

    pending = coordinator.model.add_object(
        "SENSE_PENDING",
        {
            "OBJTYP": SENSE_TYPE,
            "SUBTYP": "AIR",
            "SNAME": "Pending Sensor",
            "SOURCE": "70",
        },
    )
    assert pending is not None
    pump.update({"PWR": "850", "RPM": "2400", "MIN": "450", "MAX": "3450"})
    coordinator.async_set_updated_data(
        {"PUMP3": {"PWR": "850", "RPM": "2400", "MIN": "450", "MAX": "3450"}}
    )

    assert dispatched == [["PUMP3"], ["PUMP3"]]
    assert {"PWR", "RPM", "MIN", "MAX"} <= coordinator._pending_redispatch["PUMP3"]
