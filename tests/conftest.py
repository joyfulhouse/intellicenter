"""Fixtures for Pentair IntelliCenter integration tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    PUMP_TYPE,
    SCHED_TYPE,
    SENSE_TYPE,
    SYSTEM_TYPE,
    VALVE_TYPE,
    ICModelController,
    ICSystemInfo,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.coordinator import IntelliCenterCoordinator

# Enable custom integrations
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_system_info() -> ICSystemInfo:
    """Return a mock ICSystemInfo object."""
    mock_info = MagicMock(spec=ICSystemInfo)
    # Configure property return values using PropertyMock
    type(mock_info).unique_id = property(lambda self: "test-unique-id-123")
    type(mock_info).prop_name = property(lambda self: "Test Pool System")
    type(mock_info).sw_version = property(lambda self: "2.0.0")
    type(mock_info).uses_metric = property(lambda self: False)
    return mock_info


@pytest.fixture
def mock_controller(mock_system_info: ICSystemInfo) -> Generator[MagicMock]:
    """Return a mock ICBaseController."""
    with patch(
        "custom_components.intellicenter.config_flow.ICBaseController"
    ) as mock_controller_class:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_instance.system_info = mock_system_info
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
                "BODY": "POOL1 SPA01",
                "LISTORD": "1",
            },
        },
        # Chemistry sensor (IntelliChem)
        {
            "objnam": "CHEM1",
            "params": {
                "OBJTYP": CHEM_TYPE,
                "SUBTYP": "ICHEM",
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
                "SOURCE": "68",
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
        # Valve actuator
        {
            "objnam": "VAL01",
            "params": {
                "OBJTYP": VALVE_TYPE,
                "SUBTYP": "LEGACY",
                "SNAME": "Spillover Valve",
                "STATUS": "OFF",
            },
        },
    ]


@pytest.fixture
def pool_model(pool_model_data: list[dict[str, Any]]) -> PoolModel:
    """Return a PoolModel with test data."""
    model = PoolModel()
    model.add_objects(pool_model_data)
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
) -> Generator[ICModelController]:
    """Return a mock ICModelController for integration tests."""
    with patch(
        "custom_components.intellicenter.ICModelController"
    ) as mock_controller_class:
        mock_instance = MagicMock(spec=ICModelController)
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_instance.request_changes = AsyncMock()
        mock_instance.model = pool_model

        # Add system info properties
        system_obj = pool_model["SYS01"]
        mock_instance.system_info = MagicMock()
        type(mock_instance.system_info).unique_id = property(
            lambda self: "test-unique-id-123"
        )
        type(mock_instance.system_info).prop_name = property(
            lambda self: system_obj.properties.get("PROPNAME", "Test Pool System")
        )
        type(mock_instance.system_info).sw_version = property(
            lambda self: system_obj.properties.get("VER", "2.0.0")
        )
        type(mock_instance.system_info).uses_metric = property(
            lambda self: system_obj.properties.get("MODE") == "METRIC"
        )

        mock_controller_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_coordinator(
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> MagicMock:
    """Return a mock IntelliCenterCoordinator for entity tests."""
    mock_coord = MagicMock(spec=IntelliCenterCoordinator)

    # Configure hass reference (needed for async_create_task in entities)
    mock_coord.hass = hass

    # Configure entry
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.entry_id = "test_entry"
    mock_entry.data = {CONF_HOST: "192.168.1.100"}
    mock_coord.config_entry = mock_entry

    # Configure model
    mock_coord.model = pool_model

    # Configure controller with all convenience methods
    mock_controller = MagicMock()
    mock_controller.request_changes = AsyncMock()
    # Convenience methods from pyintellicenter v0.1.2
    mock_controller.set_valve_state = AsyncMock()
    mock_controller.set_vacation_mode = AsyncMock()
    mock_controller.set_ph_setpoint = AsyncMock()
    mock_controller.set_orp_setpoint = AsyncMock()
    mock_controller.set_chlorinator_output = AsyncMock()
    mock_controller.set_light_effect = AsyncMock()
    mock_controller.set_setpoint = AsyncMock()
    mock_controller.set_heat_mode = AsyncMock()
    mock_controller.get_chlorinator_output = MagicMock(
        return_value={"primary": 50, "secondary": 50}
    )
    mock_controller.is_vacation_mode = MagicMock(return_value=False)
    # Convenience methods from pyintellicenter v0.1.3
    mock_controller.set_alkalinity = AsyncMock()
    mock_controller.set_calcium_hardness = AsyncMock()
    mock_controller.set_cyanuric_acid = AsyncMock()
    mock_controller.get_alkalinity = MagicMock(return_value=100)
    mock_controller.get_calcium_hardness = MagicMock(return_value=300)
    mock_controller.get_cyanuric_acid = MagicMock(return_value=40)
    mock_coord.controller = mock_controller

    # Configure system info
    system_obj = pool_model["SYS01"]
    mock_coord.system_info = MagicMock()
    type(mock_coord.system_info).unique_id = property(lambda self: "test-unique-id-123")
    type(mock_coord.system_info).prop_name = property(
        lambda self: system_obj.properties.get("PROPNAME", "Test Pool System")
    )
    type(mock_coord.system_info).sw_version = property(
        lambda self: system_obj.properties.get("VER", "2.0.0")
    )
    type(mock_coord.system_info).uses_metric = property(
        lambda self: system_obj.properties.get("MODE") == "METRIC"
    )

    # Configure connection state
    mock_coord.connected = True

    return mock_coord


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Return a mock config entry for tests."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    return entry


@pytest.fixture
def mock_write_ha_state() -> Generator[MagicMock]:
    """Mock async_write_ha_state to allow testing entities not added to HA.

    Use this fixture when testing entity methods that call async_write_ha_state
    (like async_turn_on/async_turn_off with optimistic updates) without
    properly registering the entity with Home Assistant.
    """
    with patch(
        "homeassistant.helpers.entity.Entity.async_write_ha_state"
    ) as mock_write:
        yield mock_write


@pytest.fixture
def pool_object_valve() -> PoolObject:
    """Return a PoolObject representing a valve actuator."""
    return PoolObject(
        "VAL01",
        {
            "OBJTYP": VALVE_TYPE,
            "SUBTYP": "LEGACY",
            "SNAME": "Spillover Valve",
            "STATUS": "OFF",
        },
    )
