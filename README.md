# Pentair IntelliCenter for Home Assistant

Control your Pentair IntelliCenter pool system directly from Home Assistant with real-time local updates.

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![HACS][hacs-shield]][hacs]
[![CI][ci-shield]][ci]
[![Quality Scale][quality-shield]][quality]
[![Project Maintenance][maintenance-shield]][maintenance]
[![GitHub Sponsors][sponsors-shield]][sponsors]
[![Ko-fi][kofi-shield]][kofi]

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

## What's New in v3.8.0

This release adds the per-body Last Temp sensor and hardens connection, cover, config-flow, and temperature-limit handling:

- **Body "Last Temp" Sensor**: Each body (Pool, Spa) now has a "Last Temp" sensor (e.g. *Pool Last Temp*) showing the IntelliCenter body's last recorded water temperature. Unlike the physical Water Sensor — whose probe sits in an above-ground pipe and reads colder when the pump is off — the Last Temp value holds the last circulating temperature, so it stays accurate while the pump is idle. Thanks to @sheyman1 for the request (#75).
- **Reliable Availability**: Connection up/down now updates every entity, so values can no longer go stale during an outage or stick as unavailable after a reconnect.
- **Pool Covers on Real Hardware**: External-instrument pool covers (`EXTINSTR`) are now created on actual systems (previously only appeared in tests).
- **Resilient Config Flow**: A discovered unit that fails to connect re-shows the picker with a clear error instead of a generic 500.
- **Panel-Aware Temperature Limits**: Water heater, climate, and the Max Temperature control share one set of unit-aware bounds (40-104 °F / 5-40 °C), fixing a spa minimum-temperature bug and METRIC-panel setpoints.

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

See **[INSTALL.md](INSTALL.md)** for the complete guide.

**Quick version (HACS):** add this repository as a custom repository in HACS,
install **Pentair IntelliCenter**, restart Home Assistant, then add the
integration from **Settings → Devices & Services**.

[![Open in HACS][hacs-repo-shield]][hacs-repo]

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
| **Pool/Spa** | Switch, Sensors, Water Heater | On/off, temperature, heater control (incl. HCOMBO hybrid modes) |
| **Lights** | Light | On/off, color effects (IntelliBrite, MagicStream) |
| **Light Shows** | Light | Coordinated multi-light effects |
| **Circuits** | Switch | All "Featured" circuits (cleaner, blower, etc.) |
| **Pumps** | Binary Sensor, Sensors | Running status, power (W), speed (RPM), flow (GPM) |
| **Chemistry** | Sensors, Number | pH, ORP, tank levels, setpoints (IntelliChem) |
| **Heat Pumps** | Climate | UltraTemp heating/cooling with presets |
| **Heaters** | Binary Sensor, Water Heater | Running status; HCOMBO (UltraTemp ETi Hybrid) Gas/Heat Pump/Hybrid/Dual modes |
| **Schedules** | Binary Sensor | Active status (disabled by default) |
| **System** | Switch, Binary Sensor, Sensors | Vacation mode, freeze protection, temperatures, System Mode (`auto`/`service`/`timeout`), "Not in Auto" problem indicator, firmware advisories (a Repairs warning is raised for firmware with documented issues, e.g. the pulled 2.x line) |
| **Covers** | Cover | Pool cover open/close control |

### Body (Pool/Spa) Last Temp Sensor

- **Last Temp** (`sensor`, one per body, e.g. "Pool Last Temp"): the body's last
  recorded water temperature (`LSTTMP`), enabled by default. Unlike the physical
  Water Sensor — whose probe sits in an above-ground pipe and reads colder when
  the pump is off — the Last Temp value latches the last circulating temperature,
  so it stays accurate while the pump is idle.

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

### Circulation Watchdog (Stuck Valve Detection)

Valve actuators (including the IntelliValve) have no feedback path to
IntelliCenter — the panel drives them blind over a 3-wire 24VAC interface, so
neither IntelliCenter nor this integration can report a valve's position or
mode directly. Notably, IntelliValves can come back up in SERVICE mode after a
power outage and stay there until the MODE button is physically pressed,
silently stopping proper circulation.

Circulation problems can still be detected indirectly through the pump's
hydraulic signature: for a variable-speed pump, power follows the affinity law
(watts ∝ RPM³) with a plumbing-specific constant. A valve stuck in the wrong
position changes the hydraulic curve, pushing power measurably off that line.

To calibrate, note your pump's steady-state watts at each scheduled RPM and
compute `watts / rpm³` (it should be nearly identical across speeds); use that
as the constant below (`5.6e-8` is one real-world example).

