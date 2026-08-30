"""Tests for dependent-entity retirement on equipment removal (issue #124).

Ghost-equipment removal (#113) retired only the entities OF a deleted object.
Entities whose creation predicate references *another* object survived as
permanent ghosts: a body's water heater after its last heater was deleted, the
climate entity after the cooling heater was deleted, a pump circuit's mode
select and speed numbers after the parent pump was deleted, and an IntelliChlor
per-body output number after that body was deleted. These tests cover the
three-pass removal handling in ``async_setup_pool_entities``:

* pass 1 (every platform): retire entities whose own object was removed,
* pass 2 (opt-in via ``retire_dependents``): re-run the builder and retire
  entities it no longer produces,
* pass 3 (every platform): refresh surviving entities' cross-object state,

plus the full-model rebuild on new-equipment dispatch that recreates a
dependent entity when its removed dependency returns.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.light.const import LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyintellicenter import (
    CHEM_TYPE,
    HEATER_TYPE,
    PRIM_ATTR,
    SEC_ATTR,
    PoolModel,
)

from custom_components.intellicenter import async_setup_pool_entities

# A gas heater serving both fixture bodies - identical to the conftest HTR01,
# used to re-add the heater after its removal.
HTR01_PARAMS: dict[str, str] = {
    "OBJTYP": HEATER_TYPE,
    "SUBTYP": "GAS",
    "SNAME": "Gas Heater",
    "STATUS": "OFF",
    "BODY": "POOL1 SPA01",
    "LISTORD": "1",
}

# A second gas heater serving only the pool, so removing it leaves the body
# with a remaining heater (the "non-last heater" scenario).
HTR02_GAS_PARAMS: dict[str, str] = {
    "OBJTYP": HEATER_TYPE,
    "SUBTYP": "GAS",
    "SNAME": "Second Heater",
    "STATUS": "OFF",
    "BODY": "POOL1",
    "LISTORD": "2",
}

# A cooling-capable UltraTemp heat pump on the pool - the climate entity's
# creation predicate.
HTR02_ULTRA_PARAMS: dict[str, str] = {
    "OBJTYP": HEATER_TYPE,
    "SUBTYP": "ULTRA",
    "SNAME": "UltraTemp",
    "STATUS": "OFF",
    "BODY": "POOL1",
    "COOL": "ON",
    "LISTORD": "2",
}

# A non-ULTRA heat pump whose cooling eligibility rests solely on the
# runtime-toggleable COOL attribute - the ambiguous predicate that keeps the
# climate platform out of pass-2 retirement.
HTR02_COOL_HEAT_PUMP_PARAMS: dict[str, str] = {
    "OBJTYP": HEATER_TYPE,
    "SUBTYP": "HTPMP",
    "SNAME": "Heat Pump",
    "STATUS": "OFF",
    "BODY": "POOL1",
    "COOL": "ON",
    "LISTORD": "2",
}

# What the introducing NotifyList carries for a replacement heater: identity
# only, no BODY wiring yet (that backfills in a later update).
HTR02_SKELETON_PARAMS: dict[str, str] = {
    "OBJTYP": HEATER_TYPE,
    "SUBTYP": "GAS",
    "SNAME": "Replacement Heater",
}

# An IntelliChlor whose BODY reference spans both fixture bodies: the primary
# output number depends on POOL1 existing, the secondary on SPA01.
CHLOR1_OBJNAM = "CHLOR1"
CHLOR1_PARAMS: dict[str, str] = {
    "OBJTYP": CHEM_TYPE,
    "SUBTYP": "ICHLOR",
    "SNAME": "IntelliChlor",
    "BODY": "POOL1 SPA01",
    "PRIM": "50",
    "SEC": "30",
    "TIMOUT": "3600",
}

# The conftest SPA01 body, used to re-add the body after its removal.
SPA01_PARAMS: dict[str, str] = {
    "OBJTYP": "BODY",
    "SUBTYP": "SPA",
    "SNAME": "Spa",
    "STATUS": "OFF",
    "LSTTMP": "102",
    "LOTMP": "80",
    "HEATER": "HTR01",
    "HTMODE": "0",
}


def _capture_listener(mock_coordinator: MagicMock) -> dict[str, Any]:
    """Wire a mock coordinator so the registered listeners are captured.

    Same pattern as tests/test_dynamic_entities.py: returns a dict whose
    ``listener`` / ``removed_listener`` entries are populated once the platform
    registers them.
    """
    state: dict[str, Any] = {"listener": None, "removed_listener": None}

    def _register(listener: Any) -> Any:
        state["listener"] = listener
        return MagicMock()

    def _register_removed(listener: Any) -> Any:
        state["removed_listener"] = listener
        return MagicMock()

    mock_coordinator.async_add_new_objects_listener = MagicMock(side_effect=_register)
    mock_coordinator.async_add_removed_objects_listener = MagicMock(
        side_effect=_register_removed
    )
    return state


async def _setup_platform(
    hass: HomeAssistant, mock_coordinator: MagicMock, setup_entry: Any
) -> tuple[dict[str, Any], list[Any]]:
    """Run a platform's async_setup_entry against the mock coordinator."""
    state = _capture_listener(mock_coordinator)
    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()
    added: list[Any] = []
    await setup_entry(hass, entry, added.extend)
    return state, added


