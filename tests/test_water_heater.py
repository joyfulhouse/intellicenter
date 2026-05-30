"""Test the Pentair IntelliCenter water heater platform."""

from unittest.mock import MagicMock

from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_OFF,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    HeaterType,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MODE_ATTR,
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


@pytest.fixture
def pool_object_hcombo_heater() -> PoolObject:
    """Return a PoolObject representing a multi-mode (HCOMBO) heater."""
    return PoolObject(
        "HTR_COMBO",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "HCOMBO",
            "SNAME": "Hybrid",
            "BODY": "POOL1 SPA01",
            "LISTORD": "1",
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
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

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
    assert water_heater.current_operation == "Gas Heater"  # STATUS=ON, HEATER=HTR01
    assert (
        water_heater.extra_state_attributes["heating_status"] == "heating"
    )  # HTMODE=1
    assert water_heater.temperature_unit == str(UnitOfTemperature.FAHRENHEIT)


async def test_water_heater_state_heating(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when actively heating."""
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

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

    assert water_heater.current_operation == "Gas Heater"
    assert water_heater.extra_state_attributes["heating_status"] == "heating"


async def test_water_heater_state_idle(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when idle (at temperature)."""
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

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

    assert water_heater.current_operation == "Gas Heater"
    assert water_heater.extra_state_attributes["heating_status"] == "idle"


async def test_water_heater_state_body_off_heater_configured(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater shows configured heater even when body is off.

    This is the core of issue #34 bug 1: when the system is in Pool mode,
    the Spa body STATUS is OFF, but the user can still configure a heater
    for the Spa. The operation mode should reflect the configured heater.
    """
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",  # Body off (e.g., Spa while in Pool mode)
            "HEATER": "HTR01",  # But heater is configured
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    # Operation should show the configured heater, not "off"
    assert water_heater.current_operation == "Gas Heater"
    # But heating_status should not be present since body isn't running
    assert "heating_status" not in water_heater.extra_state_attributes


async def test_water_heater_state_off_no_heater_configured(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when body is off and no heater configured."""
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "OFF",
            "HEATER": NULL_OBJNAM,  # No heater configured
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])

    assert water_heater.current_operation == STATE_OFF
    assert "heating_status" not in water_heater.extra_state_attributes


async def test_water_heater_state_no_heater(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test water heater state when no heater assigned."""
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

    assert water_heater.current_operation == STATE_OFF
    assert "heating_status" not in water_heater.extra_state_attributes


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
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

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
    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    features = water_heater.supported_features

    assert features & WaterHeaterEntityFeature.TARGET_TEMPERATURE
    assert features & WaterHeaterEntityFeature.OPERATION_MODE
    assert features & WaterHeaterEntityFeature.ON_OFF


async def test_water_heater_min_max_temp_fahrenheit(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test min/max temperature in Fahrenheit."""
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


# -------------------------------------------------------------------------------------
# HCOMBO (multi-mode heater) tests
# -------------------------------------------------------------------------------------


async def test_water_heater_hcombo_turn_on_uses_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that HCOMBO heaters use MODE_ATTR instead of HEATER_ATTR for turn on.

    Pentair UltraTemp ETi Hybrid (and other HCOMBO heaters) require the body's
    MODE attribute to be set rather than the HEATER attribute.
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",  # OFF
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
    water_heater.hass = hass

    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert MODE_ATTR in args[1]
    assert args[1][MODE_ATTR] == str(HeaterType.HYBRID_DUAL.value)
    assert HEATER_ATTR not in args[1]


async def test_water_heater_hcombo_turn_off_uses_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that HCOMBO heaters use MODE_ATTR for turn off."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "1",
            "MODE": "10",  # HYBRID_DUAL (on)
            "LOTMP": "98",
            "LSTTMP": "95",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
    water_heater.hass = hass

    await water_heater.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "POOL1"
    assert MODE_ATTR in args[1]
    assert args[1][MODE_ATTR] == str(HeaterType.OFF.value)
    assert args[1][HEATER_ATTR] == NULL_OBJNAM


async def test_water_heater_hcombo_current_operation_from_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO current_operation reflects MODE_ATTR when HEATER_ATTR is null."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "1",
            "MODE": "10",  # HYBRID_DUAL active
            "LOTMP": "98",
            "LSTTMP": "95",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    assert water_heater.current_operation == "Dual"


async def test_water_heater_hcombo_current_operation_ignores_heater_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO current_operation uses MODE even when HEATER_ATTR is set.

    IntelliCenter sets HEATER=<objnam> on the body even for HCOMBO heaters when
    they're active. Without this fix current_operation would return the heater's
    sname ("Hybrid") regardless of which sub-mode is selected.
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": "HTR_COMBO",  # IntelliCenter sets this even for HCOMBO
            "HTMODE": "1",
            "MODE": "7",  # Gas Only
            "LOTMP": "98",
            "LSTTMP": "95",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    assert water_heater.current_operation == "Gas Only"


async def test_water_heater_hcombo_current_operation_off_when_mode_off(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO current_operation is off when MODE_ATTR is 1 (OFF)."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",  # OFF
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    assert water_heater.current_operation == STATE_OFF


async def test_water_heater_hcombo_set_operation_mode_uses_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO set_operation_mode uses MODE_ATTR for non-off modes."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
    water_heater.hass = hass

    await water_heater.async_set_operation_mode("Gas Only")

    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert MODE_ATTR in args[1]
    assert args[1][MODE_ATTR] == str(HeaterType.HYBRID_GAS.value)


async def test_water_heater_hcombo_is_heater_active_from_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO _is_heater_active uses MODE_ATTR when HEATER_ATTR is null."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "1",
            "MODE": "10",
            "LOTMP": "98",
            "LSTTMP": "95",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    assert water_heater._is_heater_active is True
    attrs = water_heater.extra_state_attributes
    assert "heating_status" in attrs


async def test_water_heater_non_hcombo_turn_on_unchanged(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that standard (non-HCOMBO) heaters still use HEATER_ATTR for turn on."""
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])
    water_heater.hass = hass

    await water_heater.async_turn_on()

    args = mock_coordinator.controller.request_changes.call_args[0]
    assert HEATER_ATTR in args[1]
    assert MODE_ATTR not in args[1]


async def test_water_heater_isUpdated_watches_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test isUpdated triggers on MODE_ATTR changes for HCOMBO heaters."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    assert water_heater.isUpdated({"POOL1": {MODE_ATTR: "10"}}) is True
    assert water_heater.isUpdated({"POOL1": {"UNRELATED": "x"}}) is False


async def test_water_heater_hcombo_operation_list_has_all_modes(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO operation list contains all four sub-modes."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    ops = water_heater.operation_list
    assert STATE_OFF in ops
    assert "Gas Only" in ops
    assert "Heat Pump Only" in ops
    assert "Hybrid" in ops
    assert "Dual" in ops
    assert len(ops) == 5


async def test_water_heater_hcombo_set_each_operation_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test each HCOMBO label maps to the correct HeaterType MODE value."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    expected = {
        "Gas Only": HeaterType.HYBRID_GAS,
        "Heat Pump Only": HeaterType.HYBRID_ULTRA_TEMP,
        "Hybrid": HeaterType.HYBRID_HYBRID,
        "Dual": HeaterType.HYBRID_DUAL,
    }

    for label, heater_type in expected.items():
        mock_coordinator.controller.request_changes.reset_mock()
        water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
        water_heater.hass = hass
        await water_heater.async_set_operation_mode(label)
        args = mock_coordinator.controller.request_changes.call_args[0]
        assert args[1][MODE_ATTR] == str(heater_type.value), f"Wrong MODE for {label}"


async def test_water_heater_hcombo_current_operation_each_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test current_operation returns correct label for each HCOMBO MODE value."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    mode_to_label = {
        "7": "Gas Only",
        "8": "Heat Pump Only",
        "9": "Hybrid",
        "10": "Dual",
    }

    for mode_val, expected_label in mode_to_label.items():
        body = PoolObject(
            "POOL1",
            {
                "OBJTYP": BODY_TYPE,
                "SNAME": "Spa",
                "STATUS": "ON",
                "HEATER": NULL_OBJNAM,
                "HTMODE": "1",
                "MODE": mode_val,
                "LOTMP": "98",
                "LSTTMP": "95",
            },
        )
        water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
        assert water_heater.current_operation == expected_label, f"Wrong label for MODE={mode_val}"


async def test_water_heater_hcombo_turn_on_restores_last_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turn_on uses the last active HCOMBO mode instead of defaulting to Dual."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "1",
            "MODE": "7",  # Gas Only was active
            "LOTMP": "98",
            "LSTTMP": "95",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])
    water_heater.hass = hass

    # Simulate update that records Gas Only as last mode
    updates = {"POOL1": {MODE_ATTR: "7"}}
    water_heater.isUpdated(updates)

    # Turn off
    body.update({MODE_ATTR: "1"})

    # Turn back on — should restore Gas Only, not Dual
    await water_heater.async_turn_on()

    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][MODE_ATTR] == str(HeaterType.HYBRID_GAS.value)


# -------------------------------------------------------------------------------------
# Backward-compatibility tests — standard (non-HCOMBO) heaters must be unaffected
# -------------------------------------------------------------------------------------


async def test_water_heater_standard_heater_unaffected(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Verify standard (gas/solar/heat-pump) heaters behave identically after HCOMBO changes.

    This is a regression guard: none of the HCOMBO code paths should activate
    for heaters whose subtype is not HCOMBO.
    """
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])
    water_heater.hass = hass

    # _is_multimode must be False for standard heaters
    assert water_heater._is_multimode is False

    # operation_list uses heater snames, not HCOMBO mode labels
    ops = water_heater.operation_list
    assert "Gas Heater" in ops
    assert "Gas Only" not in ops
    assert "Heat Pump Only" not in ops
    assert "Dual" not in ops

    # current_operation reflects HEATER_ATTR, not MODE_ATTR
    assert water_heater.current_operation == "Gas Heater"

    # turn_on sends HEATER_ATTR, not MODE_ATTR
    body_off = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "LOTMP": "72",
            "LSTTMP": "68",
        },
    )
    wh_off = PoolWaterHeater(mock_coordinator, body_off, ["HTR01"])
    wh_off.hass = hass
    await wh_off.async_turn_on()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert HEATER_ATTR in args[1]
    assert MODE_ATTR not in args[1]

    # turn_off sends HEATER_ATTR=NULL, not MODE_ATTR
    mock_coordinator.controller.request_changes.reset_mock()
    wh_on = PoolWaterHeater(mock_coordinator, body, ["HTR01"])
    wh_on.hass = hass
    await wh_on.async_turn_off()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == NULL_OBJNAM
    assert MODE_ATTR not in args[1]