```yaml
automation:
  - alias: "Pool Circulation Watchdog"
    trigger:
      # Pump power off its normal curve for 20 min (tolerates transients)
      - platform: template
        value_template: >-
          {% set rpm = states('sensor.pump_rpm') | float(0) %}
          {% set power = states('sensor.pump_power') | float(0) %}
          {% set expected = 5.6e-8 * rpm**3 %}
          {{ rpm >= 1300 and expected > 0
             and (((power - expected) | abs) / expected) > 0.15 }}
        for: "00:20:00"
        id: hydraulic_anomaly
      # Panel left in service/timeout mode (e.g. after a power outage).
      # The integration also ships this as a built-in "Not in Auto" problem
      # binary sensor; trigger on that entity instead if you prefer.
      - platform: state
        entity_id: sensor.system_mode
        to:
          - service
          - timeout
        for: "00:30:00"
        id: panel_not_auto
      # IntelliCenter reconnected after being unreachable
      - platform: state
        entity_id: sensor.system_mode
        from: unavailable
        for: "00:03:00"
        id: reconnected
    action:
      - choose:
          - conditions:
              - condition: trigger
                id: hydraulic_anomaly
            sequence:
              - service: notify.mobile_app
                data:
                  title: "Pool: Possible Stuck Valve"
                  message: >-
                    Pump power has been off its normal curve for 20+ min:
                    {{ states('sensor.pump_power') }} W at
                    {{ states('sensor.pump_rpm') }} RPM. A valve may be stuck
                    in SERVICE mode — check the actuator MODE buttons.
          - conditions:
              - condition: trigger
                id: panel_not_auto
            sequence:
              - service: notify.mobile_app
                data:
                  title: "Pool: Panel Not in Auto"
                  message: >-
                    IntelliCenter has been in
                    '{{ states('sensor.system_mode') }}' mode for 30+ min.
                    Schedules and valves are not running automatically.
          - conditions:
              - condition: trigger
                id: reconnected
            sequence:
              - service: notify.mobile_app
                data:
                  title: "Pool: IntelliCenter Back Online"
                  message: >-
                    IntelliCenter reconnected after being unreachable — if this
                    was a power outage, verify the valve actuator LEDs show
                    AUTO (green), not SERVICE (yellow).
    mode: single
```

Notes:

- Entity names derive from your pool objects' names; substitute your own
  (e.g. `sensor.pump_rpm`/`sensor.pump_power` come from the pump's power/RPM
  sensors, `sensor.system_mode` from the System Mode sensor, whose states are
  exactly `auto`/`service`/`timeout`).
- The pump doesn't need a separate "running" check — `rpm >= 1300` already
  gates on it (an idle pump reports 0 RPM). The floor also keeps the check
  above the power sensor's 25 W rounding step, which at very low speeds
  (< ~120 W expected) would exceed the threshold on its own.
- IntelliFlo VS pumps report 0 GPM (no flow meter) — power-at-RPM is the
  usable signal. VSF/VF owners can additionally alert on abnormal GPM.
- The 15% threshold covers a real system's observed ±2% normal spread and
  ~11% worst-case steady-state excursions, plus headroom; start there and
  widen it if you get false alarms.
- Re-calibrate the constant after plumbing changes (new salt cell, filter,
  heater bypass, etc.).

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

## Support Development

This integration is built and maintained in my spare time, with real hardware and tooling costs behind every release. If it's useful to you, consider sponsoring the project or leaving a tip to help offset development and testing — it's genuinely appreciated and helps keep the project moving.

[![GitHub Sponsors][sponsors-shield]][sponsors] [![Ko-fi][kofi-shield]][kofi]

## License

GNU GENERAL PUBLIC LICENSE v3.0 - see [LICENSE](LICENSE) file for details.

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
- Comprehensive automated testing (366 tests)
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
[hacs-shield]: https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacs-repo-shield]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=joyfulhouse&repository=intellicenter&category=integration
[ci-shield]: https://img.shields.io/github/actions/workflow/status/joyfulhouse/intellicenter/ci.yml?branch=main&label=CI&style=for-the-badge
[ci]: https://github.com/joyfulhouse/intellicenter/actions/workflows/ci.yml
[quality-shield]: https://img.shields.io/badge/quality_scale-platinum-e5e4e2?style=for-the-badge
[quality]: https://www.home-assistant.io/docs/quality_scale/
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40btli-blue.svg?style=for-the-badge
[maintenance]: https://github.com/btli
[sponsors-shield]: https://img.shields.io/badge/Sponsor-GitHub-EA4AAA.svg?style=for-the-badge&logo=githubsponsors&logoColor=white
[sponsors]: https://github.com/sponsors/btli
[kofi-shield]: https://img.shields.io/badge/Ko--fi-support-FF5E5B.svg?style=for-the-badge&logo=ko-fi&logoColor=white
[kofi]: https://ko-fi.com/bryanli
