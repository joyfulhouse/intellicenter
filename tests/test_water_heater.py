"""Test the Pentair IntelliCenter water heater platform."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MODE_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    HeaterType,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
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


def _mixed_model_getitem(standard: PoolObject, hcombo: PoolObject) -> MagicMock:
    """Return a model __getitem__ that maps each objnam to its distinct object."""
    lookup = {standard.objnam: standard, hcombo.objnam: hcombo}
    return MagicMock(side_effect=lambda oid: lookup.get(oid))


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
    pool_object_heater: PoolObject,
    pool_object_heater2: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning on the water heater defaults to the first standard heater."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        side_effect=lambda oid: {
            "HTR01": pool_object_heater,
            "HTR02": pool_object_heater2,
        }.get(oid)
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

    # No remembered operation -> default is the first standard heater (Gas Heater).
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )


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

    # Simulate update that tracks the last operation (Solar Heater)
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

    # Restores the remembered Solar Heater operation.
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR02"}
    )


async def test_water_heater_turn_off(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turning off the water heater clears both control planes."""
    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_turn_off()

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)},
    )


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
    """Test setting operation mode to a standard heater assigns HEATER only."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_set_operation_mode("Gas Heater")

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )


async def test_water_heater_set_operation_mode_off(
    hass: HomeAssistant,
    pool_object_body_with_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting operation mode to off clears both control planes."""
    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )
    water_heater.hass = hass  # Required for async_create_task

    await water_heater.async_set_operation_mode(STATE_OFF)

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)},
    )


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
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test isUpdated method for relevant attributes."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

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
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test extra state attributes expose the last operation label."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=pool_object_heater)

    water_heater = PoolWaterHeater(
        mock_coordinator,
        pool_object_body_with_heater,
        ["HTR01"],
    )

    attrs = water_heater.extra_state_attributes

    assert "OBJNAM" in attrs
    assert attrs["OBJNAM"] == "POOL1"
    # The unified model remembers the last non-off operation label, not a heater id.
    assert attrs["LAST_OPERATION"] == "Gas Heater"
    assert "LAST_HEATER" not in attrs


# -------------------------------------------------------------------------------------
# HCOMBO (multi-mode heater) tests
# -------------------------------------------------------------------------------------


async def test_water_heater_hcombo_turn_on_uses_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that HCOMBO turn-on writes the body MODE (and clears HEATER) atomically.

    Pentair UltraTemp ETi Hybrid (and other HCOMBO heaters) require the body's
    MODE attribute to be set rather than the HEATER attribute. With no remembered
    operation the economical default (Heat Pump Only) is selected.
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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

    # HCOMBO heaters are controlled via an atomic body write that sets MODE and
    # clears the standard-heater plane. Default is Heat Pump Only (not Dual).
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_ULTRA_TEMP.value), HEATER_ATTR: NULL_OBJNAM},
    )


async def test_water_heater_hcombo_turn_off_uses_mode_attr(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that HCOMBO turn-off clears MODE and HEATER atomically."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)},
    )


async def test_water_heater_hcombo_current_operation_from_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO current_operation reflects MODE_ATTR when HEATER_ATTR is null."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    they're active. Because the assigned heater is an HCOMBO heater (not a
    standard one), the standard-heater precedence does not apply and the HCOMBO
    MODE drives current_operation: it must reflect the selected sub-mode rather
    than the heater's sname ("Hybrid").
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    """Test HCOMBO set_operation_mode writes MODE and clears HEATER for non-off."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_GAS.value), HEATER_ATTR: NULL_OBJNAM},
    )


async def test_water_heater_hcombo_is_heater_active_from_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO _is_heater_active uses MODE_ATTR when HEATER_ATTR is null."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    """Test each HCOMBO label maps to the correct atomic MODE write."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
        mock_coordinator.controller.request_changes.assert_called_once_with(
            "POOL1",
            {MODE_ATTR: str(heater_type.value), HEATER_ATTR: NULL_OBJNAM},
        )


async def test_water_heater_hcombo_current_operation_each_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test current_operation returns correct label for each HCOMBO MODE value."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
        assert water_heater.current_operation == expected_label, (
            f"Wrong label for MODE={mode_val}"
        )


