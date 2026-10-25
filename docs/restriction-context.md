# Equipment restriction context

Circuit and light entities (including feature/light groups) and pump running
sensors expose a read-only `restriction_context` attribute. The same
assessment is included under `restriction_contexts` in downloaded integration
diagnostics. Configuration entities such as Don't Stop do not duplicate it.

The context is independent of measured `Status`, on/off state, pump telemetry,
and entity availability. It never blocks a command or writes a parameter.
Existing command error handling continues to report panel/transport failures.

## Reading the context

| Field | Meaning |
| --- | --- |
| `state` | `active`: a supported context observation is present; `unknown`: dependencies prevent a complete assessment; `clear`: all assessed dependencies are known and no reason is present |
| `reasons` | Confirmed observations, each with a `code`, source `objnam`, and `source` fields |
| `unknown_dependencies` | Missing, malformed, unsupported, or unresolved dependencies; these can coexist with reasons |
| `covers` | All discovered cover observations, each with independent `enabled` (`true`, `false`, or `null`) and `position` (`closed`, `open`, or `unknown`) |

`active` does **not** mean Home Assistant or the panel will reject a command.
It means a supported observation matches the app's context helper. For example,
`freeze_protection_context` means a circuit reports `STATUS=ON` and `FREEZE=ON`.
It does not establish that freeze protection caused the circuit to turn on, or
that a user cannot turn it off. A group or pump inherits observations from its
resolved members, with the original circuit ID retained.

The current implementation always reports cover assignment and purifier context
as unknown. Consequently it does not currently emit an overall `clear` result.
An empty reasons list is not an all-clear.

Cover observations are candidates for investigation, **not** proof that each
cover restricts the target. The integration cannot currently read a validated
cover assignment inventory. It deliberately lists all discovered covers rather
than guessing applicability from a name, shared body, object-ID prefix, or the
cover's existence. Multiple covers are assessed independently.

`STATUS` is cover enablement configuration. Position requires valid `POSIT` and
`NORMAL` values: equal values mean closed, different values mean open. Disabled
and closed are independent. An unsupported field echo, missing field, malformed
value, or invalid polarity produces unknown; position never falls back to
`STATUS`. Firmware such as 1.064 that omits `POSIT` cannot supply live position
through this model. Existing cover entities and controls are unchanged.

## Relationships and lifecycle

Existing `CIRCGRP.PARENT/CIRCUIT` rows resolve group members and
`PMPCIRC.PARENT/CIRCUIT` rows resolve a pump's configured circuits/bodies. These
are configuration relationships, not proof that a member currently drives the
pump. Missing targets, malformed single-object references, wrong object types,
empty membership, and cycles produce unknown dependencies. BODY freeze context
has no validated interpretation here and stays unknown.

A shared index is built once after structural changes. Entity dependencies feed
the existing coordinator dispatch index. Changes to related circuit state and
cover position/enablement refresh the explanation without reconciling optimistic
state for the target. Membership changes, additions, removals, and reconnects
invalidate the shared topology. Ordinary value notifications require no model
scan per entity. Cover updates currently reach all assessed equipment because
assignment applicability is unknown; a validated assignment API can narrow these
edges later.

During disconnection, cached observations are omitted and the assessment reports
`connection_unavailable`. On connection, the assessment uses the library's model
and subscription lifecycle. Published pyintellicenter 0.3.1 exposes no per-field
age or snapshot completeness marker: silently stale fields on a connected panel cannot
be distinguished from unchanged values. Connected assessments therefore include
`field_freshness_unverified` in `unknown_dependencies`, even when cached values
supply an active reason. This is a remaining freshness evidence and library API
gate, not a claim that every connected field is fresh. A notification for one
field does not certify the freshness of other fields or the complete snapshot.

Downloaded diagnostics also include `restriction_field_receipts`. Its `supported`
flag is false with pyintellicenter 0.3.1. When the optional controller
`field_receipt(objnam, attribute)` API is available, `objects` maps dependency IDs
to field receipt metadata or `null` for unobserved fields. Metadata includes local
`age_seconds`, `connection_generation`, and `current_connection`. Unchanged received
values refresh receipts; reconnect clears them even if old model values survive.
Direct model edits and command acknowledgements do not create receipts. The
diagnostic age is measured when downloading; entity attributes do not poll it.

Receipt is independent of value validity and panel sampling time. Even an
unsupported echo or malformed value may have a receipt. No age threshold,
snapshot-completeness assertion, or overall all-clear is inferred; the existing
`field_freshness_unverified` dependency remains. This optional API requires no
unpublished dependency pin or release. Tests cover both the published library
and the sibling source checkout.

## Evidence and remaining gates

