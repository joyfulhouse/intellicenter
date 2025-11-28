"""Test the Pentair IntelliCenter water heater platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.water_heater import PoolWaterHeater

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_object_body_with_heater() -> PoolObject:
    """Return a PoolObject representing a pool body with heater."""
    return PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "LSTTMP": "78",
            "LOTMP": "72",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )


@pytest.fixture
def pool_object_heater() -> PoolObject:
    """Return a PoolObject representing a heater."""
    return PoolObject(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GAS",
            "SNAME": "Gas Heater",
            "BODY": "POOL1 SPA01",
            "LISTORD": "1",
        },
    )


@pytest.fixture
def pool_object_heater2() -> PoolObject:
    """Return a PoolObject representing a second heater."""
    return PoolObject(
        "HTR02",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "SOLAR",
            "SNAME": "Solar Heater",
            "BODY": "POOL1",
            "LISTORD": "2",
        },
    )


async def test_water_heater_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater platform creates entities for bodies with heaters."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.water_heater import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create water heater entities for Pool and Spa bodies
    # (both have heaters in the test data)
    assert len(entities_added) == 2

    water_heater_names = [e._pool_object.sname for e in entities_added]
    assert "Pool" in water_heater_names
    assert "Spa" in water_heater_names


async def test_water_heater_entity_properties(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolWaterHeater entity properties."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    # Test properties
    assert water_heater.name == "Pool"
    assert water_heater.unique_id == "test_entry_POOL1LOTMP"
    assert water_heater.current_temperature == 78.0
    assert water_heater.target_temperature == 72.0
    assert water_heater.state == STATE_ON  # STATUS=ON, HTMODE=1
    assert water_heater.temperature_unit == str(UnitOfTemperature.FAHRENHEIT)


async def test_water_heater_state_heating(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when actively heating."""

    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",  # Heating
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    assert water_heater.state == STATE_ON


async def test_water_heater_state_idle(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when idle (at temperature)."""

    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "0",  # At temperature (idle)
            "LOTMP": "72",
            "LSTTMP": "72",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    assert water_heater.state == STATE_IDLE


async def test_water_heater_state_off(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when off."""

    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",  # Body off
            "HEATER": "HTR01",
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    assert water_heater.state == STATE_OFF


async def test_water_heater_state_no_heater(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when no heater assigned."""

    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,  # No heater assigned
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    assert water_heater.state == STATE_OFF


async def test_water_heater_set_temperature(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting target temperature uses convenience method."""
    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_set_temperature(**{ATTR_TEMPERATURE: 80})

    # Should use set_setpoint convenience method
    mock_coordinator.controller.set_setpoint.assert_called_once_with("POOL1", 80)


async def test_water_heater_set_temperature_invalid(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting invalid temperature (should be handled gracefully)."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    # This should log an error but not crash
    await water_heater.async_set_temperature(**{ATTR_TEMPERATURE: "invalid"})

    # Should not call request_changes for invalid value
    mock_coordinator.controller.request_changes.assert_not_called()


async def test_water_heater_turn_on(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning on the water heater."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,  # No heater currently
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01", "HTR02"])
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert HEATER_ATTR in args[1]
    assert args[1][HEATER_ATTR] == "HTR01"  # Uses first heater in list


async def test_water_heater_turn_on_remembers_last_heater(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_heater2: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning on uses last heater if available."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_heater2
        if x == "HTR02"
        else pool_object_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR02",  # Currently using solar heater
            "HTMODE": "1",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01", "HTR02"])
    water_heater.hass = hass  # Required for async_create_task

    # Simulate update that tracks last heater
    updates = {
        "POOL1": {
            STATUS_ATTR: "ON",
            HEATER_ATTR: "HTR02",
            HTMODE_ATTR: "1",
        }
    }
    assert water_heater.isUpdated(updates) is True

    # Now turn off
    body.update({HEATER_ATTR: NULL_OBJNAM, HTMODE_ATTR: "0"})

    # Turn back on
    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == "HTR02"  # Uses remembered heater


async def test_water_heater_turn_off(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning off the water heater."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert HEATER_ATTR in args[1]
    assert args[1][HEATER_ATTR] == NULL_OBJNAM


async def test_water_heater_operation_list(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    pool_object_heater: PoolObject,
    pool_object_heater2: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test operation mode list."""

    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_heater2
        if x == "HTR02"
        else pool_object_heater
    )
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01", "HTR02"],
    )

    operations = water_heater.operation_list

    assert STATE_OFF in operations
    assert "Gas Heater" in operations
    assert "Solar Heater" in operations


async def test_water_heater_set_operation_mode(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting operation mode."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_set_operation_mode("Gas Heater")

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert HEATER_ATTR in args[1]
    assert args[1][HEATER_ATTR] == "HTR01"


async def test_water_heater_set_operation_mode_off(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting operation mode to off."""

    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_set_operation_mode(STATE_OFF)

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == NULL_OBJNAM


async def test_water_heater_supported_features(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test supported features."""

    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    features = water_heater.supported_features

    assert features & WaterHeaterEntityFeature.TARGET_TEMPERATURE
    assert features & WaterHeaterEntityFeature.OPERATION_MODE


async def test_water_heater_min_max_temp_fahrenheit(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test min/max temperature in Fahrenheit."""

    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    assert water_heater.min_temp == 4.0
    assert water_heater.max_temp == 104.0


async def test_water_heater_min_max_temp_celsius(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test min/max temperature in Celsius."""
    # Set uses_metric to True BEFORE creating the water heater
    type(mock_coordinator.system_info).uses_metric = property(lambda self: True)

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    assert water_heater.min_temp == 5.0
    assert water_heater.max_temp == 40.0


async def test_water_heater_is_updated(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test isUpdated method for relevant attributes."""

    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    # Should update on status change
    assert water_heater.isUpdated({"POOL1": {STATUS_ATTR: "ON"}}) is True

    # Should update on heater change
    assert water_heater.isUpdated({"POOL1": {HEATER_ATTR: "HTR01"}}) is True

    # Should update on htmode change
    assert water_heater.isUpdated({"POOL1": {HTMODE_ATTR: "1"}}) is True

    # Should update on temperature change
    assert water_heater.isUpdated({"POOL1": {LSTTMP_ATTR: "80"}}) is True
    assert water_heater.isUpdated({"POOL1": {LOTMP_ATTR: "75"}}) is True

    # Should not update on unrelated object
    assert water_heater.isUpdated({"OTHER": {STATUS_ATTR: "ON"}}) is False

    # Should not update on unrelated attribute
    assert water_heater.isUpdated({"POOL1": {"UNRELATED": "value"}}) is False


async def test_water_heater_extra_state_attributes(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test extra state attributes."""

    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    attrs = water_heater.extra_state_attributes

    assert "OBJNAM" in attrs
    assert attrs["OBJNAM"] == "POOL1"
    assert "LAST_HEATER" in attrs  # Should include last heater
    assert attrs["LAST_HEATER"] == "HTR01"
