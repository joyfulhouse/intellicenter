"""Test the Pentair IntelliCenter number platform."""

from unittest.mock import MagicMock

from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    GPM_ATTR,
    PMPCIRC_TYPE,
    PRIM_ATTR,
    PUMP_TYPE,
    SEC_ATTR,
    SELECT_ATTR,
    SPEED_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
from custom_components.intellicenter.number import PoolNumber, PumpSpeedNumber

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_model_with_intellichlor() -> PoolModel:
    """Return a PoolModel with IntelliChlor."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "POOL1",
                "params": {
                    "OBJTYP": BODY_TYPE,
                    "SUBTYP": "POOL",
                    "SNAME": "Pool",
                },
            },
            {
                "objnam": "SPA01",
                "params": {
                    "OBJTYP": BODY_TYPE,
                    "SUBTYP": "SPA",
                    "SNAME": "Spa",
                },
            },
            {
                "objnam": "ICHLOR1",
                "params": {
                    "OBJTYP": CHEM_TYPE,
                    "SUBTYP": "ICHLOR",
                    "SNAME": "IntelliChlor",
                    "BODY": "POOL1 SPA01",
                    "PRIM": "50",
                    "SEC": "30",
                },
            },
        ]
    )
    return model


@pytest.fixture
def pool_object_intellichlor() -> PoolObject:
    """Return a PoolObject representing an IntelliChlor."""
    return PoolObject(
        "ICHLOR1",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHLOR",
            "SNAME": "IntelliChlor",
            "BODY": "POOL1 SPA01",
            "PRIM": "50",
            "SEC": "30",
        },
    )


async def test_number_setup_creates_entities(
    hass: HomeAssistant,
    pool_model_with_intellichlor: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test number platform creates entities for IntelliChlor."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model_with_intellichlor

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create 2 number entities (one for each body)
    assert len(entities_added) == 2


async def test_number_entity_properties_primary(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolNumber entity properties for primary output."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        unit_of_measurement=PERCENTAGE,
        attribute_key=PRIM_ATTR,
        name="+ Output % (Pool)",
    )

    assert number.native_value == 50.0
    assert number._attr_native_unit_of_measurement == PERCENTAGE
    assert number._attr_icon == "mdi:gauge"


async def test_number_entity_properties_secondary(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolNumber entity properties for secondary output."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        unit_of_measurement=PERCENTAGE,
        attribute_key=SEC_ATTR,
        name="+ Output % (Spa)",
    )

    assert number.native_value == 30.0


async def test_number_min_max_step(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test number min/max/step values."""

    # Use default values
    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )

    # Check default values
    assert number._attr_native_min_value == 0
    assert number._attr_native_max_value == 100
    assert number._attr_native_step == 1


async def test_number_custom_min_max_step(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test number with custom min/max/step values."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        min_value=10,
        max_value=90,
        step=5,
        attribute_key=PRIM_ATTR,
    )

    assert number._attr_native_min_value == 10
    assert number._attr_native_max_value == 90
    assert number._attr_native_step == 5


