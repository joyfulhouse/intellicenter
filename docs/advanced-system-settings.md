# Advanced System Settings

References [#186](https://github.com/joyfulhouse/intellicenter/issues/186).
This delivers Stage 1: manual operation priority and read-only configuration
visibility. Clock, persistent-delay, and solar-relay writes remain deferred.
There is no Cancel Delays action.

## Entities and Targets

| Setting | Object target | Encoding displayed/sent | Home Assistant representation | Support boundary |
| --- | --- | --- | --- | --- |
| Manual operation priority, `MANOVR` | The unique tracked object reporting canonical MANOVR state | String `ON` / `OFF`; only MANOVR is written | Configuration switch, enabled by default | Exactly one recognized owner; connected panel; rechecked before each write |
| Spa Manual Heat, `MANHT` | Existing SYSTEM object | String `ON` / `OFF` | Existing configuration switch and unique ID retained | Existing behavior retained |
| Pump valve delay setting, `VALVE` | SYSTEM | String `ON` / `OFF` | Optional diagnostic sensor | Read-only; key reported by panel |
| Pump heater delay setting, `HEATING` | SYSTEM | String `ON` / `OFF` | Optional diagnostic sensor | Read-only; not heater activity or cancellation |
| Body 1/2 solar relay setting, `SASHP` / `SASHP2` | SYSTEM | String `ON` / `OFF` | Optional diagnostic sensors | Read-only across topologies; key presence does not authorize writes |
| Panel time zone offset, `TIMZON` | SYSTEM | Finite numeric string, preserved verbatim | Optional diagnostic sensor without a unit or HA time-zone conversion | Read-only; offset units and fractional behavior need device validation |
| Clock source, `SOURCE` | SYSTIM object reporting SOURCE | Opaque string, e.g. the library-documented `URL` token | Optional diagnostic sensor on its own object | Read-only; not copied from SYSTEM, a sensor, or the separate clock-data object |
| Clock format, `CLK24A` | SYSTIM clock-data object | `AMPM` / `HR24` | Optional diagnostic sensor | Other formats are unknown; no format writes |
| Daylight saving setting, `DLSTIM` | SYSTIM clock-data object | String `ON` / `OFF` | Optional diagnostic sensor | Reports configuration; does not assert whether DST is currently in effect |
| Clock date/time, `DAY` / `TIME` | App's separate clock-data object | App save builder converts DAY with a helper and formats TIME as `HH,mm,00` | Deferred | Library documents a `MIN` read field; round-trip schema, date convention, units and source ownership are not validated |

Diagnostic sensors are disabled by default and have no measurement state class.
Missing/malformed values and unknown-key echoes are unknown, never silently OFF.
No date/time is constructed from the host clock or Home Assistant's time zone.
DST changes do not rewrite offsets or derive timestamps.

## Capability Discovery and Lifecycle

The packet identifies the app's `manualHeatObjectName` symbol, but does not
resolve its constant value or protocol object type. It is deliberately not
replaced with SYSTEM, a body, or a guessed fixed ID. The integration adds a
MANOVR read/subscription key to its tracked equipment/clock object types,
including SYSTIM. Relationship-only CIRCGRP membership rows are excluded. Only
canonical readback creates a priority switch. If the real owner belongs to an untracked type, the control
remains absent until that schema is validated; generic readback discovery is
not a claim that all firmware supports this setting.

Multiple recognized owners disable all priority switches. A missing or malformed
value disables an existing switch. Deferred attribute backfill retries unknown,
echoed and malformed initial MANOVR values, so a later valid value creates the
entity without reloading. Ownership is checked against the current model before
writes. The generic awaited library `request_changes()` path encodes the
single-key SETPARAMLIST operation and propagates command rejection, timeout,
connection loss and cancellation. No new library release is required.

A command acknowledgement completes the service, but the entity retains its
last readback until a subscribed panel update arrives. There is no optimistic
state or automatic replay. New advanced-setting values are invalidated on
disconnect: reconnect must supply fresh state rather than reusing a surviving
object's cached capability. Setup and reconnect only read/subscribe.

## Evidence and Remaining Gates

Encoding is supported by Pentair Pool 4.2.21 / build 21615 static evidence:
function 83088 at `0x013d5f00` writes MANHT/VALVE/HEATING to the system object,
MANOVR through `manualHeatObjectName` at relative offsets `0x203`-`0x21e`,
clock-data settings through `timeObjectName`, and SOURCE separately through
`clockSourceObjectName`. Functions 83023 and 83042 map read state. The existing
library attribute definitions independently document SYSTIM roles and
AMPM/HR24. The packet's Hermes SHA-256 is
`ed262bd769b4ce8ba25e3faf5594f1a7d611b4db61d6b7cddd364e61be7f4526`.
This document summarizes the evidence; raw decompiled files are not distributed.

Static builders prove client encoding, not successful device behavior. Automated
tests use purpose-built model data and mocked responses, not captured live
MANOVR or clock transactions. No panel was contacted during implementation.

Before claiming device-validated Stage 1 completion, collect a sanitized
MANOVR owner/type readback on identified firmware and an explicitly authorized
write followed by independent readback/notification, plus disconnect/reconnect
behavior. A 200 acknowledgement alone is insufficient. Unsupported firmware
must remain unknown/unavailable. Do not close #186 on this partial delivery.

Before enabling clock writes, validate SOURCE ownership and its allowed values,
source/manual-time interlocks, DAY and TIME/MIN read/write formats, time units,
TIMZON target/units (including fractional offsets), and DLSTIM behavior through
both spring/fall transitions. Define how failed multi-object saves reconcile;
do not guess IANA mappings or silently take ownership of a network clock.

Before enabling persistent delay writes, establish firmware/topology eligibility
and panel write/readback semantics for each flag. VALVE/HEATING are persistent
configuration, not current delay activity, duration, or cancellation commands.

Before enabling solar-relay writes, validate single/shared/dual-body topology,
heater/body associations, SASHP/SASHP2 readback, and configuration refresh and
reconciliation. Functions 83020/83136 gate these controls with a comparison
involving `OCP_VERSION_2029`; the identifier does not establish an inclusive
minimum version. Do not guess what removes or remaps a heater.

## Coordination

The sibling pyintellicenter worktree is used unchanged for tests at 0.2.3. No
secondary PR or dependency bump is needed. Calibration helpers/numbers (#185)
and the latest main heater activity behavior (#184) are untouched. Sensor
additions are confined to a separate class and builder block; the coordinator
adds subscriptions, deferred MANOVR retry, and invalidation of these settings.
These edits should be reconciled when merging concurrent #185/#187 work;
pyintellicenter #100/#104/#106 remain independent.
