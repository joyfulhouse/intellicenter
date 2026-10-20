"""Calibration contracts use synthetic limits, never claimed hardware captures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pyintellicenter import ICCommandError, ICModelController, PoolModel
import pytest

from custom_components.intellicenter.coordinator import (
    DEFAULT_ATTRIBUTES_MAP,
    IntelliCenterCoordinator,
)
from custom_components.intellicenter.number import async_setup_entry
from custom_components.intellicenter.sensor import SensorProbeReading
from custom_components.intellicenter.sensor_calibration import (
    CALIBRATION_SUPPORT,
    CalibrationLimits,
    SensorCalibrationNumber,
    build_calibration_entities,
    convert_offset,
    parse_calibration_integer,
)

pytestmark = pytest.mark.asyncio
FIRMWARE = "synthetic-contract-only"
SENSOR = {
    "OBJTYP": "SENSE",
    "SUBTYP": "POOL",
    "SNAME": "Water 1",
    "STATUS": "OK",
    "PROBE": "20",
    "SOURCE": "20",
    "CALIB": "0",
}


@pytest.fixture
def support():
    """Inject arbitrary test policy; no production firmware is enabled."""
    with patch.dict(CALIBRATION_SUPPORT, clear=True):
        for subtype in ("POOL", "SOLAR", "AIR"):
            for mode in ("METRIC", "ENGLISH"):
                CALIBRATION_SUPPORT[FIRMWARE, subtype, mode] = CalibrationLimits(
                    -4, 6, 1, "Synthetic test policy, not device evidence"
                )
        yield


def setup_model(coordinator, mode="METRIC", value="0"):
    coordinator.model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    coordinator.model.add_object(
        "SYS", {"OBJTYP": "SYSTEM", "MODE": mode, "VER": FIRMWARE}
    )
    controller = ICModelController("192.0.2.185", coordinator.model)
    coordinator.controller.get_sensor_probe_reading.side_effect = (
        controller.get_sensor_probe_reading
    )
    coordinator.controller.get_sensor_calibration.side_effect = (
        controller.get_sensor_calibration
    )
    return coordinator.model.add_object("water-west", {**SENSOR, "CALIB": value})


def make_number(coordinator, mode="METRIC", value="0"):
    sensor = setup_model(coordinator, mode, value)
    return build_calibration_entities(coordinator, [sensor])[0]


def readback(objnam="water-west", value="2"):
    return {"objectList": [{"objnam": objnam, "params": {"CALIB": value}}]}


async def test_production_gate_is_empty(mock_coordinator):
    sensor = setup_model(mock_coordinator)
    assert CALIBRATION_SUPPORT == {}
    assert build_calibration_entities(mock_coordinator, [sensor]) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0),
        (0, 0),
        (" -2 ", -2),
        ("+2", 2),
        (None, None),
        ("", None),
        ("bad", None),
        ("1.5", None),
        (1.5, None),
        (False, None),
        (float("inf"), None),
        ("NaN", None),
        ("2.0", None),
    ],
)
async def test_integer_parser(raw, expected):
    assert parse_calibration_integer(raw) == expected


@pytest.mark.parametrize("mode", ["METRIC", "ENGLISH"])
@pytest.mark.parametrize("units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
@pytest.mark.parametrize("raw", ["0", 0, "-2", "2"])
async def test_delta_values_and_bounds(mock_coordinator, support, mode, units, raw):
    mock_coordinator.hass.config.units = units
    number = make_number(mock_coordinator, mode, raw)
    source = (
        UnitOfTemperature.CELSIUS if mode == "METRIC" else UnitOfTemperature.FAHRENHEIT
    )
    factor = (
        1
        if source == units.temperature_unit
        else (1.8 if mode == "METRIC" else 1 / 1.8)
    )
    assert number.native_value == pytest.approx(int(raw) * factor)
    assert number.native_min_value == pytest.approx(-4 * factor)
    assert number.native_max_value == pytest.approx(6 * factor)
    assert number.native_step == pytest.approx(factor)
    assert number.native_unit_of_measurement == units.temperature_unit
    assert number.device_class is None
    assert number.available
    assert number.unique_id == "test_entry_water-westCALIB"
    assert number.entity_category == "config"
    assert not number.entity_registry_enabled_default


@pytest.mark.parametrize("raw", [None, "", "nope", "NaN", "1.5", "-5", "7", False])
async def test_malformed_or_out_of_range_readback_is_unknown(
    mock_coordinator, support, raw
):
    number = make_number(mock_coordinator, value=raw)
    assert number.native_value is None
    assert not number.available
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(1)
    assert exc.value.translation_key == "calibration_unavailable"
    mock_coordinator.controller.request_changes.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"STATUS": "DISCONNECTED"},
        {"STATUS": None},
        {"PROBE": None},
        {"PROBE": "ERROR"},
        {"SUBTYP": "UNKNOWN"},
    ],
)
async def test_no_controls_for_unsupported_or_disconnected(
    mock_coordinator, support, changes
):
    sensor = setup_model(mock_coordinator)
    sensor.update(changes)
    assert build_calibration_entities(mock_coordinator, [sensor]) == []


async def test_missing_calib_is_not_zero(mock_coordinator, support):
    setup_model(mock_coordinator)
    sensor = mock_coordinator.model.add_object(
        "missing", {k: v for k, v in SENSOR.items() if k != "CALIB"}
    )
    assert build_calibration_entities(mock_coordinator, [sensor]) == []


async def test_dual_body_mapping_and_probe_ids_stay_stable(mock_coordinator, support):
    setup_model(mock_coordinator)
    sensors = [
        mock_coordinator.model.add_object(objnam, {**SENSOR, "SUBTYP": subtype})
        for objnam, subtype in [
            ("water-west", "POOL"),
            ("water-east", "POOL"),
            ("roof-west", "SOLAR"),
            ("roof-east", "SOLAR"),
            ("air-custom", "AIR"),
        ]
    ]
    numbers = build_calibration_entities(mock_coordinator, sensors + sensors)
    assert {n.unique_id for n in numbers} == {
        f"test_entry_{s.objnam}CALIB" for s in sensors
    }
    assert len(numbers) == 5
    for sensor in sensors:
        probe = SensorProbeReading(mock_coordinator, sensor)
        assert probe.unique_id == f"test_entry_{sensor.objnam}PROBE"


@pytest.mark.parametrize("mode", ["METRIC", "ENGLISH"])
@pytest.mark.parametrize("units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
@pytest.mark.parametrize("offset", [-2, 0, 2])
async def test_write_encoding_and_authoritative_readback(
    mock_coordinator, support, mode, units, offset
):
    mock_coordinator.hass.config.units = units
    number = make_number(mock_coordinator, mode)

    async def acknowledge(*args):
        assert number.native_value == 0
        return {"response": "200"}

    mock_coordinator.controller.request_changes.side_effect = acknowledge
    mock_coordinator.controller.send_cmd = AsyncMock(
        return_value=readback(value=str(offset))
    )
    value = convert_offset(offset, number._panel_unit, units.temperature_unit)
    await number.async_set_native_value(value)
    mock_coordinator.controller.request_changes.assert_awaited_once_with(
        "water-west", {"CALIB": str(offset)}
    )
    mock_coordinator.controller.send_cmd.assert_awaited_once_with(
        "GetParamList", {"objectList": [{"objnam": "water-west", "keys": ["CALIB"]}]}
    )
    assert number.native_value == pytest.approx(value)


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"objectList": []},
        {"objectList": "bad"},
        {"objectList": [None]},
        readback("another-sensor"),
        readback(value="bad"),
        readback(value="2.0"),
        readback(value="0"),
        {"objectList": [{"objnam": "water-west", "params": None}]},
        {"objectList": readback()["objectList"] * 2},
    ],
)
async def test_acknowledged_write_without_valid_readback_fails(
    mock_coordinator, support, response
):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)
    mock_coordinator.controller.send_cmd = AsyncMock(return_value=response)
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(2)
    assert exc.value.translation_key == "calibration_unconfirmed"
    assert number.native_value == 0
    assert number._sensor["CALIB"] == "0"


@pytest.mark.parametrize("read_failure", [False, True])
async def test_command_errors_are_awaited_and_translated(
    mock_coordinator, support, read_failure
):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)
    mock_coordinator.controller.send_cmd = AsyncMock(return_value=readback())
    command = (
        mock_coordinator.controller.send_cmd
        if read_failure
        else mock_coordinator.controller.request_changes
    )
    command.side_effect = ICCommandError("Rejected")
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(2)
    assert exc.value.translation_key == (
        "calibration_unconfirmed" if read_failure else "command_failed"
    )
    if not read_failure:
        mock_coordinator.controller.send_cmd.assert_not_called()
    assert number.native_value == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -5, 7, 0.5])
async def test_invalid_input_never_writes(mock_coordinator, support, value):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(value)
    assert exc.value.translation_key == "invalid_calibration"
    mock_coordinator.controller.request_changes.assert_not_called()


async def test_panel_unit_change_waits_for_new_calib(mock_coordinator, support):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator, value="2")
    mock_coordinator.model["SYS"].update({"MODE": "ENGLISH"})
    mock_coordinator.data = {"SYS": {"MODE": "ENGLISH"}}
    with patch.object(number, "async_write_ha_state"):
        number._handle_coordinator_update()
        assert number.native_value is None
        assert not number.available
        number._sensor.update({"CALIB": "4"})
        mock_coordinator.data = {"water-west": {"CALIB": "4"}}
        number._handle_coordinator_update()
    assert number.native_value == pytest.approx(4 / 1.8)
    assert number.coordinator_update_dependencies() == {"SYS": {"MODE", "VER"}}


async def test_unit_change_during_write_is_unconfirmed(mock_coordinator, support):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)

    async def changed_unit(*args):
        mock_coordinator.model["SYS"].update({"MODE": "ENGLISH"})
        return readback()

    mock_coordinator.controller.send_cmd = AsyncMock(side_effect=changed_unit)
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(2)
    assert exc.value.translation_key == "calibration_unconfirmed"
    assert number._sensor["CALIB"] == "0"


async def test_ha_unit_change_refreshes_delta_state(hass, mock_coordinator, support):
    hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator, value="2")
    number.hass = hass
    with patch.object(number, "async_write_ha_state") as write:
        await number.async_added_to_hass()
        hass.config.units = US_CUSTOMARY_SYSTEM
        hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE)
        await hass.async_block_till_done()
        assert number.native_value == pytest.approx(3.6)
        write.assert_called()
        await number.async_will_remove_from_hass()


async def test_dynamic_discovery_probe_recovery_and_reconnect(hass, support):
    hass.config.units = METRIC_SYSTEM
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "calibration-lifecycle"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.185")
    coordinator._handler._is_connected = True
    coordinator._started = True
    coordinator.model.add_object(
        "SYS", {"OBJTYP": "SYSTEM", "MODE": "METRIC", "VER": FIRMWARE}
    )
    coordinator._known_objnams = {"SYS"}
    entry.runtime_data = coordinator
    added = []
    await async_setup_entry(hass, entry, added.extend)
    sensor = coordinator.model.add_object(
        "water-west", {**SENSOR, "STATUS": "DISCONNECTED"}
    )
    coordinator.async_set_updated_data({"water-west": sensor.properties})
    assert added == []
    changed = sensor.update({"STATUS": "OK"})
    coordinator.async_set_updated_data({"water-west": changed})
    numbers = [e for e in added if isinstance(e, SensorCalibrationNumber)]
    assert len(numbers) == 1
    number = numbers[0]
    # Previously seen keys may arrive malformed, then recover without key growth.
    for raw in ("bad", "0", "-2"):
        changed = sensor.update({"CALIB": raw})
        coordinator.async_set_updated_data({"water-west": changed})
    assert len(added) == 1
    coordinator._handler._is_connected = False
    assert not number.available
    coordinator._handler._is_connected = True
    assert number.available
    assert number.native_value == -2


@pytest.mark.parametrize("initial_probe", [None, "", "bad", "1.5"])
async def test_initial_malformed_probe_recovers_without_reload(
    hass, support, initial_probe
):
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "probe-recovery"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.185")
    coordinator._handler._is_connected = True
    coordinator.model.add_object(
        "SYS", {"OBJTYP": "SYSTEM", "MODE": "METRIC", "VER": FIRMWARE}
    )
    sensor = coordinator.model.add_object(
        "water-west", {**SENSOR, "PROBE": initial_probe}
    )
    coordinator._known_objnams = {obj.objnam for obj in coordinator.model}
    coordinator._started = True
    coordinator._seed_redispatch_bookkeeping(sensor, only_if_deferred=True)
    entry.runtime_data = coordinator
    added = []
    await async_setup_entry(hass, entry, added.extend)
    assert added == []
    coordinator.async_set_updated_data({sensor.objnam: sensor.update({"PROBE": "20"})})
    assert len(added) == 1
    # Healthy numeric changes use targeted dispatch, not whole-model discovery.
    with patch.object(
        coordinator,
        "_async_detect_new_objects",
        wraps=coordinator._async_detect_new_objects,
    ):
        listeners = MagicMock()
        coordinator.async_add_new_objects_listener(listeners)
        coordinator.async_set_updated_data(
            {sensor.objnam: sensor.update({"PROBE": "21"})}
        )
        listeners.assert_not_called()


async def test_reconnect_snapshot_replaces_object_without_changing_id(
    mock_coordinator, support
):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)
    old_uid = number.unique_id
    mock_coordinator.connected = False
    assert not number.available
    setup_model(mock_coordinator, value="-2")
    mock_coordinator.connected = True
    mock_coordinator.data = {}
    with patch.object(number, "async_write_ha_state"):
        number._handle_coordinator_update()
    assert number.native_value == -2
    assert number.unique_id == old_uid


@pytest.mark.parametrize("mode", [None, "UNKNOWN", [], {}])
async def test_unknown_panel_mode_never_guesses_units(mock_coordinator, support, mode):
    sensor = setup_model(mock_coordinator, mode=mode)
    assert build_calibration_entities(mock_coordinator, [sensor]) == []


async def test_unverified_firmware_never_uses_other_firmware_limits(
    mock_coordinator, support
):
    sensor = setup_model(mock_coordinator)
    mock_coordinator.model["SYS"].update({"VER": "unverified"})
    assert build_calibration_entities(mock_coordinator, [sensor]) == []


async def test_protocol_lattice_is_validated(mock_coordinator, support):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    CALIBRATION_SUPPORT[FIRMWARE, "POOL", "METRIC"] = CalibrationLimits(
        -4, 6, 2, "Synthetic"
    )
    number = make_number(mock_coordinator)
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(1)
    assert exc.value.translation_key == "invalid_calibration"
    mock_coordinator.controller.request_changes.assert_not_called()


@pytest.mark.parametrize(
    "policy",
    [
        (-4, 6, 0, "test"),
        (6, -4, 1, "test"),
        (-4, 6, 3, "test"),
        (-4, 6, 1, ""),
        (-4.0, 6, 1, "test"),
    ],
)
async def test_limits_require_valid_integer_policy_and_evidence(policy):
    with pytest.raises(ValueError):
        CalibrationLimits(*policy)


async def test_number_service_uses_deltas_in_ha_units(hass, support):
    from homeassistant.components.number import DATA_COMPONENT
    from homeassistant.setup import async_setup_component

    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "calibration-service"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.185")
    coordinator._handler._is_connected = True
    coordinator._started = True
    coordinator.model.add_object(
        "SYS", {"OBJTYP": "SYSTEM", "MODE": "METRIC", "VER": FIRMWARE}
    )
    sensor = coordinator.model.add_object("water-west", dict(SENSOR))
    coordinator._known_objnams = {obj.objnam for obj in coordinator.model}
    number = build_calibration_entities(coordinator, [sensor])[0]
    number._attr_entity_registry_enabled_default = True
    coordinator.controller.request_changes = AsyncMock(return_value={"response": "200"})
    coordinator.controller.send_cmd = AsyncMock(return_value=readback())
    assert await async_setup_component(hass, "number", {})
    await hass.data[DATA_COMPONENT].async_add_entities([number])
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": number.entity_id, "value": 3.6},
        blocking=True,
    )
    state = hass.states.get(number.entity_id)
    assert float(state.state) == pytest.approx(3.6)
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.FAHRENHEIT
    assert state.attributes["min"] == pytest.approx(-7.2)
    assert state.attributes["step"] == pytest.approx(1.8)
    coordinator.controller.request_changes.assert_awaited_once_with(
        "water-west", {"CALIB": "2"}
    )


@pytest.mark.parametrize("transition", ["disconnect", "replace"])
async def test_lost_connection_or_replaced_model_during_read_is_unconfirmed(
    mock_coordinator, support, transition
):
    mock_coordinator.hass.config.units = METRIC_SYSTEM
    number = make_number(mock_coordinator)

    async def interrupted_read(*args):
        if transition == "disconnect":
            mock_coordinator.connected = False
        else:
            setup_model(mock_coordinator)
        return readback()

    mock_coordinator.controller.send_cmd = AsyncMock(side_effect=interrupted_read)
    with pytest.raises(HomeAssistantError) as exc:
        await number.async_set_native_value(2)
    assert exc.value.translation_key == "calibration_unconfirmed"
    assert number._sensor["CALIB"] == "0"
    assert mock_coordinator.controller.request_changes.await_count == 1


async def test_removed_sensor_can_return_with_same_unique_id(hass, support):
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "calibration-removal"
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.185")
    coordinator._handler._is_connected = True
    coordinator._started = True
    coordinator.model.add_object(
        "SYS", {"OBJTYP": "SYSTEM", "MODE": "METRIC", "VER": FIRMWARE}
    )
    coordinator.model.add_object("water-west", dict(SENSOR))
    coordinator._known_objnams = {obj.objnam for obj in coordinator.model}
    entry.runtime_data = coordinator
    added = []
    await async_setup_entry(hass, entry, added.extend)
    assert len(added) == 1
    coordinator.model.remove_object("water-west")
    coordinator.async_set_updated_data({"water-west": None})
    sensor = coordinator.model.add_object("water-west", {**SENSOR, "CALIB": "-2"})
    coordinator.async_set_updated_data({"water-west": dict(sensor.properties)})
    assert len(added) == 2
    assert added[0].unique_id == added[1].unique_id
    assert added[1].native_value == -2


async def test_existing_control_becomes_unknown_for_unknown_mode(
    mock_coordinator, support
):
    number = make_number(mock_coordinator, value="2")
    mock_coordinator.model["SYS"].update({"MODE": "UNKNOWN"})
    mock_coordinator.data = {"SYS": {"MODE": "UNKNOWN"}}
    with patch.object(number, "async_write_ha_state"):
        number._handle_coordinator_update()
    assert number.native_value is None
    assert not number.available
    # A reconnect signal alone cannot establish units for cached CALIB.
    mock_coordinator.data = {}
    with patch.object(number, "async_write_ha_state"):
        number._handle_coordinator_update()
    assert number.native_value is None