References: [intellicenter #187](https://github.com/joyfulhouse/intellicenter/issues/187),
[implementation tracker #188](https://github.com/joyfulhouse/intellicenter/issues/188),
and the app evidence in [intellicenter #189](https://github.com/joyfulhouse/intellicenter/pull/189)
and [pyintellicenter #108](https://github.com/joyfulhouse/pyintellicenter/pull/108).

Static evidence is Pentair Pool 4.2.21 / build 21615, package
`com.pentair.pentairhome`, HBC v96, Hermes SHA-256
`ed262bd769b4ce8ba25e3faf5594f1a7d611b4db61d6b7cddd364e61be7f4526`.

- Function 79113 (`0x01327114`) checks CIRCUIT type and `STATUS/FREEZE` both ON.
  The implementation preserves those conditions without declaring enforcement.
- Functions 79202/79203/79204/79205 (`0x01329014` and descendants) join assignment
  `CIRCUIT` to a target and assignment `PARENT` to a cover, then check cover fields.
  Functions 79206 and 79212 extend the checks to groups and lights. The supplied
  closures do not establish the assignment object's wire type or a complete
  supported read/subscription schema. No guessed object type is admitted.
- Function 79201 reads `POSIT` and `STATUS`; it does not justify replacing the
  previously validated `POSIT/NORMAL` position interpretation with `STATUS`.
- Functions 79222 and 79489 expose dashboard cover/freeze warnings; 82183 exposes
  assignment configuration. UI warnings do not prove panel enforcement.
- IntelliBlue is conditional future support tracked by pyintellicenter #103.
  `OPSTATE` classifications alone do not establish usable purifier relationships
  or controls. The assessment reports `purifier_context_unsupported` and creates
  no purifier entities.

The purifier workstream's proposed association handoff is documented in
[pyintellicenter PR #119](https://github.com/joyfulhouse/pyintellicenter/pull/119).
It is not an exported API: subtype/state and body/pump/group references still need
device evidence. This consumer keeps `purifier_context_unsupported` until that
workstream delivers a validated API, including unresolved dependencies and
independent communication/freshness information.

Before confirming circuit-specific cover reasons, obtain sanitized authoritative
snapshot/subscription evidence identifying assignment object types, parent/target
references, empty/unassigned cases, and update/removal behavior on named firmware.
Correlate supported `STATUS/POSIT/NORMAL` values with cover enabled/disabled and
physical open/closed states. Preserve unknown on firmware without a position
channel. Cover assignment editing remains pyintellicenter #104.

Before implementing command blocking, distinguish panel enforcement from app
button gating using separately authorized device observations and correlate
commands, responses, state notifications, and physical behavior. A 200 response
is not completion. No live panel commands or app replay were used for this work.
Tests use purpose-built model fixtures and the existing cover behavior contract;
they do not represent invented device captures. Issue #187 remains open for these
gates. No dependency version changes or concurrent #100/#104/#106 APIs are
required by this read-only implementation.

### Evidence review on 2026-10-25

Reviewed current source/history and tests in both repositories, #187 and its
tracker, merged #191/#196, analysis PRs #189 and pyintellicenter #108, and the
purifier handoff #119. Historical
[pyintellicenter #44](https://github.com/joyfulhouse/pyintellicenter/issues/44)
includes real cover responses with independent `STATUS/POSIT` values and
`PARENT=PNL01`; it does not identify cover-to-circuit assignment rows or prove
inventory completeness. That panel parent cannot be treated as a circuit
assignment. No additional configured MCP resource was available. Repository
memory identity was available, but no recall tool was exposed in this sandbox.
No live panel discovery or device action was performed.

The exact remaining evidence is:

1. Named-firmware discovery and read/subscription captures identifying assignment
   object type, cover parent and target circuit references, including multiple
   covers, verified empty inventory, malformed/unsupported fields and omissions.
2. Correlated assignment addition, reassignment, removal/recreation and reconnect
   snapshots/notifications, including group and pump dependency changes. Existing
   authorized captures are preferred; assignment editing needs separate authority.
3. Independent physical open/closed and enabled/disabled observations correlated
   with `STATUS/POSIT/NORMAL`, retaining unknown on unsupported firmware.
4. The validated purifier discovery/association API from pyintellicenter #103,
   including raw unknown states and unresolved dependencies as proposed in #119.
5. A panel sampling/completeness contract beyond local receipt timestamps, and
   evidence distinguishing panel enforcement from app warnings before blocking
   any command. An acknowledged write must be correlated with state and physical
   behavior before claiming successful action.

These gaps keep #187 open. The receipt increment supplies software provenance
without presenting a synthetic assignment inventory or treating recent ingestion
as validated device freshness.
