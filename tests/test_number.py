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
    SPEED_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.number import PoolNumber

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_model_with_intellichlor() -> PoolModel:
    """Return a PoolModel with IntelliChlor."""
    model = PoolModel()
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
    model = PoolModel()
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
    model = PoolModel()
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


async def test_number_setup_creates_pmpcirc_entities(
    hass: HomeAssistant,
    pool_model_with_pmpcirc: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test number platform creates entities for pump circuit settings."""
    mock_coordinator.model = pool_model_with_pmpcirc

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.number import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create 2 number entities (RPM and GPM for VSF pump)
    pmpcirc_entities = [e for e in entities_added if "RPM" in e.name or "GPM" in e.name]
    assert len(pmpcirc_entities) == 2


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