async def test_number_set_value(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting number value uses convenience method."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )
    number.hass = hass  # Required for async_create_task

    await number.async_set_native_value(75)

    # Primary chlorinator output uses set_chlorinator_output convenience method
    mock_coordinator.controller.set_chlorinator_output.assert_called_once_with(
        "ICHLOR1", 75
    )


async def test_number_set_value_secondary(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting secondary number value uses convenience method."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=SEC_ATTR,
    )
    number.hass = hass  # Required for async_create_task

    await number.async_set_native_value(40)

    # Secondary uses set_chlorinator_output with current primary preserved
    mock_coordinator.controller.set_chlorinator_output.assert_called_once_with(
        "ICHLOR1",
        50,
        40,  # 50 is the mocked current primary value
    )


async def test_number_set_value_converts_to_int(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting number value converts float to int."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )
    number.hass = hass  # Required for async_create_task

    await number.async_set_native_value(75.5)

    # Should convert 75.5 to 75 (integer)
    mock_coordinator.controller.set_chlorinator_output.assert_called_once_with(
        "ICHLOR1", 75
    )


async def test_number_unique_id(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test number unique ID generation."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )

    # Unique ID should include attribute key since it's not STATUS_ATTR
    assert number.unique_id == "test_entry_ICHLOR1PRIM"


async def test_number_native_value_none(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test number native_value when attribute is None."""

    obj = PoolObject(
        "ICHLOR1",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHLOR",
            "SNAME": "IntelliChlor",
            "PRIM": None,  # No value
        },
    )

    number = PoolNumber(
        mock_coordinator,
        obj,
        attribute_key=PRIM_ATTR,
    )

    assert number.native_value is None


async def test_number_native_value_invalid(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test number native_value when attribute is invalid."""

    obj = PoolObject(
        "ICHLOR1",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHLOR",
            "SNAME": "IntelliChlor",
            "PRIM": "invalid",  # Invalid value
        },
    )

    number = PoolNumber(
        mock_coordinator,
        obj,
        attribute_key=PRIM_ATTR,
    )

    assert number.native_value is None


async def test_number_is_updated(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test number isUpdated method."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )

    # Should update on PRIM change
    assert number.isUpdated({"ICHLOR1": {PRIM_ATTR: "60"}}) is True

    # Should not update on SEC change
    assert number.isUpdated({"ICHLOR1": {SEC_ATTR: "40"}}) is False

    # Should not update on other object
    assert number.isUpdated({"OTHER": {PRIM_ATTR: "60"}}) is False


async def test_number_state_updates(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test number state updates from IntelliCenter."""

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=PRIM_ATTR,
    )

    # Initial value
    assert number.native_value == 50.0

    # Simulate update from IntelliCenter
    updates = {"ICHLOR1": {PRIM_ATTR: "75"}}
    assert number.isUpdated(updates) is True

    # Apply the update
    pool_object_intellichlor.update(updates["ICHLOR1"])

    # Verify value changed
    assert number.native_value == 75.0


async def test_number_no_bodies_configured(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test number setup when no bodies are configured."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "ICHLOR1",
                "params": {
                    "OBJTYP": CHEM_TYPE,
                    "SUBTYP": "ICHLOR",
                    "SNAME": "IntelliChlor",
                    "BODY": None,  # No bodies configured
                    "PRIM": "50",
                },
            },
        ]
    )
    # Set up the mock coordinator's model
    mock_coordinator.model = model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create no entities when no bodies configured
    assert len(entities_added) == 0


# --- Pump Speed Control Tests ---


@pytest.fixture
def pool_model_with_pmpcirc() -> PoolModel:
    """Return a PoolModel with a variable speed/flow pump and circuit settings."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "POOL1",
                "params": {
                    "OBJTYP": BODY_TYPE,
                    "SUBTYP": "POOL",
                    "SNAME": "Pool",
                },
            },
            {
                "objnam": "CIRC01",
                "params": {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "GENERIC",
                    "SNAME": "Pool Circuit",
                },
            },
            {
                "objnam": "PUMP1",
                "params": {
                    "OBJTYP": PUMP_TYPE,
                    "SUBTYP": "VSF",
                    "SNAME": "Pool Pump",
                    "STATUS": "10",
                    "MIN": "450",
                    "MAX": "3450",
                    "MINF": "15",
                    "MAXF": "140",
                },
            },
            {
                "objnam": "PMPCIRC01",
                "params": {
                    "OBJTYP": PMPCIRC_TYPE,
                    "SNAME": "Pool Pump Circuit 1",
                    "PARENT": "PUMP1",
                    "CIRCUIT": "CIRC01",
                    "SELECT": "GPM",
                    "SPEED": "2400",
                    "GPM": "80",
                },
            },
        ]
    )
    return model


@pytest.fixture
def pool_object_pmpcirc() -> PoolObject:
    """Return a PoolObject representing a pump circuit setting."""
    return PoolObject(
        "PMPCIRC01",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "SNAME": "Pool Pump Circuit 1",
            "PARENT": "PUMP1",
            "CIRCUIT": "CIRC01",
            "SELECT": "GPM",
            "SPEED": "2400",
            "GPM": "80",
        },
    )


async def test_number_setup_creates_vsf_pump_entity(
    hass: HomeAssistant,
    pool_model_with_pmpcirc: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test number platform creates single PumpSpeedNumber for VSF pump."""
    mock_coordinator.model = pool_model_with_pmpcirc

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create 1 PumpSpeedNumber entity for VSF pump (unified speed control)
    pump_entities = [e for e in entities_added if isinstance(e, PumpSpeedNumber)]
    assert len(pump_entities) == 1
    assert "Speed" in pump_entities[0].name


async def test_number_pmpcirc_rpm_properties(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolNumber entity properties for pump RPM setpoint."""
    from custom_components.intellicenter.const import CONST_RPM

    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        min_value=450,
        max_value=3450,
        step=50,
        attribute_key=SPEED_ATTR,
        name="+ RPM (Pool Circuit)",
        unit_of_measurement=CONST_RPM,
        integer_only=True,
    )

    assert number.native_value == 2400
    assert number._attr_native_unit_of_measurement == CONST_RPM
    assert number._attr_native_min_value == 450
    assert number._attr_native_max_value == 3450
    assert number._attr_native_step == 50


async def test_number_pmpcirc_gpm_properties(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolNumber entity properties for pump GPM setpoint."""
    from custom_components.intellicenter.const import CONST_GPM

    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        min_value=15,
        max_value=140,
        step=5,
        attribute_key=GPM_ATTR,
        name="+ GPM (Pool Circuit)",
        unit_of_measurement=CONST_GPM,
        integer_only=True,
    )

    assert number.native_value == 80
    assert number._attr_native_unit_of_measurement == CONST_GPM
    assert number._attr_native_min_value == 15
    assert number._attr_native_max_value == 140
    assert number._attr_native_step == 5


async def test_number_pmpcirc_set_rpm(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting pump RPM value."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        attribute_key=SPEED_ATTR,
        integer_only=True,
    )
    number.hass = hass

    await number.async_set_native_value(2800)

    # Should use request_changes fallback with SPEED attribute
    mock_coordinator.controller.request_changes.assert_called_once()
    call_args = mock_coordinator.controller.request_changes.call_args
    assert call_args[0][0] == "PMPCIRC01"
    assert call_args[0][1] == {SPEED_ATTR: "2800"}


async def test_number_pmpcirc_set_gpm(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting pump GPM value."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        attribute_key=GPM_ATTR,
        integer_only=True,
    )
    number.hass = hass

    await number.async_set_native_value(60)

    # Should use request_changes fallback with GPM attribute
    mock_coordinator.controller.request_changes.assert_called_once()
    call_args = mock_coordinator.controller.request_changes.call_args
    assert call_args[0][0] == "PMPCIRC01"
    assert call_args[0][1] == {GPM_ATTR: "60"}


async def test_number_pmpcirc_is_updated(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test pump circuit number isUpdated method."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        attribute_key=GPM_ATTR,
    )

    # Should update on GPM change
    assert number.isUpdated({"PMPCIRC01": {GPM_ATTR: "100"}}) is True

    # Should not update on SPEED change
    assert number.isUpdated({"PMPCIRC01": {SPEED_ATTR: "3000"}}) is False

    # Should not update on other object
    assert number.isUpdated({"OTHER": {GPM_ATTR: "100"}}) is False


async def test_number_pmpcirc_state_updates(
    hass: HomeAssistant,
    pool_object_pmpcirc: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test pump circuit number state updates from IntelliCenter."""
    number = PoolNumber(
        mock_coordinator,
        pool_object_pmpcirc,
        attribute_key=GPM_ATTR,
        integer_only=True,
    )

    # Initial value
    assert number.native_value == 80

    # Simulate update from IntelliCenter
    updates = {"PMPCIRC01": {GPM_ATTR: "100"}}
    assert number.isUpdated(updates) is True

    # Apply the update
    pool_object_pmpcirc.update(updates["PMPCIRC01"])

    # Verify value changed
    assert number.native_value == 100


# --- PumpSpeedNumber Tests (VSF Pump Dynamic Entity) ---


@pytest.fixture
def pool_object_pmpcirc_vsf() -> PoolObject:
    """Return a PoolObject representing a VSF pump circuit setting."""
    return PoolObject(
        "PMPCIRC01",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "SNAME": "Pool Pump Circuit 1",
            "PARENT": "PUMP1",
            "CIRCUIT": "CIRC01",
            "SELECT": "GPM",
            "SPEED": "80",
        },
    )


@pytest.fixture
def pool_object_pmpcirc_rpm_mode() -> PoolObject:
    """Return a PoolObject representing a pump circuit in RPM mode."""
    return PoolObject(
        "PMPCIRC01",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "SNAME": "Pool Pump Circuit 1",
            "PARENT": "PUMP1",
            "CIRCUIT": "CIRC01",
            "SELECT": "RPM",
            "SPEED": "2400",
        },
    )


