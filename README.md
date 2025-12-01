# Pentair IntelliCenter for Home Assistant

Control your Pentair IntelliCenter pool system directly from Home Assistant with real-time local updates.

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![HACS][hacsbadge]][hacs]
[![CI][ci-badge]][ci-workflow]
[![Quality Scale][quality-badge]][quality-scale]
[![Project Maintenance][maintenance-shield]][user_profile]

## What Does This Integration Do?

This integration connects your Pentair IntelliCenter pool control system to Home Assistant using a **100% local connection**. No cloud services, no internet dependency - just direct communication with your IntelliCenter over your local network.

- **Monitor Everything**: Pool/spa temperature, pump status, chemistry levels, heater activity
- **Control Your Pool**: Turn on lights, adjust heater setpoints, activate circuits, run light shows
- **Create Automations**: Schedule spa warmups, trigger party lighting, get freeze protection alerts
- **Real-time Updates**: Push-based notifications for instant state changes (no polling)

## Features

- **Local Connection**: Direct communication on port 6681 - no cloud required, no authentication needed
- **Flexible Transport**: Choose between TCP or WebSocket connections based on your network setup
- **Automatic Discovery**: Zeroconf/mDNS discovers your IntelliCenter automatically
- **Real-time Updates**: Push-based notifications for instant state changes
- **Reliable Connection**: Automatic reconnection with exponential backoff and circuit breaker
- **Highly Responsive**: Optimized async architecture with intelligent request queuing
- **Comprehensive Support**: Pools, spas, lights, pumps, heaters, chemistry, schedules, covers
- **Multi-Language**: User interface available in 12 languages
- **Easy Reconfiguration**: Change connection settings without removing the integration

## What's New in v3.5

This release brings significant performance and usability improvements:

- **Transport Selection**: Choose between TCP (default) or WebSocket connections during setup or reconfiguration - useful for networks where one protocol works better than the other
- **Reconfiguration Support**: Change your IntelliCenter's IP address or transport type through the UI without removing and re-adding the integration
- **Modernized Codebase**: Updated to use current asyncio patterns, removing all deprecated function calls for better compatibility with Python 3.13+
- **Request Queue Optimization**: Intelligent request queuing prevents overwhelming the IntelliCenter, resulting in faster and more reliable command execution
- **Improved Responsiveness**: Optimized async operations throughout the integration for snappier control response times
- **Protocol Library Extraction**: Core protocol handling extracted to standalone [pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) library for better maintainability

## Architecture

This integration is built on two separate packages:

| Package | Description |
|---------|-------------|
| **[pyintellicenter](https://github.com/joyfulhouse/pyintellicenter)** | Standalone Python library for IntelliCenter protocol ([PyPI](https://pypi.org/project/pyintellicenter/)) |
| **intellicenter** | Home Assistant integration (this repository) |

The protocol layer was extracted to `pyintellicenter` v0.1.0+ to enable:
- Independent development and testing of the protocol library
- Reuse in other projects outside Home Assistant
- Cleaner separation of concerns

## Prerequisites

Before installing this integration, you need:

| Requirement | Details |
|-------------|---------|
| **Home Assistant** | Version **2025.11** or newer |
| **IntelliCenter** | i5P, i7P, i9P, or i10P panel |
| **Network** | Local network access to IntelliCenter (TCP port 6681) |

## Installation

### HACS (Recommended)

1. Open HACS → Integrations
2. Search for "Pentair IntelliCenter"
3. Click Install
4. Restart Home Assistant

> **Note:** If you don't find the integration, you can add it as a custom repository:
> HACS → ⋮ → Custom repositories → Add `https://github.com/joyfulhouse/intellicenter` as Integration

### Manual Installation

```bash
cd /config/custom_components
git clone https://github.com/joyfulhouse/intellicenter.git intellicenter
```

Restart Home Assistant after installation.

## Configuration

### Automatic Discovery

Your IntelliCenter should be discovered automatically:

1. Navigate to **Settings** → **Devices & Services**
2. Look for "Pentair IntelliCenter" under **Discovered**
3. Click **Configure** and confirm

### Manual Setup

If discovery doesn't work:

1. Navigate to **Settings** → **Devices & Services**
2. Click **Add Integration** (bottom right)
3. Search for "Pentair IntelliCenter"
4. Enter your IntelliCenter's IP address
5. Select transport type (TCP recommended, WebSocket available as alternative)

**Finding your IP address:**
- Router's DHCP client list (look for "Pentair")
- Pentair mobile app: Settings → System Information
- IntelliCenter display panel

> **Tip:** Assign a static IP or DHCP reservation to prevent address changes.

### Reconfiguration

To change the IP address or transport type after setup:

1. Navigate to **Settings** → **Devices & Services**
2. Find the IntelliCenter integration
3. Click the three dots (⋮) → **Reconfigure**
4. Update the IP address and/or transport type
5. The integration will reconnect with the new settings

### Advanced Options

After setup, configure connection settings:

1. **Settings** → **Devices & Services** → **IntelliCenter** → **Configure**
2. Available options:
   - **Keepalive Interval** (30-300s, default 90): Connection health check frequency
   - **Reconnect Delay** (10-120s, default 30): Initial retry delay after disconnect

## Supported Equipment

| Category | Entity Type | Features |
|----------|-------------|----------|
| **Pool/Spa** | Switch, Sensors, Water Heater | On/off, temperature, heater control |
| **Lights** | Light | On/off, color effects (IntelliBrite, MagicStream) |
| **Light Shows** | Light | Coordinated multi-light effects |
| **Circuits** | Switch | All "Featured" circuits (cleaner, blower, etc.) |
| **Pumps** | Binary Sensor, Sensors | Running status, power (W), speed (RPM), flow (GPM) |
| **Chemistry** | Sensors, Number | pH, ORP, tank levels, setpoints (IntelliChem) |
| **Heaters** | Binary Sensor | Running status |
| **Schedules** | Binary Sensor | Active status (disabled by default) |
| **System** | Switch, Binary Sensor, Sensors | Vacation mode, freeze protection, temperatures |
| **Covers** | Cover | Pool cover open/close control |

## Automation Examples

### Evening Spa Warmup

```yaml
automation:
  - alias: "Evening Spa"
    trigger:
      - platform: sun
        event: sunset
        offset: "-00:30:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.spa
      - service: water_heater.set_temperature
        target:
          entity_id: water_heater.spa
        data:
          temperature: 102
```

### Pool Party Lights

```yaml
automation:
  - alias: "Pool Party Mode"
    trigger:
      - platform: state
        entity_id: input_boolean.party_mode
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.pool_light
        data:
          effect: "Party"
```

### Freeze Protection Alert

```yaml
automation:
  - alias: "Freeze Protection Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.freeze_protection
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Pool Alert"
          message: "Freeze protection activated!"
```

## Troubleshooting

### Integration Not Discovered

If your IntelliCenter is not automatically discovered:

1. **Verify network connectivity**
   - Home Assistant and IntelliCenter must be on the same network/VLAN
   - Check that mDNS/multicast traffic is not blocked by your router or firewall
   - Some managed switches block multicast by default

2. **Check IntelliCenter network settings**
   - Verify the IntelliCenter has a valid IP address
   - Ensure the network cable is securely connected
   - Check the IntelliCenter display for network status

3. **Use manual setup**
   - Go to **Settings** → **Devices & Services** → **Add Integration**
   - Search for "Pentair IntelliCenter"
   - Enter the IP address manually

### Connection Failed

If the integration fails to connect:

1. **Verify the IP address**
   - Confirm the IP address is correct in your router's DHCP client list
   - Check the Pentair mobile app under Settings → System Information

2. **Test network connectivity**
   ```bash
   telnet <intellicenter-ip> 6681
   ```
   - If connection fails, check firewall rules
   - Verify no other device is using port 6681

3. **Check IntelliCenter status**
   - Ensure the IntelliCenter is powered on
   - Verify the network cable is connected
   - Check for any error indicators on the panel

4. **Power cycle the IntelliCenter**
   - Turn off power to the IntelliCenter for 30 seconds
   - Turn power back on and wait for it to fully boot
   - Retry the connection

### Entities Unavailable

If entities show as unavailable after initial setup:

1. **Check connection status**
   - Go to **Settings** → **Devices & Services**
   - Look for the IntelliCenter integration status
   - A red indicator means the connection is down

2. **Review Home Assistant logs**
   - Go to **Settings** → **System** → **Logs**
   - Filter for "intellicenter" to see relevant messages
   - Look for connection errors or timeouts

3. **Reload the integration**
   - Go to **Settings** → **Devices & Services**
   - Click the three dots (⋮) next to IntelliCenter
   - Select **Reload**

4. **Automatic recovery**
   - The integration automatically reconnects with exponential backoff
   - Wait a few minutes for automatic recovery
   - Check the circuit breaker hasn't opened (5 consecutive failures)

### Incorrect Values or Missing Entities

1. **Reload after configuration changes**
   - After changing pool equipment in IntelliCenter, reload the integration
   - New equipment may not appear until reload

2. **Unit mismatch**
   - If you change metric/imperial units on IntelliCenter, reload the integration
   - Temperature values may be incorrect until reload

3. **Equipment not supported**
   - Some equipment types may have limited support
   - Check the Supported Equipment section above
   - Open an issue on GitHub for unsupported equipment

### Enable Debug Logging

For detailed troubleshooting, enable debug logging by adding to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.intellicenter: debug
    pyintellicenter: debug
```

After adding this configuration:
1. Restart Home Assistant
2. Reproduce the issue
3. Check logs at **Settings** → **System** → **Logs**
4. Download full logs for bug reports

### Getting Help

If you're still having issues:

1. **Check existing issues**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
2. **Open a new issue**: Include debug logs and your IntelliCenter model
3. **Community support**: [GitHub Discussions](https://github.com/joyfulhouse/intellicenter/discussions)

## Known Limitations

- **Equipment Coverage**: Tested primarily with standard configurations. Some equipment may have limited testing.
- **Unit Changes**: Reload integration after changing metric/imperial on IntelliCenter.
- **Configuration Changes**: Reload integration after significant pool configuration changes.

## Development

```bash
# Clone repositories
git clone https://github.com/joyfulhouse/intellicenter.git
git clone https://github.com/joyfulhouse/pyintellicenter.git

# Install dependencies
cd intellicenter
uv sync

# Install pyintellicenter in dev mode
uv pip install -e ../pyintellicenter

# Run tests
uv run pytest

# Lint and format
uv run ruff check --fix && uv run ruff format
```

See [docs/](docs/) for architecture documentation and development guidelines.

## Support

- **Bug Reports**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
- **Feature Requests**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/joyfulhouse/intellicenter/discussions)

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## Quality Tier: Platinum Certified

This integration meets the **Platinum tier** quality standards for Home Assistant integrations - the highest level achievable.

**Platinum Requirements:**
- Fully async architecture with optimized performance
- Comprehensive type annotations (mypy strict mode)
- Detailed code documentation throughout
- Production hardening with circuit breaker and health monitoring

**Gold Requirements:**
- Full translation support (12 languages)
- Easy reconfiguration through the UI
- Comprehensive automated testing (175+ tests)
- Extensive user-friendly documentation
- Automatic Zeroconf discovery

Plus all Silver and Bronze tier requirements met.

## Credits

This integration builds upon the excellent work of:

- **[@jlvaillant](https://github.com/jlvaillant)** - [Original intellicenter integration](https://github.com/jlvaillant/intellicenter) that pioneered Home Assistant support for Pentair IntelliCenter
- **[@dwradcliffe](https://github.com/dwradcliffe)** - [Enhanced fork](https://github.com/dwradcliffe/intellicenter) with connection fixes and improvements

We extend our sincere gratitude for their foundational work that made this integration possible.

---

[releases-shield]: https://img.shields.io/github/v/release/joyfulhouse/intellicenter?style=for-the-badge
[releases]: https://github.com/joyfulhouse/intellicenter/releases
[license-shield]: https://img.shields.io/github/license/joyfulhouse/intellicenter?style=for-the-badge
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge
[ci-badge]: https://img.shields.io/github/actions/workflow/status/joyfulhouse/intellicenter/ci.yml?branch=main&label=CI&style=for-the-badge
[ci-workflow]: https://github.com/joyfulhouse/intellicenter/actions/workflows/ci.yml
[quality-badge]: https://img.shields.io/badge/quality_scale-platinum-e5e4e2?style=for-the-badge
[quality-scale]: https://www.home-assistant.io/docs/quality_scale/
[maintenance-shield]: https://img.shields.io/badge/maintainer-joyfulhouse-blue.svg?style=for-the-badge
[user_profile]: https://github.com/joyfulhouse