async def test_water_heater_hcombo_last_heater_not_in_attributes(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test LAST_HEATER is not exposed in state attributes for HCOMBO entities."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": "HTR_COMBO",
            "HTMODE": "0",
            "MODE": "10",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    attrs = water_heater.extra_state_attributes
    assert "LAST_HEATER" not in attrs
    assert "LAST_HCOMBO_MODE" in attrs


async def test_water_heater_hcombo_restore_invalid_mode_ignored(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that restoring an invalid/non-HCOMBO HeaterType value is ignored.

    If LAST_HCOMBO_MODE is stored as HeaterType.OFF (1) or any value not in
    _HCOMBO_MODE_LABELS, async_turn_on must not use it (would send MODE=1, turning off).
    """
    from unittest.mock import AsyncMock, patch

    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_hcombo_heater)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    # Simulate restoring HeaterType.OFF (1) — an invalid HCOMBO mode
    mock_last_state = MagicMock()
    mock_last_state.attributes = {"LAST_HCOMBO_MODE": "1"}

    with patch.object(water_heater, "async_get_last_state", AsyncMock(return_value=mock_last_state)):
        await water_heater.async_added_to_hass()

    # _last_hcombo_mode must remain None — OFF is not a valid HCOMBO mode to restore
    assert water_heater._last_hcombo_mode is None

    # turn_on should fall back to HYBRID_DUAL, not send MODE=1
    water_heater.hass = hass
    await water_heater.async_turn_on()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][MODE_ATTR] == str(HeaterType.HYBRID_DUAL.value)


# -------------------------------------------------------------------------------------
# Mixed standard + HCOMBO heater tests
# -------------------------------------------------------------------------------------


async def test_water_heater_mixed_heaters_operation_list(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that a body with both standard and HCOMBO heaters exposes both in operation_list."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_hcombo_heater if x == "HTR_COMBO" else pool_object_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])

    assert water_heater._is_multimode is True
    ops = water_heater.operation_list
    assert STATE_OFF in ops
    assert "Gas Only" in ops
    assert "Heat Pump Only" in ops
    assert "Hybrid" in ops
    assert "Dual" in ops
    assert "Gas Heater" in ops  # Standard heater still accessible


async def test_water_heater_mixed_heaters_set_standard_heater(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that selecting a standard heater mode on a mixed body sends HEATER_ATTR."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_hcombo_heater if x == "HTR_COMBO" else pool_object_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass

    await water_heater.async_set_operation_mode("Gas Heater")

    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == "HTR01"
    assert MODE_ATTR not in args[1]


async def test_water_heater_mixed_heaters_turn_off_clears_both(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that turn_off on a mixed body clears both HEATER_ATTR and MODE_ATTR."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_hcombo_heater if x == "HTR_COMBO" else pool_object_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "MODE": "1",
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass

    await water_heater.async_turn_off()

    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == NULL_OBJNAM
    assert args[1][MODE_ATTR] == str(HeaterType.OFF.value)


async def test_water_heater_mixed_heaters_current_operation_standard_heater(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test current_operation reflects standard heater when HEATER is set and MODE is off."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda x: pool_object_hcombo_heater if x == "HTR_COMBO" else pool_object_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "MODE": "1",  # HCOMBO off
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])

    assert water_heater.current_operation == "Gas Heater"