def _register_entity(hass: HomeAssistant, entity: Any, domain: str) -> str:
    """Register an entity as HA would have, returning its entity_id."""
    registry = er.async_get(hass)
    reg_entry = registry.async_get_or_create(domain, "intellicenter", entity.unique_id)
    entity.entity_id = reg_entry.entity_id
    entity.hass = hass
    return str(reg_entry.entity_id)


# -------------------------------------------------------------------------------------
# Pass 2: builder-diff retirement on opted-in platforms
# -------------------------------------------------------------------------------------


async def test_last_heater_removal_retires_body_water_heaters(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Deleting a body's last heater retires the body's water heater entity."""
    from custom_components.intellicenter.water_heater import async_setup_entry

    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)

    # HTR01 serves both bodies, so both got a water heater at setup.
    assert {e._pool_object.objnam for e in added} == {"POOL1", "SPA01"}
    registry = er.async_get(hass)
    entity_ids = [_register_entity(hass, e, "water_heater") for e in added]

    pool_model.remove_object("HTR01")
    state["removed_listener"]({"HTR01"})

    # Neither entity's OWN object was removed, but their creation predicate
    # (a heater wired to the body) no longer holds: both are retired.
    for entity_id in entity_ids:
        assert registry.async_get(entity_id) is None


async def test_non_last_heater_removal_keeps_water_heater(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Deleting one of two heaters keeps (and refreshes) the water heater."""
    from custom_components.intellicenter.water_heater import async_setup_entry

    pool_model.add_object("HTR02", dict(HTR02_GAS_PARAMS))
    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)

    pool_entity = next(e for e in added if e._pool_object.objnam == "POOL1")
    entity_id = _register_entity(hass, pool_entity, "water_heater")
    pool_entity.async_refresh_model_context = MagicMock()

    pool_model.remove_object("HTR02")
    state["removed_listener"]({"HTR02"})

    # POOL1 still has HTR01, so its water heater survives - and picks up the
    # pass-3 cross-object refresh rather than being retired.
    registry = er.async_get(hass)
    assert registry.async_get(entity_id) is not None
    pool_entity.async_refresh_model_context.assert_called_once_with()


