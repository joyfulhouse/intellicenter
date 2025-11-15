# Pentair IntelliCenter for Home Assistant

[![hacs][hacsbadge]][hacs]
[![GitHub Release][releases-shield]][releases]
[![Quality Scale](https://img.shields.io/badge/quality_scale-bronze-cd7f32)](https://www.home-assistant.io/docs/quality_scale/)

Home Assistant integration for Pentair IntelliCenter pool control systems. Monitor and control your pool equipment directly from Home Assistant with real-time local push updates.

## Requirements

- Home Assistant 2023.1 or newer
- Pentair IntelliCenter controller (i5P, i7P, i9P, or i10P)
- Local network access to your IntelliCenter

## Installation

### Method 1: HACS (Recommended)

1. Install [HACS](https://hacs.xyz/docs/installation/manual) if you haven't already
2. Open HACS in Home Assistant
3. Click on "Integrations"
4. Click the three dots menu (⋮) in the top right
5. Select "Custom repositories"
6. Add repository URL: `https://github.com/dwradcliffe/intellicenter`
7. Select category: "Integration"
8. Click "Add"
9. Find "Pentair IntelliCenter" in HACS and click "Download"
10. Restart Home Assistant
11. Continue to [Configuration](#configuration)

### Method 2: Manual Installation

1. Download the [latest release](https://github.com/dwradcliffe/intellicenter/releases)
2. Extract the `custom_components/intellicenter` folder
3. Copy to your Home Assistant `config/custom_components/` directory
4. Restart Home Assistant
5. Continue to [Configuration](#configuration)

## Configuration

### Automatic Setup (Recommended)

Your IntelliCenter should be automatically discovered via Zeroconf:

1. Go to **Settings** → **Devices & Services**
2. Look for "Pentair IntelliCenter" under **Discovered**
3. Click **Configure**
4. Confirm the discovered device
5. Done! Your entities will appear automatically

### Manual Setup

If automatic discovery doesn't work:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Pentair IntelliCenter"
4. Enter your IntelliCenter's IP address
5. Click **Submit**

**Finding Your IP Address:**
- Check your router's DHCP client list
- Use the Pentair mobile app: Settings → System Information
- Check the IntelliCenter display panel

**Tip:** Assign a static IP or DHCP reservation to prevent IP address changes.

## Features

- **Local Push Updates**: Real-time updates with no polling delay
- **Automatic Discovery**: Zeroconf/mDNS discovery for easy setup
- **Reliable Connection**: Automatic reconnection if IntelliCenter reboots
- **No Cloud Required**: Direct local network connection
- **Security Independent**: Works regardless of IntelliCenter security settings

## Supported Entities

The integration automatically creates entities for all your pool equipment:

### Water Bodies (Pool/Spa)
- **Switch**: Turn pool/spa on and off
- **Sensors**: Current temperature and target temperature
- **Water Heater**: Control heater selection and temperature setpoint
  - Status: OFF, IDLE (enabled but not heating), or ON (actively heating)
  - Supports turn_on/turn_off operations

### Lights
- **Light Entity**: Individual lights and light shows
- **Color Effects**: Supported for IntelliBrite and MagicStream lights
- **Light Shows**: Coordinated multi-light effects

### Circuits & Features
- **Switches**: All circuits marked as "Featured" on IntelliCenter
  - Examples: Pool cleaner, spa blower, waterfalls, etc.

### Pumps
- **Binary Sensor**: Pump running status
- **Sensors**: Power consumption (W), speed (RPM), flow rate (GPM)
  - Power rounded to nearest 25W to reduce updates
  - RPM/GPM may fluctuate based on pump settings

### Chemistry (IntelliChem)
- **Sensors**: pH level, ORP level, pH tank level, ORP tank level

### Heaters
- **Binary Sensor**: Shows if heater is running (independent of which body)

### Schedules
- **Binary Sensor**: Indicates if schedule is currently active
  - *Note: Disabled by default*

### System
- **Switch**: Vacation mode control (*disabled by default*)
- **Binary Sensor**: Freeze prevention mode status
- **Sensors**: Water temperature, air temperature, solar sensor (if equipped)

## Troubleshooting

### Integration Not Discovered

If your IntelliCenter isn't automatically discovered:

1. **Check Network**: Ensure Home Assistant and IntelliCenter are on the same network
2. **Multicast Traffic**: Some networks block mDNS/Zeroconf traffic needed for discovery
3. **Use Manual Setup**: Add the integration manually using your IntelliCenter's IP address

### Connection Failed

If you see "Failed to connect" errors:

1. Verify the IP address is correct
2. Check your firewall isn't blocking the connection
3. Restart your IntelliCenter (power cycle)
4. Ensure your IntelliCenter firmware is up to date

### Entities Not Updating

If entities show "unavailable" or don't update:

1. Check Home Assistant logs for connection errors:
   - **Settings** → **System** → **Logs**
2. Reload the integration:
   - **Settings** → **Devices & Services** → **IntelliCenter** → ⋮ → **Reload**
3. Verify network connectivity between Home Assistant and IntelliCenter

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.intellicenter: debug
```

Then restart Home Assistant and check **Settings** → **System** → **Logs**.

## Automation Examples

### Turn on Spa at Sunset

```yaml
automation:
  - alias: "Evening Spa Relaxation"
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

### Pool Party Lighting

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

## Screenshots

<img src="device_info.png" width="400"/>

<img src="entities.png" width="400"/>

## Known Limitations

- **Equipment Coverage**: Tested primarily with standard configurations. Some equipment (covers, cascades, multiple heaters) may have limited testing.
- **Unit Changes**: Changing between metric/imperial while integration is running may cause temporary incorrect values. Reload the integration after unit changes.
- **Configuration Changes**: Reload the integration after making significant changes to your pool configuration on the IntelliCenter.

## Development & Contributing

See [VALIDATION.md](VALIDATION.md) for development setup and testing guidelines.

Contributions welcome! Please ensure all tests pass before submitting PRs:

```bash
make bronze  # Run all quality checks
```

## Support

- **Issues**: [GitHub Issues](https://github.com/dwradcliffe/intellicenter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/dwradcliffe/intellicenter/discussions)

[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange
[releases-shield]: https://img.shields.io/github/v/release/dwradcliffe/intellicenter
[releases]: https://github.com/dwradcliffe/intellicenter/releases
