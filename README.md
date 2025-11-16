# Pentair IntelliCenter for Home Assistant

[![hacs][hacsbadge]][hacs]
[![GitHub Release][releases-shield]][releases]
[![Quality Scale](https://img.shields.io/badge/quality_scale-silver-c0c0c0)](https://www.home-assistant.io/docs/quality_scale/)

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
6. Add repository URL: `https://github.com/joyfulhouse/intellicenter`
7. Select category: "Integration"
8. Click "Add"
9. Find "Pentair IntelliCenter" in HACS and click "Download"
10. Restart Home Assistant
11. Continue to [Configuration](#configuration)

### Method 2: Manual Installation

1. Download the [latest release](https://github.com/joyfulhouse/intellicenter/releases)
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

1. **Check Network**: Ensure Home Assistant and IntelliCenter are on the same network/VLAN
   - IntelliCenter uses mDNS (Zeroconf) for auto-discovery
   - Some routers/firewalls block multicast traffic between VLANs
2. **Multicast Traffic**: Enable mDNS reflection or IGMP snooping on your router if devices are on different VLANs
3. **Use Manual Setup**: Add the integration manually using your IntelliCenter's IP address
   - Go to **Settings** → **Devices & Services** → **+ Add Integration**
   - Search for "Pentair IntelliCenter"
   - Enter the IP address when prompted

**Finding Your IntelliCenter IP Address:**
- Check your router's DHCP client list for "Pentair" devices
- Use the Pentair mobile app: **Settings** → **System Information**
- Check the IntelliCenter display panel under network settings
- Assign a static IP or DHCP reservation to prevent address changes

### Connection Failed

If you see "Failed to connect" or "Cannot connect" errors during setup:

1. **Verify IP Address**: Double-check the IP address is correct
2. **Port Accessibility**: Ensure port 6681 (TCP) is not blocked by firewalls
   - Test connectivity: `telnet <intellicenter-ip> 6681` from Home Assistant host
3. **Network Routing**: Verify routing between Home Assistant and IntelliCenter
   - Test ping: `ping <intellicenter-ip>`
4. **IntelliCenter Status**:
   - Ensure the IntelliCenter is powered on and fully booted
   - Check that the IntelliCenter's network cable is connected
   - Restart your IntelliCenter (power cycle) if network seems unresponsive
5. **Firmware**: Ensure your IntelliCenter firmware is up to date
   - Update via the Pentair mobile app or directly on the device

### Entities Showing "Unavailable"

If entities show "unavailable" or stop updating:

1. **Check Connection Status**:
   - Go to **Settings** → **Devices & Services** → **IntelliCenter**
   - Look for connection status messages
2. **Review Logs**:
   - Go to **Settings** → **System** → **Logs**
   - Look for errors from `custom_components.intellicenter`
   - Common issues: network timeouts, connection refused, protocol errors
3. **Reload Integration**:
   - **Settings** → **Devices & Services** → **IntelliCenter** → ⋮ → **Reload**
   - This will reconnect to the IntelliCenter without losing configuration
4. **Network Connectivity**:
   - Verify Home Assistant can still reach the IntelliCenter IP
   - Check if the IntelliCenter IP address changed (reassign static IP/DHCP reservation)
5. **Automatic Recovery**:
   - The integration automatically attempts to reconnect with exponential backoff
   - Initial retry: 30 seconds, then 45s, 67s, 100s, etc.
   - No action needed - entities will recover when connection is restored

### Incorrect Values or Entities

If entities show wrong values or unexpected behavior:

1. **Temperature Units**:
   - The integration respects the IntelliCenter's temperature unit setting (Metric/English)
   - If you change units on IntelliCenter, reload the integration to update
2. **Missing Equipment**:
   - Not all equipment types may be supported (see Supported Entities)
   - Check logs for warnings about unrecognized equipment
   - Report missing equipment types via GitHub Issues
3. **Equipment Configuration Changes**:
   - After adding/removing equipment on IntelliCenter, reload the integration
   - New equipment should appear automatically
4. **Entity Names**:
   - Entity names come from IntelliCenter's "Short Name" (sname) attribute
   - Change names in the Pentair app or IntelliCenter UI, then reload integration

### Performance Issues

If the integration causes performance problems:

1. **Too Many Entities**:
   - Disable unused entities: **Settings** → **Devices & Services** → **IntelliCenter** → device → entity → ⚙️ → disable
   - Schedule entities are disabled by default (enable only if needed)
2. **Network Latency**:
   - Ensure Home Assistant and IntelliCenter have low-latency connection (<10ms ping)
   - Avoid WiFi for IntelliCenter if possible - use wired Ethernet
3. **CPU Usage**:
   - Integration uses async I/O and minimal polling
   - High CPU usage likely indicates network issues causing frequent reconnects

### Authentication and Security

**Note**: This integration connects locally to IntelliCenter via TCP port 6681. It does NOT use cloud services or require authentication credentials.

- No username/password needed
- Works independently of IntelliCenter's password protection settings
- Entirely local communication - no internet required
- Network-level security recommended (VLAN isolation, firewall rules)

### Enable Debug Logging

To diagnose issues, enable detailed debug logging:

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.intellicenter: debug
```

Then restart Home Assistant and check **Settings** → **System** → **Logs**.

**What to look for in debug logs:**
- Connection establishment messages
- Protocol-level communication (request/response pairs)
- Entity update notifications
- Reconnection attempts and delays
- Error messages with stack traces

### Still Having Issues?

1. **Check Known Limitations**: See the Known Limitations section below
2. **Search Existing Issues**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
3. **Ask for Help**: [GitHub Discussions](https://github.com/joyfulhouse/intellicenter/discussions)
4. **Report Bugs**: Include:
   - Home Assistant version
   - IntelliCenter model and firmware version
   - Integration version
   - Debug logs showing the issue
   - Steps to reproduce

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

- **Issues**: [GitHub Issues](https://github.com/joyfulhouse/intellicenter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/joyfulhouse/intellicenter/discussions)

[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange
[releases-shield]: https://img.shields.io/github/v/release/joyfulhouse/intellicenter
[releases]: https://github.com/joyfulhouse/intellicenter/releases