async def test_cooling_heater_removal_keeps_climate_and_water_heater(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Deleting the ULTRA heater keeps PoolClimate (accepted ghost) and PoolWaterHeater.

    climate deliberately does NOT opt into pass-2 retirement: its eligibility
    check accepts a heater on the COOL attribute, whose semantics are
    firmware-ambiguous between capability configuration and live cooling
    action, so the builder output is not a safe retirement signal (see
    climate.async_setup_entry). The climate entity therefore survives as a
    benign ghost - retired on reload - and only gets the pass-3 refresh.
    """
    from custom_components.intellicenter.climate import (
        async_setup_entry as climate_setup,
    )
    from custom_components.intellicenter.water_heater import (
        async_setup_entry as water_heater_setup,
    )

    pool_model.add_object("HTR02", dict(HTR02_ULTRA_PARAMS))
    mock_coordinator.model = pool_model

    # Cooling support follows the ULTRA heater's presence in the live model,
    # mirroring the real controller's model-derived answer.
    def _supports_cooling(body_objnam: str) -> bool:
        heater = pool_model["HTR02"]
        return heater is not None and body_objnam in (heater["BODY"] or "").split(" ")

    mock_coordinator.controller.body_supports_cooling = MagicMock(
        side_effect=_supports_cooling
    )

    climate_state, climate_added = await _setup_platform(
        hass, mock_coordinator, climate_setup
    )
    water_state, water_added = await _setup_platform(
        hass, mock_coordinator, water_heater_setup
    )

    climate_entity = next(e for e in climate_added if e._pool_object.objnam == "POOL1")
    water_entity = next(e for e in water_added if e._pool_object.objnam == "POOL1")
    climate_id = _register_entity(hass, climate_entity, "climate")
    water_id = _register_entity(hass, water_entity, "water_heater")
    climate_entity.async_refresh_model_context = MagicMock()

    pool_model.remove_object("HTR02")
    climate_state["removed_listener"]({"HTR02"})
    water_state["removed_listener"]({"HTR02"})

    registry = er.async_get(hass)
    # The climate entity survives (opt-out) and picks up the pass-3 refresh;
    # the gas heater remains wired, so the water heater survives too.
    assert registry.async_get(climate_id) is not None
    climate_entity.async_refresh_model_context.assert_called_once_with()
    assert registry.async_get(water_id) is not None


async def test_climate_survives_cool_toggle_during_unrelated_removal(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A COOL=OFF toggle plus an unrelated removal must not retire climate.

    Regression guard for the climate opt-out: body_supports_cooling() can
    derive eligibility from a non-ULTRA heater's COOL=="ON", and firmware may
    toggle COOL at runtime as a live cooling *action* indicator. Were climate
    opted into pass-2 builder-diff retirement, this sequence would falsely
    delete a live entity.
    """
    from custom_components.intellicenter.climate import async_setup_entry

    pool_model.add_object("HTR02", dict(HTR02_COOL_HEAT_PUMP_PARAMS))
    mock_coordinator.model = pool_model

    # Eligibility derived from the heater's live COOL attribute - the
    # ambiguous fallback path in body_supports_cooling().
    def _supports_cooling(body_objnam: str) -> bool:
        heater = pool_model["HTR02"]
        return (
            heater is not None
            and heater["COOL"] == "ON"
            and body_objnam in (heater["BODY"] or "").split(" ")
        )

    mock_coordinator.controller.body_supports_cooling = MagicMock(
        side_effect=_supports_cooling
    )

    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)
    climate_entity = next(e for e in added if e._pool_object.objnam == "POOL1")
    climate_id = _register_entity(hass, climate_entity, "climate")

    # The heat pump stops cooling (COOL flips OFF) just as unrelated equipment
    # is removed in the same reconnect reconciliation.
    heater = pool_model["HTR02"]
    assert heater is not None
    heater.update({"COOL": "OFF"})
    pool_model.remove_object("SENSE1")
    state["removed_listener"]({"SENSE1"})

    registry = er.async_get(hass)
    assert registry.async_get(climate_id) is not None


async def test_pump_removal_retires_select_and_pmpcirc_numbers(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Deleting a pump retires its PMPCIRC select/number entities, nothing else."""
    from custom_components.intellicenter.number import (
        async_setup_entry as number_setup,
    )
    from custom_components.intellicenter.select import (
        async_setup_entry as select_setup,
    )

    mock_coordinator.model = pool_model
    select_state, select_added = await _setup_platform(
        hass, mock_coordinator, select_setup
    )
    number_state, number_added = await _setup_platform(
        hass, mock_coordinator, number_setup
    )

    mode_select = next(e for e in select_added if e._pool_object.objnam == "PMPCIRC01")
    speed_number = next(e for e in number_added if e._pool_object.objnam == "PMPCIRC01")
    egg_timer = next(e for e in number_added if e._pool_object.objnam == "CIRC01")
    select_id = _register_entity(hass, mode_select, "select")
    speed_id = _register_entity(hass, speed_number, "number")
    egg_timer_id = _register_entity(hass, egg_timer, "number")

    pool_model.remove_object("PUMP1")
    select_state["removed_listener"]({"PUMP1"})
    number_state["removed_listener"]({"PUMP1"})

    registry = er.async_get(hass)
    # Both PMPCIRC01 entities keyed off the deleted parent pump are retired;
    # the unrelated egg-timer number is untouched.
    assert registry.async_get(select_id) is None
    assert registry.async_get(speed_id) is None
    assert registry.async_get(egg_timer_id) is not None


async def test_body_removal_retires_only_that_bodys_chlorinator_number(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Deleting one IntelliChlor body retires its output number, keeps the other."""
    from custom_components.intellicenter.number import async_setup_entry

    pool_model.add_object(CHLOR1_OBJNAM, dict(CHLOR1_PARAMS))
    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)

    prim_number = next(
        e
        for e in added
        if e._pool_object.objnam == CHLOR1_OBJNAM and e._attribute_key == PRIM_ATTR
    )
    sec_number = next(
        e
        for e in added
        if e._pool_object.objnam == CHLOR1_OBJNAM and e._attribute_key == SEC_ATTR
    )
    prim_id = _register_entity(hass, prim_number, "number")
    sec_id = _register_entity(hass, sec_number, "number")

    pool_model.remove_object("SPA01")
    state["removed_listener"]({"SPA01"})

    registry = er.async_get(hass)
    # SEC maps to SPA01 (the second BODY reference): retired. PRIM (POOL1) stays.
    assert registry.async_get(sec_id) is None
    assert registry.async_get(prim_id) is not None


