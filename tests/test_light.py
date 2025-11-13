"""Test the IntelliCenter light platform."""
from unittest.mock import MagicMock

import pytest
from homeassistant.components.light import ATTR_EFFECT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellicenter.const import DOMAIN
from custom_components.intellicenter.light import PoolLight, async_setup_entry


async def test_async_setup_entry_with_lights(
    hass: HomeAssistant, mock_model_controller, mock_pool_object
):
    """Test setting up lights."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    # Setup mock objects
    light_obj = mock_pool_object
    light_obj.isALight = True
    light_obj.supportColorEffects = True
    light_obj.objtype = "CIRCUIT"
    light_obj.subtype = "LIGHT"

    mock_model_controller.model.objectList = [light_obj]
    entry.runtime_data = MagicMock(controller=mock_model_controller)

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    assert len(async_add_entities.call_args[0][0]) == 1
    assert isinstance(async_add_entities.call_args[0][0][0], PoolLight)


def test_pool_light_is_on(mock_model_controller, mock_pool_object):
    """Test light is_on property."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    mock_pool_object.status = "ON"
    mock_pool_object.onStatus = "ON"

    light = PoolLight(entry, mock_model_controller, mock_pool_object)

    assert light.is_on is True


def test_pool_light_turn_on(mock_model_controller, mock_pool_object):
    """Test light turn_on."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    mock_pool_object.onStatus = "ON"
    mock_pool_object.requestChanges = MagicMock()

    light = PoolLight(entry, mock_model_controller, mock_pool_object)
    light.turn_on()

    # Verify requestChanges was called with STATUS: ON
    assert mock_model_controller.requestChanges.called


def test_pool_light_turn_off(mock_model_controller, mock_pool_object):
    """Test light turn_off."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    light = PoolLight(entry, mock_model_controller, mock_pool_object)
    light.turn_off()

    # Verify requestChanges was called
    assert mock_model_controller.requestChanges.called


def test_pool_light_with_effects(mock_model_controller, mock_pool_object):
    """Test light with color effects."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    mock_pool_object.attributes = {"USE": "PARTY"}
    color_effects = {"PARTY": "Party Mode", "CARIB": "Caribbean"}

    light = PoolLight(entry, mock_model_controller, mock_pool_object, color_effects)

    assert light.effect == "Party Mode"
    assert "Party Mode" in light.effect_list
    assert "Caribbean" in light.effect_list
