# Testing Guide for IntelliCenter Integration

This document describes the automated testing infrastructure for the Pentair IntelliCenter Home Assistant integration.

## Test Framework

This project uses `pytest` with the `pytest-homeassistant-custom-component` framework for automated testing. The integration test suite (257 tests across 13 files) covers:

- **Config Flow Tests**: User setup, Zeroconf discovery, error handling
- **Integration/Setup Tests**: Entry setup and unload, retry on transient connection errors, connection handler behavior
- **Platform Tests**: Entity creation and behavior for all platforms (light, switch, sensor, binary_sensor, water_heater, climate, number, cover)
- **Diagnostics Tests**: Diagnostic data export
- **Contract & Version Tests**: pyintellicenter library contract and version-sync guards

**Protocol Tests**, **Controller Tests**, and **Model Tests** (TCP communication, connection management/reconnection, and PoolModel/PoolObject state) live in the standalone [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) repository, not here.

## Installation

### Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

This installs:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-homeassistant-custom-component` - Home Assistant test utilities
- `ruff` - Linting and formatting
- `mypy` - Type checking

## Running Tests

### Run All Tests

```bash
make pytest
```

Or directly with pytest:

```bash
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_light.py -v
```

### Run Specific Test Function

```bash
pytest tests/test_light.py::test_light_turn_on_basic -v
```

### Run Tests with Coverage

```bash
pytest tests/ --cov=custom_components/intellicenter --cov-report=html
```

View coverage report:
```bash
open htmlcov/index.html
```

## Quality Checks

### Run All Quality Checks (Bronze Level)

```bash
make bronze
```

This runs:
1. Linting with `ruff`
2. Format checking with `ruff format`
3. Type checking with `mypy`
4. All pytest tests

### Individual Quality Checks

```bash
# Linting
make lint

# Format code
make format