# -------------------------------------------------------------------------------------
# Re-add symmetry: the full-model rebuild on new-equipment dispatch
# -------------------------------------------------------------------------------------


async def test_readded_heater_recreates_water_heaters(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A heater returning after retirement produces fresh water heater entities."""
    from custom_components.intellicenter.water_heater import async_setup_entry

    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)
    originals = list(added)

    pool_model.remove_object("HTR01")
    state["removed_listener"]({"HTR01"})

    # The heater comes back (panel re-add); the new-objects dispatch rebuilds.
    readded = pool_model.add_object("HTR01", dict(HTR01_PARAMS))
    assert readded is not None
    added.clear()
    state["listener"]([readded])

    # Fresh entities for both bodies - the dedup records were dropped with the
    # retirement, so the rebuild is not swallowed.
    assert {e._pool_object.objnam for e in added} == {"POOL1", "SPA01"}
    assert all(e not in originals for e in added)


async def test_heater_swap_within_one_reconnect_recreates_water_heaters(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A heater removed AND replaced in one reconnect churns, never loses entities.

    The accepted caveat's RECREATE leg: the replacement heater enters the model
    as a skeleton (no BODY wiring yet) alongside the removal, so the removal
    dispatch retires the body water heaters - the skeleton serves no body at
    that instant. The skeleton's own new-objects dispatch builds nothing, and
    once the BODY backfill lands the coordinator re-dispatches the heater
    (skeleton add -> _pending_redispatch -> backfill re-dispatch) through the
    same listener, whose full-model rebuild recreates the entities.
    """
    from custom_components.intellicenter.water_heater import async_setup_entry

    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)
    registry = er.async_get(hass)
    entity_ids = [_register_entity(hass, e, "water_heater") for e in added]

    # One reconnect reconciliation: HTR01 pruned, its replacement admitted as a
    # skeleton, then the removal dispatched.
    pool_model.remove_object("HTR01")
    skeleton = pool_model.add_object("HTR02", dict(HTR02_SKELETON_PARAMS))
    assert skeleton is not None
    state["removed_listener"]({"HTR01"})

    # RETIRE leg: no heater serves the bodies yet, so both are retired.
    for entity_id in entity_ids:
        assert registry.async_get(entity_id) is None

    # The skeleton's introducing dispatch builds nothing (no BODY wiring).
    added.clear()
    state["listener"]([skeleton])
    assert added == []

    # RECREATE leg: the BODY backfill lands and the coordinator re-dispatches
    # the (now complete) heater; the full-model rebuild restores both entities.
    skeleton.update({"BODY": "POOL1 SPA01", "LISTORD": "1"})
    state["listener"]([skeleton])
    assert {e._pool_object.objnam for e in added} == {"POOL1", "SPA01"}


