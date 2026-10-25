# Advanced System Settings

References [#186](https://github.com/joyfulhouse/intellicenter/issues/186).
Stage 1 software was delivered in [#190](https://github.com/joyfulhouse/intellicenter/pull/190)
and its reconnect fix in [#193](https://github.com/joyfulhouse/intellicenter/pull/193):
manual operation priority and read-only configuration visibility. This is a
partial delivery, not device validation. #186 was reopened on 2026-10-25 because
its remaining acceptance criteria still require device evidence.
Clock, persistent-delay, and solar-relay writes remain deferred.
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
state or automatic replay. New advanced-setting values are invalidated in
the immediate handler disconnect callback, before reconnect can start. This
also covers quick reconnects that cancel the debounced disconnect announcement.
Invalidation does not emit an early availability broadcast or clear unrelated
fields (including calibration); the existing disconnect debounce stays intact.
Reconnect must supply fresh state rather than reusing a surviving object's
cached capability. Fresh subscription readback is not cleared by the successful
reconnect announcement. Setup and reconnect only read/subscribe.

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

## Evidence Intake and Staged Acceptance

The 2026-10-25 review found no correlated advanced-setting device transactions
in the owning issues, merged feature PRs, repository fixtures, or available
app-analysis branches. The [production soak](PRODUCTION_SOAK_3.12.0.md)
expressly excludes MANOVR writes and forced disconnects. Its disabled diagnostic
sensors and connection counters do not validate these settings. The static app
builders and library attribute comments do not fill those gaps.

Provide sanitized, timestamped request/response/NotifyList sequences with stable
object aliases, object types, firmware versions, transport, and single/shared/
dual-body topology. Preserve attribute values, ordering, errors and correlations;
remove credentials, addresses, personal data and device identifiers. Record the
panel/app setting independently before and after an authorized edit. Each device
mutation and any disruptive reconnect experiment needs applicable explicit
authorization; this handoff does not authorize running them.

| Stage | Required correlated evidence | Acceptance boundary |
| --- | --- | --- |
| MANOVR validation | Actual owner ID/type and canonical initial read; authorized ON/OFF changes; independent subsequent read/notification; rejection/timeout and reconnect with present/omitted state | Confirm owner selection and freshness on the identified firmware; acknowledgements alone do not demonstrate priority behavior or equipment actuation |
| Clock ownership/schema | Inventory both SYSTIM objects and SYSTEM; SOURCE values and manual/network interlocks; raw DAY/TIME/MIN requests and reads across midnight/date/year boundaries | Resolve source owner separately from data owner, date convention and seconds; never substitute TIME for MIN based only on names |
| Offset/DST | Actual TIMZON target and units; positive/negative and fractional offsets, including 30/45-minute cases where supported; DLSTIM ON/OFF through spring/fall transitions and repeated/skipped local time | No host timezone conversion, inferred IANA mapping, or automatic offset rewrite; unsupported cases remain unavailable |
| Persistent delays | Separate VALVE and HEATING edits/readback on identified firmware/topology; observed pump behavior during relevant valve movement/heater cooldown | Enable each flag only for validated profiles; do not expose activity, durations, or Cancel Delays from these flags |
| Solar relays | SASHP/SASHP2 independently on applicable single/shared/dual-body layouts, heater/body associations before/after, unsupported layouts and version boundary observations | Refresh configuration and reconcile affected objects after writes; no version threshold inferred from OCP_VERSION_2029, no guessed heater removal/remapping |

Clock saves span distinct owners and must not be treated as atomic. Before a
writer is implemented, capture partial rejection, timeout after send, connection
loss, and cancellation between object writes. The implementation must identify
which writes were attempted, stop further dependent writes after failure, mark
uncertain fields unknown, and independently reread every affected owner and
association. Preserve observed partial state and report incomplete application;
do not replay, roll back, retry a source takeover, or claim success from an ACK.
If reread fails, keep controls unavailable until fresh state reconciles them.
Test these paths with synthetic fixtures clearly labeled as such, then validate
the protocol behavior with correlated device evidence before enabling profiles.

The library's [advanced configuration evidence contract](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/ADVANCED_CONFIGURATION.md)
records the shared schema questions. There is no new typed clock/delay/solar
writer or library release dependency. Existing offline tests validate software
guards, not the physical semantics required to finish #186.

## Coordination

The original Stage 1 tests used the unchanged pyintellicenter 0.2.3 worktree.
The current integration pins published pyintellicenter 0.3.1; this evidence
handoff requires no dependency bump or package publication. Calibration helpers/numbers (#185)
and the latest main heater activity behavior (#184) are untouched. Sensor
additions are confined to a separate class and builder block; the coordinator
adds subscriptions, deferred MANOVR retry, and invalidation of these settings.
These edits should be reconciled when merging concurrent #185/#187 work;
pyintellicenter #100/#104/#106 remain independent.

The immediate `_CoordinatorConnectionHandler._on_disconnect` hook also serves
the calibration freshness follow-up in #192. When combining those changes,
retain both calibration invalidation and `async_invalidate_advanced_settings()`
under the stopped guard, then delegate to the library hook once. Advanced
invalidation does not replace calibration's own freshness bookkeeping.
