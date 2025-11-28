"""Test the Pentair IntelliCenter number platform."""

from unittest.mock import MagicMock

from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    PRIM_ATTR,
    SEC_ATTR,
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
