"""Test the Pentair IntelliCenter integration initialization."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pyintellicenter import ICCommandError, ICConnectionError, ICTimeoutError
import pytest

from custom_components.intellicenter import (
    PLATFORMS,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator

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
    entry.options = {}  # No custom options, will use defaults
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    # Mock the coordinator's async_start method
    with patch.object(
        IntelliCenterCoordinator,
        "async_start",
        new_callable=AsyncMock,
    ):
        with patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward:
            result = await async_setup_entry(hass, entry)

            assert result is True

            # Verify coordinator is stored in runtime_data
            assert entry.runtime_data is not None
            assert isinstance(entry.runtime_data, IntelliCenterCoordinator)

            # Wait a bit for the async task to complete
            await hass.async_block_till_done()

            # Verify platforms were set up
            mock_forward.assert_called_once_with(entry, PLATFORMS)


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionRefusedError(),
        OSError("EHOSTUNREACH"),
        TimeoutError(),
        ICConnectionError("connection lost"),
        ICTimeoutError("request timed out"),
        ICCommandError("404"),
    ],
)
async def test_async_setup_entry_transient_error_retries(
    hass: HomeAssistant, exc: Exception
) -> None:
    """Transient connection errors during start raise ConfigEntryNotReady.

    Covers issue #41: each of these must trigger HA's retry loop instead of a
    permanent setup_error. ICCommandError represents a reachable-but-not-ready
    panel that rejects the initial handshake; pyintellicenter's own reconnect loop
    treats it as retryable, so setup must too.
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}  # No custom options, will use defaults

    with (
        patch.object(
            IntelliCenterCoordinator,
            "async_start",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch.object(
            IntelliCenterCoordinator,
            "async_stop",
            new_callable=AsyncMock,
        ) as mock_stop,
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    # The partially-started coordinator must be torn down on failure so its
    # EVENT_HOMEASSISTANT_STOP listener and pyintellicenter reconnect task don't
    # leak on every retry during an outage.
    mock_stop.assert_awaited_once()


async def test_async_setup_entry_unexpected_error_propagates(
    hass: HomeAssistant,
) -> None:
    """A non-connection error during start is not reclassified as transient.

    Only the connection attempt is inside the retry try/except, so an unrelated
    error (here ValueError) propagates unchanged instead of being masked as
    ConfigEntryNotReady and retried forever.
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}

    with patch.object(
        IntelliCenterCoordinator,
        "async_start",
        new_callable=AsyncMock,
        side_effect=ValueError("boom"),
    ):
        with pytest.raises(ValueError):
            await async_setup_entry(hass, entry)


async def test_async_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Set up mock coordinator in runtime_data
    mock_coordinator = MagicMock(spec=IntelliCenterCoordinator)
    mock_coordinator.async_stop = AsyncMock()
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(return_value=True),
    ) as mock_unload:
        result = await async_unload_entry(hass, entry)

        # Verify async_unload_platforms was called with entry and platforms
        mock_unload.assert_called_once_with(entry, PLATFORMS)

        # Verify coordinator was stopped
        mock_coordinator.async_stop.assert_called_once()

        assert result is True


async def test_async_unload_entry_platforms_fail(hass: HomeAssistant) -> None:
    """Test unload returns False when platforms fail to unload."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Set up mock coordinator in runtime_data
    mock_coordinator = MagicMock(spec=IntelliCenterCoordinator)
    mock_coordinator.async_stop = AsyncMock()
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(
            return_value=False
        ),  # Simulate platform unload failure
    ):
        result = await async_unload_entry(hass, entry)

        # Coordinator should still be stopped even if platforms fail
        mock_coordinator.async_stop.assert_called_once()

        # Returns False when platforms fail to unload
        assert result is False


async def test_async_unload_entry_no_runtime_data(hass: HomeAssistant) -> None:
    """Test unload handles missing runtime_data gracefully."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # No runtime_data set
    entry.runtime_data = None

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

        # Should complete without error
        assert result is True


# -------------------------------------------------------------------------------------
# IntelliCenterCoordinator Tests
# -------------------------------------------------------------------------------------


class TestIntelliCenterCoordinator:
    """Tests for the IntelliCenterCoordinator class."""

    async def test_coordinator_init(self, hass: HomeAssistant) -> None:
        """Test coordinator initialization."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
            keepalive_interval=90,
            reconnect_delay=30,
        )

        assert coordinator._host == "192.168.1.100"
        assert coordinator._keepalive_interval == 90
        assert coordinator._reconnect_delay == 30
        assert coordinator.connected is False

    async def test_coordinator_async_start_and_stop(self, hass: HomeAssistant) -> None:
        """Test coordinator start and stop."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Mock the controller
        with patch.object(
            coordinator._controller,
            "start",
            new_callable=AsyncMock,
        ):
            with patch.object(
                coordinator._controller,
                "stop",
                new_callable=AsyncMock,
            ):
                await coordinator.async_start()
                await coordinator.async_stop()

    async def test_coordinator_connected_property(self, hass: HomeAssistant) -> None:
        """Test coordinator connected property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Initially not connected
        assert coordinator.connected is False

        # Simulate connection
        coordinator._connected = True
        assert coordinator.connected is True

    async def test_coordinator_model_property(self, hass: HomeAssistant) -> None:
        """Test coordinator model property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Model should come from controller
        model = coordinator.model
        assert model is not None

    async def test_coordinator_system_info_property(self, hass: HomeAssistant) -> None:
        """Test coordinator system_info property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # System info should come from controller
        system_info = coordinator.system_info
        # Initially None since controller hasn't started
        assert system_info is None or system_info is coordinator._controller.system_info
