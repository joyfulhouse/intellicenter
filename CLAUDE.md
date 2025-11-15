# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Guidelines

**IMPORTANT**: This repository is `joyfulhouse/intellicenter`. It was forked from upstream repositories, but we maintain our own independent development.

**NEVER submit pull requests to**:
- `https://github.com/dwradcliffe/intellicenter`
- `https://github.com/jlvaillant/intellicenter`

All development, pull requests, and collaboration should happen within the `joyfulhouse/intellicenter` repository only.

## Project Overview

This is a Home Assistant custom integration for Pentair IntelliCenter pool control systems. It connects to IntelliCenter via local network (not cloud) using a custom TCP protocol on port 6681, supporting Zeroconf discovery and local push updates for real-time responsiveness.

**Current Quality Scale**: Not yet Bronze (despite `manifest.json` claiming Gold)
**Target Quality Scale**: Platinum

The integration does not yet meet Bronze quality scale requirements due to missing automated tests. We will work towards Bronze first, then Silver, Gold, and ultimately Platinum quality over upcoming iterations. See the Quality Scale Roadmap section below for current gaps and planned improvements.

## Development Commands

### Code Quality
```bash
# Run all pre-commit hooks (includes black, flake8, isort, bandit, codespell, yamllint)
pre-commit run --all-files

# Auto-format code with black
black custom_components/intellicenter/

# Sort imports with isort
isort custom_components/intellicenter/

# Run linting with flake8
flake8 custom_components/intellicenter/
```

### Testing

**Framework**: This project uses `pytest-homeassistant-custom-component` for automated testing.

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=custom_components/intellicenter --cov-report=html

# Run specific test file
pytest tests/test_config_flow.py

# Run tests with verbose output
pytest -v
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
   - Platform modules: `light.py`, `sensor.py`, `switch.py`, `binary_sensor.py`, `water_heater.py`, `number.py`, `cover.py`
   - Entry point: `__init__.py` - Sets up integration, manages entity lifecycle
   - Config flow: `config_flow.py` - Handles UI setup and Zeroconf discovery
   - Base entity: `PoolEntity` class in `__init__.py` - Common functionality for all entities

2. **Protocol/Model Layer** (`pyintellicenter/`)
   - `controller.py` - Three controller classes:
     - `BaseController`: Basic TCP connection and command handling
     - `ModelController`: Manages PoolModel state and tracks attribute changes
     - `ConnectionHandler`: Reconnection logic with exponential backoff
   - `protocol.py` - `ICProtocol`: Low-level asyncio protocol, handles JSON message framing, request queuing (one-at-a-time), and heartbeat pings
   - `model.py` - `PoolModel` and `PoolObject`: Object model representing pool equipment
   - `attributes.py` - Attribute definitions and type mappings

### Key Architectural Patterns

**Connection Management**: The integration uses a layered approach to handle unreliable network connections:
- `ICProtocol` handles transport-level concerns (message framing, flow control)
- `ModelController` manages state synchronization
- `ConnectionHandler` implements automatic reconnection with exponential backoff starting at 30s

**State Updates**: Real-time updates flow through the system via:
1. IntelliCenter sends `NotifyList` messages when equipment state changes
2. `ModelController.receivedNotifyList()` updates the `PoolModel`
3. Dispatcher signals (`DOMAIN_UPDATE_{entry_id}`) notify Home Assistant entities
4. Entities call `async_write_ha_state()` to update HA

**Request Flow Control**: IntelliCenter struggles with concurrent requests, so `ICProtocol` enforces one request on the wire at a time using `_out_pending` counter and `_out_queue`.

### Entity Creation Logic

Entities are created based on equipment characteristics in the pool model:

- **Lights**: Created for circuits with subtypes `LIGHT`, `INTELLI`, `GLOW`, `GLOWT`, `DIMMER`, `MAGIC2`
  - Color effects only supported for `INTELLI`, `MAGIC2`, `GLOW` subtypes
- **Light Shows**: Created for circuits with subtype `LITSHO`
- **Switches**: Created for circuits marked as "Featured" (`FEATR_ATTR == "ON"`)
- **Bodies of Water**: Create switch, temperature sensors, and water heater entities
- **Pumps**: Create binary_sensor plus optional power/RPM/GPM sensors
- **Schedules**: Create binary_sensors (disabled by default)
- **IntelliChem**: Create pH, ORP, and tank level sensors

### Important Protocol Details

- **Message Format**: JSON over TCP, terminated with `\r\n`
- **Message IDs**: Auto-incremented integers for request/response correlation
- **Heartbeat**: Protocol sends "ping" every 10s, expects "pong" response, closes connection after 2 missed pongs
- **Attribute Tracking**: Integration requests monitoring of specific attributes via `RequestParamList` command
  - Queries are batched to max 50 attributes to avoid choking the protocol
- **Temperature Units**: System supports METRIC/ENGLISH mode via `MODE_ATTR` on SYSTEM object

### Entity Naming and IDs

