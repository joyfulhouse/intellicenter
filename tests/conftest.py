"""Fixtures for Pentair IntelliCenter integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.intellicenter.pyintellicenter import SystemInfo

# Enable custom integrations
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_system_info() -> SystemInfo:
    """Return a mock SystemInfo object."""
    mock_info = MagicMock(spec=SystemInfo)
    # Configure property return values using PropertyMock
    type(mock_info).uniqueID = property(lambda self: "test-unique-id-123")
    type(mock_info).propName = property(lambda self: "Test Pool System")
    type(mock_info).swVersion = property(lambda self: "2.0.0")
    type(mock_info).usesMetric = property(lambda self: False)
    return mock_info


@pytest.fixture
def mock_controller(mock_system_info: SystemInfo) -> Generator[MagicMock, None, None]:
    """Return a mock BaseController."""
    with patch(
        "custom_components.intellicenter.config_flow.BaseController"
    ) as mock_controller_class:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = MagicMock()
        mock_instance.systemInfo = mock_system_info
        mock_controller_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_model_controller() -> Generator[MagicMock, None, None]:
    """Return a mock ModelController for integration tests."""
    with patch(
        "custom_components.intellicenter.ModelController"
    ) as mock_controller_class:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = MagicMock()
        mock_instance.model = MagicMock()
        mock_instance.model.system = MagicMock()
        mock_instance.model.system.propName = "Test Pool System"
        mock_controller_class.return_value = mock_instance
        yield mock_instance
