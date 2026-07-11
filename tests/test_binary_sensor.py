"""Test the Pentair IntelliCenter binary sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    PUMP_TYPE,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.binary_sensor import (
    HeaterBinarySensor,
    PoolBinarySensor,
)

pytestmark = pytest.mark.asyncio


def _mock_model(*objects: PoolObject) -> MagicMock:
    """Return a coordinator-model mock that is iterable and indexable by objnam."""
    by_name = {obj.objnam: obj for obj in objects}
    model = MagicMock()
    model.__getitem__ = MagicMock(side_effect=lambda objnam: by_name.get(objnam))
    model.__iter__ = MagicMock(side_effect=lambda: iter(objects))
    return model


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
    mock_coordinator.model = _mock_model(pool_body)

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
    mock_coordinator.model = _mock_model(pool_body)

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
    mock_coordinator.model = _mock_model(pool_body)

    sensor = HeaterBinarySensor(
        mock_coordinator,
        pool_object_heater_sensor,
    )

    assert sensor.is_on is False


async def test_heater_sensor_different_heater(
    hass: HomeAssistant,
    pool_object_heater_sensor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test heater sensor when a different heater is being used."""

    # Create mock pool body using a different heater
    pool_body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR02",  # Different heater
            "HTMODE": "1",
        },
    )
    mock_coordinator.model = _mock_model(pool_body)

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
    mock_coordinator.model = _mock_model(pool_body, spa_body)

    sensor = HeaterBinarySensor(mock_coordinator, heater)

    # Should be on because pool is heating
    assert sensor.is_on is True

    # Should update on either body's changes
    assert sensor.isUpdated({"POOL1": {HTMODE_ATTR: "0"}}) is True
    assert sensor.isUpdated({"SPA01": {STATUS_ATTR: "ON"}}) is True


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
    mock_coordinator.model = _mock_model(pool_body)

    sensor = HeaterBinarySensor(mock_coordinator, pool_object_heater_sensor)
    assert sensor.is_on is False


async def test_heater_sensor_cross_body_heat_source(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: heating via a heater whose BODY list omits the body.

    The panel allows a body's heat source (HEATER) to point at a heater
    whose own BODY attribute does not include that body. Observed on a real
    IntelliCenter: spa B1202 heats with HEATER=H0001 ("Pool Heater") while
    H0001.BODY only lists the pool body B1101. The served-body scan missed
    it, so neither heater sensor ever reported the spa heating.
    """
    pool_heater = PoolObject(
        "H0001",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Pool Heater",
            "BODY": "B1101",
        },
    )
    spa_heater = PoolObject(
        "H0002",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Spa Heater",
            "BODY": "B1202",
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
            "HEATER": "H0001",  # Heat source outside this body's heater
            "HTMODE": "1",  # Actively heating
        },
    )
    mock_coordinator.model = _mock_model(pool_heater, spa_heater, pool_body, spa_body)

    pool_heater_sensor = HeaterBinarySensor(mock_coordinator, pool_heater)
    spa_heater_sensor = HeaterBinarySensor(mock_coordinator, spa_heater)

    # H0001 is firing (for the spa); H0002 is idle.
    assert pool_heater_sensor.is_on is True
    assert spa_heater_sensor.is_on is False

    # Updates to the spa body must refresh H0001's sensor even though the
    # spa is absent from H0001's BODY list.
    assert pool_heater_sensor.isUpdated({"B1202": {HTMODE_ATTR: "0"}}) is True
