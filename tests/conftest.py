"""Fixtures for Pentair IntelliCenter integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intellicenter.const import DOMAIN
from custom_components.intellicenter.pyintellicenter import SystemInfo

# Enable custom integrations
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_system_info() -> SystemInfo:
    """Return a mock SystemInfo object."""
    mock_info = MagicMock(spec=SystemInfo)
    mock_info.uniqueID = "test-unique-id-123"
    mock_info.propName = "Test Pool System"
    mock_info.sw_version = "2.0.0"
    mock_info.mode = "AUTO"
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