# Type checking
make type-check
```

## Test Structure

### Fixtures (tests/conftest.py)

The `conftest.py` file provides reusable fixtures for tests:

- `mock_system_info` - Mock SystemInfo object
- `mock_controller` - Mock BaseController for config flow tests
- `pool_model_data` - Comprehensive test data for a complete pool system
- `pool_model` - Fully populated PoolModel with test equipment
- `pool_object_light` - Individual PoolObject fixtures for testing
- `pool_object_switch` - Fixture for switch entity testing
- `pool_object_pump` - Fixture for pump entity testing
- `pool_object_body` - Fixture for body (pool/spa) testing
- `mock_model_controller` - Mock ModelController with test model

### Test Categories

#### Config Flow Tests (`test_config_flow.py`)

Tests user-initiated setup and Zeroconf discovery:
- ✅ User setup flow
- ✅ Zeroconf discovery
- ✅ Error handling (connection refused, timeouts)
- ✅ Duplicate detection
- ✅ Already configured handling

#### Integration Tests (`test_init.py`)

Tests integration setup and lifecycle (21 tests):
- ✅ Integration setup and entry loading
- ✅ Entry unloading
- ✅ Retry on transient connection errors (`ConfigEntryNotReady` so HA retries with backoff)
- ✅ Loud failure on rejected-command / non-network errors
- ✅ Clean teardown of the partially-started coordinator (no leaked reconnect task)
- ✅ Connection handler behavior

> **Model Tests**: PoolModel and PoolObject state-management tests live in the
> [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) repository, not in this repo.

#### Light Platform Tests (`test_light.py`)

Comprehensive light entity tests (47 tests, including parameterized effect tests):
- ✅ Entity creation for IntelliBrite/regular lights/light shows
- ✅ Turn on/off operations
- ✅ Color effect support
- ✅ Effect selection and application
- ✅ State updates from IntelliCenter
- ✅ Update filtering (ignores irrelevant changes)

#### Switch Platform Tests (`test_switch.py`)

Comprehensive switch entity tests (11 tests):
- ✅ Entity creation for circuits and bodies
- ✅ Turn on/off operations
- ✅ Featured circuit filtering
- ✅ Body (pool/spa) switch behavior
- ✅ Vacation mode switch
- ✅ State updates
- ✅ Device class

#### Sensor Platform Tests (`test_sensor.py`)

Sensor entity tests (18 tests):
- ✅ Temperature sensors
- ✅ Power/RPM/GPM pump sensors
- ✅ Chemistry sensors (pH device class, ORP, tank levels)
- ✅ Platform setup and state updates

#### Binary Sensor Tests (`test_binary_sensor.py`)

Binary sensor entity tests (15 tests):
- ✅ Pump status sensors
- ✅ Heater status sensors
- ✅ Schedule sensors
- ✅ Freeze protection sensor

#### Water Heater Tests (`test_water_heater.py`)

Water heater entity tests (46 tests):
- ✅ Water heater entity creation
- ✅ Temperature setpoint changes
- ✅ Mode selection (heat/idle/off)
- ✅ Heater status tracking
- ✅ HCOMBO multi-mode operation (Gas Only / Heat Pump Only / Hybrid / Dual)
- ✅ Last-used operation remembered and restored on turn-on
- ✅ Bodies combining an HCOMBO with a standard heater

#### Climate Tests (`test_climate.py`)

UltraTemp heat pump climate tests (22 tests):
- ✅ Heating/cooling modes and HVAC action
- ✅ Setpoint changes and preset detection

#### Number Platform Tests (`test_number.py`)

Setpoint number entity tests (33 tests):
- ✅ Chemistry setpoints and pump speed/flow targets

#### Cover Platform Tests (`test_cover.py`)

Pool cover entity tests (17 tests):
- ✅ Open/close control and device class

#### Diagnostics Tests (`test_diagnostics.py`)

Diagnostic export tests (10 tests):
- ✅ Connection metrics and config-entry diagnostics

#### Contract & Version Tests

- ✅ `test_library_contract.py` (2 tests): pyintellicenter API contract
- ✅ `test_versions.py` (2 tests): manifest/pyproject version-sync guards

## Test Coverage Status

### Current Coverage

**Total Tests**: 257 tests across 13 test files

| Component | Tests | Status |
|-----------|-------|--------|
| Light Platform | 47 tests | ✅ Complete |
| Water Heater | 46 tests | ✅ Complete |
| Number Platform | 33 tests | ✅ Complete |
| Climate Platform | 22 tests | ✅ Complete |
| Integration / Setup | 21 tests | ✅ Complete |
| Sensor Platform | 18 tests | ✅ Complete |
| Cover Platform | 17 tests | ✅ Complete |
| Binary Sensor | 15 tests | ✅ Complete |
| Config Flow | 13 tests | ✅ Complete |
| Switch Platform | 11 tests | ✅ Complete |
| Diagnostics | 10 tests | ✅ Complete |
| Library Contract | 2 tests | ✅ Complete |
| Version Sync | 2 tests | ✅ Complete |
| **Total** | **257 tests** | ✅ Complete |

> Protocol, controller, and model tests are maintained in the standalone
> [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) repository and are not counted here.

### Gold Quality Requirements Met

✅ **Extensive automated test coverage** - 257 tests covering:
  - Config flow (user + Zeroconf)
  - Integration setup, unload, and retry-on-transient-error
  - Platform entity creation across all platforms
  - Entity state management
  - Turn on/off operations
  - State updates

✅ **Automatic discovery** - Zeroconf tests verify auto-discovery

✅ **Comprehensive documentation** - README with troubleshooting

✅ **Diagnostic capabilities** - diagnostics.py implemented

✅ **UI reconfiguration** - Config flow supports reconfiguration

⚠️ **Firmware updates** - Not applicable (hardware limitation)

## Writing New Tests

### Test Template

```python
"""Test the Pentair IntelliCenter [component] platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pytest

from custom_components.intellicenter import DOMAIN
from custom_components.intellicenter.pyintellicenter import PoolModel, PoolObject

pytestmark = pytest.mark.asyncio


async def test_[component]_[behavior](
    hass: HomeAssistant,
    pool_model: PoolModel,
) -> None:
    """Test [component] [behavior]."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"

    mock_controller = MagicMock()
    mock_controller.model = pool_model

    # Test implementation
    assert True
```

### Using Fixtures

```python
async def test_with_pool_object(
    pool_object_light: PoolObject,
) -> None:
    """Test using a PoolObject fixture."""
    assert pool_object_light.objnam == "LIGHT1"
    assert pool_object_light.isALight is True
```

### Mocking ModelController

```python
async def test_with_controller(
    mock_model_controller: ModelController,
) -> None:
    """Test with full ModelController mock."""
    controller = mock_model_controller
    assert controller.model is not None
    assert len(list(controller.model.objectList)) > 0
```

## Continuous Integration

Tests run automatically on:
- Every push to `main` branch
- Every pull request
- Manual workflow dispatch

See `.github/workflows/quality-validation.yml` for CI configuration.

## Debugging Tests

### Run with Verbose Output

```bash
pytest tests/ -vv
```

### Show Print Statements

```bash
pytest tests/ -s
```

### Run Specific Test with Debug

```bash
pytest tests/test_light.py::test_light_turn_on_basic -vv -s
```

### Stop on First Failure

```bash
pytest tests/ -x
```

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure all tests pass: `make bronze`
3. Maintain test coverage above 80%
4. Update this document if adding new test categories

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
- [Home Assistant Testing](https://developers.home-assistant.io/docs/development_testing)
- [Home Assistant Quality Scale](https://www.home-assistant.io/docs/quality_scale/)
