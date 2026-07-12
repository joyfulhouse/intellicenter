# Changelog

All notable changes to the Pentair IntelliCenter integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Covers disabled in Settings > Covers still appeared in Home Assistant.** `STATUS` on an `EXTINSTR`/`COVER` object was assumed to be the cover's open/closed position, but capturing the panel web app's own traffic shows `STATUS` is actually the "Cover Enabled" toggle - enabling a cover sends a `SETPARAMLIST` writing `STATUS` and never touching position. The real position attribute, `POSIT`, wasn't tracked at all. As a result, `is_closed`/open/close previously read and wrote the wrong attribute, and covers disabled on the panel still got a permanent, non-functional entity. The cover platform now skips creating an entity for a panel-disabled cover, and disables (via `disabled_by=INTEGRATION`, preserving entity_id/history) any cover entity already registered before this fix or before it was disabled on the panel - re-enabling it automatically if the panel re-enables the cover. Entities the user disabled manually are left untouched either way. `is_closed`/open/close now correctly use `POSIT`.

### Changed
- **Requires pyintellicenter >= 0.1.21** - Picks up `POSIT_ATTR` and the corrected `set_cover_state()`/`is_cover_on()` semantics (was previously writing/reading the wrong attribute for the same reason as above).

## [3.8.1] - 2026-07-05

