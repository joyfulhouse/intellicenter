# Design: System Delay Status and Cancellation (Issue #92)

**Date:** 2026-07-14
**Updated:** 2026-07-15
**Branch:** `docs/issues-92-93-plans`
**Issue:** [#92 — delay status + Cancel Delays button](https://github.com/joyfulhouse/intellicenter/issues/92)

## Problem

IntelliCenter can keep equipment running while a heater-cooldown or
valve-rotation delay completes. Home Assistant currently exposes neither the
active delay nor the panel's "Cancel Systems Delay" action, so a delayed
shutdown can look like a failed command.

The issue's original implementation model is disproved on the project's live
IntelliCenter 1.064 unit:

- `CIRCUIT.DLY` is unsupported; the panel echoes the requested key name.
- `HEATER.DLY` is the configured cooldown duration, not active state.
- `VALVE.DLY` is configuration, not active state.
- `_5451.VALVE` and `_5451.HEATING` are global delay-enable settings. Writing
  them off would change configuration and is not an acceptable substitute for
  cancelling one active delay.

A sensor and button built from those values would either remain unknown or
silently disable safety-related configuration. This design therefore makes
protocol evidence a release gate rather than an implementation detail.

## Goal

Expose every delay capability that the local protocol can prove safely:

1. A `System delay active` binary sensor when a reliable active-state signal
   exists.
2. A `Cancel system delays` button when a distinct, acknowledged cancellation
   command exists.

The two capabilities are independently gated. A verified cancellation action
may ship without a sensor; an unverified or configuration-mutating action must
not ship.

## Planning Boundary

Protocol discovery is a separate prerequisite plan, not a conditional branch
inside the feature implementation plan. Discovery records the sanitized
command, acknowledgement predicate, state attribute/value mapping, supported
delay types and firmware scope, passive runtime capability predicate, and one
selected row from the decision table below. Those results are added to this
specification and reviewed before an implementation plan is written.

## Discovery Progress (2026-07-15)

The button and sensor gates have diverged:

- The deployed official `bundle.web.js` asset inspected for this gate had
  SHA-256
  `933e2fc35fd5e5fe26477f0199873bedaf4c266d510f6e8259e3684da18317fd`—the
  same identified asset recorded in the issue #93 evidence—and contains no
  transient `Cancel Systems Delay` operation. Its only related writes change
  persistent heater/valve delay-enable or duration settings. Those writes are
  explicitly forbidden by this design, so the cancellation button gate has
  failed and no local replay is authorized.
- Read-only TCP and WebSocket calls to `GetActiveStatusMessages` both returned
  a correlated `200` with an empty answer while no delay was active. This proves
  that the read command exists on firmware `1.064`; it does not establish the
  active schema, delay-type coverage, push delivery, or a runtime capability
  predicate.
- The sensor gate therefore remains unresolved. No production helper, entity,
  coordinator key, or polling behavior is approved.

The discovery observer has been extended and locally verified on its isolated
non-production branch. It issues only privacy-safe, bounded, read-only
`GetActiveStatusMessages` checks while retaining `NotifyList` frames; nested
answers and labels are privacy-aliased and resource-bounded. That polling is
discovery instrumentation, not permission to add production polling. If
repeated natural delays produce only query responses and no authoritative
push/model signal, the push-driven sensor architecture fails and no sensor
ships.

Before selecting `sensor only` or `unsupported`, discovery still requires two
independent natural heater cooldown transitions, one over TCP and one over
WebSocket, with inactive -> active -> inactive reads and corresponding
notification evidence. Two independent valve-delay transitions, again one per
transport, are additionally required before a generic “system delay” sensor may
claim valve coverage. Matching results may satisfy this cross-transport gate;
divergent single observations select unsupported/no capability and cannot claim
transport-scoped support without a separately amended, reviewed plan containing
within-transport repeats. No production feature plan or PR starts until those
results are sanitized, added here, and adversarially reviewed.

## Non-Goals

- Do not infer delay state from elapsed time, requested circuit state, heater
  configuration, or optimistic Home Assistant state.
- Do not write `CIRCUIT.DLY`, `HEATER.DLY`, `VALVE.DLY`, `_5451.VALVE`, or
  `_5451.HEATING` as a cancellation mechanism unless an official-client capture
  proves that exact operation and a before/after snapshot proves configuration
  is unchanged.
- Do not implement panel delay configuration controls.
- Do not add polling; state must come from the initial model or push updates.
- Do not require physical hardware in automated tests.

## Protocol Discovery Gate

Discovery happens before feature code and uses the official panel/Web App
operation as the source of truth.

### Preconditions and snapshot

Before changing equipment:

1. Confirm the panel is in Auto mode and the integration is connected.
2. Select a known Pool/Spa transition that can produce a normal delay without
   involving cleaners, freeze protection, service mode, or unrelated circuits.
3. Record firmware, current body/circuit/heater/valve states, heat modes,
   setpoints, group/light states, and the values of every observed delay-related
   attribute.
4. Start one experimental client only after the snapshot is complete.

### Capture sequence

For every heater-cooldown or valve-rotation delay type that the entities will
claim to represent:

1. Subscribe to notifications for the relevant system, body, circuit, heater,
   and valve objects, and retain bounded `GetActiveStatusMessages` reads.
2. Produce a natural delay through the official UI.
3. Record canonical inactive -> active -> natural completion values, correlate
   any non-empty active-status answer with `NotifyList`, and query the same
   objects after completion.
4. Repeat natural completion to establish repeatability and distinguish a
   durable push/model signal from query-only or transient data.
5. Restore the initial equipment, heat-mode, setpoint, and configuration
   snapshot through the official UI and verify it twice.

Cancellation and simultaneous-cancellation capture steps are not applicable to
the identified asset/firmware: the dated Discovery Progress gate found no
transient operation and authorizes no replay. Those steps may be reconsidered
only after a different precisely identified official asset supplies a distinct
non-configuration-mutating command and this specification is reviewed again.

The state gate passes only if the same readable attribute reports an explicit
inactive value before/after the delay and an explicit active value during it.
An attribute that exists only as a transient command echo cannot drive the
binary sensor.

Raw captures retained as development evidence must redact network addresses,
property names, identifiers, and credentials. Captures are not committed when
they contain private installation data.

### Abort conditions

Disconnect the experimental client and restore from the official panel if any
of the following occurs:

- an unrelated actuator changes;
- the panel leaves Auto mode;
- delay-enable configuration changes;
- the response is malformed, unsupported, or not acknowledged;
- the connection drops during a state-changing step;
- the original state cannot be restored promptly.

### Decision table

| Evidence | Result |
|---|---|
| Reliable active-state signal and distinct cancellation command | Ship sensor and button |
| Distinct cancellation command, no reliable active-state signal | Ship button only; keep sensor out of scope |
| Reliable active-state signal, no safe cancellation command | Ship sensor only; keep button out of scope |
| Cancellation changes delay configuration or cannot be acknowledged | Do not ship the button |
| No reliable state and no safe cancellation | Close the feature as unsupported with captured evidence; no speculative PR |

### Runtime capability predicate

Each shipped entity requires a passive, deterministic setup-time capability
predicate derived from the approved discovery evidence. Setup must never test a
cancellation command. The predicate may use a read-only protocol response or a
firmware range only when captures establish that range explicitly. Current
state validity alone is not a capability predicate.

If no passive predicate can distinguish supported installations, that entity
does not ship. A button-only outcome is therefore allowed only when the button
has an independent passive capability predicate.

## Architecture

### Protocol boundary

Raw command shape and state interpretation belong in `pyintellicenter` when
they require knowledge beyond the library's existing generic public API.

If discovery identifies a dedicated protocol operation, add the controller
helper `cancel_system_delays()` and, when applicable, the nullable
`is_system_delay_active()` accessor. The helper must:

- target only the captured object/command;
- await and return the panel response;
- preserve the library's existing command-error translation;
- avoid optimistic model mutation;
- expose unsupported/malformed state as `None`, not `False`.

If the captured operation is exactly expressible through the existing stable
`request_changes()` contract without new parsing or semantics, the integration
may use that public primitive and no library release is required.

### Coordinator tracking

When discovery identifies a readable attribute, add only that verified
object/attribute to `DEFAULT_ATTRIBUTES_MAP`. The existing push path then
updates the model and entity listeners. Unsupported placeholder echoes are
treated as malformed/unknown rather than inactive. Capability is recorded
separately from the current attribute value so a supported sensor remains
present and becomes unknown during a malformed update instead of disappearing.

Discovery must identify the exact owning `SYSTEM` object. Runtime setup requires
exactly one object matching that captured identity/type contract; zero or
multiple matches are ambiguous and create neither entity.

### Home Assistant entities

Add `Platform.BUTTON` to `PLATFORMS` only when the cancellation gate passes and
create `custom_components/intellicenter/button.py`.

The `Cancel system delays` button:

- is attached to the integration device;
- is available only while the coordinator is connected;
- uses `mdi:timer-cancel-outline` and no misleading button device class;
- awaits the controller command through `_async_execute_command()`;
- raises the existing translated `command_failed` error on rejection, timeout,
  or disconnect;
- does not optimistically clear the sensor;
- uses the stable unique ID
  `{entry_id}_{system_objnam}CANCEL_SYSTEM_DELAYS`;
- serializes presses through the entity platform so only one cancellation is
  in flight at a time.

When the state gate passes, add a `System delay active` binary sensor from the
verified system object. It uses `BinarySensorDeviceClass.RUNNING`, the name
`+ System delay`, and nullable state semantics:

- canonical active value -> `True`;
- canonical inactive value -> `False`;
- missing, echoed, or malformed value -> `None`.

The builder creates the sensor when the independent passive capability
predicate passes, regardless of the current state value. Its stable unique ID
follows the existing `PoolEntity` convention:
`{entry_id}_{system_objnam}{verified_state_attribute}`. A missing, echoed, or
malformed initial or later value renders the supported entity unknown. The
sensor updates only from the verified attribute in coordinator push data.

### Data flow

```text
Panel notification -> pyintellicenter model -> IntelliCenterCoordinator
  -> System delay binary sensor -> Home Assistant state

Button press -> controller cancellation helper -> panel acknowledgement
  -> later panel notification -> binary sensor state
```

The button never fabricates the second line's final notification.

## Error Handling

- A disconnected coordinator makes both entities unavailable.
- Protocol rejection, timeout, or connection loss during cancellation becomes a
  translated `HomeAssistantError` and leaves observed state unchanged.
- The library helper normalizes rejection, request timeout, and mid-command
  disconnect into the existing `ICError` hierarchy; the integration translates
  those exact errors to `command_failed`.
- Missing or malformed delay state is unknown, not inactive.
- Unsupported firmware does not get a partially functional entity. Entity
  creation is gated on the proven model/attribute contract, not firmware
  version guesses.

## Testing

### pyintellicenter tests, when a library helper is required

- exact captured command/object/parameter serialization;
- acknowledgement passthrough;
- command rejection and timeout propagation;
- active/inactive/missing/echoed/malformed state parsing;
- no optimistic mutation of model state.

### intellicenter tests

- `Platform.BUTTON` setup and unload behavior;
- button creation, name, unique ID, icon, device attachment, and availability;
- successful press awaits the controller exactly once;
- rejection/timeout becomes `HomeAssistantError`;
- binary sensor true/false/unknown mappings, when included;
- absent, echoed, malformed, and ambiguous capability evidence creates no
  entity and never sends a setup-time cancellation command;
- a supported sensor remains present but unknown when its state later becomes
  missing, echoed, or malformed;
- push-update propagation for the verified state attribute;
- dynamic setup does not create duplicates;
- rapid duplicate presses never put two cancellations in flight;
- regression guard proving `DLY` configuration values cannot create the active
  sensor or drive its state.

All protocol tests use the exact sanitized frames captured from hardware. The
full lint, format, type, security, and pytest suites run in both repositories,
followed by one controlled live smoke test with snapshot and restoration.

## Documentation

- Document what kinds of system delay the entities represent.
- State that cancellation skips the current operational delay but does not
  disable configured heater or valve protections.
- Warn that cancelling a live delay can stop equipment or begin valve movement
  immediately.
- If only one capability passes discovery, document only that capability and
  keep the issue/PR title accurate.

## PR and Release Topology

- Integration branch: `feat/issue-92-delay-status-cancel`, based on the fetched
  `intellicenter/origin/main` commit used by the implementation plan.
- The first post-spec plan performs protocol discovery only. Feature worktrees
  and implementation PRs start after the captured contract and selected
  decision-table result are written into this spec and approved.
- Reserve `feat/issue-92-delay-protocol` in pyintellicenter only if discovery
  requires a new public helper or parser.
- The pyintellicenter PR, if any, is related to issue #92 but does not close the
  Home Assistant issue.
- The integration PR is the only PR that may close #92, and only when every
  capability named in its title has passed the discovery gate.
- Never merge integration code that calls a newer library API while retaining a
  requirement compatible with older pyintellicenter versions. If a new API is
  required, release the library first and update `manifest.json`,
  `pyproject.toml`, and `uv.lock` atomically.

## Acceptance Criteria

- Every shipped state or command is backed by an official-client capture and a
  live round-trip on the supported test unit.
- Cancellation leaves delay-enable configuration and unrelated equipment
  unchanged.
- Original equipment state is restored after validation.
- Automated tests cover success, failure, unknown state, and the disproved
  `DLY` regression.
- `agy` and Cursor `agent` independently review the final diff, and all confirmed
  findings are resolved or documented before the draft PR is handed off.