async def test_water_heater_hcombo_turn_on_restores_last_mode(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turn_on uses the last active HCOMBO mode instead of the default."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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

    # Simulate update that records Gas Only as the last operation
    updates = {"POOL1": {MODE_ATTR: "7"}}
    water_heater.isUpdated(updates)

    # Turn off
    body.update({MODE_ATTR: "1"})

    # Turn back on — should restore Gas Only, not the Heat Pump Only default
    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_GAS.value), HEATER_ATTR: NULL_OBJNAM},
    )


# -------------------------------------------------------------------------------------
# LAST_OPERATION restore tests
# -------------------------------------------------------------------------------------


async def test_water_heater_restore_invalid_operation_ignored(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test restoring a LAST_OPERATION label that is no longer valid is ignored.

    If the saved label is not in the current operation_list (or is STATE_OFF),
    async_turn_on must not use it and instead falls back to the safe default.
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",  # OFF -> _last_operation starts None
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    # Simulate restoring a label that is not a valid operation for this body.
    mock_last_state = MagicMock()
    mock_last_state.attributes = {"LAST_OPERATION": "No Longer Wired Heater"}

    with patch.object(
        water_heater, "async_get_last_state", AsyncMock(return_value=mock_last_state)
    ):
        await water_heater.async_added_to_hass()

    # The invalid label must not be adopted.
    assert water_heater._last_operation is None

    # turn_on falls back to the economical default (Heat Pump Only), not MODE=OFF.
    water_heater.hass = hass
    await water_heater.async_turn_on()
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_ULTRA_TEMP.value), HEATER_ATTR: NULL_OBJNAM},
    )


async def test_water_heater_restore_valid_operation(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test a valid saved LAST_OPERATION label is restored and used by turn_on."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Spa",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "1",  # OFF -> _last_operation starts None
            "LOTMP": "98",
            "LSTTMP": "98",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO"])

    mock_last_state = MagicMock()
    mock_last_state.attributes = {"LAST_OPERATION": "Gas Only"}

    with patch.object(
        water_heater, "async_get_last_state", AsyncMock(return_value=mock_last_state)
    ):
        await water_heater.async_added_to_hass()

    assert water_heater._last_operation == "Gas Only"

    # turn_on restores the saved Gas Only operation, not the default.
    water_heater.hass = hass
    await water_heater.async_turn_on()
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_GAS.value), HEATER_ATTR: NULL_OBJNAM},
    )


# -------------------------------------------------------------------------------------
# Backward-compatibility tests — standard (non-HCOMBO) heaters must be unaffected
# -------------------------------------------------------------------------------------


async def test_water_heater_standard_heater_unaffected(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Verify standard heaters behave correctly after the HCOMBO redesign.

    This is a regression guard: none of the HCOMBO code paths should activate
    for heaters whose subtype is not HCOMBO, and selecting/turning on a standard
    heater must write HEATER only (no MODE key).
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

    # selecting a standard heater sends HEATER_ATTR only, with NO MODE key
    await water_heater.async_set_operation_mode("Gas Heater")
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )

    # turn_on sends HEATER_ATTR, not MODE_ATTR
    mock_coordinator.controller.request_changes.reset_mock()
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

    # turn_off clears both planes atomically (HEATER=NULL + MODE=OFF). Writing
    # MODE=OFF is harmless for a pure-standard body and keeps the off-path uniform.
    mock_coordinator.controller.request_changes.reset_mock()
    wh_on = PoolWaterHeater(mock_coordinator, body, ["HTR01"])
    wh_on.hass = hass
    await wh_on.async_turn_off()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[1][HEATER_ATTR] == NULL_OBJNAM
    assert args[1][MODE_ATTR] == str(HeaterType.OFF.value)


async def test_water_heater_hcombo_last_operation_in_attributes(
    hass: HomeAssistant,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test HCOMBO entities expose LAST_OPERATION (and no legacy heater attrs)."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(
        return_value=pool_object_hcombo_heater
    )

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
    assert attrs["LAST_OPERATION"] == "Dual"
    assert "LAST_HEATER" not in attrs
    assert "LAST_HCOMBO_MODE" not in attrs


