# IntelliCenter Developer Documentation

Technical documentation for developers working on the Pentair IntelliCenter Home Assistant integration.

| Metric | Value |
|--------|-------|
| **Current Version** | 3.7.0 |
| **Quality Scale** | Platinum |
| **Test Coverage** | 217 tests |
| **Home Assistant** | 2025.11+ required |
| **pyintellicenter** | 0.1.15+ required |

## Documentation Index

| Document | Description |
|----------|-------------|
| [CHANGELOG.md](./CHANGELOG.md) | Version history and release notes |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Technical architecture and design |
| [QUALITY_SCALE_COMPLIANCE.md](./QUALITY_SCALE_COMPLIANCE.md) | Home Assistant quality scale compliance |

## Project Structure

```
intellicenter/
├── custom_components/intellicenter/
│   ├── __init__.py          # Entry point, PoolEntity base class
│   ├── config_flow.py       # UI configuration flow
│   ├── coordinator.py       # Connection coordination
│   ├── diagnostics.py       # Diagnostic data export
│   ├── const.py             # Constants
│   ├── manifest.json        # Integration metadata
│   ├── strings.json         # English strings (source)
│   ├── translations/        # 12 language translations
│   └── Platforms:
│       ├── light.py         # Pool/spa lights
│       ├── switch.py        # Circuits, bodies
│       ├── sensor.py        # Temperature, chemistry
│       ├── binary_sensor.py # Pumps, schedules
│       ├── water_heater.py  # Heater control
│       ├── climate.py       # UltraTemp heat pump
│       ├── number.py        # Setpoints
│       └── cover.py         # Pool covers
├── tests/                   # 216 automated tests
├── docs/                    # This documentation
└── README.md                # User guide
```

## Related Projects

| Project | Repository | Description |
|---------|------------|-------------|
| **intellicenter** | [joyfulhouse/intellicenter](https://github.com/joyfulhouse/intellicenter) | Home Assistant integration (this repo) |
| **pyintellicenter** | [joyfulhouse/pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) | Protocol library ([PyPI](https://pypi.org/project/pyintellicenter/)) |

### Package Separation

As of v3.5.0, the protocol layer has been extracted to a standalone package:

- **pyintellicenter** handles all TCP communication, protocol parsing, and state management
- **intellicenter** focuses on Home Assistant entity creation and integration

This separation enables:
- Independent versioning and releases
- Reuse of the protocol library in non-HA projects
- Cleaner testing and development workflows

## Development Setup

### Prerequisites

- Python 3.12+
- uv package manager
- Home Assistant dev environment (for testing)

### Quick Start

```bash
# Clone repositories
git clone https://github.com/joyfulhouse/intellicenter.git
git clone https://github.com/joyfulhouse/pyintellicenter.git

# Install dependencies
cd intellicenter
uv sync

# Install pyintellicenter in dev mode (for local changes)
uv pip install -e ../pyintellicenter

# Run tests
uv run pytest

# Lint and format
uv run ruff check --fix && uv run ruff format

# Type checking
uv run mypy custom_components/intellicenter/ --ignore-missing-imports
```

### Testing

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=custom_components/intellicenter --cov-report=html

# Specific test file
uv run pytest tests/test_config_flow.py -v

# Run with verbose output
uv run pytest -v
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Home Assistant                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           intellicenter integration              │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐           │   │
│  │  │ light   │ │ switch  │ │ sensor  │  ...      │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘           │   │
│  │       └───────────┼───────────┘                 │   │
│  │                   │                             │   │
│  │  ┌────────────────┴──────────────────────┐     │   │
│  │  │     PoolEntity + Coordinator           │     │   │
│  │  └────────────────┬──────────────────────┘     │   │
│  └───────────────────┼─────────────────────────────┘   │
│                      │                                  │
│  ┌───────────────────┼─────────────────────────────┐   │
│  │              pyintellicenter                     │   │
│  │  ICProtocol → Controllers → PoolModel           │   │
│  └───────────────────┼─────────────────────────────┘   │
└──────────────────────┼──────────────────────────────────┘
                       │
              TCP/6681 (local)
                       │
            ┌──────────┴──────────┐
            │  Pentair            │
            │  IntelliCenter      │
            └─────────────────────┘
```

### Key Components

**Home Assistant Layer (`intellicenter`):**
- Platform modules create entities based on pool equipment
- `PoolEntity` base class provides common functionality
- `IntelliCenterCoordinator` manages connection lifecycle
- Config flow handles setup, discovery, and options

**Protocol Layer (`pyintellicenter`):**
- `ICProtocol` handles TCP transport and message framing
- `ModelController` manages state and attribute tracking
- `PoolModel` represents pool equipment as objects
- `ConnectionHandler` implements reconnection logic

### Data Flow

1. IntelliCenter sends `NotifyList` messages when equipment changes
2. `ModelController` updates the `PoolModel` state
3. Dispatcher signals notify Home Assistant entities
4. Entities call `async_write_ha_state()` to update HA

## Publishing Updates

### Updating pyintellicenter

When changes are made to the protocol library:

1. Bump version in `pyintellicenter/pyproject.toml`
2. Commit and push changes
3. Create a GitHub release to trigger PyPI publish:
   ```bash
   cd ../pyintellicenter
   gh release create v0.1.X --title "v0.1.X" --notes "Release notes"
   ```
4. Update requirement in `intellicenter/manifest.json`

### Releasing intellicenter

1. Update version in `manifest.json`
2. Update `CHANGELOG.md`
3. Create PR and merge to main
4. Create GitHub release

## Support

- **Issues**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/joyfulhouse/intellicenter/discussions)
