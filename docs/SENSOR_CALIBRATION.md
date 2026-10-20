# Sensor Calibration (Issue #185)

Implementation is staged pending device evidence. **No production firmware is
currently enabled, and this change creates no calibration controls by default.**
The app evidence establishes a CALIB writer, but does not establish safe offset
bounds or persistence across panels. Issue #185 must remain open.

Once supported, calibration numbers are configuration entities, disabled by
default, attached to discovered physical SENSE objects of subtype POOL, SOLAR or
AIR. IDs use `<entry_id>_<objnam>CALIB`; existing SOURCE and raw PROBE entity IDs
are unchanged. Multiple water/solar sensors retain their distinct object IDs,
including dual-body installations. No special air ID or body ordering is assumed.
A missing CALIB channel, unsupported firmware/unit profile, disconnected probe,
or unknown health prevents control discovery or makes an existing control
unavailable. Zero and negative offsets are values; missing/malformed values are
unknown. The existing library accessors supply parsed probe/calibration values,
with strict integer checks and explicit handling of numeric zero.

## Units and Commands

A support profile must establish CALIB's unit, integer resolution and limits for
an exact firmware, subtype and panel MODE. Changing panel MODE requires fresh
CALIB data before the previous offset can be displayed or edited in the new unit.
The profile for the new MODE must also be validated. Fractional protocol offsets
are deliberately unsupported until evidence establishes their encoding.

The entity explicitly converts differences to Home Assistant's configured unit:
`delta_F = delta_C * 9/5`. It does not add 32. It has no HA TEMPERATURE device
class, since that class applies absolute conversions. HA unit changes refresh
state, bounds and step. The complete converted step is retained (for example,
one Fahrenheit degree is 5/9 Celsius degrees). Inputs must convert back to a
whole supported protocol step; floating point representation error is tolerated,
but unsupported precision is rejected rather than silently truncated.

Writes use the existing awaited `request_changes(actual_objnam, {"CALIB": ...})`
command/error path. There is no automatic retry or optimistic value. An accepted
write is followed by a targeted GetParamList request for CALIB. Only a unique,
matching object response with an exact integer offset equal to the requested
value updates the model. Wrong-object, missing, duplicate, malformed or mismatched
readback raises a translated unconfirmed error. A connection failure or panel
unit/model replacement during the write or read also fails confirmation. A command error
propagates normally and prevents a follow-up read. NotifyList updates remain
authoritative. Immediate readback confirms the observed setting; persistence
across a reconnect/restart needs separate captured evidence.

The coordinator records a per-sensor observation revision, panel-unit revision
and connection generation before the write starts. A newer CALIB observation
or connection/unit generation during either await rejects confirmation without
overwriting current model state. This includes a notification with exactly the
same numeric offset: explicit observation is distinct from a value change.
The scoped controller adapter retains unchanged CALIB observations from the
library's `_apply_updates` path, used by both NotifyList and reconnect backfill.
No freshness is fabricated from an omitted field or a connection-success event.

Disconnect invalidates calibration immediately at the library disconnect hook,
before its public debounced callback. Stop and failed reconnects invalidate it
too. Retaining the same PoolObject, firmware and unit therefore cannot validate
an old pending response. Cached CALIB remains unknown/unavailable until explicitly
observed again; a reconnect read of exactly the prior value restores freshness
even when the library produces an empty numeric diff. These checks live in the
coordinator, so a disabled or not-yet-registered entity cannot miss invalidation.
Both the calibration probe-readiness predicate and #190's canonical MANOVR
readiness/disconnect behavior are retained.

Calibration changes panel temperature readings and may affect temperature-based
operation. Use stable reference measurements appropriate to each probe. Do not
calibrate stagnant pipe water against a circulating body measurement.

## Evidence and Activation Gate

Static source: Pentair Pool 4.2.21 / build 21615, `com.pentair.pentairhome`,
Hermes HBC v96, SHA-256
`ed262bd769b4ce8ba25e3faf5594f1a7d611b4db61d6b7cddd364e61be7f4526`.
The supplied packet was analyzed without downloading or decompiling an APK again.
Related evidence PRs are [intellicenter #189](https://github.com/joyfulhouse/intellicenter/pull/189)
and [pyintellicenter #108](https://github.com/joyfulhouse/pyintellicenter/pull/108).

- Function 83088 (`0x013d5f00`), relative `0x2db` through `0x44d`, builds string
  CALIB writes for distinct water, solar, air and dual-body object references.
  The water path at `0x304` through `0x317` parses the target as an integer,
  subtracts `waterSensorTrueValue` and serializes the resulting offset.
- Function 83136 (`0x013d876f`) references `minSliderValue` and `maxSliderValue`
  at relative `0x12f4`/`0x12ff`, with step 1 at `0x1345`. These are target-reading
  UI constraints, not proven CALIB offset limits. The supplied descendants do
  not establish device-confirmed bounds.
- Function 83042 (`0x013d467a`) routes PROBE to `checkSensorError` at relative
  `0xb28`/`0xb2e`, then uses the result for disabled UI controls. The external
  error classifier is not in the supplied closure packet. Until verified,
  discovery conservatively requires STATUS `OK` plus a numeric probe.
- The repository documents SOURCE as calibrated and PROBE as raw. The app's
  initialization at 83042 relative `0x86e` through `0x8a2` adds CALIB to SOURCE
  for its target value and uses SOURCE as its "true" value. This discrepancy
  needs device correlation; this implementation never derives CALIB from either
  reading and does not change existing read-only semantics.

Before adding entries to `CALIBRATION_SUPPORT`, obtain sanitized, separately
authorized device captures that establish:

1. Firmware and hardware configuration, actual SENSE identities/subtypes, body
   mapping, and healthy/disconnected PROBE and STATUS values, including error
   sentinels. Cover both channels of a dual-body installation.
2. Negative, zero, positive and boundary CALIB values, rejected out-of-range
   values, and accepted precision. Identify offset bounds independently of the
   app's target-temperature slider.
3. Celsius/Fahrenheit MODE transitions, including ordering of MODE and CALIB
   notifications, and the relationship between CALIB, SOURCE and PROBE.
4. A supported write, authoritative notification/GetParamList readback, and
   persisted values after reconnect (and panel restart where authorized), with
   reference measurements. A `200` acknowledgement alone is insufficient.

Each profile needs an evidence reference and only enables that exact
firmware/subtype/MODE combination. Tests inject an explicitly synthetic policy
to exercise discovery, encoding, errors and lifecycle handling. Those policy
values are not hardware captures or proposed production bounds. There were no
live panel commands, commissioning, firmware operations or LAN probes in this
session.

No pyintellicenter changes or dependency bumps are required. Tests install this
session's sibling library worktree. The code uses existing model, discovery and
command APIs and adds no settings owned by #186 or topology/assignment writers
owned by pyintellicenter #100/#104/#106. The remaining work is device evidence,
profile activation and a hardware-backed regression fixture, not merging an
unreleased library API.
