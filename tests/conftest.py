"""Fixtures for Pentair IntelliCenter integration tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.intellicenter.pyintellicenter import (
    ModelController,
    PoolModel,
    PoolObject,
    SystemInfo,
)
from custom_components.intellicenter.pyintellicenter.attributes import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    PUMP_TYPE,
    SCHED_TYPE,
    SENSE_TYPE,
    SYSTEM_TYPE,
)

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
def pool_model_data() -> list[dict[str, Any]]:
    """Return test data for a complete pool model."""
    return [
        # System object
        {
            "objnam": "SYS01",
            "params": {
                "OBJTYP": SYSTEM_TYPE,
                "SNAME": "IntelliCenter System",
                "PROPNAME": "Test Pool System",
                "MODE": "ENGLISH",
                "VER": "2.0.0",
                "STATUS": "READY",
            },
        },
        # Pool body
        {
            "objnam": "POOL1",
            "params": {
                "OBJTYP": BODY_TYPE,
                "SUBTYP": "POOL",
                "SNAME": "Pool",
                "STATUS": "ON",
                "LSTTMP": "78",
                "LOTMP": "72",
                "HEATER": "HTR01",
                "HTMODE": "1",
            },
        },
        # Spa body
        {
            "objnam": "SPA01",
            "params": {
                "OBJTYP": BODY_TYPE,
                "SUBTYP": "SPA",
                "SNAME": "Spa",
                "STATUS": "OFF",
                "LSTTMP": "102",
                "LOTMP": "80",
                "HEATER": "HTR01",
                "HTMODE": "0",
            },
        },
        # IntelliBrite light (supports color effects)
        {
            "objnam": "LIGHT1",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "INTELLI",
                "SNAME": "Pool Light",
                "STATUS": "OFF",
                "USE": "WHITER",
                "FEATR": "ON",
            },
        },
        # Regular light (no color effects)
        {
            "objnam": "LIGHT2",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "LIGHT",
                "SNAME": "Spa Light",
                "STATUS": "OFF",
                "FEATR": "ON",
            },
        },
        # Light show
        {
            "objnam": "SHOW1",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "LITSHO",
                "SNAME": "Party Show",
                "STATUS": "OFF",
                "FEATR": "ON",
            },
        },
        # Featured circuit (switch)
        {
            "objnam": "CIRC01",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GENERIC",
                "SNAME": "Pool Cleaner",
                "STATUS": "OFF",
                "FEATR": "ON",
            },
        },
        # Non-featured circuit (should not create switch)
        {
            "objnam": "CIRC02",
            "params": {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GENERIC",
                "SNAME": "Aux Circuit",
                "STATUS": "OFF",
                "FEATR": "OFF",
            },
        },
        # Pump
        {
            "objnam": "PUMP1",
            "params": {
                "OBJTYP": PUMP_TYPE,
                "SUBTYP": "VS",
                "SNAME": "Pool Pump",
                "STATUS": "10",
                "PWR": "1200",
                "RPM": "2000",
                "GPM": "55",
            },
        },
        # Heater
        {
            "objnam": "HTR01",
            "params": {
                "OBJTYP": HEATER_TYPE,
                "SUBTYP": "GAS",
                "SNAME": "Gas Heater",
                "STATUS": "OFF",
            },
        },
        # Chemistry sensor
        {
            "objnam": "CHEM1",
            "params": {
                "OBJTYP": CHEM_TYPE,
                "SNAME": "IntelliChem",
                "PHVAL": "7.4",
                "ORPVAL": "650",
                "PHTNK": "5",
                "ORPTNK": "3",
            },
        },
        # Temperature sensor
        {
            "objnam": "SENSE1",
            "params": {
                "OBJTYP": SENSE_TYPE,
                "SUBTYP": "AIR",
                "SNAME": "Air Temp",
                "STATUS": "68",
            },
        },
        # Schedule
        {
            "objnam": "SCHED1",
            "params": {
                "OBJTYP": SCHED_TYPE,
                "SNAME": "Morning Filter",
                "STATUS": "OFF",
                "ENABLE": "ON",
            },
        },
    ]


@pytest.fixture
def pool_model(pool_model_data: list[dict[str, Any]]) -> PoolModel:
    """Return a PoolModel with test data."""
    model = PoolModel()
    model.addObjects(pool_model_data)
    return model


@pytest.fixture
def pool_object_light() -> PoolObject:
    """Return a PoolObject representing an IntelliBrite light."""
    return PoolObject(
        "LIGHT1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "INTELLI",
            "SNAME": "Pool Light",
            "STATUS": "OFF",
            "USE": "WHITER",
            "FEATR": "ON",
        },
    )


@pytest.fixture
def pool_object_switch() -> PoolObject:
    """Return a PoolObject representing a featured circuit (switch)."""
    return PoolObject(
        "CIRC01",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "GENERIC",
            "SNAME": "Pool Cleaner",
            "STATUS": "OFF",
            "FEATR": "ON",
        },
    )


@pytest.fixture
def pool_object_pump() -> PoolObject:
    """Return a PoolObject representing a variable speed pump."""
    return PoolObject(
        "PUMP1",
        {
            "OBJTYP": PUMP_TYPE,
            "SUBTYP": "VS",
            "SNAME": "Pool Pump",
            "STATUS": "10",
            "PWR": "1200",
            "RPM": "2000",
            "GPM": "55",
        },
    )


@pytest.fixture
def pool_object_body() -> PoolObject:
    """Return a PoolObject representing a pool body."""
    return PoolObject(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "LSTTMP": "78",
            "LOTMP": "72",
            "HEATER": "HTR01",
            "HTMODE": "1",
        },
    )


@pytest.fixture
def mock_model_controller(
    pool_model: PoolModel,
) -> Generator[ModelController, None, None]:
    """Return a mock ModelController for integration tests."""
    with patch(
        "custom_components.intellicenter.ModelController"
    ) as mock_controller_class:
        mock_instance = MagicMock(spec=ModelController)
        mock_instance.start = AsyncMock()
        mock_instance.stop = MagicMock()
        mock_instance.requestChanges = AsyncMock()
        mock_instance.model = pool_model

        # Add system info properties
        system_obj = pool_model["SYS01"]
        mock_instance.systemInfo = MagicMock()
        type(mock_instance.systemInfo).uniqueID = property(
            lambda self: "test-unique-id-123"
        )
        type(mock_instance.systemInfo).propName = property(
            lambda self: system_obj.properties.get("PROPNAME", "Test Pool System")
        )
        type(mock_instance.systemInfo).swVersion = property(
            lambda self: system_obj.properties.get("VER", "2.0.0")
        )
        type(mock_instance.systemInfo).usesMetric = property(
            lambda self: system_obj.properties.get("MODE") == "METRIC"
        )

        mock_controller_class.return_value = mock_instance
        yield mock_instance
