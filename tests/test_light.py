"""Test the Pentair IntelliCenter light platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellicenter import DOMAIN

pytestmark = pytest.mark.asyncio


async def test_light_setup(hass: HomeAssistant) -> None:
    """Test light platform setup."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Mock the handler
    mock_handler = MagicMock()
    mock_controller = MagicMock()
    mock_controller.model = MagicMock()
    mock_controller.model.__iter__ = MagicMock(return_value=iter([]))
    mock_handler.controller = mock_controller

    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    with patch(
        "custom_components.intellicenter.light.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await mock_setup(hass, entry, AsyncMock())
        assert result is True
