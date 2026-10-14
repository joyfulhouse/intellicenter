"""Test the Pentair IntelliCenter binary sensor platform."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    ORPHI_ATTR,
    ORPLO_ATTR,
    PHHI_ATTR,
    PHLO_ATTR,
    PUMP_TYPE,
    SCHED_TYPE,
    STATUS_ATTR,
    STATUS_ON,
    SYSTEM_TYPE,
    UPDATE_ATTR,
    ICBaseController,
    ICCommandError,
    ICModelController,
    ICSystemInfo,
    ICTimeoutError,
    PoolModel,
    PoolObject,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intellicenter import async_unload_entry
from custom_components.intellicenter.binary_sensor import (
    ChemAlertBinarySensor,
    FirmwareUpdateBinarySensor,
    HeaterBinarySensor,
    PoolBinarySensor,
    PumpBinarySensor,
    ScheduleBinarySensor,
    SystemModeBinarySensor,
    _build_entities,
)
from custom_components.intellicenter.const import DNTSTP_ATTR, DOMAIN, SINGLE_ATTR
from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP

from tests.conftest import ON_OFF_UNKNOWN_CASES

pytestmark = pytest.mark.asyncio


@pytest.fixture
def connection_transport() -> Generator[tuple[AsyncMock, AsyncMock]]:
    """Mock network operations while keeping library startup/retry/stop real."""

    async def connect(controller: ICBaseController) -> None:
        controller._connection = MagicMock(connected=True)
        controller._connection.disconnect = AsyncMock()
        controller._system_info = ICSystemInfo(
            "SYS01",
            {
                "SNAME": "System",
                "PROPNAME": "Test Pool",
                "VER": "3.008",
                "MODE": "ENGLISH",
            },
        )

    with (
        patch.object(ICBaseController, "start", connect),
        patch.object(
            ICModelController, "get_all_objects", new_callable=AsyncMock
        ) as snapshot,
        patch.object(ICModelController, "send_cmd", new_callable=AsyncMock) as command,
    ):
        snapshot.return_value = []
        command.return_value = {"objectList": []}
        yield snapshot, command


def _connection_entry(hass: HomeAssistant, suffix: str = "1") -> MockConfigEntry:
    """Register an independent entry without running a config flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Pool {suffix}",
        unique_id=f"panel-{suffix}",
        data={CONF_HOST: f"192.0.2.{suffix}"},
    )
    entry.add_to_hass(hass)
    return entry


def _connection_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Find the sensor through its stable registry identity."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_connection"
    )
    assert entity_id is not None
    return entity_id


async def test_connection_registry_empty_model_two_entries_and_retirement(
    hass: HomeAssistant, connection_transport: tuple[AsyncMock, AsyncMock]
) -> None:
    """Empty models still get complete shared devices and independent observers."""
    entries = []
    for suffix in ("1", "2"):
        entry = _connection_entry(hass, suffix)
        entries.append(entry)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ids = [_connection_id(hass, entry) for entry in entries]
    assert ids[0] != ids[1]
    registry = er.async_get(hass)
    for entry, entity_id in zip(entries, ids, strict=True):
        sensor = registry.async_get(entity_id)
        assert sensor is not None
        assert sensor.original_name == "Connection"
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC
        assert sensor.disabled_by is None
        state = hass.states.get(entity_id)
        assert state is not None and state.state == "on"
        assert state.attributes["device_class"] == "connectivity"
        device = dr.async_get(hass).async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
        assert device is not None and sensor.device_id == device.id
        assert (device.manufacturer, device.model, device.name, device.sw_version) == (
            "Pentair",
            "IntelliCenter",
            "Test Pool",
            "3.008",
        )
        coordinator = entry.runtime_data
        assert len(coordinator._broadcast_update_listeners) == 1
        # Repeated equipment discovery/removal must not own this observer.
        for _ in range(2):
            coordinator.model.add_object(
                "FRZ01",
                {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "FRZ",
                    "SNAME": "Freeze",
                    "STATUS": "OFF",
                },
            )
            coordinator.async_set_updated_data({"FRZ01": {"STATUS": "OFF"}})
            await hass.async_block_till_done()
            equipment_id = registry.async_get_entity_id(
                "binary_sensor", DOMAIN, f"{entry.entry_id}_FRZ01"
            )
            assert equipment_id is not None
            assert registry.async_get(equipment_id).device_id == device.id
            coordinator.model.remove_object("FRZ01")
            coordinator.async_set_updated_data({"FRZ01": None})
            await hass.async_block_till_done()
        assert (
            len(
                [
                    e
                    for e in registry.entities.values()
                    if e.unique_id == f"{entry.entry_id}_connection"
                ]
            )
            == 1
        )
        assert hass.states.get(entity_id).state == "on"
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._broadcast_update_listeners
        coordinator.async_set_connection_state(False)
        assert hass.states.get(entity_id).state == "unavailable"