### Fixed
- **System Mode showed "Unknown" in service/timeout mode** (#80) - IntelliCenter reports the timed service mode on the SYSTEM object's `SERVICE` attribute as the misspelled protocol string `TIMOUT` (no "E"). The System Mode sensor normalized it to `timout`, which is not one of the `auto`/`service`/`timeout` enum options, so it fell through to Unknown while the panel was actually in service/timeout mode. Raw `SERVICE` values are now resolved through an alias map, so both `TIMEOUT` and the hardware spelling `TIMOUT` map to `timeout`. `AUTO` and `TIMOUT` are now hardware-confirmed. Thanks to @nall for the report and the hardware-confirmed protocol string.

## [3.8.0] - 2026-06-22

### Added
- **Body "Last Temp" sensor** (#75) - Each body of water (Pool, Spa) now exposes a "Last Temp" temperature sensor (e.g. "Pool Last Temp") reading the IntelliCenter body's `LSTTMP` (last recorded temperature), enabled by default. Unlike the physical Water Sensor - whose probe sits in an above-ground pipe and reads colder when the pump is off - the Last Temp value latches the last circulating temperature, so it stays steady while the pump is idle. This restores the "last temp" entity that the original dwradcliffe integration provided. Thanks to @sheyman1 for the request.

### Fixed
- **Stale availability after connection changes** (#72) - Entities not named in the most recent push update could stay `available` with stale values through an outage, or remain `unavailable` after a reconnect. Connection-state changes now fan out to every entity (rendered from the live model) and drop optimistic state, so a command issued around a disconnect can no longer wedge the UI.
- **Pool covers missing on real hardware** (#72) - External-instrument pool covers (`EXTINSTR`) were never admitted into the production pool model, so the cover platform created no entities on actual systems (tests passed only because fixtures used the library's all-attributes default). Covers are now tracked and created, and `is_closed` reports unknown instead of fabricating "closed" when status is missing. Test fixtures were realigned to the production attribute map.
- **Config flow crash on a failed discovered unit** (#72) - Selecting a Zeroconf-discovered unit that then failed to connect escaped the flow as a generic "unknown error" (HTTP 500). The discovery step now re-shows the picker with a `cannot_connect` error, and slow-but-reachable panels (IntelliCenter timeout/command errors) are mapped correctly instead of surfacing as "unknown".
- **Body temperature limits ignored panel units; spa min-temp typo** (#72) - A shared `body_temperature_limits()` helper (40-104 °F / 5-40 °C) now backs water_heater, climate, and the HITMP "Max Temperature" number, replacing three drifted copies. Fixes a long-standing dropped-zero bug where the spa water_heater minimum was 4 °F instead of 40 °F (out-of-range setpoints reached the panel verbatim), and makes the HITMP number usable on METRIC panels (it previously rejected every valid Celsius setpoint and rendered values unconverted).
- **Defensive parsing and runtime backfill** (#72) - Malformed integer attributes no longer crash platform setup or live property reads (a bad pump flow value skips that sensor instead of killing every sensor; unparseable heater sort keys sort last). Equipment added at runtime is re-dispatched after the controller backfills its tracked attributes, so attribute-gated entities (pump power/RPM/GPM, pump limits) are created on the first update rather than skipped.

### Changed
- **Requires pyintellicenter >= 0.1.20** - Bumped the protocol-library pin (manifest + pyproject) and dropped the pyintellicenter mypy skip.

## [3.7.0] - 2026-06-01

### Added
- **System operating mode sensor (Auto / Service / Time out)** - Exposes the IntelliCenter system operating mode that the Pentair app shows as a dashboard banner. IntelliCenter reports it on the SYSTEM object's `SERVICE` attribute; the integration surfaces it as an enum sensor (`auto`/`service`/`timeout`) with per-state labels localized across all 12 supported languages. Requires pyintellicenter >= 0.1.18 (which exports the `SERVICE_ATTR` constant). Only the `AUTO` value is hardware-confirmed; the Service/Timeout protocol strings are inferred from Pentair documentation and normalized case/space-insensitively, with any unexpected value reported as unknown. Thanks to the Home Assistant community member (dbb1) who requested it.
- **Runtime detection of newly-added equipment** (#42) - Equipment added to the Pentair system after Home Assistant has started (for example a second IntelliChem controller coming online) now surfaces its sensors and controls automatically, without requiring a restart. The coordinator watches the pool model for previously-unseen objects and notifies each platform so it can create the matching entities at runtime. Thanks to @bhamiltoncx for the report.
- **Runtime detection now covers dependent equipment** (#57) - Extends the runtime detection above to equipment whose entities depend on another object: a heater added to a body that already has a water heater / climate entity now updates that entity's available modes in place (derived from the live model), and a pump circuit (`PMPCIRC`) that arrives before its parent pump is re-evaluated once the pump appears. Neither requires a restart any more.
- **HCOMBO operation modes** - Water heater entities backed by an HCOMBO heater now expose all four sub-modes as selectable operation modes: Gas Only, Heat Pump Only, Hybrid, and Dual. The last-used operation is remembered and restored on turn-on. Bodies with both an HCOMBO and a standard heater are fully supported. Thanks to @jbonta whose PRs #45 and #46 this work is based on.

### Changed
- **Test/dev environment now tracks released Home Assistant** - Bumped the test stack to Home Assistant 2026.5.4 (Python 3.14.2+, `pytest-homeassistant-custom-component` 0.13.333) to match production. The previous pin (HA 2025.11.3) still shipped the deprecated options-flow `config_entry` setter (warn-only for custom integrations), which silently masked #40 in CI; tracking the shipped HA version ensures such removals are exercised before release.
- **Integration type-checked against current Home Assistant** (#55) - Modernized the integration's type annotations for the Home Assistant 2026.5.x API (`ConfigFlowResult`, `ZeroconfServiceInfo`, fully typed config-flow steps) so it passes `mypy --strict` against the installed Home Assistant, removing a long-standing type-checking escape hatch. Internal only - no functional change.

### Fixed
- **Options flow 500 error** (#40) - Opening the integration options (the gear icon on the integration card) raised *"Config flow could not be loaded: 500 Internal Server Error"*. `OptionsFlowHandler` assigned `self.config_entry` in its `__init__`, but Home Assistant made `config_entry` a read-only property on the base `OptionsFlow` and removed the deprecated setter in 2025.12, so the assignment raised `AttributeError: property 'config_entry' ... has no setter` on current Home Assistant. The handler now relies on the `config_entry` that the base class provides. Thanks to @jeffstearns for the detailed report and traceback.
- **Retry setup on transient connection errors** (#41) - When Home Assistant restarts while IntelliCenter (or its bridge) is briefly unreachable or still booting, setup now raises `ConfigEntryNotReady` so HA retries with exponential backoff instead of leaving the entry in a permanent error state requiring a manual reload. Only connection-level failures are retried; a rejected command or non-network error still fails loudly, and the partially started coordinator is always torn down (no leaked reconnect task). Thanks to @jeffstearns for the report and @merritt925 whose PR #44 this fix is based on.
- **SAm light show missing from effect list** (#47) - The SAm IntelliBrite light show (reported by IntelliCenter as `USE=SAMMOD`) was missing from the effect map, so selecting it from the controller or IntelliCenter web app left the Home Assistant light entity's effect showing null. Added the `SAMMOD` -> "SAm" mapping in pyintellicenter (>=0.1.17). Thanks to @CrewDawg72 for reporting.
- **HCOMBO heater control** - Multi-mode heaters (e.g. Pentair UltraTemp ETi Hybrid, subtype `HCOMBO`) can now be turned on and off correctly. IntelliCenter ignores `HEATER` attribute changes for HCOMBO heaters; the fix routes all control through the body's `MODE` attribute instead. Thanks to @jbonta whose PRs #45 and #46 this work is based on.
- **Pump-circuit setpoints no longer lock in guessed defaults** - A pump circuit (`PMPCIRC`) that briefly appeared before its parent pump caused the number platform to build a speed/flow setpoint with default RPM-only limits; because Home Assistant de-duplicates entities by unique id, that placeholder could never be upgraded to the correct control once the real pump (RPM-only, GPM-only, or dual-mode VSF) arrived in a later update. The number platform now defers entity creation until the parent pump is known (mirroring the select platform), so the runtime re-dispatch builds the correct entity and limits the first time. Follow-up to #57.

---

## [3.6.6] - 2026-03-10

### Added
- **Climate Entity** - Full support for UltraTemp heat pump with cooling
  - `HVACAction.COOLING` detection for active cooling state
  - Preset modes reflecting detected heating/cooling capabilities
  - Simplified HVAC modes (Off/Auto) driven by actual equipment state
- **IntelliChem Dosing Sensors** - Acid and chlorine dosing volume monitoring
- **VSF Pump Control** - Variable Speed/Flow pump mode selection and speed/flow setpoints
  - Unified speed entity for RPM and GPM control
  - Mode selector for VSF pumps supporting both RPM and GPM
- **Pump Speed/Flow Control** - Number entities for variable speed pump setpoints

### Changed
- **pyintellicenter 0.1.15** - Updated protocol library with climate and pump improvements
- Climate entity current state driven by actual heating/cooling action, not mode status
- Improved pump entity creation: removed restrictive subtype checks for PMPCIRC entities

### Fixed
- **Water Heater Operation Mode** - Resolved validation error when setting operation mode; decoupled operation from body STATUS
- **IntelliChem Tank Level** - Corrected off-by-one error in acid tank level reporting (#36)
- Light effect control now works correctly with pyintellicenter 0.1.7+

---

## [3.6.5] - 2026-03-05

### Fixed
- Decoupled water heater operation from body STATUS for independent control (#35)
- Corrected IntelliChem acid tank level off-by-one error (#36)
- Updated `native_value` docstring to document `value_offset` parameter

---

## [3.6.4] - 2026-03-04

### Fixed
- Resolved water heater operation mode validation error when changing heater modes (#33)

---

## [3.6.3] - 2026-02-26

### Changed
- Climate entity preset modes now reflect detected heating/cooling capabilities
- Simplified climate HVAC modes to Off/Auto
- Climate current state properly driven by heating/cooling action instead of mode status
- **pyintellicenter 0.1.15** - Protocol library update

---

## [3.6.2] - 2026-01-21

### Added
- **Climate Entity** - New platform for UltraTemp heat pump cooling support (#24)
- `HVACAction.COOLING` detection for climate entity (#26)

---

## [3.6.1] - 2026-01-21

### Added
- **IntelliChem Dosing Sensors** - Acid and chlorine dosing volume monitoring (#18)
- **VSF Pump Control** - Variable Speed/Flow pump mode selection with unified speed entity (#22)
- **Pump Speed/Flow Control** - Number entities for variable speed pump setpoints (#19, #20)

### Fixed
- Removed restrictive pump subtype checks for PMPCIRC entities (#21)
- License in README corrected to match actual license (#16)

---

## [3.6.0] - 2025-12-22

### Fixed
- Light effect control with pyintellicenter 0.1.7 (#17)
- HACS zip release structure (#14)

### Changed
- **pyintellicenter 0.1.7** - Protocol library update with light effect fixes
- Updated README for HACS default repository status (#15)

---

## [3.5.6] - 2025-11-28

### Changed
- UI improvements for entity display and configuration
- **pyintellicenter 0.1.6** - Protocol library update

---

## [3.5.5] - 2025-11-28

### Fixed
- Entity default values corrected for initial state handling

### Changed
- **pyintellicenter 0.1.5** - Protocol library update

---

## [3.5.4] - 2025-11-27

### Removed
- **Deprecated valve support** - Removed unused valve platform (#10)

---

## [3.5.3] - 2025-11-27

### Changed
- **pyintellicenter 0.1.4** - Protocol library update
- Removed dead code and unused imports

---

## [3.5.2] - 2025-11-27

### Added
- Convenience methods for entity state management
- Config entity support improvements
- Release workflow to attach zip asset to GitHub releases

### Changed
- Code cleanup and organization improvements

---

## [3.5.0] - 2025-11-27

### Added
- **IntelliChem Controls** - pH and ORP setpoint control via Number entities
- **Chemistry Sensors** - pH level, ORP level, calcium hardness, cyanuric acid, total alkalinity
- **Pump Diagnostics** - Power (W), speed (RPM), flow (GPM) sensors with diagnostic entity category
- **Tank Level Sensors** - Acid and chlorine tank level monitoring (diagnostic category)
- **Internationalization** - 12 language translations:
  - English, Spanish, French, German, Italian, Portuguese
  - Chinese (Simplified & Traditional), Japanese, Korean
  - Russian, Dutch

### Changed
- **Home Assistant 2025.11+ Required** - Minimum version updated
- **pyintellicenter 0.1.1** - Updated to stable release of protocol library
- **Documentation Rewrite** - Complete overhaul following joyfulhouse organization standards
- Sensor entity categories reorganized for cleaner UI:
  - Chemistry and pump sensors marked as diagnostic
  - Tank levels moved to diagnostic category
- Translation system updated to use `translation_key` for SelectSelector options
- Improved config flow translations with proper abort messages

### Fixed
- Fixed `reconfigure_successful` translation key not displaying properly
- Fixed firmware version sensor incorrectly having `state_class` attribute

---

## [3.1.0] - 2025-11-25

### Added
- **Protocol Library Extraction** - Separated `pyintellicenter` into standalone PyPI package
  - Published to PyPI: [pyintellicenter](https://pypi.org/project/pyintellicenter/)
  - Enables reuse in other projects
  - Simplifies testing and maintenance
- **Device Classes** - Added appropriate device classes to entities:
  - `SensorDeviceClass.PH` for pH sensors
  - `CoverDeviceClass.SHUTTER` for pool covers
  - `SwitchDeviceClass.SWITCH` for circuits
- **Configuration Options Flow** - User-configurable connection settings:
  - Keepalive interval (30-300 seconds)
  - Reconnect delay (10-120 seconds)
- **PoolConnectionHandler** - Extracted connection management from coordinator
- **Connection Metrics** - Response time tracking and health monitoring

### Changed
- Integration now imports from `pyintellicenter` package instead of embedded modules
- Manifest requires `pyintellicenter>=0.0.5a12`
- Updated code structure for better separation of concerns

---

## [3.0.0] - 2025-11-24

### Added
- **Platinum Quality Scale Achievement** - Full compliance with Home Assistant's highest quality tier
- **Comprehensive Test Suite** - 175+ automated tests covering:
  - Protocol layer (message parsing, flow control, keepalive)
  - Controller layer (connection management, reconnection logic)
  - Model layer (PoolObject, PoolModel state management)
  - All platform entities (light, switch, sensor, binary_sensor, water_heater, cover, number)
  - Config flow and options flow
  - Diagnostics
- **Full Type Annotations** - mypy strict mode compliance
- **Code Documentation** - Comprehensive docstrings throughout
- **Circuit Breaker Pattern** - Prevents hammering dead servers (opens after 5 failures)
- **orjson Integration** - 2-3x faster JSON serialization

### Changed
- Quality scale upgraded from Gold to Platinum
- All code formatted with ruff (replaced black/isort)
- Enhanced error handling and logging

---

## [2.2.1] - 2025-11-20

### Fixed
- **CRITICAL: Keepalive Mechanism** - Replaced broken ping/pong with lightweight queries
  - IntelliCenter doesn't support ping/pong protocol
  - Now sends `{"command":"GetQuery","queryName":"GetHardwareDefinition"}` as keepalive
  - Configurable interval (default 90s) prevents idle disconnections

---

## [2.2.0] - 2025-11-18

### Added
- **Gold Quality Scale Achievement** - Comprehensive automated test suite
- Test coverage for critical integration components
- Enhanced test fixtures with realistic pool equipment data

### Changed
- **Improved Connection Stability**
  - 15-second debounce before marking device disconnected
  - Prevents rapid online/offline transitions
- **Protocol Health Monitoring**
  - Idle timeout: 120s with no data = dead connection
  - Flow control deadlock detection: 45s stuck = reset queue
  - Heartbeat interval: 30s (reduced from 10s)

### Fixed
- Excessive device unavailable notifications during brief network interruptions
- Entities going offline too frequently
- Rapid reconnection attempts

---

## [2.1.0] - 2025-11-15

### Added
- **Silver Quality Scale Achievement**
- Comprehensive troubleshooting documentation
- Diagnostic capabilities

### Changed
- Connection recovery with exponential backoff (30s base, 1.5x multiplier)
- Enhanced documentation

---

## [2.0.0] - 2025-11-10

### Added
- Home Assistant config flow UI setup
- Zeroconf auto-discovery
- Multiple platform support:
  - `light` - Pool/spa lights with color effects
  - `switch` - Circuits, bodies of water, vacation mode
  - `sensor` - Temperature, chemistry, pump metrics
  - `binary_sensor` - Pump status, schedules, freeze protection
  - `water_heater` - Pool/spa heater control
  - `number` - Setpoint controls
  - `cover` - Pool covers

### Changed
- Migrated from black/isort to ruff
- Fixed network connectivity issues
- Added automated test suite

---

## [1.x and Earlier]

This integration builds upon the foundational work of the original IntelliCenter integrations:

- **[@dwradcliffe/intellicenter](https://github.com/dwradcliffe/intellicenter)** - Original implementation that pioneered Home Assistant support for Pentair IntelliCenter
- **[@jlvaillant/intellicenter](https://github.com/jlvaillant/intellicenter)** - Enhanced fork with additional features

See the [Credits](README.md#credits) section of the README for full attributions.

---

## Version Comparison

| Version | Quality Scale | Tests | Key Feature |
|---------|---------------|-------|-------------|
| 3.6.6 | Platinum | 217 | Climate entity, VSF pumps, water heater fixes |
| 3.6.x | Platinum | 217 | Climate, IntelliChem dosing, pump control |
| 3.5.x | Platinum | 175+ | IntelliChem, i18n, valve removal |
| 3.1.0 | Platinum | 175+ | pyintellicenter extraction |
| 3.0.0 | Platinum | 175+ | Full test coverage |
| 2.2.x | Gold | 59 | Connection stability |
| 2.1.0 | Silver | 16 | Documentation |
| 2.0.0 | Bronze | 14 | Config flow |

---

[Unreleased]: https://github.com/joyfulhouse/intellicenter/compare/v3.7.0...HEAD
[3.7.0]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.6...v3.7.0
[3.6.6]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.5...v3.6.6
[3.6.5]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.4...v3.6.5
[3.6.4]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.3...v3.6.4
[3.6.3]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.2...v3.6.3
[3.6.2]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.1...v3.6.2
[3.6.1]: https://github.com/joyfulhouse/intellicenter/compare/v3.6.0...v3.6.1
[3.6.0]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.6...v3.6.0
[3.5.6]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.5...v3.5.6
[3.5.5]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.4...v3.5.5
[3.5.4]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.3...v3.5.4
[3.5.3]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.2...v3.5.3
[3.5.2]: https://github.com/joyfulhouse/intellicenter/compare/v3.5.0...v3.5.2
[3.5.0]: https://github.com/joyfulhouse/intellicenter/compare/v3.1.0...v3.5.0
[3.1.0]: https://github.com/joyfulhouse/intellicenter/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/joyfulhouse/intellicenter/compare/v2.2.1...v3.0.0
[2.2.1]: https://github.com/joyfulhouse/intellicenter/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/joyfulhouse/intellicenter/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/joyfulhouse/intellicenter/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/joyfulhouse/intellicenter/releases/tag/v2.0.0
