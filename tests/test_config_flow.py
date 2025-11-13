"""Test the IntelliCenter config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType

from custom_components.intellicenter.const import DOMAIN


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


async def test_user_flow_success(hass):
    """Test successful user flow."""
    with patch(
        "custom_components.intellicenter.config_flow.BaseController"
    ) as mock_controller_class:
        # Setup mock
        mock_controller = MagicMock()
        mock_controller.start = AsyncMock()
        mock_controller.stop = MagicMock()
        mock_controller.systemInfo = MagicMock()
        mock_controller.systemInfo.propName = "Test Pool"
        mock_controller.systemInfo.uniqueID = "test123"
        mock_controller_class.return_value = mock_controller

        # Start flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Submit form
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100"},
        )

        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Test Pool"
        assert result2["data"] == {CONF_HOST: "192.168.1.100"}


async def test_user_flow_cannot_connect(hass):
    """Test user flow when cannot connect."""
    with patch(
        "custom_components.intellicenter.config_flow.BaseController"
    ) as mock_controller_class:
        # Setup mock to raise ConnectionRefusedError
        mock_controller = MagicMock()
        mock_controller.start = AsyncMock(side_effect=ConnectionRefusedError())
        mock_controller.stop = MagicMock()
        mock_controller_class.return_value = mock_controller

        # Start flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Submit form
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate(hass):
    """Test user flow with duplicate entry."""
    with patch(
        "custom_components.intellicenter.config_flow.BaseController"
    ) as mock_controller_class:
        # Setup mock
        mock_controller = MagicMock()
        mock_controller.start = AsyncMock()
        mock_controller.stop = MagicMock()
        mock_controller.systemInfo = MagicMock()
        mock_controller.systemInfo.propName = "Test Pool"
        mock_controller.systemInfo.uniqueID = "test123"
        mock_controller_class.return_value = mock_controller

        # Create existing entry
        entry = MagicMock()
        entry.unique_id = "test123"
        hass.config_entries._entries[DOMAIN] = [entry]

        # Start flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Submit form
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100"},
        )

        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "already_configured"


async def test_zeroconf_flow(hass):
    """Test zeroconf discovery flow."""
    with patch(
        "custom_components.intellicenter.config_flow.BaseController"
    ) as mock_controller_class:
        # Setup mock
        mock_controller = MagicMock()
        mock_controller.start = AsyncMock()
        mock_controller.stop = MagicMock()
        mock_controller.systemInfo = MagicMock()
        mock_controller.systemInfo.propName = "Test Pool"
        mock_controller.systemInfo.uniqueID = "test123"
        mock_controller_class.return_value = mock_controller

        # Start zeroconf flow
        discovery_info = MagicMock()
        discovery_info.host = "192.168.1.100"
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"

        # Confirm
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )

        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Test Pool"
        assert result2["data"] == {CONF_HOST: "192.168.1.100"}