async def test_connection_states_refresh_and_silent_reconnect(
    hass: HomeAssistant, connection_transport: tuple[AsyncMock, AsyncMock]
) -> None:
    """Connection stays available off; a stale diff cannot hide transitions."""
    snapshot, command = connection_transport
    snapshot.return_value = [
        {
            "objnam": "FRZ01",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "FRZ",
                "SNAME": "Freeze",
                "STATUS": "OFF",
            },
        }
    ]
    entry = _connection_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _connection_id(hass, entry)
    equipment_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_FRZ01"
    )
    assert equipment_id is not None
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data({"OTHER": {"STATUS": "ON"}})
    health = coordinator.last_update_success
    requests = command.await_count
    assert await async_setup_component(hass, "homeassistant", {})
    with patch.object(
        coordinator, "async_request_refresh", new_callable=AsyncMock
    ) as refresh:
        await hass.services.async_call(
            "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True
        )
        refresh.assert_not_awaited()
    assert coordinator.last_update_success is health
    assert command.await_count == requests
    assert hass.states.get(equipment_id).state == "off"
    coordinator._handler._is_connected = False
    coordinator._controller._connection = None
    coordinator._handler.on_disconnected(coordinator.controller, None)
    assert hass.states.get(entity_id).state == "off"
    assert hass.states.get(equipment_id).state == "unavailable"
    # Transport live during backfill, before on_reconnected / handler flag.
    coordinator._controller._connection = MagicMock(
        connected=True, disconnect=AsyncMock()
    )
    coordinator.async_set_updated_data({"OTHER": {"STATUS": "OFF"}})
    assert coordinator._handler._is_connected is False
    assert hass.states.get(entity_id).state == "on"
    coordinator._handler._is_connected = True
    coordinator._handler.on_reconnected(coordinator.controller)
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(equipment_id).state == "off"
    assert command.await_count == requests
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "failure",
    [ICCommandError("rejected"), ICTimeoutError("timed out")],
    ids=["rejected", "timeout"],
)
async def test_connection_failed_partial_reconnect_publishes_off_before_wait(
    hass: HomeAssistant,
    connection_transport: tuple[AsyncMock, AsyncMock],
    failure: Exception,
) -> None:
    """Exercise real model rollback and retry callbacks, with no injected disconnect."""
    snapshot, command = connection_transport
    snapshot.return_value = [
        {
            "objnam": "OLD",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "FRZ",
                "SNAME": "Old",
                "STATUS": "OFF",
            },
        }
    ]
    entry = _connection_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _connection_id(hass, entry)
    coordinator = entry.runtime_data
    handler = coordinator._handler
    handler._is_connected = False
    coordinator.controller._connection = None
    # Leave the last published on state until the original delay/debounce runs.
    snapshot.return_value = [
        {"objnam": "SYS01", "params": {"OBJTYP": SYSTEM_TYPE, "SNAME": "System"}}
    ]
    early_states = []

    async def reject_monitoring(*args, **kwargs):
        early_states.append(hass.states.get(entity_id).state)
        assert coordinator.connected is True
        assert handler._is_connected is False
        raise failure

    command.side_effect = reject_monitoring

    class RetryWait(BaseException):
        """Stop the real starter at its second failed-attempt retry wait."""

    waits = []

    async def retry_sleep(delay):
        waits.append((delay, hass.states.get(entity_id).state))
        if len(waits) == 1:
            assert waits[-1] == (30, "on")  # original delay does not advance debounce
            return
        assert coordinator.connected is False
        assert hass.states.get(entity_id).state == "off"
        if len(waits) == 3:
            raise RetryWait

    try:
        with patch("pyintellicenter.controller.asyncio.sleep", retry_sleep):
            with pytest.raises(RetryWait):
                await handler._starter(30)
        assert early_states == ["on", "off"]
        assert [state for _, state in waits] == ["on", "off", "off"]
        assert hass.states.get(entity_id).state == "off"
        command.side_effect = None
        await handler._starter(0)
        assert coordinator.connected is True
        assert handler._failure_count == 0
        assert hass.states.get(entity_id).state == "on"
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


