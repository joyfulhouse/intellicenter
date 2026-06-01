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

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import CHEM_TYPE, SENSE_TYPE, PoolModel, PoolObject
import pytest

from custom_components.intellicenter import (
    async_setup_pool_entities,
    bodies_affected_by,
)
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator

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
        model = PoolModel()
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
