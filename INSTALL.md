# Installing Pentair IntelliCenter

## Prerequisites

- Home Assistant 2025.11 or newer.
- A Pentair IntelliCenter panel (i5P, i7P, i9P, or i10P) reachable on your local
  network (TCP port 6681).
- [HACS](https://hacs.xyz) installed (recommended), or filesystem access to your
  Home Assistant `config` directory (for manual installation).

## Method 1 — HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Click the **⋮** menu → **Custom repositories**.
3. Add `https://github.com/joyfulhouse/intellicenter` with category **Integration**.
4. Search for **Pentair IntelliCenter** and click **Download**.
5. **Restart Home Assistant.**

Or use this one-click link:

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=joyfulhouse&repository=intellicenter&category=integration)

## Method 2 — Manual installation

1. Download the latest release from the
   [releases page](https://github.com/joyfulhouse/intellicenter/releases).
2. Copy the `custom_components/intellicenter` folder into your Home Assistant
   `config/custom_components/` directory. The result should be
   `config/custom_components/intellicenter/`.
3. **Restart Home Assistant.**

## Adding the Integration

Your IntelliCenter is usually discovered automatically via Zeroconf/mDNS:

1. Go to **Settings → Devices & Services**.
2. Look for **Pentair IntelliCenter** under **Discovered** and click **Configure**.

If it is not discovered, add it manually:

1. Go to **Settings → Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Pentair IntelliCenter** and select it.
4. Enter your IntelliCenter's IP address and choose a transport type (TCP is
   recommended; WebSocket is available as an alternative).

**Finding your IP address:**

- Router's DHCP client list (look for "Pentair").
- Pentair mobile app: **Settings → System Information**.
- The IntelliCenter display panel.

> **Tip:** Assign a static IP or DHCP reservation to prevent address changes.

## Verifying

After setup, the integration's devices and entities appear under
**Settings → Devices & Services → Pentair IntelliCenter**.

## Updating

- **HACS:** update from the HACS dashboard when a new version is available, then
  restart Home Assistant.
- **Manual:** replace the `custom_components/intellicenter` folder with the new
  release and restart.

## Troubleshooting

If the integration does not appear or fails to set up, see the **Troubleshooting**
section of the [README](README.md#troubleshooting) and enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.intellicenter: debug
    pyintellicenter: debug
```