async def test_connection_registry_choices_reload_and_failed_unload(
    hass: HomeAssistant, connection_transport: tuple[AsyncMock, AsyncMock]
) -> None:
    """Names/disable choices persist; subscriptions follow successful unload only."""
    entry = _connection_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _connection_id(hass, entry)
    registry = er.async_get(hass)
    coordinator = entry.runtime_data
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await async_unload_entry(hass, entry)
    assert len(coordinator._broadcast_update_listeners) == 1
    assert coordinator._handler._stopped is False
    coordinator._handler._is_connected = False
    coordinator.controller._connection = None
    coordinator._handler.on_disconnected(coordinator.controller, None)
    assert hass.states.get(entity_id).state == "off"
    registry.async_update_entity(
        entity_id, name="My panel link", disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert not coordinator._broadcast_update_listeners
    # Reload uses a new coordinator without changing the identity or choices.
    hass.config_entries.async_update_entry(
        entry, data={CONF_HOST: "192.0.2.99", "transport": "websocket"}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    new_coordinator = entry.runtime_data
    assert new_coordinator is not coordinator
    assert _connection_id(hass, entry) == entity_id
    assert registry.async_get(entity_id).name == "My panel link"
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.USER
    assert not new_coordinator._broadcast_update_listeners
    registry.async_update_entity(entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data._broadcast_update_listeners) == 1
    assert hass.states.get(entity_id).attributes["friendly_name"] == "My panel link"
    coordinator.async_set_connection_state(False)
    assert hass.states.get(entity_id).state == "on"
    active_coordinator = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not active_coordinator._broadcast_update_listeners


async def test_connection_startup_and_reload_failure_do_not_fabricate_off(
    hass: HomeAssistant, connection_transport: tuple[AsyncMock, AsyncMock]
) -> None:
    """Failed setup has no new observer; a registered observer becomes unavailable."""
    entry = _connection_entry(hass)
    with patch.object(ICBaseController, "start", side_effect=ICTimeoutError("offline")):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert (
        er.async_get(hass).async_get_entity_id(
            "binary_sensor", DOMAIN, f"{entry.entry_id}_connection"
        )
        is None
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _connection_id(hass, entry)
    assert hass.states.get(entity_id).state == "on"
    coordinator = entry.runtime_data
    with patch.object(ICBaseController, "start", side_effect=ICTimeoutError("offline")):
        assert not await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get(entity_id).state == "unavailable"
    assert not coordinator._broadcast_update_listeners
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _connection_id(hass, entry) == entity_id
    assert hass.states.get(entity_id).state == "on"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_schedule_attributes_are_tracked() -> None:
    """PoolModel retains every schedule attribute exposed by its entities."""
    assert {
        "STATUS",
        "ACT",
        "CIRCUIT",
        "DAY",
        "TIME",
        "TIMOUT",
        "HEATER",
        "LOTMP",
        SINGLE_ATTR,
        DNTSTP_ATTR,
        "VACFLO",
    } <= DEFAULT_ATTRIBUTES_MAP[SCHED_TYPE]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", True),
        ("0", False),
        ("ON", True),
        ("OFF", False),
        (None, None),
        ("BROKEN", None),
    ],
)
async def test_firmware_update_sensor_state_mapping(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    raw_value: str | None,
    expected: bool | None,
) -> None:
    """SYSTEM.UPDATE maps valid flags and rejects malformed values."""
    system = PoolObject(
        "SYS01",
        {"OBJTYP": SYSTEM_TYPE, "SNAME": "System", "UPDATE": raw_value},
    )

    sensors = _build_entities(mock_coordinator, [system])
    update_sensors = [
        item for item in sensors if isinstance(item, FirmwareUpdateBinarySensor)
    ]

    assert len(update_sensors) == 1
    sensor = update_sensors[0]
    assert sensor.name == "Firmware Update Available"
    assert sensor.device_class == BinarySensorDeviceClass.UPDATE
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.entity_registry_enabled_default is True
    assert sensor.is_on is expected
    assert sensor.isUpdated({"SYS01": {UPDATE_ATTR: STATUS_ON}}) is True


@pytest.fixture
def pool_object_freeze() -> PoolObject:
    """Return a PoolObject representing a freeze protection circuit."""
    return PoolObject(
        "FRZ01",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "FRZ",
            "SNAME": "Freeze Protection",
            "STATUS": "OFF",
        },
    )


@pytest.fixture
def pool_object_heater_sensor() -> PoolObject:
    """Return a PoolObject representing a heater."""
    return PoolObject(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GAS",
            "SNAME": "Gas Heater",
            "BODY": "POOL1 SPA01",
        },
    )


@pytest.fixture
def pool_object_pump_sensor() -> PoolObject:
    """Return a PoolObject representing a pump."""
    return PoolObject(
        "PUMP1",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VS",
            "SNAME": "Pool Pump",
            "STATUS": "10",
        },
    )


