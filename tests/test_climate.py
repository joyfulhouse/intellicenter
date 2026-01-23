"""Test the Pentair IntelliCenter climate platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HITMP_ATTR,
    HTMODE_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.climate import PoolClimate

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_object_body_with_ultratemp() -> PoolObject:
    """Return a PoolObject representing a pool body with UltraTemp heat pump."""
    return PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "LSTTMP": "78",
            "LOTMP": "72",
            "HITMP": "85",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )


@pytest.fixture
def pool_object_ultratemp_heater() -> PoolObject:
    """Return a PoolObject representing an UltraTemp heat pump."""
    return PoolObject(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "ULTRA",
            "SNAME": "UltraTemp",
            "BODY": "POOL1 SPA01",
            "LISTORD": "1",
        },
    )


async def test_climate_setup_creates_entities_only_for_cooling_capable(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test climate platform only creates entities for bodies with cooling support."""
    mock_coordinator.model = pool_model

    # Mock body_supports_cooling: Pool supports cooling, Spa does not
    mock_coordinator.controller.body_supports_cooling = MagicMock(
        side_effect=lambda objnam: objnam == "POOL1"
    )

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.climate import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should only create climate entity for Pool (has cooling support)
    assert len(entities_added) == 1
    assert entities_added[0]._pool_object.objnam == "POOL1"


async def test_climate_setup_no_entities_when_no_cooling_support(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test climate platform creates no entities when no cooling support."""
    mock_coordinator.model = pool_model

    # Mock body_supports_cooling: No bodies support cooling
    mock_coordinator.controller.body_supports_cooling = MagicMock(return_value=False)

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.climate import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create no climate entities
    assert len(entities_added) == 0


async def test_climate_entity_properties(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    pool_object_ultratemp_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolClimate entity properties."""
    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_ultratemp_heater
    )
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    # Test properties
    assert climate.name == "Pool"
    assert climate.unique_id == "test_entry_POOL1_climate"
    assert climate.current_temperature == 78.0
    assert climate.target_temperature_low == 72.0  # Heating setpoint
    assert climate.target_temperature_high == 85.0  # Cooling setpoint
    assert climate.temperature_unit == str(UnitOfTemperature.FAHRENHEIT)