async def test_pump_speed_number_gpm_mode(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber in GPM mode returns correct unit and limits."""
    from custom_components.intellicenter.const import CONST_GPM

    # Mock the controller to return the expected speed value
    mock_coordinator.controller.get_pump_circuit_speed.return_value = 80

    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # In GPM mode
    assert number._current_mode == "GPM"
    assert number.native_unit_of_measurement == CONST_GPM
    assert number.native_min_value == 15.0
    assert number.native_max_value == 140.0
    assert number.native_step == 5.0
    assert number.native_value == 80


async def test_pump_speed_number_rpm_mode(
    hass: HomeAssistant,
    pool_object_pmpcirc_rpm_mode: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber in RPM mode returns correct unit and limits."""
    from custom_components.intellicenter.const import CONST_RPM

    # Mock the controller to return the expected speed value
    mock_coordinator.controller.get_pump_circuit_speed.return_value = 2400

    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_rpm_mode,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # In RPM mode
    assert number._current_mode == "RPM"
    assert number.native_unit_of_measurement == CONST_RPM
    assert number.native_min_value == 450.0
    assert number.native_max_value == 3450.0
    assert number.native_step == 50.0
    assert number.native_value == 2400


async def test_pump_speed_number_mode_switching(
    hass: HomeAssistant,
    pool_object_pmpcirc_rpm_mode: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber updates when mode switches from RPM to GPM."""
    from custom_components.intellicenter.const import CONST_GPM, CONST_RPM

    # Mock the controller to return initial RPM value, then updated GPM value
    mock_coordinator.controller.get_pump_circuit_speed.return_value = 2400

    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_rpm_mode,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Initially in RPM mode
    assert number.native_unit_of_measurement == CONST_RPM
    assert number.native_max_value == 3450.0

    # Simulate mode switch to GPM - controller now returns GPM value
    pool_object_pmpcirc_rpm_mode.update({SELECT_ATTR: "GPM", SPEED_ATTR: "80"})
    mock_coordinator.controller.get_pump_circuit_speed.return_value = 80

    # Now in GPM mode
    assert number._current_mode == "GPM"
    assert number.native_unit_of_measurement == CONST_GPM
    assert number.native_max_value == 140.0
    assert number.native_value == 80


async def test_pump_speed_number_is_updated_on_speed_change(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber isUpdated returns True for SPEED changes."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Should update on SPEED change
    assert number.isUpdated({"PMPCIRC01": {SPEED_ATTR: "100"}}) is True


async def test_pump_speed_number_is_updated_on_select_change(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber isUpdated returns True for SELECT changes."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Should update on SELECT change (mode switch)
    assert number.isUpdated({"PMPCIRC01": {SELECT_ATTR: "RPM"}}) is True


async def test_pump_speed_number_not_updated_on_other_object(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber isUpdated returns False for other objects."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Should not update on other object
    assert number.isUpdated({"OTHER": {SPEED_ATTR: "100"}}) is False


async def test_pump_speed_number_set_value(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test setting PumpSpeedNumber value writes to SPEED attribute."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )
    number.hass = hass

    await number.async_set_native_value(100)

    # Should use request_changes with SPEED attribute
    mock_coordinator.controller.request_changes.assert_called_once()
    call_args = mock_coordinator.controller.request_changes.call_args
    assert call_args[0][0] == "PMPCIRC01"
    assert call_args[0][1] == {SPEED_ATTR: "100"}


async def test_pump_speed_number_unique_id(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber unique ID generation."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Unique ID includes SPEED attribute key
    assert number.unique_id == "test_entry_PMPCIRC01SPEED"


async def test_pump_speed_number_name(
    hass: HomeAssistant,
    pool_object_pmpcirc_vsf: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber name format."""
    number = PumpSpeedNumber(
        mock_coordinator,
        pool_object_pmpcirc_vsf,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Name format: "{pump_name} Speed ({circuit_name})"
    assert number.name == "Pool Pump Speed (Pool Circuit)"


async def test_pump_speed_number_default_mode_when_none(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test PumpSpeedNumber defaults to RPM mode when SELECT is None."""
    from custom_components.intellicenter.const import CONST_RPM

    obj = PoolObject(
        "PMPCIRC01",
        {
            "OBJTYP": PMPCIRC_TYPE,
            "SNAME": "Pool Pump Circuit 1",
            "PARENT": "PUMP1",
            "CIRCUIT": "CIRC01",
            "SELECT": None,  # No mode set
            "SPEED": "2400",
        },
    )

    number = PumpSpeedNumber(
        mock_coordinator,
        obj,
        pump_name="Pool Pump",
        circuit_name="Pool Circuit",
        rpm_min=450,
        rpm_max=3450,
        gpm_min=15,
        gpm_max=140,
    )

    # Should default to RPM mode
    assert number._current_mode == "RPM"
    assert number.native_unit_of_measurement == CONST_RPM


# --- VS-only and VF-only Pump Tests ---


@pytest.fixture
def pool_model_with_vs_pump() -> PoolModel:
    """Return a PoolModel with a variable speed (VS) pump (RPM only)."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "CIRC01",
                "params": {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "GENERIC",
                    "SNAME": "Pool Circuit",
                },
            },
            {
                "objnam": "PUMP1",
                "params": {
                    "OBJTYP": PUMP_TYPE,
                    "SUBTYP": "VS",
                    "SNAME": "VS Pump",
                    "STATUS": "10",
                    "MIN": "450",
                    "MAX": "3450",
                    "MINF": "0",  # VS pump doesn't support GPM
                    "MAXF": "0",  # VS pump doesn't support GPM
                },
            },
            {
                "objnam": "PMPCIRC01",
                "params": {
                    "OBJTYP": PMPCIRC_TYPE,
                    "SNAME": "VS Pump Circuit 1",
                    "PARENT": "PUMP1",
                    "CIRCUIT": "CIRC01",
                    "SELECT": "RPM",
                    "SPEED": "2400",
                },
            },
        ]
    )
    return model


@pytest.fixture
def pool_model_with_vf_pump() -> PoolModel:
    """Return a PoolModel with a variable flow (VF) pump (GPM only)."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "CIRC01",
                "params": {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "GENERIC",
                    "SNAME": "Pool Circuit",
                },
            },
            {
                "objnam": "PUMP1",
                "params": {
                    "OBJTYP": PUMP_TYPE,
                    "SUBTYP": "VF",
                    "SNAME": "VF Pump",
                    "STATUS": "10",
                    "MIN": "0",  # VF pump doesn't support RPM
                    "MAX": "0",  # VF pump doesn't support RPM
                    "MINF": "15",
                    "MAXF": "140",
                },
            },
            {
                "objnam": "PMPCIRC01",
                "params": {
                    "OBJTYP": PMPCIRC_TYPE,
                    "SNAME": "VF Pump Circuit 1",
                    "PARENT": "PUMP1",
                    "CIRCUIT": "CIRC01",
                    "SELECT": "GPM",
                    "GPM": "80",
                },
            },
        ]
    )
    return model


async def test_number_setup_creates_vs_pump_rpm_entity(
    hass: HomeAssistant,
    pool_model_with_vs_pump: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test number platform creates PoolNumber with RPM for VS pump."""
    mock_coordinator.model = pool_model_with_vs_pump

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create 1 PoolNumber entity for VS pump (RPM only)
    pump_entities = [
        e
        for e in entities_added
        if hasattr(e, "_pool_object") and e._pool_object.objtype == PMPCIRC_TYPE
    ]
    assert len(pump_entities) == 1
    assert isinstance(pump_entities[0], PoolNumber)
    assert "RPM" in pump_entities[0].name


async def test_number_setup_creates_vf_pump_gpm_entity(
    hass: HomeAssistant,
    pool_model_with_vf_pump: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test number platform creates PoolNumber with GPM for VF pump."""
    mock_coordinator.model = pool_model_with_vf_pump

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create 1 PoolNumber entity for VF pump (GPM only)
    pump_entities = [
        e
        for e in entities_added
        if hasattr(e, "_pool_object") and e._pool_object.objtype == PMPCIRC_TYPE
    ]
    assert len(pump_entities) == 1
    assert isinstance(pump_entities[0], PoolNumber)
    assert "GPM" in pump_entities[0].name


async def test_number_pmpcirc_skipped_when_parent_pump_absent(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """No pump-circuit number is built while the parent pump is absent.

    Regression test for the number-platform limit-upgrade gap: building a
    PMPCIRC entity before its parent pump is known would lock in guessed
    RPM-only defaults that unique_id de-duplication could never upgrade once
    the real (e.g. VSF or VF) pump arrives. The builder must skip instead and
    rely on the coordinator re-dispatch (issue #57).
    """
    from custom_components.intellicenter.number import _build_entities

    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "CIRC01",
                "params": {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "GENERIC",
                    "SNAME": "Pool Circuit",
                },
            },
            {
                "objnam": "PMPCIRC01",
                "params": {
                    "OBJTYP": PMPCIRC_TYPE,
                    "SNAME": "Pool Pump Circuit 1",
                    "PARENT": "PUMP1",  # parent pump intentionally NOT in the model
                    "CIRCUIT": "CIRC01",
                    "SELECT": "RPM",
                    "SPEED": "2400",
                },
            },
        ]
    )
    mock_coordinator.model = model

    entities = _build_entities(mock_coordinator, list(model))

    pmpcirc_entities = [
        e
        for e in entities
        if getattr(e, "_pool_object", None) is not None
        and e._pool_object.objnam == "PMPCIRC01"
    ]
    assert pmpcirc_entities == []


# -------------------------------------------------------------------------------------
# Body max-temperature (HITMP) entity: panel-unit-aware limits (regression)
# -------------------------------------------------------------------------------------


def _make_hitmp_number(mock_coordinator: MagicMock) -> PoolNumber:
    """Build the body Max Temperature number entity like the platform does."""
    from homeassistant.components.number import NumberDeviceClass, NumberMode

    body = PoolObject(
        "POOL1",
        {"OBJTYP": BODY_TYPE, "SUBTYP": "POOL", "SNAME": "Pool", "HITMP": "30"},
    )
    return PoolNumber(
        mock_coordinator,
        body,
        step=1,
        attribute_key="HITMP",
        name="+ Max Temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        integer_only=True,
    )


async def test_hitmp_limits_and_unit_fahrenheit(
    hass: HomeAssistant, mock_coordinator: MagicMock
) -> None:
    """ENGLISH panel: 40-104 F with an explicit Fahrenheit native unit."""
    number = _make_hitmp_number(mock_coordinator)

    assert number.native_min_value == 40.0
    assert number.native_max_value == 104.0
    assert number.native_unit_of_measurement == "°F"


async def test_hitmp_limits_and_unit_celsius(
    hass: HomeAssistant, mock_coordinator: MagicMock
) -> None:
    """Regression: METRIC panel must allow 5-40 C, not the Fahrenheit range.

    Hardcoded 40-104 bounds with no native unit made every valid Celsius
    setpoint (5-39) raise ServiceValidationError and displayed raw values
    without unit conversion.
    """
    type(mock_coordinator.system_info).uses_metric = property(lambda self: True)

    number = _make_hitmp_number(mock_coordinator)

    assert number.native_min_value == 5.0
    assert number.native_max_value == 40.0
    assert number.native_unit_of_measurement == "°C"
    # A mid-range Celsius value reads back fine
    assert number.native_value == 30


# -------------------------------------------------------------------------------------
# Service-call error handling (regression)
# -------------------------------------------------------------------------------------


async def test_number_set_value_connection_error_raises(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: failures must raise, not silently 'succeed'.

    async_set_native_value used to catch every exception and only log, so the
    service call reported success while the UI value snapped back.
    """
    from homeassistant.exceptions import HomeAssistantError
    from pyintellicenter import ICConnectionError

    mock_coordinator.controller.set_ph_setpoint.side_effect = ICConnectionError(
        "Not connected"
    )

    chem = PoolObject(
        "ICHEM1",
        {
            "OBJTYP": CHEM_TYPE,
            "SUBTYP": "ICHEM",
            "SNAME": "IntelliChem",
            "PHSET": "7.4",
        },
    )
    number = PoolNumber(
        mock_coordinator,
        chem,
        attribute_key="PHSET",
        name="+ pH Setpoint",
    )

    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(7.4)


async def test_number_secondary_chlorinator_aborts_without_primary(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: unknown primary output must abort, not be zeroed.

    The old code defaulted a missing primary to 0 and wrote it alongside the
    secondary value - silently turning off the primary chlorinator.
    """
    from homeassistant.exceptions import HomeAssistantError

    mock_coordinator.controller.get_chlorinator_output.return_value = {
        "primary": None,
        "secondary": 30,
    }

    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=SEC_ATTR,
        name="+ Output % (Spa)",
    )

    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(40)

    mock_coordinator.controller.set_chlorinator_output.assert_not_called()


async def test_number_without_device_class_always_has_the_attr(
    hass: HomeAssistant,
    pool_object_intellichlor: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Regression: _attr_device_class must exist even when none is given.

    Newer HA cores declare _attr_device_class as an annotation with no class
    default; the old conditional assignment left the attribute missing and
    every no-device-class number raised AttributeError while being added
    (caught live on the dev container, invisible under the pinned test HA).
    """
    number = PoolNumber(
        mock_coordinator,
        pool_object_intellichlor,
        attribute_key=SEC_ATTR,
        name="+ Output %",
    )

    # The attribute must be readable (HA stores it behind a descriptor; an
    # unassigned one raises AttributeError on newer cores)...
    assert number._attr_device_class is None
    assert number.device_class is None
    # ...and every capability property must be readable without raising.
    assert number.native_min_value is not None
    assert number.native_max_value is not None
    assert number.native_unit_of_measurement is None