@pytest.fixture
def pool_object_vsf_pump() -> PoolObject:
    """Return a PoolObject for a VSF pump that publishes RPM/PWR/GPM telemetry.

    STATUS is "10" (the pump is enabled) while every telemetry reading is zero -
    the idle-VSF case from issue #112, where a STATUS-keyed sensor reads on.
    """
    return PoolObject(
        "PMP02",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VSF",
            "SNAME": "Spa Jets",
            "STATUS": "10",
            "RPM": "0",
            "PWR": "0",
            "GPM": "0",
        },
    )


@pytest.fixture
def pool_object_schedule() -> PoolObject:
    """Return a PoolObject representing a schedule."""
    return PoolObject(
        "SCHED1",
        {
            "OBJTYP": "SCHED",
            "SNAME": "Morning Filter",
            "ACT": "ON",
            "VACFLO": "OFF",
            "CIRCUIT": "CIRC01",
            "DAY": "MTWRF",
            "TIME": "08:00",
            "TIMOUT": "10:00",
            "HEATER": "HTR01",
            "LOTMP": "82",
            "SINGLE": "OFF",
            "DNTSTP": "ON",
        },
    )


async def test_binary_sensor_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test binary sensor platform creates entities."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.binary_sensor import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create binary sensors for:
    # - Heater (HTR01)
    # - Pump (PUMP1)
    # - Schedule (SCHED1)
    assert len(entities_added) >= 3


async def test_chemistry_binary_sensors_created_only_for_intellichem(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Only IntelliChem creates the aggregate chemistry alert sensor."""
    intellichem = PoolObject(
        "CHEM1",
        {"OBJTYP": CHEM_TYPE, "SUBTYP": "ICHEM", "SNAME": "IntelliChem"},
    )
    intellichlor = PoolObject(
        "CHEM2",
        {"OBJTYP": CHEM_TYPE, "SUBTYP": "ICHLOR", "SNAME": "IntelliChlor"},
    )

    sensors = _build_entities(mock_coordinator, [intellichem, intellichlor])

    assert (
        len([sensor for sensor in sensors if isinstance(sensor, ChemAlertBinarySensor)])
        == 1
    )
    chemistry_alert = next(
        sensor for sensor in sensors if isinstance(sensor, ChemAlertBinarySensor)
    )
    assert chemistry_alert.unique_id == "test_entry_CHEM1CHEM_ALERT"
    assert chemistry_alert.entity_registry_enabled_default is True
    assert all(sensor._pool_object.objnam != "CHEM2" for sensor in sensors)


async def test_legacy_alarm_sensors_remain_on_intellichem_subtype(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """All four existing per-alarm sensors remain attached only to IntelliChem."""
    alarm_values = {
        PHHI_ATTR: "OFF",
        PHLO_ATTR: "OFF",
        ORPHI_ATTR: "OFF",
        ORPLO_ATTR: "OFF",
    }
    intellichem = PoolObject(
        "CHEM1",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHEM",
            "SNAME": "IntelliChem",
            **alarm_values,
        },
    )
    intellichlor = PoolObject(
        "CHEM2",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHLOR",
            "SNAME": "IntelliChlor",
            **alarm_values,
        },
    )

    chem_sensors = _build_entities(mock_coordinator, [intellichem])
    chlor_sensors = _build_entities(mock_coordinator, [intellichlor])

    individual_chem_alarms = {
        sensor._attribute_key
        for sensor in chem_sensors
        if type(sensor) is PoolBinarySensor
    }
    individual_chlor_alarms = {
        sensor._attribute_key
        for sensor in chlor_sensors
        if type(sensor) is PoolBinarySensor
    }
    assert individual_chem_alarms == {
        PHHI_ATTR,
        PHLO_ATTR,
        ORPHI_ATTR,
        ORPLO_ATTR,
    }
    assert individual_chlor_alarms == set()


@pytest.mark.parametrize(
    ("values", "helper_result", "expected"),
    [
        (
            {PHHI_ATTR: "OFF", PHLO_ATTR: "OFF", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            False,
            False,
        ),
        (
            {PHHI_ATTR: "ON", PHLO_ATTR: "OFF", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            True,
            True,
        ),
        (
            {PHHI_ATTR: None, PHLO_ATTR: "ON", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            True,
            True,
        ),
        (
            {PHHI_ATTR: None, PHLO_ATTR: "OFF", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            False,
            None,
        ),
        (
            {PHHI_ATTR: None, PHLO_ATTR: "OFF", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            True,
            None,
        ),
        (
            {PHHI_ATTR: "BAD", PHLO_ATTR: "OFF", ORPHI_ATTR: "OFF", ORPLO_ATTR: "OFF"},
            False,
            None,
        ),
    ],
)
async def test_chem_alert_state_mapping(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    values: dict[str, str | None],
    helper_result: bool,
    expected: bool | None,
) -> None:
    """A known active alert wins even when another input is unknown."""
    chem = PoolObject(
        "CHEM1",
        {"OBJTYP": CHEM_TYPE, "SUBTYP": "ICHEM", "SNAME": "IntelliChem", **values},
    )
    mock_coordinator.controller.has_chem_alert.return_value = helper_result
    mock_coordinator.controller.get_chem_alerts.return_value = (
        ["pH High"] if helper_result else []
    )
    sensor = ChemAlertBinarySensor(mock_coordinator, chem)

    assert sensor.is_on is expected
    if expected is not None:
        assert sensor.extra_state_attributes["active_alerts"] == (
            ["pH High"] if helper_result else []
        )
    else:
        assert "active_alerts" not in sensor.extra_state_attributes


async def test_freeze_protection_sensor_off(
    hass: HomeAssistant,
    pool_object_freeze: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test freeze protection sensor when off."""

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_freeze,
        icon="mdi:snowflake",
        device_class=BinarySensorDeviceClass.COLD,
    )

    assert sensor.is_on is False
    assert sensor.name == "Freeze Protection"
    assert sensor._attr_device_class == BinarySensorDeviceClass.COLD