async def test_readded_body_recreates_chlorinator_number(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A returning BODY recreates the IntelliChlor output number that depends on it.

    The critical re-add hole: the new-objects dispatch carries only the body,
    and the CHEM object that BUILDS the output number is not among the new
    objects. Only a full-model rebuild reconsiders the CHEM builder, so the
    dependent number comes back.
    """
    from custom_components.intellicenter.number import async_setup_entry

    pool_model.add_object(CHLOR1_OBJNAM, dict(CHLOR1_PARAMS))
    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)

    pool_model.remove_object("SPA01")
    state["removed_listener"]({"SPA01"})

    # The body returns; the dispatch names ONLY the body, not the IntelliChlor.
    readded = pool_model.add_object("SPA01", dict(SPA01_PARAMS))
    assert readded is not None
    added.clear()
    state["listener"]([readded])

    assert any(
        e._pool_object.objnam == CHLOR1_OBJNAM and e._attribute_key == SEC_ATTR
        for e in added
    ), "IntelliChlor output number was not recreated when its body returned"


# -------------------------------------------------------------------------------------
# Safety: builder isolation and the telemetry-gated opt-out
# -------------------------------------------------------------------------------------


async def test_builder_exception_does_not_block_own_object_retirement(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A builder failing during pass 2 must not block pass 1 or escape."""
    from custom_components.intellicenter.sensor import PoolSensor

    mock_coordinator.model = pool_model
    state = _capture_listener(mock_coordinator)
    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()
    added: list[Any] = []

    calls = {"count": 0}

    def _build(coordinator: Any, candidates: Any) -> list[Any]:
        # Succeed for the initial setup, then blow up on the pass-2 rebuild.
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("builder exploded")
        return [
            PoolSensor(
                coordinator,
                coordinator.model["CHEM1"],
                device_class=None,
                attribute_key="PHVAL",
            ),
            PoolSensor(
                coordinator,
                coordinator.model["SENSE1"],
                device_class=None,
                attribute_key="SOURCE",
            ),
        ]

    async_setup_pool_entities(entry, added.extend, _build, retire_dependents=True)
    chem_entity = next(e for e in added if e._pool_object.objnam == "CHEM1")
    sense_entity = next(e for e in added if e._pool_object.objnam == "SENSE1")
    chem_id = _register_entity(hass, chem_entity, "sensor")
    sense_id = _register_entity(hass, sense_entity, "sensor")

    pool_model.remove_object("CHEM1")
    # Must not raise despite the builder failure.
    state["removed_listener"]({"CHEM1"})

    registry = er.async_get(hass)
    # Pass 1 still retired the removed object's entity; pass 2 was skipped so
    # the survivor was not touched.
    assert registry.async_get(chem_id) is None
    assert registry.async_get(sense_id) is not None
    assert calls["count"] > 1  # the pass-2 rebuild was actually attempted


async def test_sensor_platform_never_retires_on_empty_telemetry(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """The sensor platform's opt-out protects telemetry-gated entities.

    sensor builders gate on telemetry truthiness (``if obj[PWR_ATTR]:``); a
    live pump can legitimately report an empty PWR at the instant an unrelated
    removal dispatch fires. Were the platform opted into pass 2, the rebuild
    would miss the power sensor and falsely retire it.
    """
    from custom_components.intellicenter.sensor import async_setup_entry

    mock_coordinator.model = pool_model
    state, added = await _setup_platform(hass, mock_coordinator, async_setup_entry)

    pwr_sensor = next(
        e
        for e in added
        if e._pool_object.objnam == "PUMP1" and e._attribute_key == "PWR"
    )
    pwr_id = _register_entity(hass, pwr_sensor, "sensor")

    # The pump momentarily reports no power draw while unrelated equipment is
    # removed in the same reconnect reconciliation.
    pump = pool_model["PUMP1"]
    assert pump is not None
    pump.update({"PWR": ""})
    pool_model.remove_object("CHEM1")
    state["removed_listener"]({"CHEM1"})

    registry = er.async_get(hass)
    assert registry.async_get(pwr_id) is not None


# -------------------------------------------------------------------------------------
# Pass 3: cross-object refresh for surviving entities
# -------------------------------------------------------------------------------------


async def test_member_light_removal_drops_group_effect_support(
    hass: HomeAssistant,
    complete_light_group_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Removing a member circuit drops the surviving group light's effects."""
    from custom_components.intellicenter.light import _build_entities

    mock_coordinator.model = complete_light_group_model
    state = _capture_listener(mock_coordinator)
    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()
    added: list[Any] = []

    async_setup_pool_entities(entry, added.extend, _build_entities)
    group_entity = next(e for e in added if e._pool_object.objnam == "GROUP")
    assert group_entity.supported_features & LightEntityFeature.EFFECT
    group_entity.hass = hass
    group_entity.async_write_ha_state = MagicMock()

    # The panel deletes the member light; its membership row survives but now
    # references a missing circuit, so the group is no longer complete.
    complete_light_group_model.remove_object("GLOW2")
    state["removed_listener"]({"GLOW2"})

    # The pass-3 refresh recomputed the group capability and re-rendered.
    assert not group_entity.supported_features & LightEntityFeature.EFFECT
    assert group_entity.effect_list is None
    group_entity.async_write_ha_state.assert_called_once_with()