- `unique_id`: Combines `entry_id` + `objnam` + optional `attribute_key` (for multi-attribute entities)
- `name`: Defaults to `sname` from pool object, can be prefixed with "+" for suffix, or custom name
- All entities share a single device representing the IntelliCenter system

## Common Modifications

When adding support for new equipment types:
1. Add type/subtype constants to `attributes.py` if needed
2. Add to `attributes_map` in `__init__.py:async_setup_entry()` to specify tracked attributes
3. Create new platform module (e.g., `cover.py`) or extend existing one
4. Add platform to `PLATFORMS` list in `__init__.py`
5. Update `manifest.json` domains list and version
6. Implement entity creation logic in platform's `async_setup_entry()`

When modifying protocol handling:
- Be careful with request/response correlation - message IDs can mismatch on errors (IntelliCenter bug)
- Maintain one-request-at-a-time flow control in `ICProtocol`
- Handle both responses (with `response` field) and notifications (without `response` field)

## Configuration Files

- `manifest.json`: Integration metadata, version, dependencies, Zeroconf config
- `hacs.json`: HACS custom repository configuration
- `.pre-commit-config.yaml`: Code quality tools configuration
- `strings.json`/`translations/en.json`: UI text for config flow

## Quality Scale Roadmap

**Reference**: https://www.home-assistant.io/docs/quality_scale/

The integration is currently **below Bronze** quality scale. The roadmap below outlines requirements for each tier:

### Bronze Requirements (Current Priority)

**Must achieve these first**:
- ✅ Can be easily set up through the UI (config flow exists)
- ⚠️ **Source code adheres to coding standards** - Partially met, needs improvement:
  - Complete type annotations throughout codebase
  - Ensure all code follows Home Assistant style guide
- ❌ **Automated tests that verify integration can be configured correctly** - NOT MET
  - Need config flow tests
  - Need platform setup tests
  - Need basic entity tests
- ✅ Provides fundamental end-user documentation (README exists)

### Silver Requirements (After Bronze)

**Builds on Bronze**:
- ✅ Has active code owner
- ✅ Automatically recovers from connection errors (ConnectionHandler with exponential backoff)
- ⚠️ Triggers re-authentication when credentials fail - May need review (integration doesn't use auth currently)
- ⚠️ Detailed documentation with troubleshooting - Needs expansion

### Gold Requirements (After Silver)

**Premium experience**:
- ✅ Automatic discovery via Zeroconf
- ✅ Supports translations (English in `strings.json`)
- ⚠️ Extensive non-technical user documentation - Needs improvement
- ❌ Firmware/software updates through HA - Not applicable (hardware doesn't support)
- ❌ **Automated tests covering entire integration** - NOT MET
- ✅ UI reconfiguration support
- ✅ Diagnostic capabilities (`diagnostics.py`)

### Platinum Requirements (Target)

**Code Quality & Standards**:
- ✅ Follows Home Assistant integration standards (mostly complete)
- ⚠️ **Add comprehensive type annotations** throughout codebase (partially complete - see `__init__.py` and platform files)
- ⚠️ **Add detailed code comments** explaining complex logic, especially in:
  - `pyintellicenter/protocol.py`: Flow control and message handling
  - `pyintellicenter/controller.py`: Connection lifecycle and state management
  - Platform entity creation logic

**Async & Performance**:
- ✅ Fully asynchronous integration using asyncio
- ⚠️ **Optimize data handling**: Review attribute tracking batching (currently 50 attr limit) for efficiency
- ⚠️ **Reduce polling/network overhead**: Already uses push model, but validate minimal CPU usage

**Testing**:
- ❌ **Implement comprehensive automated tests** using `pytest-homeassistant-custom-component`:
  - Config flow tests (user setup, Zeroconf discovery, error handling)
  - Platform tests for all entity types (light, switch, sensor, water_heater, etc.)
  - Protocol tests (message parsing, connection handling, reconnection logic)
  - Model tests (PoolObject, PoolModel state updates)
  - Integration tests (end-to-end entity creation and updates)
  - Mock the TCP connection for repeatable tests

### Critical Gaps Blocking Bronze

The integration is currently **below Bronze** due to:
- ❌ **Missing automated tests** - CRITICAL BLOCKER for Bronze
  - No config flow tests
  - No platform tests
  - No entity tests
  - No protocol/model tests
- ⚠️ **Incomplete type annotations** - Needed for coding standards compliance
  - `pyintellicenter/` modules lack comprehensive typing
  - Some platform files missing type hints

**Development Priority Order**:
1. **Achieve Bronze**: Add automated test suite (config flow, platforms, basic entity tests)
2. **Achieve Bronze**: Complete type annotations and ensure code standards compliance
3. **Achieve Silver**: Enhance documentation with troubleshooting section
4. **Achieve Gold**: Expand test coverage to entire integration
5. **Achieve Platinum**: Add detailed code comments, optimize performance, full async compliance

## Caveats and Limitations

- Only tested with original author's pool configuration - may not work with all equipment (chemistry, multiple heaters, cascades, etc.)
- Changing metric/English units while integration is running can cause incorrect values
- Recommended to reload integration after significant pool configuration changes
- Limited automated test coverage - requires physical hardware for full validation