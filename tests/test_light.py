"""Test the Pentair IntelliCenter light platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.light import ATTR_EFFECT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
import pytest

from custom_components.intellicenter import DOMAIN
from custom_components.intellicenter.light import LIGHTS_EFFECTS, PoolLight
from custom_components.intellicenter.pyintellicenter import (
    ACT_ATTR,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)

pytestmark = pytest.mark.asyncio


async def test_light_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """Test light platform creates entities for lights in the model."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Mock the handler
    mock_handler = MagicMock()
    mock_controller = MagicMock()
    mock_controller.model = pool_model
    mock_handler.controller = mock_controller

    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.light import async_setup_entry

    await async_setup_entry(hass, entry, capture_entities)

    # Should create entities for:
    # - LIGHT1 (IntelliBrite light)
    # - LIGHT2 (Regular light)
    # - SHOW1 (Light show)
    assert len(entities_added) == 3

    # Verify entity types
    light_names = [e._poolObject.sname for e in entities_added]
    assert "Pool Light" in light_names
    assert "Spa Light" in light_names
    assert "Party Show" in light_names


async def test_light_entity_properties(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test PoolLight entity properties."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    # Test initial state
    assert light.is_on is False
    assert light.name == "Pool Light"
    assert light.unique_id == "test_entry_LIGHT1"


async def test_light_turn_on_basic(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test turning on a light without effects."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    await hass.async_block_till_done()
    await light.async_turn_on()

    # Should request status change to ON
    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_light_turn_on_with_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test turning on a light with color effect."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: "Party Mode"})

    # Should request status ON and effect PARTY
    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"
    assert ACT_ATTR in args[1]
    assert args[1][ACT_ATTR] == "PARTY"


async def test_light_turn_off(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test turning off a light."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.requestChanges = AsyncMock()

    # Set light to ON initially
    pool_object_light.update({STATUS_ATTR: "ON"})

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    assert light.is_on is True

    await hass.async_block_till_done()
    await light.async_turn_off()

    # Should request status change to OFF
    mock_controller.requestChanges.assert_called_once()
    args = mock_controller.requestChanges.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_light_supports_effects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test light with color effects support."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    # Should have effect list
    assert light.effect_list is not None
    assert len(light.effect_list) > 0
    assert "Party Mode" in light.effect_list
    assert "Caribbean" in light.effect_list
    assert "White" in light.effect_list


async def test_light_no_effects_support(
    hass: HomeAssistant,
) -> None:
    """Test light without color effects support."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

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

    light = PoolLight(entry, mock_controller, regular_light_obj, None)

    # Should not support effects
    assert light._lightEffects is None


async def test_light_current_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test getting current effect."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    # Set light to use PARTY effect
    pool_object_light.update({"USE": "PARTY"})

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    assert light.effect == "Party Mode"


async def test_light_state_updates(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test light state updates from IntelliCenter."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

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
) -> None:
    """Test light show entity creation and properties."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.model = pool_model

    show_obj = pool_model["SHOW1"]

    # For the light show, we need to add circuit references as children
    # Add a child circuit to the light show
    pool_model.addObject(
        "SHOW1_CIRC1",
        {
            "OBJTYP": "CIRCGRP",
            "CIRCUIT": "LIGHT1",
            "PARENT": "SHOW1",
        },
    )

    light_show = PoolLight(entry, mock_controller, show_obj, LIGHTS_EFFECTS)

    assert light_show.name == "Party Show"
    assert light_show.is_on is False


async def test_light_is_not_updated_by_other_objects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
) -> None:
    """Test that light ignores updates to other objects."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

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
) -> None:
    """Test that light ignores irrelevant attribute updates."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()

    light = PoolLight(entry, mock_controller, pool_object_light, LIGHTS_EFFECTS)

    # Update with irrelevant attributes
    updates = {
        "LIGHT1": {
            "SOME_OTHER_ATTR": "value",
        }
    }

    assert light.isUpdated(updates) is False