# -------------------------------------------------------------------------------------
# Mixed standard + HCOMBO heater tests
# -------------------------------------------------------------------------------------


async def test_water_heater_mixed_heaters_operation_list(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test a mixed body exposes both standard and HCOMBO modes in operation_list."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
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
    """Test selecting a standard heater on a mixed body assigns HEATER only.

    current_operation must then show the standard heater's sname even though the
    body MODE still holds a stale HCOMBO value.
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "MODE": "7",  # stale HCOMBO "Gas Only" value present
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass

    await water_heater.async_set_operation_mode("Gas Heater")

    # Standard heater selection writes HEATER only (panel derives MODE).
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )

    # Apply the change; current_operation prefers the assigned standard heater
    # over the still-stale HCOMBO MODE=7.
    body.update({HEATER_ATTR: "HTR01"})
    assert water_heater.current_operation == "Gas Heater"


async def test_water_heater_mixed_set_hcombo_mode(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test selecting an HCOMBO mode on a mixed body sets MODE and clears HEATER."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",  # standard heater currently assigned
            "HTMODE": "1",
            "MODE": "1",
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass

    await water_heater.async_set_operation_mode("Hybrid")

    # MODE is set to the HCOMBO value and the stale standard heater is cleared.
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_HYBRID.value), HEATER_ATTR: NULL_OBJNAM},
    )

    # Apply the change; current_operation now reflects the HCOMBO mode.
    body.update({HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: "9"})
    assert water_heater.current_operation == "Hybrid"


async def test_water_heater_mixed_heaters_turn_off_clears_both(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that turn_off on a mixed body clears both HEATER_ATTR and MODE_ATTR."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
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

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)},
    )


async def test_water_heater_mixed_heaters_current_operation_standard_heater(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test current_operation reflects standard heater when HEATER set and MODE off."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
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


async def test_water_heater_mixed_current_operation_standard_wins_over_stale_mode(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test an assigned standard heater wins even when MODE holds a stale HCOMBO value.

    After switching from an HCOMBO mode to a standard heater on a mixed body, the
    body MODE may still hold the old HCOMBO value momentarily. current_operation
    must report the standard heater (its plane was selected last).
    """
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",  # standard heater assigned
            "HTMODE": "1",
            "MODE": "7",  # stale HCOMBO "Gas Only" value still present
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])

    assert water_heater.current_operation == "Gas Heater"


async def test_water_heater_mixed_turn_on_restores_standard_heater(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turn_on on a mixed body restores a last standard-heater operation."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",  # standard heater was last selected
            "HTMODE": "1",
            "MODE": "1",
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass
    assert water_heater._last_operation == "Gas Heater"

    # Body turned off, then turned back on.
    body.update({HEATER_ATTR: NULL_OBJNAM})
    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )


async def test_water_heater_mixed_turn_on_restores_hcombo_mode(
    hass: HomeAssistant,
    pool_object_heater: PoolObject,
    pool_object_hcombo_heater: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test turn_on on a mixed body restores a last HCOMBO-mode operation."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = _mixed_model_getitem(
        pool_object_heater, pool_object_hcombo_heater
    )

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "1",
            "MODE": "10",  # HCOMBO "Dual" was last selected
            "LOTMP": "80",
            "LSTTMP": "75",
        },
    )

    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR_COMBO", "HTR01"])
    water_heater.hass = hass
    assert water_heater._last_operation == "Dual"

    # Body turned off, then turned back on.
    body.update({MODE_ATTR: "1"})
    await water_heater.async_turn_on()

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1",
        {MODE_ATTR: str(HeaterType.HYBRID_DUAL.value), HEATER_ATTR: NULL_OBJNAM},
    )


