# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Guidelines

**IMPORTANT**: This repository is `joyfulhouse/intellicenter`. It was forked from upstream repositories, but we maintain our own independent development.

**NEVER submit pull requests to upstream repositories**:
- `https://github.com/dwradcliffe/intellicenter` (original upstream)
- `https://github.com/jlvaillant/intellicenter` (another fork)

All development, pull requests, and collaboration should happen within the `joyfulhouse/intellicenter` repository only.

## Project Overview

This is a Home Assistant custom integration for Pentair IntelliCenter pool control systems. It connects to IntelliCenter via local network (not cloud) using a custom TCP protocol on port 6681, supporting Zeroconf discovery and local push updates for real-time responsiveness.

**Current Quality Scale**: **Platinum** ✅ (v3.1.0+)

The integration meets **Platinum** quality scale requirements with:
- 257 automated tests across all platforms
- Comprehensive type annotations (mypy strict mode)
- Full code documentation
- Production hardening (circuit breaker, metrics, health monitoring)
- User-configurable options (keepalive, reconnect delay)
- External `pyintellicenter` library for protocol layer (https://github.com/joyfulhouse/pyintellicenter)

## Related Projects and Navigation

This integration consists of two repositories that work together:

### Project Locations

| Project | Path | Repository |
|---------|------|------------|
| **intellicenter** (HA Integration) | `/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter` | `joyfulhouse/intellicenter` |
| **pyintellicenter** (Protocol Library) | `/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter` | `joyfulhouse/pyintellicenter` |

### When to Edit Each Project

- **intellicenter**: Home Assistant entities, config flow, coordinator, platform logic
- **pyintellicenter**: TCP connection, protocol handling, model/PoolObject, discovery

### Publishing pyintellicenter to PyPI

When changes are made to pyintellicenter:

1. Bump version in `pyintellicenter/pyproject.toml`
2. Update requirement in `intellicenter/custom_components/intellicenter/manifest.json`
3. Commit and push pyintellicenter changes
4. Create a GitHub release to trigger the publish workflow:
   ```bash
   cd /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter
   gh release create v0.0.X --title "v0.0.X" --notes "Release notes here"
   ```
5. Wait for publish workflow to complete (~60s)
6. Restart Home Assistant container to pick up new version

### Docker Development

The integration is volume-mounted to the homeassistant-dev container:
```bash
# Restart container after changes
cd /Users/bryanli/Projects/joyfulhouse/homeassistant-dev
docker compose restart homeassistant

# Check logs for intellicenter
docker compose logs --since 1m homeassistant 2>&1 | grep -i intellicenter

# Check installed pyintellicenter version
docker compose exec homeassistant pip show pyintellicenter | grep Version
```

## Development Commands

### Code Quality
```bash
# Run ruff linting with auto-fix
uv run ruff check --fix

# Format code with ruff
uv run ruff format

# Run type checking with mypy
uv run mypy custom_components/intellicenter/ --ignore-missing-imports

# Run all pre-commit hooks
pre-commit run --all-files
```

### Development Setup

The protocol layer is in a separate package (`pyintellicenter`), checked out locally at
`/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter` (repo `joyfulhouse/pyintellicenter`).
For development against a local copy of the library:

```bash
# From the intellicenter repo root, install the local library editable:
uv pip install -e /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter
```

For normal test/CI runs the published release is used (per `manifest.json`:
`pyintellicenter>=0.1.20`). Keep `pyproject.toml`'s pin and `uv.lock` in sync with
`manifest.json` — they have drifted in the past.

### Testing

**Framework**: This project uses `pytest-homeassistant-custom-component` for automated testing.

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=custom_components/intellicenter --cov-report=html

# Run specific test file
uv run pytest tests/test_config_flow.py

# Run tests with verbose output
uv run pytest -v
```

**Setting up tests**:
1. Install test dependencies: `pytest`, `pytest-homeassistant-custom-component`, `pytest-asyncio`
2. Create `tests/` directory at repository root
3. Add `conftest.py` with required fixtures:
   ```python
   from pytest_homeassistant_custom_component.common import MockConfigEntry

   # Enable custom integrations (required for HA 2021.6.0b0+)
   pytest_plugins = "pytest_homeassistant_custom_component"
   ```
4. Import test utilities using `from pytest_homeassistant_custom_component.common import ...` instead of `from tests.common import ...`
5. Reference: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component

**Manual testing** (still required for hardware-specific features):
1. A physical Pentair IntelliCenter system or access to one on the network
2. Installing the integration in a Home Assistant instance
3. Configuring via UI (config flow) or Zeroconf auto-discovery

**Writing tests**:
Tests should mock the TCP connection to IntelliCenter rather than requiring physical hardware. Key testing patterns:

```python
# Example config flow test structure
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.intellicenter.const import DOMAIN

async def test_config_flow_user_step(hass):
    """Test user-initiated config flow."""
    # Mock BaseController.start() to return SystemInfo
    # Test UI form display, validation, entry creation

async def test_config_flow_zeroconf(hass):
    """Test Zeroconf discovery flow."""
    # Mock discovery_info, test auto-discovery logic

# Example platform test structure
async def test_light_entity_creation(hass):
    """Test light entities are created for pool lights."""
    # Create MockConfigEntry
    # Mock ModelController with test PoolObjects
    # Verify entities created with correct attributes

async def test_light_turn_on(hass):
    """Test turning on a pool light."""
    # Setup entity, call async_turn_on()
    # Verify requestChanges() called with correct params
```

Mock the protocol layer by patching `ModelController` or creating test `PoolModel` instances with fixture data. Avoid requiring actual IntelliCenter hardware.

## Architecture

### High-Level Structure

The integration follows a layered architecture:

1. **Home Assistant Layer** (`custom_components/intellicenter/`)
   - Platform modules: `light.py`, `sensor.py`, `switch.py`, `binary_sensor.py`, `water_heater.py`, `climate.py`, `number.py`, `cover.py`, `select.py`
   - Entry point: `__init__.py` - Sets up integration, manages entity lifecycle
   - Coordinator: `coordinator.py` - `IntelliCenterCoordinator` (a `DataUpdateCoordinator`) owns the connection and fans out push updates to entities
   - Config flow: `config_flow.py` - Handles UI setup, Zeroconf discovery, and options flow
   - Base entity: `PoolEntity` class in `__init__.py` (subclass of `CoordinatorEntity`) - common functionality for all entities
   - `OnOffControlMixin` - Mixin for simple on/off entities

2. **Protocol/Model Layer** (`pyintellicenter` - external package)
   - Separate repository: https://github.com/joyfulhouse/pyintellicenter (checked out at `/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter`)
   - Installed via `manifest.json` requirements: `pyintellicenter>=0.1.20`
   - `controller.py` - Controller classes (all `IC`-prefixed):
     - `ICBaseController`: connection + command handling; exposes `ICSystemInfo` and `ICConnectionMetrics`
     - `ICModelController`: manages `PoolModel` state, tracks attribute changes, and provides domain control/query helpers (lights, pumps, heaters, bodies, chemistry). NOTE: this class is large (~1,200 lines / 130+ methods) and is the main refactor target
     - `ICConnectionHandler`: reconnection with exponential backoff + circuit breaker; emits events via the `ICConnectionHandlerCallbacks` protocol
     - `ICConnectionMetrics`: tracks response times, reconnect attempts, and health
   - `connection.py` - Transport layer: `ICProtocol` (TCP, port 6681) and `ICWebSocketTransport` (port 6680) share `ICRequestMixin`/`ICNotificationMixin`, wrapped by `ICConnection`. Uses orjson; handles framing, one-request-at-a-time flow control, and keepalive queries
   - `model.py` - `PoolModel` and `PoolObject`: object model representing pool equipment
   - `attributes/` - Attribute definitions and type mappings (package: `constants.py`, `body.py`, `circuit.py`, `equipment.py`, `system.py`, `schedule.py`, `misc.py`)
   - `discovery.py` - Zeroconf discovery (`ICUnit`, `discover_intellicenter_units()`)

### Key Architectural Patterns

**Connection Management**: The integration uses a layered approach to handle unreliable network connections:
- `ICProtocol` / `ICWebSocketTransport` (in `connection.py`) handle transport-level concerns (message framing, flow control, keepalive queries)
- `ICModelController` manages state synchronization
- `ICConnectionHandler` implements automatic reconnection with exponential backoff (configurable, default 30s)
- Circuit breaker pattern prevents hammering dead servers (opens after 5 failures)
- `ICConnectionMetrics` tracks response times and reconnect attempts for observability

**State Updates**: Real-time updates flow through a `DataUpdateCoordinator` (no polling; `local_push`):
1. IntelliCenter sends `NotifyList` messages when equipment state changes
2. `ICModelController` applies them to the `PoolModel` and invokes the handler's `on_updated(controller, updates)` callback
3. `_CoordinatorConnectionHandler.on_updated()` (in `coordinator.py`) calls `IntelliCenterCoordinator.async_set_updated_data(updates)`, which calls `async_update_listeners()`
4. Each `PoolEntity` (a `CoordinatorEntity`) runs `_handle_coordinator_update()`; if its tracked attribute changed it calls `async_write_ha_state()`

Connection up/down propagates the same way via `on_reconnected` / `on_disconnected` → `async_set_connection_state()`, which drives each entity's `available`.

**Request Flow Control**: IntelliCenter struggles with concurrent requests, so the transport (`connection.py`) keeps a single in-flight request (`_response_future`) and queues the rest.

### Entity Creation Logic

Entities are created based on equipment characteristics in the pool model:

- **Lights**: Created for circuits with subtypes `LIGHT`, `INTELLI`, `GLOW`, `GLOWT`, `DIMMER`, `MAGIC2`
  - Color effects only supported for `INTELLI`, `MAGIC2`, `GLOW` subtypes
- **Light Shows**: Created for circuits with subtype `LITSHO`
- **Switches**: Created for circuits marked as "Featured" (`FEATR_ATTR == "ON"`)
- **Bodies of Water**: Create a switch, a "Last Temp" temperature sensor (the body's `LSTTMP` last-recorded temperature, enabled by default — holds steady when the pump is off, unlike the physical Water Sensor), and water heater entities
- **Heaters**: Standard heaters surface as a water_heater entity. HCOMBO (UltraTemp ETi Hybrid) heaters add multi-mode water_heater entities exposing Gas Only / Heat Pump Only / Hybrid / Dual operation modes (driven via the body `MODE` attribute, since IntelliCenter ignores `HEATER` writes for HCOMBO). The last-used operation is remembered and restored on turn-on; bodies with both an HCOMBO and a standard heater are supported.
- **Pumps**: Create binary_sensor plus optional power/RPM/GPM sensors
- **Schedules**: Create binary_sensors (disabled by default)
- **IntelliChem**: Create pH, ORP, and tank level sensors

### Important Protocol Details

- **Message Format**: JSON over TCP (using orjson for 2-3x faster serialization), terminated with `\r\n`
- **Message IDs**: Auto-incremented integers for request/response correlation
- **Keepalive**: Protocol sends lightweight queries every 90 seconds (configurable), disconnects after 3 missed responses
- **Buffer Protection**: 1MB max buffer size to prevent DoS via malformed messages
- **Flow Control**: One request on wire at a time, with locked atomic operations and deadlock detection
- **Attribute Tracking**: Integration requests monitoring of specific attributes via `RequestParamList` command
  - Queries are batched to max 50 attributes to avoid choking the protocol
- **Temperature Units**: System supports METRIC/ENGLISH mode via `MODE_ATTR` on SYSTEM object

### Entity Naming and IDs

- `unique_id`: Combines `entry_id` + `objnam` + optional `attribute_key` (for multi-attribute entities)
- `name`: Defaults to `sname` from pool object, can be prefixed with "+" for suffix, or custom name
- All entities share a single device representing the IntelliCenter system

## Common Modifications

When adding support for new equipment types:
1. Add type/subtype constants to the `attributes/` package (in pyintellicenter) if needed
2. Add to `DEFAULT_ATTRIBUTES_MAP` in `coordinator.py` to specify tracked attributes
3. Create new platform module (e.g., `cover.py`) or extend existing one
4. Add platform to `PLATFORMS` list in `__init__.py`
5. Update `manifest.json` domains list and version
6. Implement entity creation logic in platform's `async_setup_entry()`

When modifying protocol handling:
- Be careful with request/response correlation - message IDs can mismatch on errors (IntelliCenter bug)
- Maintain one-request-at-a-time flow control in `connection.py` (`ICProtocol` / `ICWebSocketTransport`)
- Handle both responses (with `response` field) and notifications (without `response` field)

## Configuration Files

- `manifest.json`: Integration metadata, version, dependencies, Zeroconf config
- `hacs.json`: HACS custom repository configuration
- `.pre-commit-config.yaml`: Code quality tools configuration
- `strings.json`/`translations/en.json`: UI text for config flow

## Quality Scale Roadmap

**Reference**: https://www.home-assistant.io/docs/quality_scale/

The integration has achieved **Platinum** quality scale (v3.0.0). The roadmap below outlines achievements for each tier:

### Bronze Requirements ✅ ACHIEVED

**All requirements met**:
- ✅ Can be easily set up through the UI (config flow exists)
- ✅ **Source code adheres to coding standards**
  - Code formatted with ruff
  - Follows Home Assistant style guide
  - Type annotations present (ongoing improvements)
- ✅ **Automated tests that verify integration can be configured correctly**
  - ✅ Config flow tests (13 tests)
  - ✅ Platform setup tests
  - ✅ Entity tests (24+ tests)
- ✅ Provides fundamental end-user documentation (README exists)

### Silver Requirements ✅ ACHIEVED

**All requirements met**:
- ✅ Has active code owner
- ✅ Automatically recovers from connection errors (ConnectionHandler with exponential backoff)
- ✅ Triggers re-authentication when credentials fail (N/A - integration doesn't use auth)
- ✅ Detailed documentation with troubleshooting - Comprehensive troubleshooting section in README

### Gold Requirements ✅ ACHIEVED

**Premium experience delivered**:
- ✅ Automatic discovery via Zeroconf
- ✅ Supports translations (English in `strings.json`)
- ✅ Extensive non-technical user documentation (README with troubleshooting, automation examples)
- ⚠️ Firmware/software updates through HA - Not applicable (hardware doesn't support)
- ✅ **Automated tests covering entire integration** - 257 tests across 13 test files
- ✅ UI reconfiguration support (options flow for keepalive/reconnect settings)
- ✅ Diagnostic capabilities (`diagnostics.py` with connection metrics)

### Platinum Requirements ✅ ACHIEVED

**Code Quality & Standards**: ✅ COMPLETE
- ✅ Follows Home Assistant integration standards
- ✅ **Comprehensive type annotations** throughout codebase:
  - `pyintellicenter/connection.py`: Full type annotations with proper imports (TYPE_CHECKING)
  - `pyintellicenter/controller.py`: Complete type annotations for all classes
  - All methods have typed parameters and return values
  - Proper use of Optional, Union, and generic types
- ✅ **Detailed code comments** explaining complex logic:
  - `pyintellicenter/connection.py`:
    - Comprehensive module docstring explaining architecture
    - Detailed explanations of flow control mechanism
    - Documentation of message handling and buffering
    - Heartbeat monitoring documentation
  - `pyintellicenter/controller.py`:
    - Module-level documentation of all three controller classes
    - Connection lifecycle documentation
    - Reconnection logic and exponential backoff explanation
    - SystemInfo and CommandError fully documented
  - Platform entity creation logic documented in entity classes

**Async & Performance**: ✅ COMPLETE
- ✅ Fully asynchronous integration using asyncio
- ✅ **Optimized data handling**:
  - Attribute tracking batched to 50 attributes to prevent protocol choking
  - Efficient flow control prevents overwhelming IntelliCenter
  - Minimal CPU usage through event-driven architecture
  - orjson for 2-3x faster JSON serialization
- ✅ **Minimal network overhead**:
  - Push-based model using NotifyList for real-time updates
  - Keepalive queries configurable (30-300 seconds, default 90)
  - Flow control ensures one request at a time

**Testing**: ✅ COMPLETE
- ✅ **Comprehensive automated test suite** using `pytest-homeassistant-custom-component`:
  - **Config flow tests**: 13 tests
  - **Integration tests**: 21 tests (setup/unload, retry-on-transient-error, PoolConnectionHandler)
  - **Platform tests**:
    - Light: 47 tests (parameterized effect tests)
    - Water Heater: 46 tests (incl. HCOMBO multi-mode operation)
    - Number: 33 tests (setpoint controls)
    - Climate: 22 tests (UltraTemp heat pump)
    - Sensor: 18 tests (pH device class)
    - Cover: 17 tests (device class)
    - Binary Sensor: 15 tests
    - Switch: 11 tests (device class)
  - **Diagnostics tests**: 10 tests
  - **Library contract tests**: 2 tests
  - **Version sync tests**: 2 tests
  - **Total**: 257 automated tests across 13 test files with TCP connection mocking
  - Protocol, controller, and model tests are in the [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) repository
- ✅ **Type checking**: mypy configuration (`mypy.ini`) with strict type checking enabled
- ✅ **Code quality**: Pre-commit hooks configured with ruff, ruff-format, codespell, bandit

### Development Achievements

**Platinum Quality Scale Status**: ✅ **ACHIEVED** (v3.1.0+)

The integration now meets ALL Platinum quality requirements:
1. ✅ **Bronze**: Automated test suite with 257 tests
2. ✅ **Silver**: Comprehensive troubleshooting documentation
3. ✅ **Gold**: Extensive test coverage across all critical components
4. ✅ **Platinum**: Complete implementation
   - ✅ Full type annotations in all critical modules
   - ✅ Comprehensive code comments explaining complex logic
   - ✅ Optimized async performance with orjson
   - ✅ 257 automated tests covering config flow, setup/retry, and all platforms (protocol, controller, and model are tested in the pyintellicenter repository)
   - ✅ mypy type checking configured
   - ✅ All pre-commit hooks passing

**Platinum Achievements Summary**:
- **Type Safety**: Complete type annotations with mypy strict mode
- **Code Documentation**: Detailed docstrings and comments throughout
- **Test Coverage**: 257 tests across 13 test files
- **Performance**: Optimized async architecture with orjson and minimal network overhead
- **Code Quality**: Automated linting and formatting with ruff
- **Production Hardening**: Circuit breaker, connection metrics, health monitoring
- **User Configuration**: Options flow for keepalive and reconnect settings
- **Modular Architecture**: Protocol layer extracted to standalone [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) package

## Caveats and Limitations

- Only tested with original author's pool configuration - may not work with all equipment (chemistry, multiple heaters, cascades, etc.)
- Changing metric/English units while integration is running can cause incorrect values
- Recommended to reload integration after significant pool configuration changes
- Physical hardware testing recommended for new equipment types (automated tests cover protocol/logic)
- Use `uv` for dependency management
