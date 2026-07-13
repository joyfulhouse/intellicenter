"""Test the Pentair IntelliCenter binary sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    DLY_ATTR,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    PUMP_TYPE,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    SYSTEM_TYPE,
    UPDATE_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.binary_sensor import (
    DelayBinarySensor,
    FirmwareUpdateBinarySensor,
    HeaterBinarySensor,
    PoolBinarySensor,
    SystemModeBinarySensor,
    _build_entities,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(STATUS_ON, True), (STATUS_OFF, False), (None, None), ("BROKEN", None)],
)
async def test_circuit_delay_sensor_state_mapping(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    raw_value: str | None,
    expected: bool | None,
) -> None:
    """Circuit delay status is diagnostic and unknown for invalid values."""
    circuit = PoolObject(
        "CIRC01",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SNAME": "Pool Cleaner",
            "DLY": raw_value,
        },
    )

    sensor = DelayBinarySensor(mock_coordinator, circuit)

    assert sensor.name == "Pool Cleaner Delay"
    assert sensor.is_on is expected
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.entity_registry_enabled_default is False


async def test_circuit_delay_sensor_created_when_value_missing(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Every circuit gets a stable delay entity even before DLY is delivered."""
    circuit = PoolObject(
        "CIRC01",
        {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Pool Cleaner"},
    )

    sensors = _build_entities(mock_coordinator, [circuit])

    delay_sensors = [item for item in sensors if isinstance(item, DelayBinarySensor)]
    assert len(delay_sensors) == 1
    assert delay_sensors[0].is_on is None
    assert delay_sensors[0].isUpdated({"CIRC01": {DLY_ATTR: STATUS_ON}}) is True


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(STATUS_ON, True), (STATUS_OFF, False), (None, None), ("BROKEN", None)],
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
def pool_object_schedule() -> PoolObject:
    """Return a PoolObject representing a schedule."""
    return PoolObject(
        "SCHED1",
        {
            "OBJTYP": "SCHED",
            "SNAME": "Morning Filter",
            "ACT": "ON",
            "VACFLO": "OFF",
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
    """Test pump sensor when running."""

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_pump_sensor,
        value_for_on="10",  # Pump running value
        device_class=BinarySensorDeviceClass.RUNNING,
    )

    assert sensor.is_on is True
    assert sensor._attr_device_class == BinarySensorDeviceClass.RUNNING


async def test_pump_sensor_stopped(
    hass: HomeAssistant,
    pool_object_pump_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test pump sensor when stopped."""

    # Set pump to stopped
    pool_object_pump_sensor.update({STATUS_ATTR: "4"})

    sensor = PoolBinarySensor(
        mock_coordinator,
        pool_object_pump_sensor,
        value_for_on="10",
        device_class=BinarySensorDeviceClass.RUNNING,
    )

    assert sensor.is_on is False


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
