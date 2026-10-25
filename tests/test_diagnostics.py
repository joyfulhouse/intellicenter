"""Test the Pentair IntelliCenter diagnostics."""

from unittest.mock import MagicMock, PropertyMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CIRCUIT_TYPE,
    PoolModel,
)
import pytest

from custom_components.intellicenter.coordinator import (
    DEFAULT_ATTRIBUTES_MAP,
    IntelliCenterCoordinator,
)
from custom_components.intellicenter.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.intellicenter.restrictions import RestrictionIndex

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_model_for_diagnostics() -> PoolModel:
    """Return a PoolModel for diagnostics testing."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "POOL1",
                "params": {
                    "OBJTYP": BODY_TYPE,
                    "SUBTYP": "POOL",
                    "SNAME": "Pool",
                    "STATUS": "ON",
                    "PROPNAME": "My Pool System",
                },
            },
            {
                "objnam": "LIGHT1",
                "params": {
                    "OBJTYP": CIRCUIT_TYPE,
                    "SUBTYP": "INTELLI",
                    "SNAME": "Pool Light",
                    "STATUS": "OFF",
                },
            },
        ]
    )
    return model


def _create_mock_entry(
    hass: HomeAssistant,
    pool_model: PoolModel,
    entry_id: str = "test_entry",
    title: str = "IntelliCenter",
    host: str = "192.168.1.100",
    sw_version: str = "2.0.0",
    uses_metric: bool = False,
    connected: bool = True,
    has_system_info: bool = True,
    has_coordinator: bool = True,
) -> MagicMock:
    """Create a mock config entry with runtime_data."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.title = title
    entry.data = {CONF_HOST: host}
    entry.options = {}

    if has_coordinator:
        # Create mock coordinator
        mock_coord = MagicMock(spec=IntelliCenterCoordinator)
        mock_coord.hass = hass
        mock_coord.model = pool_model
        mock_coord.restrictions = RestrictionIndex(pool_model)
        mock_coord.connected = connected

        # Create mock controller
        mock_controller = MagicMock()
        mock_controller.metrics = None  # No metrics by default
        mock_coord.controller = mock_controller

        # Create mock system info
        if has_system_info:
            mock_coord.system_info = MagicMock()
            mock_coord.system_info.sw_version = sw_version
            mock_coord.system_info.uses_metric = uses_metric
        else:
            mock_coord.system_info = None

        entry.runtime_data = mock_coord
    else:
        entry.runtime_data = None

    return entry


async def test_diagnostics_returns_data(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics returns expected data structure."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "entry" in result
    assert "system_info" in result
    assert "connection_state" in result
    assert "object_count" in result
    assert "objects" in result
    assert "restriction_contexts" in result
    assert "error" not in result


async def test_diagnostics_redacts_sensitive_data(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics redacts sensitive information."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Check that host is redacted
    assert result["entry"]["data"][CONF_HOST] == "**REDACTED**"

    # Check that PROPNAME in pool objects is redacted
    pool_obj = next(o for o in result["objects"] if o["objnam"] == "POOL1")
    assert pool_obj["properties"].get("PROPNAME") == "**REDACTED**"


async def test_diagnostics_object_count(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics returns correct object count."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["object_count"] == 2
    assert len(result["objects"]) == 2


async def test_diagnostics_system_info(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics returns system info."""
    entry = _create_mock_entry(
        hass, pool_model_for_diagnostics, sw_version="2.0.0", uses_metric=True
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["system_info"]["sw_version"] == "2.0.0"
    assert result["system_info"]["uses_metric"] is True


async def test_diagnostics_no_coordinator(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics when coordinator is not found."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics, has_coordinator=False)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "error" in result
    assert "Coordinator not found" in result["error"]


async def test_diagnostics_no_system_info(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics when system info is None."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics, has_system_info=False)

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Should still work, just with empty system_info
    assert result["system_info"] == {}
    assert result["object_count"] == 2


async def test_diagnostics_object_details(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics includes correct object details."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Find the light object
    light_obj = next(o for o in result["objects"] if o["objnam"] == "LIGHT1")
    assert light_obj["objtype"] == CIRCUIT_TYPE
    assert light_obj["subtype"] == "INTELLI"


async def test_diagnostics_entry_info(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics includes entry info."""
    entry = _create_mock_entry(
        hass,
        pool_model_for_diagnostics,
        entry_id="test_entry_123",
        title="My IntelliCenter",
        host="10.0.0.50",
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["entry_id"] == "test_entry_123"
    # The title is the PROPNAME (often a street address) - must be redacted.
    assert result["entry"]["title"] == "**REDACTED**"
    # Host should be redacted
    assert result["entry"]["data"][CONF_HOST] == "**REDACTED**"


async def test_diagnostics_connection_state(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics includes connection state."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics, connected=True)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["connection_state"]["connected"] is True


async def test_diagnostics_connection_state_disconnected(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """Test diagnostics shows disconnected state."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics, connected=False)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["connection_state"]["connected"] is False


@pytest.mark.parametrize("key", ["PASSWRD", "passwrd", "Password", "PASSCODE"])
@pytest.mark.parametrize("has_coordinator", [True, False])
async def test_diagnostics_redacts_permission_credentials(
    hass: HomeAssistant,
    key: str,
    has_coordinator: bool,
) -> None:
    """Raw model and entry data must not bypass credential redaction."""
    secret = "synthetic-access-secret"
    nested = {"records": [{key: secret, "ENABLE": "ON"}]}
    pool_model_for_diagnostics = PoolModel({"PERMIT": {"OBJTYP", key, "nested"}})
    pool_model_for_diagnostics.add_object(
        "PERMIT1", {"OBJTYP": "PERMIT", key: secret, "nested": nested}
    )
    entry = _create_mock_entry(
        hass, pool_model_for_diagnostics, has_coordinator=has_coordinator
    )
    entry.data["nested"] = nested
    entry.options[key] = secret

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert secret not in str(result)
    assert result["entry"]["data"]["nested"]["records"][0][key] == "**REDACTED**"
    assert entry.data["nested"]["records"][0][key] == secret
    permit = pool_model_for_diagnostics["PERMIT1"]
    assert permit is not None
    assert permit.properties[key] == secret
    if has_coordinator:
        obj = next(o for o in result["objects"] if o["objnam"] == "PERMIT1")
        assert obj["properties"][key] == "**REDACTED**"
        assert obj["properties"]["nested"]["records"][0]["ENABLE"] == "ON"


@pytest.mark.parametrize("value", [None, "", "synthetic-access-secret"])
async def test_diagnostics_masks_nested_empty_credentials(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
    value: str | None,
) -> None:
    """Empty credentials are masked too, including within tuple containers."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)
    entry.options["records"] = ({"PassCode": value},)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["options"]["records"] == [{"PassCode": "**REDACTED**"}]
    assert entry.options["records"] == ({"PassCode": value},)


async def test_diagnostics_omits_sensitive_exception_text(
    hass: HomeAssistant,
    pool_model_for_diagnostics: PoolModel,
) -> None:
    """An unstructured failure message cannot be safely scrubbed by key."""
    entry = _create_mock_entry(hass, pool_model_for_diagnostics)
    with patch.object(
        type(entry.runtime_data),
        "system_info",
        new_callable=PropertyMock,
        side_effect=ValueError("synthetic-access-secret"),
        create=True,
    ):
        result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["error"] == "Error collecting diagnostics"
    assert "synthetic-access-secret" not in str(result)
