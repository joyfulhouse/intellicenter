"""Test the Pentair IntelliCenter config flow."""

from unittest.mock import MagicMock

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intellicenter.const import (
    CONF_KEEPALIVE_INTERVAL,
    CONF_RECONNECT_DELAY,
    CONF_TRANSPORT,
    DEFAULT_TRANSPORT,
    DOMAIN,
)

pytestmark = pytest.mark.asyncio


async def test_user_flow_success(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test successful user flow with manual entry."""
    # Start the flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"setup_method": "manual"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"

    # Enter IP address
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Pool System"
    assert result["data"] == {
        CONF_HOST: "192.168.1.100",
        CONF_TRANSPORT: DEFAULT_TRANSPORT,
    }


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow when connection fails."""
    mock_controller.start.side_effect = ConnectionRefusedError()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"setup_method": "manual"},
    )

    # Enter IP address
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unexpected_exception(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow when unexpected exception occurs."""
    mock_controller.start.side_effect = Exception("Unexpected error")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"setup_method": "manual"},
    )

    # Enter IP address
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "unknown"}


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

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"setup_method": "manual"},
    )

    # Enter IP address
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_invalid_host(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test user flow with invalid host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Select manual entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"setup_method": "manual"},
    )

    # Enter invalid IP (empty string)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: ""},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_host"}


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


# -------------------------------------------------------------------------------------
# Options flow tests
# -------------------------------------------------------------------------------------


async def test_options_flow_init_and_save(hass: HomeAssistant) -> None:
    """Test the options flow shows its form and saves new settings.

    Regression test for issue #40: clicking the gear icon raised
    "Config flow could not be loaded: 500 Internal Server Error". The cause was
    ``OptionsFlowHandler.__init__`` assigning ``self.config_entry``; Home
    Assistant made that a read-only property and removed the deprecated setter
    in 2025.12, so the assignment raised ``AttributeError: property
    'config_entry' ... has no setter`` whenever the options flow was created.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Pool System",
        data={CONF_HOST: "192.168.1.100", CONF_TRANSPORT: DEFAULT_TRANSPORT},
        options={},
    )
    entry.add_to_hass(hass)

    # Opening the options flow is exactly what clicking the gear icon triggers.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_KEEPALIVE_INTERVAL: 120,
            CONF_RECONNECT_DELAY: 45,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_KEEPALIVE_INTERVAL: 120,
        CONF_RECONNECT_DELAY: 45,
    }
    assert entry.options == {
        CONF_KEEPALIVE_INTERVAL: 120,
        CONF_RECONNECT_DELAY: 45,
    }


async def test_options_flow_defaults_from_existing_options(
    hass: HomeAssistant,
) -> None:
    """Test the options form pre-fills defaults from the entry's saved options.

    This exercises the ``self.config_entry`` property resolution: the form's
    defaults are read from ``config_entry.options``, so wrong resolution would
    surface as wrong defaults.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Pool System",
        data={CONF_HOST: "192.168.1.100", CONF_TRANSPORT: DEFAULT_TRANSPORT},
        options={
            CONF_KEEPALIVE_INTERVAL: 150,
            CONF_RECONNECT_DELAY: 60,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # The voluptuous schema's Optional markers carry the current values as
    # their defaults.
    defaults = {
        marker.schema: marker.default() for marker in result["data_schema"].schema
    }
    assert defaults[CONF_KEEPALIVE_INTERVAL] == 150
    assert defaults[CONF_RECONNECT_DELAY] == 60


# -------------------------------------------------------------------------------------
# Reconfigure flow tests
# -------------------------------------------------------------------------------------


async def test_reconfigure_flow_success(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test successful reconfigure flow."""
    # Create an existing entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.99"},
        unique_id="test-unique-id-123",
        title="Old Pool System",
    )
    entry.add_to_hass(hass)

    # Start reconfigure flow
    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Enter new IP address
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # Verify entry was updated
    assert entry.data[CONF_HOST] == "192.168.1.100"
    assert entry.title == "Test Pool System"


async def test_reconfigure_flow_same_host(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test reconfigure flow with same host (no change)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="test-unique-id-123",
        title="Test Pool System",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_flow_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test reconfigure flow when connection fails."""
    mock_controller.start.side_effect = ConnectionRefusedError()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.99"},
        unique_id="test-unique-id-123",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_flow_host_already_configured(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Test reconfigure flow when new host is already configured by another entry."""
    # Create two entries
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.99"},
        unique_id="unique-id-1",
    )
    entry1.add_to_hass(hass)

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="unique-id-2",
    )
    entry2.add_to_hass(hass)

    # Try to reconfigure entry1 to use entry2's host
    result = await entry1.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.100"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# -------------------------------------------------------------------------------------
# Discover step (library-based discovery) and exception-mapping regressions
# -------------------------------------------------------------------------------------


def _patch_discovery(units):
    """Patch the discovery helpers used by the discover step."""
    from unittest.mock import AsyncMock, patch as mock_patch

    return (
        mock_patch(
            "custom_components.intellicenter.config_flow.discover_intellicenter_units",
            AsyncMock(return_value=units),
        ),
        mock_patch(
            "custom_components.intellicenter.config_flow.zeroconf.async_get_instance",
            AsyncMock(return_value=MagicMock()),
        ),
    )


async def test_discover_flow_success(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Selecting a discovered unit creates an entry."""
    from pyintellicenter import ICUnit

    unit = ICUnit(name="IntelliCenter", host="192.168.1.50", port=6681, ws_port=6680)
    discovery_patch, zc_patch = _patch_discovery([unit])

    with discovery_patch, zc_patch:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"setup_method": "discover"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "discover"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "192.168.1.50"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.50"


async def test_discover_flow_selected_unit_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Regression: a failing discovered unit re-shows the form, not a crash.

    The unit-selection call used to sit outside the step's try/except while the
    helper deliberately re-raised CannotConnect, so the flow died with a
    generic 'unknown error' dialog instead of showing cannot_connect.
    """
    from pyintellicenter import ICUnit

    unit = ICUnit(name="IntelliCenter", host="192.168.1.50", port=6681, ws_port=6680)
    discovery_patch, zc_patch = _patch_discovery([unit])
    mock_controller.start.side_effect = ConnectionRefusedError()

    with discovery_patch, zc_patch:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"setup_method": "discover"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "192.168.1.50"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discover"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_ic_timeout_maps_to_cannot_connect(
    hass: HomeAssistant, mock_controller: MagicMock
) -> None:
    """Regression: ICTimeoutError is a connection problem, not 'unknown'.

    ICTimeoutError subclasses ICError, NOT the builtin TimeoutError, so the
    old except tuple missed it and a slow-to-answer panel showed 'unknown'.
    """
    from pyintellicenter import ICTimeoutError

    mock_controller.start.side_effect = ICTimeoutError("GetParamList timed out")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"setup_method": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.100"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}
