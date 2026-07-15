"""Tests for runtime dynamic entity addition (issue #42).

When new equipment appears in the pool model after the integration has started
(for example a second IntelliChem controller coming online), the platforms must
create entities for it without requiring a Home Assistant restart. These tests
cover both halves of the mechanism:

* the coordinator detecting previously-unseen objects and notifying listeners,
* the platforms creating the right entities for those objects while never
  duplicating entities for objects that already have them.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.light.const import LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    CHEM_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_TYPE,
    PMPCIRC_TYPE,
    PUMP_TYPE,
    SENSE_TYPE,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter import (
    async_setup_pool_entities,
    bodies_affected_by,
)
from custom_components.intellicenter.coordinator import (
    DEFAULT_ATTRIBUTES_MAP,
    IntelliCenterCoordinator,
)

# A second IntelliChem controller - the exact scenario reported in issue #42.
# Includes both sensor readings (PHVAL/ORPVAL/tank levels) and the controllable
# setpoints/config attributes so it exercises multiple platforms.
CHEM2_OBJNAM = "CHEM2"
CHEM2_PARAMS: dict[str, str] = {
    "OBJTYP": CHEM_TYPE,
    "SUBTYP": "ICHEM",
    "SNAME": "IntelliChem 2",
    "PHVAL": "7.5",
    "ORPVAL": "700",
    "PHTNK": "6",
    "ORPTNK": "6",
    "PHSET": "7.4",
    "ORPSET": "700",
    "ALK": "100",
    "CALC": "300",
    "CYACID": "40",
}

# A second temperature sensor.
SENSE2_OBJNAM = "SENSE2"
SENSE2_PARAMS: dict[str, str] = {
    "OBJTYP": SENSE_TYPE,
    "SUBTYP": "POOL",
    "SNAME": "Water Temp",
    "SOURCE": "80",
}


def _make_coordinator(
    hass: HomeAssistant, model: PoolModel
) -> IntelliCenterCoordinator:
    """Build a real coordinator wired to a pre-populated model.

    The coordinator is put in the "started" state with its known-object snapshot
    seeded from ``model`` - mirroring the state right after async_start().
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100"}

    coordinator = IntelliCenterCoordinator(hass, entry, host="192.168.1.100")
    # Replace the controller's empty model with our populated test model.
    coordinator._model = model
    # Simulate the post-start seed: every current object is already known.
    coordinator._known_objnams = {obj.objnam for obj in model}
    coordinator._started = True
    return coordinator


# -------------------------------------------------------------------------------------
# Coordinator detection
# -------------------------------------------------------------------------------------


