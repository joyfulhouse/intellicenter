# Architecture

This document describes the technical architecture of the Pentair IntelliCenter integration for Home Assistant.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Package Structure](#package-structure)
- [Protocol Layer](#protocol-layer)
- [Controller Layer](#controller-layer)
- [Home Assistant Layer](#home-assistant-layer)
- [Entity Mapping](#entity-mapping)
- [Connection Management](#connection-management)
- [Data Flow](#data-flow)
- [Testing Architecture](#testing-architecture)

---

## Overview

The integration consists of two main packages:

| Package | Repository | Description |
|---------|------------|-------------|
| **pyintellicenter** | [joyfulhouse/pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) | Standalone Python library for IntelliCenter protocol |
| **intellicenter** | [joyfulhouse/intellicenter](https://github.com/joyfulhouse/intellicenter) | Home Assistant custom integration |

This separation enables:
- **Reusability**: The protocol library can be used in any Python project
- **Testability**: Protocol and HA logic can be tested independently
- **Maintainability**: Clear separation of concerns

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Home Assistant                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              intellicenter integration                    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │  light  │ │ switch  │ │ sensor  │ │  water  │  ...  │   │
│  │  │ .py     │ │ .py     │ │ .py     │ │ heater  │       │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │   │
│  │       │           │           │           │             │   │
│  │       └───────────┴───────────┴───────────┘             │   │
│  │                        │                                 │   │
│  │  ┌─────────────────────▼─────────────────────────────┐  │   │
│  │  │           PoolEntity (base class)                  │  │   │
│  │  │     Coordinator + Connection Handler               │  │   │
│  │  └─────────────────────┬─────────────────────────────┘  │   │
│  └────────────────────────┼─────────────────────────────────┘   │
│                           │                                      │
├───────────────────────────┼──────────────────────────────────────┤
│                           │                                      │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │                   pyintellicenter                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │  ICProtocol │  │ Controllers │  │   PoolModel     │   │   │
│  │  │  (asyncio)  │  │ Base/Model/ │  │   PoolObject    │   │   │
│  │  │             │  │ Connection  │  │                 │   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │   │
│  │         │                │                   │            │   │
│  │         └────────────────┼───────────────────┘            │   │
│  │                          │                                │   │
│  └──────────────────────────┼────────────────────────────────┘   │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                    TCP/6681 or WS/6680
                              │
                   ┌──────────▼──────────┐
                   │  Pentair            │
                   │  IntelliCenter      │
                   │  (i5P/i7P/i9P/i10P) │
                   └─────────────────────┘
```

---

## Package Structure

### pyintellicenter (Protocol Library)

```
pyintellicenter/
├── __init__.py          # Public API exports
├── protocol.py          # ICProtocol - asyncio transport protocol
├── controller.py        # Controller classes
│   ├── ICBaseController     # Basic TCP connection
│   ├── ICModelController    # State management
│   └── ICConnectionHandler  # Reconnection logic
├── model.py             # Data model
│   ├── PoolModel            # Collection of pool objects
│   └── PoolObject           # Individual equipment
├── attributes.py        # Attribute constants & types
└── discovery.py         # Zeroconf discovery
```

### intellicenter (HA Integration)

```
custom_components/intellicenter/
├── __init__.py          # Entry point, setup, PoolEntity base
├── config_flow.py       # UI configuration flow
├── coordinator.py       # PoolConnectionHandler
├── const.py             # Constants
├── diagnostics.py       # Diagnostic data export
├── strings.json         # English strings (source)
├── translations/        # Localized strings (12 languages)
│   ├── en.json
│   ├── es.json
│   ├── fr.json
│   └── ...
└── Platform modules:
    ├── light.py         # Pool/spa lights
    ├── switch.py        # Circuits, bodies
    ├── sensor.py        # Temperatures, chemistry
    ├── binary_sensor.py # Pumps, schedules
    ├── water_heater.py  # Heater control
    ├── number.py        # Setpoints
    └── cover.py         # Pool covers
```

---

## Protocol Layer

### ICProtocol

The `ICProtocol` class implements Python's `asyncio.Protocol` for TCP communication with IntelliCenter.

```python
class ICProtocol(asyncio.Protocol):
    """Low-level IntelliCenter protocol handler."""

    # Message framing
    TERMINATOR = b"\r\n"
    MAX_BUFFER = 1024 * 1024  # 1MB protection

    # Flow control - one request at a time
    _out_pending: int = 0
    _out_queue: asyncio.Queue
```

**Key Features**:

1. **Message Framing**: JSON messages terminated with `\r\n`
2. **Flow Control**: One request on wire at a time (IntelliCenter limitation)
3. **Request Correlation**: Message IDs for request/response matching
4. **Keepalive**: Configurable interval (default 90s) using lightweight queries
5. **Buffer Protection**: 1MB max to prevent DoS

**Message Format**:

```json
// Request
{"command": "RequestParamList", "objectList": [...], "messageID": "42"}

// Response
{"command": "RequestParamList", "response": "200", "objectList": [...], "messageID": "42"}

// Notification (no messageID, no response)
{"command": "NotifyList", "objectList": [...]}
```

### Flow Control

IntelliCenter cannot handle concurrent requests. The protocol enforces serialization:

```python
async def _send_request(self, message: dict) -> dict:
    """Send request with flow control."""
    async with self._request_lock:
        self._out_pending += 1
        try:
            self._send_message(message)
            return await self._wait_for_response(message["messageID"])
        finally:
            self._out_pending -= 1
```

---

## Controller Layer

### ICBaseController

Manages TCP connection lifecycle:

```python
class ICBaseController:
    """Basic IntelliCenter connection."""

    async def start(self) -> None:
        """Connect and get system info."""

    async def stop(self) -> None:
        """Disconnect cleanly."""

    async def send_request(self, request: dict) -> dict:
        """Send request and wait for response."""
```

### ICModelController

Extends base with state management:

```python
class ICModelController(ICBaseController):
    """Controller with pool model state tracking."""

    model: PoolModel  # Current equipment state

    def receivedNotifyList(self, objects: list) -> set[str]:
        """Process state update, return changed object IDs."""
```

### ICConnectionHandler

Implements reconnection with exponential backoff:

```python
class ICConnectionHandler:
    """Automatic reconnection handler."""

    # Backoff parameters
    initial_delay: float = 30.0
    max_delay: float = 300.0
    backoff_factor: float = 1.5

    # Circuit breaker
    failure_threshold: int = 5
    circuit_open_duration: float = 60.0
```

**Reconnection Sequence**:

```
Connection Lost
    │
    ▼
Wait initial_delay (30s)
    │
    ▼
Attempt reconnect ──────► Success ──► Resume normal operation
    │
    │ Failure
    ▼
Wait delay * 1.5 (45s)
    │
    ▼
Attempt reconnect ──────► Success ──► Resume
    │
    │ Failure (5th time)
    ▼
Circuit breaker opens
    │
    ▼
Wait 60s before retry
```

---

## Home Assistant Layer

### PoolEntity (Base Class)

All entities inherit from `PoolEntity`:

```python
class PoolEntity(Entity):
    """Base class for IntelliCenter entities."""

    _attr_has_entity_name = True
    _poolObject: PoolObject

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._handler.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DOMAIN_UPDATE, self._update_callback)
        )
```

### PoolConnectionHandler

Bridges pyintellicenter to Home Assistant:

```python
class PoolConnectionHandler:
    """Manages IntelliCenter connection for HA."""

    @property
    def connected(self) -> bool:
        """Return connection status."""

    async def request_changes(self, objnam: str, params: dict) -> None:
        """Request parameter changes on equipment."""

    def _on_notify(self, changed_ids: set[str]) -> None:
        """Handle state updates, dispatch to entities."""
        async_dispatcher_send(self.hass, DOMAIN_UPDATE, changed_ids)
```

---

## Entity Mapping

Equipment types map to Home Assistant entity platforms:

| IntelliCenter Type | Subtype | HA Platform | Entity Class |
|-------------------|---------|-------------|--------------|
| CIRCUIT | LIGHT, INTELLI, GLOW, MAGIC2 | light | PoolLight |
| CIRCUIT | LITSHO | light | LightShowLight |
| CIRCUIT | (featured) | switch | CircuitSwitch |
| BODY | - | switch, sensor, water_heater | Body entities |
| PUMP | - | binary_sensor, sensor | PumpSensor |
| CHEM | - | sensor, number | Chemistry entities |
| SENSE | - | sensor | TemperatureSensor |
| SCHED | - | binary_sensor | ScheduleSensor |
| COVER | - | cover | PoolCover |

### Entity Creation Logic

```python
# light.py - simplified
async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for obj in handler.model.objectList.values():
        if obj.objtype == "CIRCUIT":
            subtype = obj["SUBTYPE"]
            if subtype in LIGHT_SUBTYPES:
                entities.append(PoolLight(handler, obj))
            elif subtype == "LITSHO":
                entities.append(LightShowLight(handler, obj))

    async_add_entities(entities)
```

---

## Connection Management

### Lifecycle

```
User adds integration
         │
         ▼
    config_flow.py
    ├── Discover via Zeroconf OR
    └── Manual IP entry
         │
         ▼
    Validate connection (ICBaseController.start())
         │
         ▼
    Create config entry
         │
         ▼
    __init__.py::async_setup_entry()
    ├── Create PoolConnectionHandler
    ├── Start ICConnectionHandler
    └── Setup platforms
         │
         ▼
    Platforms create entities
         │
         ▼
    Normal operation
    ├── Push updates via NotifyList
    ├── User commands via RequestChanges
    └── Keepalive queries
```

### Connection States

```
     ┌──────────────┐
     │ Disconnected │◄────────────────┐
     └──────┬───────┘                 │
            │                          │
            │ start()                  │ connection_lost()
            ▼                          │
     ┌──────────────┐                 │
     │  Connecting  │─────────────────┤
     └──────┬───────┘                 │
            │                          │
            │ connection_made()        │
            ▼                          │
     ┌──────────────┐                 │
     │  Connected   │─────────────────┘
     └──────────────┘
```

---

## Data Flow

### State Updates (Push)

```
IntelliCenter                    Integration                    Home Assistant
     │                               │                               │
     │  NotifyList (JSON/TCP)        │                               │
     │──────────────────────────────►│                               │
     │                               │                               │
     │                    PoolModel.update()                         │
     │                               │                               │
     │                    dispatcher_send(DOMAIN_UPDATE)             │
     │                               │──────────────────────────────►│
     │                               │                               │
     │                               │              entity._update_callback()
     │                               │                               │
     │                               │              async_write_ha_state()
     │                               │                               │
```

### Commands (Request/Response)

```
Home Assistant                   Integration                    IntelliCenter
     │                               │                               │
     │  service call                 │                               │
     │──────────────────────────────►│                               │
     │                               │                               │
     │              handler.request_changes()                        │
     │                               │                               │
     │                               │  SetParamList (JSON/TCP)      │
     │                               │──────────────────────────────►│
     │                               │                               │
     │                               │  Response (200)               │
     │                               │◄──────────────────────────────│
     │                               │                               │
     │                               │  NotifyList (state update)    │
     │                               │◄──────────────────────────────│
     │                               │                               │
```

---

## Testing Architecture

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_config_flow.py      # Config flow tests (13)
├── test_init.py             # Integration lifecycle (12)
├── test_light.py            # Light platform (14)
├── test_switch.py           # Switch platform (11)
├── test_sensor.py           # Sensor platform (18)
├── test_binary_sensor.py    # Binary sensor (15)
├── test_water_heater.py     # Water heater (19)
├── test_cover.py            # Cover platform (17)
├── test_number.py           # Number platform (14)
└── test_diagnostics.py      # Diagnostics (9)

# pyintellicenter tests (separate repo)
├── test_protocol.py         # Protocol tests (24)
├── test_controller.py       # Controller tests (33)
└── test_model.py            # Model tests (24)
```

### Testing Patterns

**Mocking the Protocol**:

```python
@pytest.fixture
def mock_controller():
    """Create mock controller with test data."""
    controller = MagicMock(spec=ICModelController)
    controller.model = create_test_model()
    controller.system_info = ICSystemInfo(...)
    return controller
```

**Testing Entity State**:

```python
async def test_light_turn_on(hass, mock_handler):
    """Test turning on a pool light."""
    await setup_integration(hass, mock_handler)

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.pool_light"},
        blocking=True,
    )

    mock_handler.request_changes.assert_called_once_with("C0001", {"STATUS": "ON"})
```

---

## Performance Considerations

### orjson

The protocol layer uses orjson for JSON handling:

```python
import orjson

# 2-3x faster than stdlib json
data = orjson.loads(raw_bytes)
message = orjson.dumps(request)
```

### Attribute Batching

Attribute tracking requests are batched to avoid overwhelming IntelliCenter:

```python
MAX_ATTRS_PER_REQUEST = 50

for batch in chunked(attributes, MAX_ATTRS_PER_REQUEST):
    await controller.send_request({"command": "RequestParamList", "objectList": batch})
```

### Efficient State Updates

Only changed objects trigger entity updates:

```python
def _on_notify(self, changed_ids: set[str]) -> None:
    """Dispatch only for changed objects."""
    for entity in self._entities:
        if entity._poolObject.objnam in changed_ids:
            entity.async_write_ha_state()
```

---

## Security

### Local-Only Communication

- No cloud connectivity required
- Direct TCP/WebSocket to IntelliCenter on local network
- No authentication (IntelliCenter local protocol doesn't require it)
- Firewall recommended between pool equipment and internet

### Input Validation

All user inputs validated:

```python
def _validate_host(host: str) -> str:
    """Validate IP address or hostname."""
    host = host.strip()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if " " in host or not host:
            raise InvalidHost(f"Invalid host: {host}")
    return host
```

---

*Last updated: 2025-11-27*