async def test_climate_hvac_modes(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test climate HVAC modes."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    # Check available HVAC modes (only OFF and HEAT_COOL - system manages heat vs cool)
    assert HVACMode.OFF in climate.hvac_modes
    assert HVACMode.HEAT_COOL in climate.hvac_modes
    assert len(climate.hvac_modes) == 2


async def test_climate_hvac_mode_heat_cool_when_active(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC mode is heat_cool when heater is active."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    # Body is ON, heater is assigned, htmode is 1
    assert climate.hvac_mode == HVACMode.HEAT_COOL


async def test_climate_hvac_mode_heat_cool_when_heater_assigned(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC mode is heat_cool when heater is assigned, even if body is off.

    The hvac_mode reflects whether climate control is enabled (heater assigned),
    while hvac_action reflects actual heating/cooling state.
    """
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "LOTMP": "72",
            "HITMP": "85",
            "LSTTMP": "78",
        },
    )

    climate = PoolClimate(mock_coordinator, body, ["HTR01"])

    # Mode is HEAT_COOL when heater is assigned (system manages heat vs cool)
    # hvac_action will show OFF since body is off
    assert climate.hvac_mode == HVACMode.HEAT_COOL


async def test_climate_hvac_mode_off_when_no_heater(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC mode is off when no heater assigned."""
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
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "LOTMP": "72",
            "HITMP": "85",
            "LSTTMP": "78",
        },
    )

    climate = PoolClimate(mock_coordinator, body, ["HTR01"])

    assert climate.hvac_mode == HVACMode.OFF


async def test_climate_hvac_action_heating(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC action is heating when actively heating."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )
    mock_coordinator.controller.is_body_heating = MagicMock(return_value=True)

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    assert climate.hvac_action == HVACAction.HEATING


async def test_climate_hvac_action_cooling(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC action is cooling when actively cooling."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )
    mock_coordinator.controller.is_body_heating = MagicMock(return_value=False)
    mock_coordinator.controller.is_body_cooling = MagicMock(return_value=True)

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    assert climate.hvac_action == HVACAction.COOLING


async def test_climate_hvac_action_idle(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC action is idle when heater enabled but not heating or cooling."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )
    mock_coordinator.controller.is_body_heating = MagicMock(return_value=False)
    mock_coordinator.controller.is_body_cooling = MagicMock(return_value=False)

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    assert climate.hvac_action == HVACAction.IDLE


async def test_climate_hvac_action_off(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test HVAC action is off when body is off."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "LOTMP": "72",
            "HITMP": "85",
            "LSTTMP": "78",
        },
    )

    climate = PoolClimate(mock_coordinator, body, ["HTR01"])

    assert climate.hvac_action == HVACAction.OFF


async def test_climate_set_hvac_mode_off(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting HVAC mode to off."""
    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_set_hvac_mode(HVACMode.OFF)

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert args[1][HEATER_ATTR] == NULL_OBJNAM


async def test_climate_set_hvac_mode_heat_cool(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting HVAC mode to heat_cool."""
    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_set_hvac_mode(HVACMode.HEAT_COOL)

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert args[1][HEATER_ATTR] == "HTR01"


async def test_climate_set_temperature_heating(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting heating setpoint."""
    mock_coordinator.controller.set_heating_setpoint = AsyncMock()
    mock_coordinator.controller.set_cooling_setpoint = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_set_temperature(target_temp_low=75)

    mock_coordinator.controller.set_heating_setpoint.assert_called_once_with(
        "POOL1", 75
    )
    mock_coordinator.controller.set_cooling_setpoint.assert_not_called()


async def test_climate_set_temperature_cooling(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting cooling setpoint."""
    mock_coordinator.controller.set_heating_setpoint = AsyncMock()
    mock_coordinator.controller.set_cooling_setpoint = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_set_temperature(target_temp_high=88)

    mock_coordinator.controller.set_cooling_setpoint.assert_called_once_with(
        "POOL1", 88
    )
    mock_coordinator.controller.set_heating_setpoint.assert_not_called()


async def test_climate_set_temperature_both(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting both heating and cooling setpoints."""
    mock_coordinator.controller.set_heating_setpoint = AsyncMock()
    mock_coordinator.controller.set_cooling_setpoint = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_set_temperature(target_temp_low=75, target_temp_high=88)

    mock_coordinator.controller.set_heating_setpoint.assert_called_once_with(
        "POOL1", 75
    )
    mock_coordinator.controller.set_cooling_setpoint.assert_called_once_with(
        "POOL1", 88
    )


async def test_climate_turn_on(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning on the climate entity."""
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
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "LOTMP": "72",
            "HITMP": "85",
            "LSTTMP": "78",
        },
    )

    climate = PoolClimate(mock_coordinator, body, ["HTR01"])
    climate.hass = hass

    await climate.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert args[1][HEATER_ATTR] == "HTR01"


async def test_climate_turn_off(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning off the climate entity."""
    mock_coordinator.controller.request_changes = AsyncMock()
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )
    climate.hass = hass

    await climate.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert args[1][HEATER_ATTR] == NULL_OBJNAM


async def test_climate_supported_features(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test supported features."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    features = climate.supported_features

    assert features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert features & ClimateEntityFeature.TURN_ON
    assert features & ClimateEntityFeature.TURN_OFF


async def test_climate_min_max_temp_fahrenheit(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test min/max temperature in Fahrenheit."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    assert climate.min_temp == 40.0
    assert climate.max_temp == 104.0


async def test_climate_min_max_temp_celsius(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test min/max temperature in Celsius."""
    type(mock_coordinator.system_info).uses_metric = property(lambda self: True)

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    assert climate.min_temp == 5.0
    assert climate.max_temp == 40.0


async def test_climate_is_updated(
    hass: HomeAssistant,
    pool_object_body_with_ultratemp: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test isUpdated method for relevant attributes."""
    mock_coordinator.controller.system_info = MagicMock()
    type(mock_coordinator.controller.system_info).uses_metric = property(
        lambda self: False
    )

    climate = PoolClimate(
        mock_coordinator,
        pool_object_body_with_ultratemp,
        ["HTR01"],
    )

    # Should update on status change
    assert climate.isUpdated({"POOL1": {STATUS_ATTR: "ON"}}) is True

    # Should update on heater change
    assert climate.isUpdated({"POOL1": {HEATER_ATTR: "HTR01"}}) is True

    # Should update on htmode change
    assert climate.isUpdated({"POOL1": {HTMODE_ATTR: "1"}}) is True

    # Should update on heating setpoint change
    assert climate.isUpdated({"POOL1": {LOTMP_ATTR: "75"}}) is True

    # Should update on cooling setpoint change
    assert climate.isUpdated({"POOL1": {HITMP_ATTR: "88"}}) is True

    # Should update on current temperature change
    assert climate.isUpdated({"POOL1": {LSTTMP_ATTR: "80"}}) is True

    # Should not update on unrelated object
    assert climate.isUpdated({"OTHER": {STATUS_ATTR: "ON"}}) is False

    # Should not update on unrelated attribute
    assert climate.isUpdated({"POOL1": {"UNRELATED": "value"}}) is False