async def test_water_heater_standard_heater_named_like_hcombo_not_misrouted(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A standard heater whose name matches an HCOMBO label is not misrouted.

    On a non-multimode body, selecting a standard heater named e.g. "Gas Only"
    must assign HEATER (not write the HCOMBO MODE plane), and the dropdown must
    list it exactly once.
    """
    standard = PoolObject(
        "HTR01",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "GAS",
            "SNAME": "Gas Only",
            "BODY": "POOL1",
            "LISTORD": "1",
        },
    )
    # Swap in a MagicMock model first: __getitem__ is a dunder resolved on the
    # type, so setting it on the real PoolModel instance from the fixture would be
    # silently ignored and lookups would return the fixture's heater instead.
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.__getitem__ = MagicMock(return_value=standard)

    body = PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": NULL_OBJNAM,
            "HTMODE": "0",
            "LOTMP": "80",
            "LSTTMP": "78",
        },
    )
    water_heater = PoolWaterHeater(mock_coordinator, body, ["HTR01"])
    water_heater.hass = hass

    assert water_heater._is_multimode is False
    assert water_heater.operation_list.count("Gas Only") == 1

    await water_heater.async_set_operation_mode("Gas Only")
    mock_coordinator.controller.request_changes.assert_called_once_with(
        "POOL1", {HEATER_ATTR: "HTR01"}
    )


# -------------------------------------------------------------------------------------
# issue #57: a heater added to an EXISTING body must surface on the existing entity
# -------------------------------------------------------------------------------------


async def test_water_heater_second_heater_added_to_existing_body(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A second heater added to an existing body shows on the existing entity.

    Regression test for issue #57 (Fix A). A body that already has a water
    heater entity gains a SECOND heater at runtime. The heater list is derived
    live from the model, so the existing entity's ``operation_list`` must gain
    the new heater on the next coordinator update WITHOUT a fresh entity being
    created (the platform de-dups the rebuilt entity by ``unique_id``).
    """
    # A real model so the live heater derivation (get_by_type) actually runs.
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "POOL1",
                "params": {
                    "OBJTYP": BODY_TYPE,
                    "SUBTYP": "POOL",
                    "SNAME": "Pool",
                    "STATUS": "ON",
                    "LSTTMP": "78",
                    "LOTMP": "72",
                    "HEATER": "HTR01",
                    "HTMODE": "1",
                },
            },
            {
                "objnam": "HTR01",
                "params": {
                    "OBJTYP": HEATER_TYPE,
                    "SUBTYP": "GAS",
                    "SNAME": "Gas Heater",
                    "BODY": "POOL1",
                    "LISTORD": "1",
                },
            },
        ]
    )
    mock_coordinator.model = model

    # Build the platform's entities for the objects present at setup, capturing
    # the dynamic new-objects listener and de-duplicating by unique_id exactly
    # like the production helper does.
    from custom_components.intellicenter.water_heater import async_setup_entry

    listener_holder: dict[str, Any] = {"listener": None}

    def _register(listener: Any) -> Any:
        listener_holder["listener"] = listener
        return MagicMock()

    mock_coordinator.async_add_new_objects_listener = MagicMock(side_effect=_register)

    entry = MagicMock()
    entry.runtime_data = mock_coordinator
    entry.async_on_unload = MagicMock()

    added: list[PoolWaterHeater] = []
    await async_setup_entry(hass, entry, added.extend)

    # Exactly one water heater for POOL1 was created, and it lists only the gas
    # heater so far.
    pool_heaters = [e for e in added if e._pool_object.objnam == "POOL1"]
    assert len(pool_heaters) == 1
    existing = pool_heaters[0]
    assert "Gas Heater" in existing.operation_list
    assert "Solar Heater" not in existing.operation_list

    # A second heater for the SAME body comes online in a later update.
    new_heater = model.add_object(
        "HTR02",
        {
            "OBJTYP": HEATER_TYPE,
            "SUBTYP": "SOLAR",
            "SNAME": "Solar Heater",
            "BODY": "POOL1",
            "LISTORD": "2",
        },
    )
    assert new_heater is not None

    # The platform re-evaluates the body; the rebuilt entity is de-duped away.
    added.clear()
    assert listener_holder["listener"] is not None
    listener_holder["listener"]([new_heater])

    # No duplicate water heater entity was added for the already-known body.
    assert [e for e in added if e._pool_object.objnam == "POOL1"] == []

    # The EXISTING entity now exposes the new heater because its heater list is
    # derived from the live model.
    assert "Gas Heater" in existing.operation_list
    assert "Solar Heater" in existing.operation_list
