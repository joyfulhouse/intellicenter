# FDR/FDP event diagnostics: pending local validation

The [library request #107](https://github.com/joyfulhouse/pyintellicenter/issues/107)
owns the local schema investigation. The FDR/FDP row of
[tracker #188](https://github.com/joyfulhouse/intellicenter/issues/188) records this
evidence-based limitation. No event-active HA entity is enabled yet.

The library's offline `EventState`/`observe_fdr_event` model preserves raw
EVENTSTATUS and EVENTID, maps only the app-established exact `running` value
to True, and represents every unvalidated value as unknown. There is no validated
inactive mapping. It does not attach to controllers or subscribe automatically.
See the [library evidence and capture requirements](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/FDR_EVENTS.md).
The integration does not import this unreleased API or require an unpublished
library version; existing published-library compatibility is unchanged.

## Evidence and dependencies

Pentair Pool 4.2.21/build 21615 static analysis identifies `_FDR` snapshot and
subscription templates (function 79341), the `running` status comparison and
event ID (79486), and navigation to FDP scheduled-event details (79485).
Function 79651 derives the UI enable gate from
`featureConfigReducer.cecConfig.isEnable`. Its origin and any requirement for
cloud enrollment/local observation remain unresolved. These are app-code
observations, not successful local snapshots/subscriptions. Provenance and exact
bytecode offsets are in #107 and the
[protocol documentation PR #108](https://github.com/joyfulhouse/pyintellicenter/pull/108).

The only located device `_FDR` example is a
[definition response with key echoes](https://github.com/joyfulhouse/pyintellicenter/issues/12#issuecomment-3765379001).
It has no EVENTSTATUS/EVENTID and does not establish support. Existing library
model pruning remains appropriate. No configured device resource or captured
event lifecycle was available in this sandbox; no live panel actions were taken.

Before delivering the entity, obtain sanitized, correlated local snapshots and
notifications for supported/enabled, inactive, active, unknown, missing and
unavailable cases; changed IDs and partial updates; disconnect/reconnect and
fresh subscription restoration. Record hardware, firmware, transport, field
types and ordering. Establish each inactive value from independently confirmed
behavior and resolve the feature flag/local/cloud dependency. Collect naturally
occurring observations or use separately authorized device access, rather than
enrolling, opting out or cancelling events to produce fixtures.

## Required HA behavior once validated

- Use a stable panel-based diagnostic entity ID, not a changing EVENTID.
- Expose tri-state event activity, raw status/ID and a quality explanation;
  missing, unsupported and unknown must never become confirmed inactive.
- Preserve raw values without coercion, including null/absent distinctions.
  Avoid combining a changed ID with cached running status from another event.
- Make disconnect unavailable and invalidate freshness before fast reconnect;
  require new local evidence before reporting activity again. Cover ordering,
  partial notifications and stale data in integration tests.
- Reuse a device-validated library controller/subscription API after an
  appropriately published dependency is available. The current offline helper
  cannot establish automatic freshness or capability.
- Keep event diagnostics separate from firmware update progress. Visibility,
  disappearance or an acknowledgement proves neither cancellation nor physical
  event completion. No event controls are part of this scope.

The request remains open for these dependencies. Synthetic parser tests validate
unknown-state safety, not physical panel behavior or feature availability.
