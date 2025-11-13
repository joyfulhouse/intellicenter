"""Common fixtures for IntelliCenter tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_setup_entry():
    """Mock setup entry."""
    with patch(
        "custom_components.intellicenter.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_connection_handler():
    """Mock ConnectionHandler."""
    mock_handler = MagicMock()
    mock_handler.controller = MagicMock()
    mock_handler.controller.systemInfo = MagicMock()
    mock_handler.controller.systemInfo.propName = "Test Pool"
    mock_handler.controller.systemInfo.swVersion = "1.0.0"
    mock_handler.controller.systemInfo.usesMetric = False
    mock_handler.controller.systemInfo.uniqueID = "test123"
    mock_handler.controller.model = MagicMock()
    mock_handler.controller.model.objectList = []
    mock_handler.start = AsyncMock()
    mock_handler.stop = MagicMock()
    return mock_handler


@pytest.fixture
def mock_model_controller():
    """Mock ModelController."""
    mock = MagicMock()
    mock.start = AsyncMock()
    mock.stop = MagicMock()
    mock.systemInfo = MagicMock()
    mock.systemInfo.propName = "Test Pool"
    mock.systemInfo.swVersion = "1.0.0"
    mock.systemInfo.usesMetric = False
    mock.systemInfo.uniqueID = "test123"
    mock.model = MagicMock()
    mock.model.objectList = []
    return mock


@pytest.fixture
def mock_pool_object():
    """Mock PoolObject."""
    obj = MagicMock()
    obj.objnam = "TEST_OBJ"
    obj.objtype = "BODY"
    obj.subtype = None
    obj.sname = "Test Pool Body"
    obj.status = "ON"
    obj.onStatus = "ON"
    obj.offStatus = "OFF"
    obj.attributes = {}
    obj.properties = {}
    obj.isALight = False
    obj.isALightShow = False
    obj.isFeatured = False
    obj.supportColorEffects = False
    obj.__getitem__ = lambda self, key: self.attributes.get(key)
    return obj


@pytest.fixture
async def hass():
    """Fixture to provide a test instance of Home Assistant."""
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant("/tmp")
    await hass.async_start()
    yield hass
    await hass.async_stop()
