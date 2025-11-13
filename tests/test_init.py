"""Test the IntelliCenter integration init."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import pytest

from custom_components.intellicenter import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.intellicenter.const import DOMAIN


async def test_async_setup(hass: HomeAssistant):
    """Test the setup."""
    assert await async_setup(hass, {}) is True


async def test_async_setup_entry_success(hass: HomeAssistant, mock_connection_handler):
    """Test successful setup of entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    with patch(
        "custom_components.intellicenter.ModelController"
    ) as mock_controller_class, patch(
        "custom_components.intellicenter.ConnectionHandler"
    ) as mock_handler_class:
        # Setup mocks
        mock_controller = MagicMock()
        mock_controller.systemInfo = MagicMock()
        mock_controller.systemInfo.propName = "Test Pool"
        mock_controller.model = MagicMock()
        mock_controller.model.objectList = []
        mock_controller_class.return_value = mock_controller

        mock_handler = mock_connection_handler
        mock_handler_class.return_value = mock_handler

        # Call setup
        result = await async_setup_entry(hass, entry)

        assert result is True
        assert hasattr(entry, "runtime_data")
        mock_handler.start.assert_called_once()


async def test_async_setup_entry_connection_error(hass: HomeAssistant):
    """Test setup with connection error."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    with patch(
        "custom_components.intellicenter.ConnectionHandler"
    ) as mock_handler_class:
        # Setup mocks to raise ConnectionRefusedError
        mock_handler = MagicMock()
        mock_handler.start = AsyncMock(side_effect=ConnectionRefusedError())
        mock_handler_class.return_value = mock_handler

        # Call setup and expect ConfigEntryNotReady
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


async def test_async_unload_entry(hass: HomeAssistant, mock_connection_handler):
    """Test unloading an entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Pool",
        data={CONF_HOST: "192.168.1.100"},
        source="user",
        unique_id="test123",
    )

    # Setup runtime data
    entry.runtime_data = mock_connection_handler

    with patch(
        "custom_components.intellicenter.asyncio.gather", return_value=[True] * 7
    ):
        result = await async_unload_entry(hass, entry)

        assert result is True
        mock_connection_handler.stop.assert_called_once()
