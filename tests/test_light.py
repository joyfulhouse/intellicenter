"""Test the Pentair IntelliCenter light platform."""

from unittest.mock import MagicMock

from homeassistant.components.light import ATTR_EFFECT
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    ACT_ATTR,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.light import PoolLight

pytestmark = pytest.mark.asyncio


async def test_light_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test light platform creates entities for lights in the model."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.light import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create entities for:
    # - LIGHT1 (IntelliBrite light)
    # - LIGHT2 (Regular light)
    # - SHOW1 (Light show)
    assert len(entities_added) == 3

    # Verify entity types
    light_names = [e._pool_object.sname for e in entities_added]
    assert "Pool Light" in light_names
    assert "Spa Light" in light_names
    assert "Party Show" in light_names


async def test_light_entity_properties(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolLight entity properties."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Test initial state
    assert light.is_on is False
    assert light.name == "Pool Light"
    assert light.unique_id == "test_entry_LIGHT1"


async def test_light_turn_on_basic(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a light without effects."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on()

    # Should request status change to ON
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"
    # Verify optimistic update was called
    mock_write_ha_state.assert_called()


async def test_light_turn_on_with_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a light with color effect."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: "Party Mode"})

    # Effect is set via convenience method
    mock_coordinator.controller.set_light_effect.assert_called_once_with(
        "LIGHT1", "PARTY"
    )

    # Light is turned on via request_changes
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_light_turn_off(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning off a light."""
    # Set light to ON initially
    pool_object_light.update({STATUS_ATTR: "ON"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    assert light.is_on is True

    await hass.async_block_till_done()
    await light.async_turn_off()

    # Should request status change to OFF
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_light_supports_effects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test light with color effects support."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Should have effect list
    assert light.effect_list is not None
    assert len(light.effect_list) > 0
    assert "Party Mode" in light.effect_list
    assert "Caribbean" in light.effect_list
    assert "White" in light.effect_list


async def test_light_no_effects_support(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test light without color effects support."""
    # Create a regular light without color effect support
    regular_light_obj = PoolObject(
        "LIGHT2",
        {
            "OBJTYP": "CIRCUIT",
            "SUBTYP": "LIGHT",
            "SNAME": "Regular Light",
            "STATUS": "OFF",
        },
    )

    light = PoolLight(mock_coordinator, regular_light_obj, None)

    # Should not support effects
    assert light._light_effects is None


async def test_light_current_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test getting current effect."""
    # Set light to use PARTY effect
    pool_object_light.update({"USE": "PARTY"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    assert light.effect == "Party Mode"


async def test_light_state_updates(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test light state updates from IntelliCenter."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Simulate update from IntelliCenter
    updates = {
        "LIGHT1": {
            STATUS_ATTR: "ON",
            "USE": "BLUER",
        }
    }

    # Check if entity should be updated
    assert light.isUpdated(updates) is True

    # Apply the update
    pool_object_light.update(updates["LIGHT1"])

    # Verify state changed
    assert light.is_on is True
    assert light.effect == "Blue"


async def test_light_show_entity(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test light show entity creation and properties."""
    mock_coordinator.model = pool_model

    show_obj = pool_model["SHOW1"]

    # For the light show, we need to add circuit references as children
    # Add a child circuit to the light show
    pool_model.add_object(
        "SHOW1_CIRC1",
        {
            "OBJTYP": "CIRCGRP",
            "CIRCUIT": "LIGHT1",
            "PARENT": "SHOW1",
        },
    )

    light_show = PoolLight(mock_coordinator, show_obj, LIGHT_EFFECTS)

    assert light_show.name == "Party Show"
    assert light_show.is_on is False


async def test_light_is_not_updated_by_other_objects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that light ignores updates to other objects."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Update for a different object
    updates = {
        "LIGHT2": {
            STATUS_ATTR: "ON",
        }
    }

    assert light.isUpdated(updates) is False


async def test_light_is_not_updated_by_irrelevant_attributes(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that light ignores irrelevant attribute updates."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Update with irrelevant attributes
    updates = {
        "LIGHT1": {
            "SOME_OTHER_ATTR": "value",
        }
    }

    assert light.isUpdated(updates) is False


# -------------------------------------------------------------------------------------
# Parameterized tests for light effects
# -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "effect_code,effect_name",
    [
        ("PARTY", "Party Mode"),
        ("CARIB", "Caribbean"),
        ("SSET", "Sunset"),
        ("ROMAN", "Romance"),
        ("AMERCA", "American"),
        ("ROYAL", "Royal"),
        ("WHITER", "White"),
        ("REDR", "Red"),
        ("BLUER", "Blue"),
        ("GREENR", "Green"),
        ("MAGNTAR", "Magenta"),
    ],
)
async def test_light_effect_mapping(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    effect_code: str,
    effect_name: str,
) -> None:
    """Test that each effect code maps to correct effect name."""
    # Set light to use this effect
    pool_object_light.update({"USE": effect_code})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    assert light.effect == effect_name
    assert effect_name in light.effect_list


@pytest.mark.parametrize(
    "effect_name,expected_code",
    [
        ("Party Mode", "PARTY"),
        ("Caribbean", "CARIB"),
        ("Sunset", "SSET"),
        ("Romance", "ROMAN"),
        ("American", "AMERCA"),
        ("Royal", "ROYAL"),
        ("White", "WHITER"),
        ("Red", "REDR"),
        ("Blue", "BLUER"),
        ("Green", "GREENR"),
        ("Magenta", "MAGNTAR"),
    ],
)
async def test_light_turn_on_with_each_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    effect_name: str,
    expected_code: str,
) -> None:
    """Test turning on light with each effect sends correct code."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: effect_name})

    # Effect is set via convenience method with correct code
    mock_coordinator.controller.set_light_effect.assert_called_once_with(
        "LIGHT1", expected_code
    )

    # Light is turned on via request_changes
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert args[1][STATUS_ATTR] == "ON"


@pytest.mark.parametrize(
    "effect_code",
    [
        "PARTY",
        "CARIB",
        "SSET",
        "ROMAN",
        "AMERCA",
        "ROYAL",
        "WHITER",
        "REDR",
        "BLUER",
        "GREENR",
        "MAGNTAR",
    ],
)
async def test_light_state_update_with_each_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    effect_code: str,
) -> None:
    """Test light state updates correctly for each effect code."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Simulate IntelliCenter update with this effect
    updates = {
        "LIGHT1": {
            STATUS_ATTR: "ON",
            "USE": effect_code,
        }
    }

    # Verify entity recognizes the update
    assert light.isUpdated(updates) is True

    # Apply update
    pool_object_light.update(updates["LIGHT1"])

    # Verify effect is correctly reported
    assert light.is_on is True
    assert light.effect == LIGHT_EFFECTS[effect_code]


async def test_light_invalid_effect_ignored(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test that invalid effect is ignored when turning on."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: "Invalid Effect"})

    # Should still turn on, but without ACT_ATTR since effect is invalid
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert args[1][STATUS_ATTR] == "ON"
    # ACT_ATTR should NOT be present for invalid effect
    assert ACT_ATTR not in args[1]


async def test_light_unknown_effect_code_returns_none(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that unknown effect code returns None for effect property."""
    # Set light to use an unknown effect code
    pool_object_light.update({"USE": "UNKNOWN"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Effect should be None for unknown codes
    assert light.effect is None
