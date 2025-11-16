"""Test the Pentair IntelliCenter config flow."""

from unittest.mock import MagicMock

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intellicenter.const import DOMAIN

pytestmark = pytest.mark.asyncio


async def test_user_flow_success(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Pool System"
    assert result["data"] == {CONF_HOST: "192.168.1.100"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow when connection fails."""
    mock_controller.start.side_effect = ConnectionRefusedError()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unexpected_exception(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow when unexpected exception occurs."""
    mock_controller.start.side_effect = Exception("Unexpected error")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.xfail(
    reason="Duplicate detection with MockConfigEntry needs investigation"
)
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow when device is already configured."""
    # Create an existing entry with the same unique_id
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="test-unique-id-123",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_flow_success(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test successful zeroconf discovery flow."""
    discovery_info = MagicMock()
    discovery_info.host = "192.168.1.100"
    discovery_info.hostname = "pentair-intellicenter.local."
    discovery_info.name = "pentair-intellicenter"
    discovery_info.type = "_http._tcp.local."

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"] == {
        "host": "192.168.1.100",
        "name": "Test Pool System",
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Pool System"
    assert result["data"] == {CONF_HOST: "192.168.1.100"}


async def test_zeroconf_flow_already_configured_host(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test zeroconf flow when host is already configured."""
    # Create an existing entry with the same host
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="different-unique-id",
    )
    entry.add_to_hass(hass)

    discovery_info = MagicMock()
    discovery_info.host = "192.168.1.100"
    discovery_info.hostname = "pentair-intellicenter.local."

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_flow_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test zeroconf flow when connection fails."""
    mock_controller.start.side_effect = ConnectionRefusedError()

    discovery_info = MagicMock()
    discovery_info.host = "192.168.1.100"
    discovery_info.hostname = "pentair-intellicenter.local."

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.xfail(
    reason="Duplicate detection with MockConfigEntry needs investigation"
)
async def test_zeroconf_flow_updates_existing_entry(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test zeroconf flow updates existing entry with new IP."""
    # Create an existing entry with the same unique ID but different host
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.99"},
        unique_id="test-unique-id-123",
    )
    entry.add_to_hass(hass)

    discovery_info = MagicMock()
    discovery_info.host = "192.168.1.100"
    discovery_info.hostname = "pentair-intellicenter.local."

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