class TestCoordinatorNewObjectDetection:
    """Tests for IntelliCenterCoordinator new-object detection."""

    async def test_listener_notified_for_new_object(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """A newly-added object is dispatched to registered listeners."""
        coordinator = _make_coordinator(hass, pool_model)

        received: list[list[PoolObject]] = []
        coordinator.async_add_new_objects_listener(received.append)

        # New equipment enters the model (as it would after a reconnect re-fetch).
        pool_model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
        coordinator._async_detect_new_objects()

        assert len(received) == 1
        assert [obj.objnam for obj in received[0]] == ["CHEM2"]
        # The new object is now tracked, so it is not reported again.
        coordinator._async_detect_new_objects()
        assert len(received) == 1

    async def test_no_notification_for_known_objects(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """Objects present at startup never trigger the new-object listeners."""
        coordinator = _make_coordinator(hass, pool_model)

        received: list[list[PoolObject]] = []
        coordinator.async_add_new_objects_listener(received.append)

        coordinator._async_detect_new_objects()

        assert received == []

    async def test_no_notification_before_started(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """Detection is a no-op until the initial connection has completed.

        This keeps the burst of attribute updates emitted during the very first
        controller.start() from being misread as newly-added equipment.
        """
        coordinator = _make_coordinator(hass, pool_model)
        coordinator._started = False
        coordinator._known_objnams = set()

        received: list[list[PoolObject]] = []
        coordinator.async_add_new_objects_listener(received.append)

        pool_model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
        coordinator._async_detect_new_objects()

        assert received == []

    async def test_set_updated_data_detects_new_object(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """A push update surfaces objects added to the model on reconnect."""
        coordinator = _make_coordinator(hass, pool_model)

        received: list[list[PoolObject]] = []
        coordinator.async_add_new_objects_listener(received.append)

        # The controller re-fetched every object on reconnect; the model now has
        # the new one. The coordinator learns of it on the next push.
        pool_model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
        coordinator.async_set_updated_data({"CHEM2": {"PHVAL": "7.5"}})

        assert len(received) == 1
        assert received[0][0].objnam == "CHEM2"

    async def test_reconnect_detects_new_object(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """Becoming connected again surfaces equipment added while offline."""
        coordinator = _make_coordinator(hass, pool_model)

        received: list[list[PoolObject]] = []
        coordinator.async_add_new_objects_listener(received.append)

        pool_model.add_object(SENSE2_OBJNAM, dict(SENSE2_PARAMS))
        coordinator.async_set_connection_state(True)

        assert len(received) == 1
        assert received[0][0].objnam == "SENSE2"

        # Going offline must not re-run detection.
        coordinator.async_set_connection_state(False)
        assert len(received) == 1

    async def test_listener_unregister(
        self, hass: HomeAssistant, pool_model: PoolModel
    ) -> None:
        """The unregister callback stops further notifications."""
        coordinator = _make_coordinator(hass, pool_model)

        received: list[list[PoolObject]] = []
        unregister = coordinator.async_add_new_objects_listener(received.append)
        unregister()

        pool_model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
        coordinator._async_detect_new_objects()

        assert received == []


# -------------------------------------------------------------------------------------
# Platform dynamic setup
# -------------------------------------------------------------------------------------


def _capture_listener(
    mock_coordinator: MagicMock,
) -> dict[str, Any]:
    """Wire a mock coordinator so the registered new-objects listener is captured.

    Returns a dict with the captured ``listener`` (populated once the platform
    registers it) and the list of ``added`` entity batches.
    """
    state: dict[str, Any] = {"listener": None, "added": []}

    def _register(listener: Any) -> Any:
        state["listener"] = listener
        return MagicMock()

    mock_coordinator.async_add_new_objects_listener = MagicMock(side_effect=_register)
    return state


async def test_sensor_platform_adds_entities_for_new_intellichem(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """A second IntelliChem added at runtime produces new sensor entities.

    Reproduces issue #42: the platform is set up against the original model, then
    a new CHEM object appears and the dynamic listener must create its sensors
    without re-running async_setup_entry.
    """
    from custom_components.intellicenter.sensor import async_setup_entry

    mock_coordinator.model = pool_model
    state = _capture_listener(mock_coordinator)

    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)

    # Initial setup created sensors for the single existing IntelliChem (CHEM1).
    initial_chem2 = [e for e in added if e.unique_id.startswith("test_entry_CHEM2")]
    assert initial_chem2 == []
    assert state["listener"] is not None

    # A second IntelliChem comes online and enters the model.
    new_obj = pool_model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
    assert new_obj is not None

    added.clear()
    state["listener"]([new_obj])

    # New sensors are created for CHEM2 (pH, ORP, tank levels, ...) at runtime.
    chem2_sensors = [e for e in added if e.unique_id.startswith("test_entry_CHEM2")]
    assert len(chem2_sensors) >= 2
    assert all(e._pool_object.objnam == "CHEM2" for e in chem2_sensors)


async def test_platform_does_not_duplicate_known_objects(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """Re-notifying with an already-known object creates no duplicate entities."""
    from custom_components.intellicenter.sensor import async_setup_entry

    mock_coordinator.model = pool_model
    state = _capture_listener(mock_coordinator)

    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)

    # CHEM1 already produced entities during initial setup.
    existing_chem1 = pool_model["CHEM1"]
    assert existing_chem1 is not None
    before = len(added)

    # A spurious notification for the already-known object must add nothing.
    added.clear()
    state["listener"]([existing_chem1])

    assert added == []
    assert before > 0


async def test_multiple_platforms_handle_new_object(
    hass: HomeAssistant,
    pool_model_data: list[dict[str, Any]],
    mock_coordinator: MagicMock,
) -> None:
    """The new IntelliChem produces both sensor and number entities at runtime."""
    from custom_components.intellicenter.number import (
        async_setup_entry as number_setup,
    )
    from custom_components.intellicenter.sensor import (
        async_setup_entry as sensor_setup,
    )

    for setup in (sensor_setup, number_setup):
        # Fresh model per platform so the new object is genuinely absent at setup.
        model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
        model.add_objects(pool_model_data)
        mock_coordinator.model = model

        state = _capture_listener(mock_coordinator)
        entry = MagicMock()
        entry.runtime_data = mock_coordinator
        entry.async_on_unload = MagicMock()

        # Set up against the original model (CHEM2 not yet present), then deliver
        # the new IntelliChem via the dynamic listener - mirroring it coming
        # online after startup.
        added: list[Any] = []
        await setup(hass, entry, added.extend)

        new_obj = model.add_object(CHEM2_OBJNAM, dict(CHEM2_PARAMS))
        assert new_obj is not None

        added.clear()
        state["listener"]([new_obj])

        chem2 = [e for e in added if e.unique_id.startswith("test_entry_CHEM2")]
        # Both platforms expose at least one CHEM2 entity (sensor readings /
        # setpoint numbers).
        assert chem2, f"{setup.__module__} created no entity for the new IntelliChem"


# -------------------------------------------------------------------------------------
# bodies_affected_by helper
# -------------------------------------------------------------------------------------


class TestBodiesAffectedBy:
    """Tests for the heater/body cross-reference helper."""

    def test_body_candidate_returned(
        self, hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
    ) -> None:
        """A body passed as a candidate is returned."""
        mock_coordinator.model = pool_model
        body = pool_model["POOL1"]
        assert body is not None

        result = bodies_affected_by(mock_coordinator, [body])

        assert [b.objnam for b in result] == ["POOL1"]

    def test_heater_candidate_resolves_to_served_bodies(
        self, hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
    ) -> None:
        """A candidate heater maps to every body it serves."""
        mock_coordinator.model = pool_model
        heater = pool_model["HTR01"]
        assert heater is not None  # serves "POOL1 SPA01"

        result = bodies_affected_by(mock_coordinator, [heater])

        assert {b.objnam for b in result} == {"POOL1", "SPA01"}

    def test_non_body_non_heater_ignored(
        self, hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
    ) -> None:
        """Unrelated candidate objects yield no bodies."""
        mock_coordinator.model = pool_model
        sensor = pool_model["SENSE1"]
        assert sensor is not None

        assert bodies_affected_by(mock_coordinator, [sensor]) == []


# -------------------------------------------------------------------------------------
# async_setup_pool_entities dedup
# -------------------------------------------------------------------------------------


async def test_setup_pool_entities_dedups_across_calls(
    hass: HomeAssistant, pool_model: PoolModel, mock_coordinator: MagicMock
) -> None:
    """The shared helper never emits the same unique_id twice."""
    mock_coordinator.model = pool_model
    state = _capture_listener(mock_coordinator)

    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []

    def _build(coordinator: IntelliCenterCoordinator, candidates: Any) -> list[Any]:
        # Always emit a single entity for CHEM1 regardless of the candidate set,
        # to prove dedup is keyed on unique_id and not on the candidate identity.
        chem1 = coordinator.model["CHEM1"]
        from custom_components.intellicenter.sensor import PoolSensor

        return [
            PoolSensor(coordinator, chem1, device_class=None, attribute_key="PHVAL")
        ]

    async_setup_pool_entities(entry, added.extend, _build)
    assert len(added) == 1

    # Driving the listener again with the same builder output must add nothing.
    added.clear()
    state["listener"]([pool_model["CHEM1"]])
    assert added == []


async def test_light_group_parent_refreshes_when_members_arrive_later(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A parent built first gains and loses effects without replacement."""
    from custom_components.intellicenter.light import _build_entities

    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    parent = model.add_object(
        "GROUP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "LITSHO",
            "SNAME": "Color Group",
            "STATUS": "OFF",
            "USE": "WHITER",
        },
    )
    assert parent is not None
    mock_coordinator.model = model
    state = _capture_listener(mock_coordinator)
    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    async_setup_pool_entities(entry, added.extend, _build_entities)

    assert len(added) == 1
    parent_entity = added[0]
    assert parent_entity._pool_object is parent
    assert parent_entity.effect_list is None
    assert not parent_entity.supported_features & LightEntityFeature.EFFECT
    parent_entity.hass = hass
    parent_entity.async_write_ha_state = MagicMock()

    added.clear()
    later_objects = (
        (
            "GLOW1",
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GLOW",
                "SNAME": "GloBrite One",
                "STATUS": "OFF",
                "USE": "WHITER",
            },
        ),
        (
            "GLOW2",
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GLOW",
                "SNAME": "GloBrite Two",
                "STATUS": "OFF",
                "USE": "WHITER",
            },
        ),
        (
            "GROUP_ROW_1",
            {
                "OBJTYP": CIRCGRP_TYPE,
                "PARENT": "GROUP",
                "CIRCUIT": "GLOW1",
                "LISTORD": "1",
            },
        ),
        (
            "GROUP_ROW_2",
            {
                "OBJTYP": CIRCGRP_TYPE,
                "PARENT": "GROUP",
                "CIRCUIT": "GLOW2",
                "LISTORD": "2",
            },
        ),
    )
    for objnam, params in later_objects:
        candidate = model.add_object(objnam, params)
        assert candidate is not None
        state["listener"]([candidate])

    assert {entity._pool_object.objnam for entity in added} == {"GLOW1", "GLOW2"}
    assert all(entity is not parent_entity for entity in added)
    assert parent_entity.effect_list is not None
    assert parent_entity.supported_features & LightEntityFeature.EFFECT
    parent_entity.async_write_ha_state.assert_called_once_with()

    row = model["GROUP_ROW_2"]
    assert row is not None
    row.update({"CIRCUIT": "MISSING"})
    mock_coordinator.data = {"GROUP_ROW_2": {"CIRCUIT": "MISSING"}}
    parent_entity._handle_coordinator_update()

    assert parent_entity.effect_list is None
    assert not parent_entity.supported_features & LightEntityFeature.EFFECT
    assert parent_entity.async_write_ha_state.call_count == 2


# -------------------------------------------------------------------------------------
# issue #57: a PMPCIRC child arriving BEFORE its parent pump
# -------------------------------------------------------------------------------------

# A pump-circuit whose parent pump may not yet be in the model. Its select
# entity can only be built once the parent VSF pump (supporting BOTH RPM and
# GPM) is present, so it cleanly demonstrates the "child before parent" skip.
PMPCIRC2_OBJNAM = "PMPCIRC2"
PMPCIRC2_PARAMS: dict[str, str] = {
    "OBJTYP": PMPCIRC_TYPE,
    "SNAME": "Spa Pump Circuit",
    "PARENT": "PUMP2",
    "CIRCUIT": "SPA01",
    "SELECT": "RPM",
    "SPEED": "2400",
    "GPM": "60",
}

PUMP2_OBJNAM = "PUMP2"
PUMP2_PARAMS: dict[str, str] = {
    "OBJTYP": PUMP_TYPE,
    "SUBTYP": "VSF",
    "SNAME": "Spa Pump",
    "STATUS": "10",
    "MIN": "450",
    "MAX": "3450",
    "MINF": "15",
    "MAXF": "140",
}


async def test_pmpcirc_select_built_when_parent_pump_arrives_later(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """A PMPCIRC's select entity is built once its parent pump arrives later.

    Regression test for issue #57 (Fix B). The pump-mode select needs its parent
    pump to know the pump supports BOTH RPM and GPM. If the PMPCIRC arrives in
    one update and the pump in a LATER separate update, the child was previously
    skipped, marked known, and never reconsidered. The coordinator now
    re-dispatches an already-known object whose parent just arrived, so the
    select entity is finally created.
    """
    from custom_components.intellicenter.select import async_setup_entry

    coordinator = _make_coordinator(hass, pool_model)

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)

    def added_for(objnam: str) -> list[Any]:
        return [e for e in added if e._pool_object.objnam == objnam]

    # The PMPCIRC child appears first, while its parent pump is still absent.
    new_child = pool_model.add_object(PMPCIRC2_OBJNAM, dict(PMPCIRC2_PARAMS))
    assert new_child is not None
    assert pool_model[PUMP2_OBJNAM] is None  # parent genuinely not in the model

    added.clear()
    coordinator._async_detect_new_objects()

    # With no parent pump, capabilities are unknown so NO select is created. The
    # child is now recorded as known (and would never be reconsidered without
    # the dependent re-dispatch).
    assert added_for(PMPCIRC2_OBJNAM) == []
    assert PMPCIRC2_OBJNAM in coordinator._known_objnams

    # The parent pump arrives in a SEPARATE, later update.
    new_pump = pool_model.add_object(PUMP2_OBJNAM, dict(PUMP2_PARAMS))
    assert new_pump is not None

    added.clear()
    coordinator._async_detect_new_objects()

    # The pump itself is new; the PMPCIRC is re-dispatched as a dependent and its
    # select is now created because the parent pump's capabilities are known.
    assert added_for(PMPCIRC2_OBJNAM), (
        "select did not create an entity for the PMPCIRC once its parent pump arrived"
    )


async def test_pmpcirc_number_built_when_parent_pump_arrives_later(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """A PMPCIRC's number entity is built once its parent pump arrives later.

    Regression test for the number-platform limit-upgrade gap (companion to the
    select test above). Previously the number platform eagerly built a PMPCIRC
    entity with guessed RPM-only defaults even when the parent pump was absent;
    unique_id de-duplication then prevented the correct entity (e.g. the VSF
    PumpSpeedNumber) from ever replacing it. The builder now skips while the
    parent is absent, and the coordinator re-dispatch (issue #57) builds the
    correct entity once the parent VSF pump appears.
    """
    from custom_components.intellicenter.number import (
        PumpSpeedNumber,
        async_setup_entry,
    )

    coordinator = _make_coordinator(hass, pool_model)

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)

    def added_for(objnam: str) -> list[Any]:
        return [e for e in added if e._pool_object.objnam == objnam]

    # The PMPCIRC child appears first, while its parent pump is still absent.
    new_child = pool_model.add_object(PMPCIRC2_OBJNAM, dict(PMPCIRC2_PARAMS))
    assert new_child is not None
    assert pool_model[PUMP2_OBJNAM] is None  # parent genuinely not in the model

    added.clear()
    coordinator._async_detect_new_objects()

    # With no parent pump, the pump type/limits are unknown, so NO number entity
    # is created (it would otherwise be a wrong-class default that could never be
    # upgraded). The child is recorded as known.
    assert added_for(PMPCIRC2_OBJNAM) == []
    assert PMPCIRC2_OBJNAM in coordinator._known_objnams

    # The parent VSF pump arrives in a SEPARATE, later update.
    new_pump = pool_model.add_object(PUMP2_OBJNAM, dict(PUMP2_PARAMS))
    assert new_pump is not None

    added.clear()
    coordinator._async_detect_new_objects()

    # The PMPCIRC is re-dispatched as a dependent; the number platform now builds
    # the correct VSF entity (a single dynamic PumpSpeedNumber) for it.
    pmpcirc_numbers = added_for(PMPCIRC2_OBJNAM)
    assert pmpcirc_numbers, (
        "number platform did not build an entity for the PMPCIRC once its "
        "parent pump arrived"
    )
    assert any(isinstance(e, PumpSpeedNumber) for e in pmpcirc_numbers)


async def test_pmpcirc_redispatched_when_parent_pump_arrives_later(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """A known PMPCIRC is re-dispatched when its parent pump arrives later.

    Regression test for issue #57 (Fix B) at the coordinator layer, covering the
    re-dispatch mechanism that feeds every dependent platform (select AND number
    both key their PMPCIRC entities off the parent pump). The PMPCIRC is known
    but its parent pump only arrives in a later, separate update; the coordinator
    must include the PMPCIRC in that update's dispatched batch so the platforms
    get a chance to (re)build its entities.
    """
    coordinator = _make_coordinator(hass, pool_model)

    received: list[list[PoolObject]] = []
    coordinator.async_add_new_objects_listener(received.append)

    # The PMPCIRC arrives before its parent pump and is skipped/recorded.
    pool_model.add_object(PMPCIRC2_OBJNAM, dict(PMPCIRC2_PARAMS))
    coordinator._async_detect_new_objects()
    assert len(received) == 1
    assert {obj.objnam for obj in received[0]} == {PMPCIRC2_OBJNAM}

    # The parent pump arrives later; the known PMPCIRC is re-dispatched with it.
    pool_model.add_object(PUMP2_OBJNAM, dict(PUMP2_PARAMS))
    coordinator._async_detect_new_objects()
    assert len(received) == 2
    dispatched = {obj.objnam for obj in received[1]}
    assert dispatched == {PUMP2_OBJNAM, PMPCIRC2_OBJNAM}


async def test_pmpcirc_not_redispatched_without_parent_arrival(
    hass: HomeAssistant, pool_model: PoolModel
) -> None:
    """A known PMPCIRC is not re-dispatched when an UNRELATED object arrives.

    The dependent re-dispatch (issue #57, Fix B) must be scoped to children
    whose parent is among the just-arrived objects, so an unrelated new object
    does not cause spurious re-evaluation of every known child.
    """
    coordinator = _make_coordinator(hass, pool_model)

    received: list[list[PoolObject]] = []
    coordinator.async_add_new_objects_listener(received.append)

    # PMPCIRC01 (parent PUMP1) is already known from the fixture. An unrelated
    # new sensor arrives - it shares no parent relationship with the PMPCIRC.
    pool_model.add_object(SENSE2_OBJNAM, dict(SENSE2_PARAMS))
    coordinator._async_detect_new_objects()

    assert len(received) == 1
    dispatched = {obj.objnam for obj in received[0]}
    # Only the genuinely-new sensor is dispatched; the known PMPCIRC is not.
    assert dispatched == {SENSE2_OBJNAM}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# -------------------------------------------------------------------------------------
# Backfill re-dispatch: a runtime-added pump arrives WITHOUT its telemetry attrs
# -------------------------------------------------------------------------------------

PUMP3_OBJNAM = "PUMP3"
# What the introducing NotifyList carries: identity only, no PWR/RPM/GPM yet.
PUMP3_SPARSE_PARAMS: dict[str, str] = {
    "OBJTYP": PUMP_TYPE,
    "SUBTYP": "SPEED",
    "SNAME": "Booster Pump",
    "STATUS": "10",
}
# What the controller's RequestParamList backfill delivers afterwards.
PUMP3_BACKFILL_UPDATE: dict[str, str] = {
    "PWR": "850",
    "RPM": "2400",
    "MIN": "450",
    "MAX": "3450",
}


async def test_pump_sensors_built_after_attribute_backfill(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """Pump telemetry sensors are created once the attribute backfill arrives.

    Regression: a runtime-added pump is dispatched to the platforms before the
    controller has fetched its tracked attributes, so the power/RPM sensor
    builders (gated on those attributes) skipped it - and nothing ever
    reconsidered the pump, leaving the sensors missing until a reload. The
    coordinator now re-dispatches an object once its first post-add update
    (the backfill) lands.
    """
    from custom_components.intellicenter.sensor import async_setup_entry

    coordinator = _make_coordinator(hass, pool_model)

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []
    await async_setup_entry(hass, entry, added.extend)

    def added_for(objnam: str) -> list[Any]:
        return [e for e in added if e._pool_object.objnam == objnam]

    # The NotifyList introduces the pump with only the notified params.
    new_pump = pool_model.add_object(PUMP3_OBJNAM, dict(PUMP3_SPARSE_PARAMS))
    assert new_pump is not None
    added.clear()
    coordinator.async_set_updated_data({PUMP3_OBJNAM: dict(PUMP3_SPARSE_PARAMS)})

    # Sparse first dispatch: telemetry attrs absent, so no PWR/RPM sensors yet.
    assert not [
        e for e in added_for(PUMP3_OBJNAM) if e._attribute_key in ("PWR", "RPM")
    ]
    assert PUMP3_OBJNAM in coordinator._pending_redispatch

    # The backfill applies the remaining tracked attributes to the model and
    # surfaces as a normal update for the (now known) object.
    new_pump.update(dict(PUMP3_BACKFILL_UPDATE))
    added.clear()
    coordinator.async_set_updated_data({PUMP3_OBJNAM: dict(PUMP3_BACKFILL_UPDATE)})

    keys = {e._attribute_key for e in added_for(PUMP3_OBJNAM)}
    assert "PWR" in keys, "power sensor missing after backfill re-dispatch"
    assert "RPM" in keys, "rpm sensor missing after backfill re-dispatch"
    assert PUMP3_OBJNAM not in coordinator._pending_redispatch

    # The re-dispatch is one-shot: further updates add nothing new.
    added.clear()
    coordinator.async_set_updated_data({PUMP3_OBJNAM: {"RPM": "2600"}})
    assert added_for(PUMP3_OBJNAM) == []