async def test_freeze_protection_sensor_on(
    hass: HomeAssistant,
    pool_object_freeze: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test freeze protection sensor when on."""

    # Set status to ON
    pool_object_freeze.update({STATUS_ATTR: "ON"})

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_freeze,
        device_class=BinarySensorDeviceClass.COLD,
    )

    assert sensor.is_on is True


async def test_pump_sensor_running(
    hass: HomeAssistant,
    pool_object_pump_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """A single-speed pump with no telemetry falls back to STATUS."""

    sensor = PumpBinarySensor(mock_coordinator, pool_object_pump_sensor)

    assert sensor.is_on is True
    assert sensor._attr_device_class == BinarySensorDeviceClass.RUNNING


async def test_pump_sensor_stopped(
    hass: HomeAssistant,
    pool_object_pump_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """A single-speed pump reads off when STATUS leaves the running value."""

    pool_object_pump_sensor.update({STATUS_ATTR: "4"})

    sensor = PumpBinarySensor(mock_coordinator, pool_object_pump_sensor)

    assert sensor.is_on is False


async def test_pump_sensor_idle_despite_status_on(
    hass: HomeAssistant,
    pool_object_vsf_pump: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Zero telemetry means off even while STATUS still reads "10" (issue #112)."""

    sensor = PumpBinarySensor(mock_coordinator, pool_object_vsf_pump)

    assert sensor.is_on is False


@pytest.mark.parametrize(
    ("telemetry", "expected"),
    [
        ({"RPM": "3068", "PWR": "1300", "GPM": "53"}, True),
        ({"RPM": "3068", "PWR": "0", "GPM": "0"}, True),
        ({"RPM": "0", "PWR": "1300", "GPM": "0"}, True),
        ({"RPM": "0", "PWR": "0", "GPM": "53"}, True),
        ({"RPM": "0", "PWR": "0", "GPM": "0"}, False),
    ],
)
async def test_pump_sensor_any_telemetry_above_zero_means_running(
    hass: HomeAssistant,
    pool_object_vsf_pump: PoolObject,
    mock_coordinator: MagicMock,
    telemetry: dict[str, str],
    expected: bool,
) -> None:
    """Any of RPM, PWR or GPM above zero reports the pump as running."""

    pool_object_vsf_pump.update(telemetry)

    sensor = PumpBinarySensor(mock_coordinator, pool_object_vsf_pump)

    assert sensor.is_on is expected


async def test_pump_sensor_ignores_unparsable_telemetry(
    hass: HomeAssistant,
    pool_object_vsf_pump: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Empty telemetry is skipped; the remaining readings still decide."""

    pool_object_vsf_pump.update({"RPM": "", "PWR": "1300", "GPM": ""})

    sensor = PumpBinarySensor(mock_coordinator, pool_object_vsf_pump)

    assert sensor.is_on is True


async def test_pump_sensor_updates_on_telemetry(
    hass: HomeAssistant,
    pool_object_vsf_pump: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Telemetry-only pushes update the entity; the panel never pushes STATUS."""

    sensor = PumpBinarySensor(mock_coordinator, pool_object_vsf_pump)

    assert sensor.isUpdated({"PMP02": {"RPM": "3069"}}) is True
    assert sensor.isUpdated({"PMP02": {"PWR": "1306"}}) is True
    assert sensor.isUpdated({"PMP02": {"GPM": "53"}}) is True
    assert sensor.isUpdated({"PMP02": {STATUS_ATTR: "4"}}) is True
    assert sensor.isUpdated({"PMP02": {"SNAME": "Renamed"}}) is False
    assert sensor.isUpdated({"OTHER": {"RPM": "3069"}}) is False


async def test_pump_sensor_unique_id_unchanged(
    hass: HomeAssistant,
    pool_object_vsf_pump: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """The entity keys off STATUS_ATTR, so existing pump entities carry over."""

    sensor = PumpBinarySensor(mock_coordinator, pool_object_vsf_pump)
    legacy = PoolBinarySensor(
        mock_coordinator,
        pool_object_vsf_pump,
        value_for_on="10",
        device_class=BinarySensorDeviceClass.RUNNING,
    )

    assert sensor.unique_id == legacy.unique_id


async def test_schedule_sensor_active(
    hass: HomeAssistant,
    pool_object_schedule: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test schedule sensor when active."""

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_schedule,
        attribute_key="ACT",
        name="+ (schedule)",
        enabled_by_default=False,
    )

    assert sensor.is_on is True
    assert sensor._attr_entity_registry_enabled_default is False


async def test_schedule_sensor_inactive(
    hass: HomeAssistant,
    pool_object_schedule: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test schedule sensor when inactive."""

    # Set schedule to inactive
    pool_object_schedule.update({"ACT": "OFF"})

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_schedule,
        attribute_key="ACT",
    )

    assert sensor.is_on is False


@pytest.mark.parametrize(("raw_value", "expected"), ON_OFF_UNKNOWN_CASES)
async def test_schedule_binary_sensor_state_mapping(
    mock_coordinator: MagicMock,
    raw_value: str | None,
    expected: bool | None,
) -> None:
    """Schedule runtime state maps only canonical protocol ON/OFF values."""
    schedule = PoolObject(
        "SCHED1",
        {"OBJTYP": SCHED_TYPE, "SNAME": "Schedule", "ACT": raw_value},
    )

    assert ScheduleBinarySensor(mock_coordinator, schedule).is_on is expected


async def test_schedule_sensor_details_and_disabled_default(
    hass: HomeAssistant,
    pool_object_schedule: PoolObject,
    pool_object_switch: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Schedule running sensor exposes complete details and circuit name."""
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda objnam: (
            pool_object_switch if objnam == "CIRC01" else pool_object_schedule
        )
    )
    mock_coordinator.controller.get_schedule_circuit.return_value = "CIRC01"
    mock_coordinator.controller.get_schedule_days.return_value = "MTWRF"
    mock_coordinator.controller.get_schedule_start_time.return_value = "08:00"
    mock_coordinator.controller.get_schedule_stop_time.return_value = "10:00"

    sensor = ScheduleBinarySensor(mock_coordinator, pool_object_schedule)
    attrs = sensor.extra_state_attributes

    assert sensor.entity_registry_enabled_default is False
    assert attrs["CIRCUIT"] == "CIRC01"
    assert attrs["CIRCUIT_NAME"] == "Pool Cleaner"
    assert attrs["DAY"] == "MTWRF"
    assert attrs["TIME"] == "08:00"
    assert attrs["TIMOUT"] == "10:00"
    assert attrs["HEATER"] == "HTR01"
    assert attrs["LOTMP"] == "82"
    assert attrs["SINGLE"] == "OFF"
    assert attrs["DNTSTP"] == "ON"
    assert attrs["VACFLO"] == "OFF"

    for attribute in (
        "ACT",
        "CIRCUIT",
        "DAY",
        "TIME",
        "TIMOUT",
        "HEATER",
        "LOTMP",
        "SINGLE",
        "DNTSTP",
        "STATUS",
        "VACFLO",
    ):
        assert sensor.isUpdated({"SCHED1": {attribute: "changed"}}) is True


async def test_schedule_sensor_omits_missing_details(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Missing schedule detail fields are absent from state attributes."""
    schedule = PoolObject(
        "SCHED2",
        {"OBJTYP": SCHED_TYPE, "SNAME": "Incomplete", "ACT": "OFF"},
    )
    mock_coordinator.controller.get_schedule_circuit.return_value = None
    mock_coordinator.controller.get_schedule_days.return_value = None
    mock_coordinator.controller.get_schedule_start_time.return_value = None
    mock_coordinator.controller.get_schedule_stop_time.return_value = None

    attrs = ScheduleBinarySensor(mock_coordinator, schedule).extra_state_attributes

    for key in (
        "CIRCUIT",
        "CIRCUIT_NAME",
        "DAY",
        "TIME",
        "TIMOUT",
        "HEATER",
        "LOTMP",
        "SINGLE",
        "DNTSTP",
        "VACFLO",
    ):
        assert key not in attrs


async def test_heater_sensor_heating(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor when actively heating."""

    # Create mock pool body that is using this heater
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",  # Heating
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_body)
    mock_coordinator.model.get_by_type.return_value = [pool_body]

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    assert sensor.is_on is True
    assert sensor._attr_device_class == BinarySensorDeviceClass.HEAT


async def test_heater_sensor_not_heating(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor when not heating."""

    # Create mock pool body that is not using this heater
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "0",  # Not heating (at temperature)
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_body)
    mock_coordinator.model.get_by_type.return_value = [pool_body]

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    assert sensor.is_on is False


async def test_heater_sensor_body_off(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor when body is off."""

    # Create mock pool body that is off
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_body)
    mock_coordinator.model.get_by_type.return_value = [pool_body]

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    assert sensor.is_on is False


@pytest.mark.parametrize(
    "heater_attrs",
    [{}, {"HEATER": "HTR02"}],
    ids=["missing-heater", "different-heater"],
)
async def test_heater_sensor_ignores_unselected_body(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
    heater_attrs: dict[str, str],
) -> None:
    """Test heater sensor when the body has no heater or a different heater."""

    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HTMODE": "1",
            **heater_attrs,
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_body)
    mock_coordinator.model.get_by_type.return_value = [pool_body]

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    assert sensor.is_on is False


async def test_heater_sensor_is_updated_body_changes(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor isUpdated when body attributes change."""

    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=None)

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    # Should update on body status change
    assert sensor.isUpdated({"POOL1": {STATUS_ATTR: "ON"}}) is True

    # Should update on body heater change
    assert sensor.isUpdated({"POOL1": {HEATER_ATTR: "HTR01"}}) is True

    # Should update on body htmode change
    assert sensor.isUpdated({"POOL1": {HTMODE_ATTR: "1"}}) is True

    # Should update on heater object change
    assert sensor.isUpdated({"HTR01": {"STATUS": "ON"}}) is True

    # Should not update on unrelated object
    assert sensor.isUpdated({"OTHER": {STATUS_ATTR: "ON"}}) is False


async def test_heater_sensor_multiple_bodies(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor with multiple bodies."""

    heater = PoolObject(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SNAME": "Gas Heater",
            "BODY": "POOL1 SPA01",  # Supports both bodies
        },
    )

    # Pool is heating
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )

    # Spa is not
    spa_body = PoolObject(
        "SPA01",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "OFF",
            "HEATER": "HTR01",
            "HTMODE": "0",
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_body if x == "POOL1" else spa_body
    )
    mock_coordinator.model.get_by_type.return_value = [pool_body, spa_body]

    sensor = HeaterBinarySensor(mock_coordinator, heater)

    # Should be on because pool is heating
    assert sensor.is_on is True

    # Should update on either body's changes
    assert sensor.isUpdated({"POOL1": {HTMODE_ATTR: "0"}}) is True
    assert sensor.isUpdated({"SPA01": {STATUS_ATTR: "ON"}}) is True


async def test_heater_sensor_detects_body_outside_heater_body_list(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: a body's HEATER is authoritative over the heater's BODY list."""
    heater = PoolObject(
        "H0001",
        {
            "OBJTYP": HEATER_TYPE,
            "SNAME": "Pool Heater",
            "BODY": "B1101",
        },
    )
    pool_body = PoolObject(
        "B1101",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "H0001",
            "HTMODE": "0",
        },
    )
    spa_body = PoolObject(
        "B1202",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": "H0001",
            "HTMODE": "1",
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda objnam: {
            pool_body.objnam: pool_body,
            spa_body.objnam: spa_body,
        }.get(objnam)
    )
    mock_coordinator.model.get_by_type.return_value = [pool_body, spa_body]

    sensor = HeaterBinarySensor(mock_coordinator, heater)

    assert sensor.is_on is True
    assert sensor.isUpdated({"B1202": {HTMODE_ATTR: "0"}}) is True


async def test_binary_sensor_unique_id(
    hass: HomeAssistant,
    pool_object_freeze: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test binary sensor unique ID generation."""

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_freeze,
    )

    assert sensor.unique_id == "test_entry_FRZ01"


async def test_binary_sensor_state_updates(
    hass: HomeAssistant,
    pool_object_freeze: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test binary sensor state updates from IntelliCenter."""

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_freeze,
    )

    # Initial state is OFF
    assert sensor.is_on is False

    # Simulate update from IntelliCenter
    updates = {"FRZ01": {STATUS_ATTR: "ON"}}
    assert sensor.isUpdated(updates) is True

    # Apply the update
    pool_object_freeze.update(updates["FRZ01"])

    # Verify state changed
    assert sensor.is_on is True


async def test_heater_sensor_tracks_rewired_bodies(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: the served-body set must be derived live, not frozen.

    The bodies were parsed from BODY once at construction, so a heater
    rewired to a different body at runtime kept reporting against the stale
    set until restart (the issue-#57 staleness class).
    """
    sensor = HeaterBinarySensor(mock_coordinator, pool_object_heater_sensor)

    before = sensor._bodies

    # The panel rewires the heater to another body at runtime.
    pool_object_heater_sensor.update({"BODY": "B1102"})

    assert sensor._bodies == {"B1102"}
    assert sensor._bodies != before


async def test_heater_sensor_unknown_htmode_is_not_heating(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: a missing HTMODE must not report 'heating' (None != '0')."""
    # Body on, this heater selected, but HTMODE never delivered.
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": pool_object_heater_sensor.objnam,
        },
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_body)
    mock_coordinator.model.get_by_type.return_value = [pool_body]

    sensor = HeaterBinarySensor(mock_coordinator, pool_object_heater_sensor)
    assert sensor.is_on is False


# -------------------------------------------------------------------------------------
# System mode "Not in Auto" problem sensor


@pytest.fixture
def pool_object_system_mode() -> PoolObject:
    """Return a SYSTEM PoolObject exposing the SERVICE operating-mode attribute."""
    return PoolObject(
        "_5451",
        {
            "OBJTYP": SYSTEM_TYPE,
            "SNAME": "IntelliCenter System",
            "MODE": "ENGLISH",
            "VER": "2.0.0",
            "SERVICE": "AUTO",
        },
    )


async def test_system_mode_binary_sensor_created(
    hass: HomeAssistant,
    pool_object_system_mode: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """A Not in Auto problem sensor is created for a SYSTEM object with SERVICE."""
    sensors = _build_entities(mock_coordinator, [pool_object_system_mode])

    problem_sensors = [s for s in sensors if isinstance(s, SystemModeBinarySensor)]
    assert len(problem_sensors) == 1
    sensor = problem_sensors[0]
    assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


async def test_system_mode_binary_sensor_not_created_without_service(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """No Not in Auto sensor is created when SYSTEM lacks the SERVICE attribute."""
    system_obj = PoolObject(
        "_5451",
        {
            "OBJTYP": SYSTEM_TYPE,
            "SNAME": "IntelliCenter System",
            "MODE": "ENGLISH",
        },
    )
    sensors = _build_entities(mock_coordinator, [system_obj])
    assert not [s for s in sensors if isinstance(s, SystemModeBinarySensor)]


@pytest.mark.parametrize(
    ("raw_service", "expected"),
    [
        ("AUTO", False),
        ("auto", False),
        ("SERVICE", True),
        ("Service", True),
        ("MANUAL", True),  # hardware protocol spelling for indefinite service
        ("manual", True),
        ("TIMOUT", True),  # hardware protocol spelling (issue #80)
        ("TIMEOUT", True),
        ("Time Out", True),
        ("GARBAGE", None),  # unknown mode -> unknown, never a false alarm
        (None, None),
    ],
)
async def test_system_mode_binary_sensor_is_on(
    hass: HomeAssistant,
    pool_object_system_mode: PoolObject,
    mock_coordinator: MagicMock,
    raw_service: str | None,
    expected: bool | None,
) -> None:
    """is_on mirrors the normalized system mode: on iff not auto, unknown if unmapped."""
    if raw_service is None:
        pool_object_system_mode.update({"SERVICE": None})
    else:
        pool_object_system_mode.update({"SERVICE": raw_service})

    sensor = SystemModeBinarySensor(mock_coordinator, pool_object_system_mode)
    assert sensor.is_on is expected


async def test_system_mode_binary_sensor_state_updates(
    hass: HomeAssistant,
    pool_object_system_mode: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """The sensor tracks SERVICE updates pushed by IntelliCenter."""
    sensor = SystemModeBinarySensor(mock_coordinator, pool_object_system_mode)
    assert sensor.is_on is False

    updates = {"_5451": {"SERVICE": "TIMOUT"}}
    assert sensor.isUpdated(updates) is True
    pool_object_system_mode.update(updates["_5451"])
    assert sensor.is_on is True
