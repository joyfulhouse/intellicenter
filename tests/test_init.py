"""Test the Pentair IntelliCenter integration initialization."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.intellicenter import (
    DOMAIN,
    PLATFORMS,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)

pytestmark = pytest.mark.asyncio


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test the async_setup function."""
    result = await async_setup(hass, {})
    assert result is True


async def test_async_setup_entry_success(
    hass: HomeAssistant, mock_model_controller: MagicMock
) -> None:
    """Test successful setup of a config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Mock the handler's start method
    with patch(
        "custom_components.intellicenter.ModelController"
    ) as mock_controller_class:
        mock_controller = MagicMock()
        mock_controller.systemInfo.propName = "Test Pool System"
        mock_controller.model = MagicMock()
        mock_controller.model.__iter__ = MagicMock(return_value=iter([]))
        mock_controller_class.return_value = mock_controller

        with patch(
            "custom_components.intellicenter.ConnectionHandler"
        ) as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.start = AsyncMock()
            mock_handler.stop = MagicMock()
            mock_handler_class.return_value = mock_handler

            with patch.object(
                hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
            ) as mock_forward:
                result = await async_setup_entry(hass, entry)

                assert result is True
                assert DOMAIN in hass.data
                assert entry.entry_id in hass.data[DOMAIN]
                mock_handler.start.assert_called_once()

                # Wait a bit for the async task to complete
                await hass.async_block_till_done()

                # Verify platforms were set up
                mock_forward.assert_called_once_with(entry, PLATFORMS)


async def test_async_setup_entry_connection_failed(hass: HomeAssistant) -> None:
    """Test setup fails when connection is refused."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}

    with patch(
        "custom_components.intellicenter.ModelController"
    ) as mock_controller_class:
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller

        with patch(
            "custom_components.intellicenter.ConnectionHandler"
        ) as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler.start = AsyncMock(side_effect=ConnectionRefusedError())
            mock_handler_class.return_value = mock_handler

            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)


async def test_async_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Set up the handler in hass.data
    mock_handler = MagicMock()
    mock_handler.stop = MagicMock()
    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    with patch.object(
        hass.config_entries,
        "async_forward_entry_unload",
        new_callable=lambda: AsyncMock(return_value=True),
    ) as mock_unload:
        result = await async_unload_entry(hass, entry)

        # Verify all platforms were unloaded
        assert mock_unload.call_count == len(PLATFORMS)
        for platform in PLATFORMS:
            assert call(entry, platform) in mock_unload.call_args_list

        # Verify handler was stopped
        mock_handler.stop.assert_called_once()

        # Verify entry was removed from hass.data
        assert entry.entry_id not in hass.data[DOMAIN]

        assert result is True


async def test_async_unload_entry_platforms_fail(hass: HomeAssistant) -> None:
    """Test unload returns False when platforms fail to unload."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"

    # Set up the handler in hass.data
    mock_handler = MagicMock()
    hass.data[DOMAIN] = {entry.entry_id: mock_handler}

    with patch.object(
        hass.config_entries,
        "async_forward_entry_unload",
        new_callable=lambda: AsyncMock(return_value=False),  # Simulate platform unload failure
    ):
        result = await async_unload_entry(hass, entry)

        # Handler should still be stopped even if platforms fail
        mock_handler.stop.assert_called_once()

        # Entry should still be removed
        assert entry.entry_id not in hass.data[DOMAIN]

        assert result is False
