# Design: Light Group Actions and Membership Modeling (Issue #93)

**Date:** 2026-07-14
**Updated:** 2026-07-15
**Branch:** `docs/issues-92-93-plans`
**Issue:** [#93 — true circuit/light group entities + Sync/Swim/Set](https://github.com/joyfulhouse/intellicenter/issues/93)
**Evidence:** [Light group protocol discovery](../evidence/2026-07-14-light-group-protocol.md)

## Problem

The issue originally assumed each `CIRCGRP` object represented a group. Live
hardware disproved that model:

- The controllable group is a `CIRCUIT` whose subtype is `CIRCGRP` or `LITSHO`.
- Each `CIRCGRP` object is one membership row with a `PARENT` reference to the
  group circuit, one singular `CIRCUIT` reference, `LISTORD`, and the
  per-member `USE` value observed on the test unit.
- `CIRCGRP.SNAME` and `CIRCGRP.STATUS` are unsupported placeholder echoes.

Basic group on/off control already shipped through the parent circuit path in
PR #105. Building entities directly from membership rows would create duplicate
garbage entities. The remaining work is to correct pyintellicenter's group
helpers and expose only the light-group action contracts that passed controlled
official-client capture and local transport replay.

## Goal

1. Make pyintellicenter model real hardware groups without breaking legacy
   fixture/API behavior unnecessarily.
2. Expose Color Sync as a momentary action on an existing `LITSHO` light entity
   over TCP and WebSocket, the two transports whose same-connection sender
   lifecycle passed the final protocol gate.
3. Omit Color Set, Color Swim, and member-position configuration because their
   independent safety and discovery gates did not pass.

## Planning Boundary

Implementation remains split into separately reviewed plans so the captured
protocol boundary cannot leak into broader group-model changes:

1. capture and sanitize the official-client and local replay evidence;
2. close the sender-side field, prestate, and timing gates identified by
   adversarial review;
3. correct the library group model and its compatibility contract;
4. implement Sync on TCP and WebSocket, the only transport/action pairs that
   passed the sender-side gate; and
5. reject Set, Swim, unsupported action tokens, and incomplete group topology
   before state-changing network I/O.

Discovery established exact request payloads, acknowledgements, transport
differences, collateral-change checks, and restoration evidence. Adversarial
review found that the action-active field differed by receiving client and
that the original 60-second gate was not a valid universal bound. The final
same-connection gate passed Sync over both transports and rejected TCP Swim
after a late mixed target state. Production implementation waits only for the
separately reviewed implementation plan. Discovery did not establish a
member-position writer or finite option set, so no position implementation
plan or select is in scope.

## Non-Goals

- Do not create switch or light entities for `CIRCGRP` membership rows.
- Do not duplicate the parent circuit's existing on/off light/switch entity.
- Do not add group creation/deletion, membership editing, or arbitrary circuit
  batching.
- Do not infer group type from membership-row attributes.
- Do not optimistically change a group effect or member position.
- Do not expose unsupported `CIRCGRP.SNAME` or `CIRCGRP.STATUS` values.
- Do not serialize the disproved `{ACT: token, STATUS: ON}` proposal.
- Do not expose Color Set, Color Swim on either transport, or member-position
  selects.

## Corrected Hardware Model

```text
CIRCUIT parent (SUBTYP=LITSHO)
  <- CIRCGRP membership row A (PARENT=parent, CIRCUIT=child A, LISTORD=1)
  <- CIRCGRP membership row B (PARENT=parent, CIRCUIT=child B, LISTORD=2)

CIRCUIT child A (SUBTYP=GLOW)
CIRCUIT child B (SUBTYP=GLOW)
```

The parent circuit owns identity, display name, power, and group actions. The
rows own membership references and order. Discovery did not prove a supported
per-member writer. Referenced child circuits own each physical light's ordinary
state and capabilities.

## Protocol Discovery Results

Discovery used firmware `1.064` in `SERVICE=AUTO`. Independent TCP and
WebSocket baselines were identical and contained exactly one complete target:
one `LITSHO` parent, two `CIRCGRP` membership rows, and two resolved `GLOW`
children. Complete, non-empty membership remains a mandatory read-model
predicate; the initial writer narrows eligibility to this exact firmware,
member count, and child subtype.

The official client repeated each valid action twice with exact mixed-case
`SetParamList`, one parent object, and one dedicated parameter:

| Action | Accepted official runs | Parent params | Correlated response | Official completion |
| --- | --- | --- | --- | --- |
| Sync | 3 and 4 | `{"SYNC": "ON"}` | `200` | complete lifecycle |
| Set | 2 and 3 | `{"SET": "ON"}` | `200` | complete lifecycle |
| Swim | 1 and 2 | `{"SWIM": "ON"}` | `200` | complete lifecycle |

The semantic lifecycle tolerated leading-order variation, but its
action-active key depended on the receiving client. For every action, the
official browser connection saw parent `SWIM=ON` then `SWIM=OFF`, while the
simultaneous local observer saw parent `SYNC=ON` then `SYNC=OFF`. Both saw the
parent and resolved children reach `STATUS=ON`. Browser terminal timings were
about 36 seconds for Sync, 75 seconds for Swim, and 103 seconds for Set. Only
the parent and two children persisted `STATUS=OFF` to `STATUS=ON`; no
membership or unrelated inventory delta remained. Each valid official run was
restored and checked twice. Earlier Sync runs 1 and 2 and Set run 1 were
discarded because an unrelated generic circuit changed during their capture
windows.

Initial cross-client local replay produced a narrower matrix:

| Action | TCP | WebSocket | Initial result |
| --- | --- | --- | --- |
| Sync | five-push cross-client lifecycle passed | five-push cross-client lifecycle passed | advance both transports |
| Set | `200`, four leading pushes, then no terminal edge and persisted action flags | same failure | omit this local path and reject before state-changing I/O |
| Swim | `200`, four leading pushes; a 60-second read appeared clean | `200`, four leading pushes, then stuck action flags | advance TCP to a longer run; omit WebSocket |

Both Set replays lacked the final `SYNC=OFF` and left `SYNC`, `SET`, and
`SWIM` persisted as `ON` on the target and another group with
`SUBTYP=CIRCGRP`. WebSocket Swim left the same action flags stuck `ON`.

The final production-shaped harness subscribed and sent on one connection,
armed before the write, retained pre-response notifications, observed for 180
seconds, and finished with full in-band inventory reads:

| Action | Transport / prestate | Sender-side result | Persistent result |
| --- | --- | --- | --- |
| Sync | TCP / all off | `SYNC=ON` at 0.219557 s; target statuses on at 1.255901–1.258996 s; `SYNC=OFF` at 35.286805 s | only the three expected target statuses changed |
| Sync | TCP / all on | `SYNC=ON` at 0.275896 s; `SYNC=OFF` at 36.238773 s | no status edge and no inventory delta |
| Sync | WebSocket / all off | `SYNC=ON` at 0.852700 s; target statuses on at 0.852716–0.852729 s; `SYNC=OFF` at 35.852674 s | only the three expected target statuses changed |
| Sync | WebSocket / all on | `SYNC=ON` at 0.765173 s; `SYNC=OFF` at 35.773954 s | no status edge and no inventory delta |
| Swim | TCP / all off | `SYNC=ON` at 0.593273 s; target statuses on at 0.602877–0.602899 s; `SYNC=OFF` at 74.567605 s; both children off at 83.613525–83.614324 s | mixed final state: parent on, both children off |

Every write received a correlated `200` in at most 0.011 seconds. No run
produced a collateral-group action-flag edge. The sender-side field was `SYNC`
on both transports. Sync therefore passed on TCP and WebSocket from uniform
all-off and all-on prestates. Mixed prestates remain unsupported.

TCP Swim failed. Its late child-off edges show that neither its terminal flag
nor its earlier 60-second read represented a stable supported result. No
Swim-from-on run was justified after the all-off contract failed. Set and Swim
are omitted on both transports and rejected before state-changing I/O.

Sync uses a Sync-specific 60-second terminal bound: both official and all four
sender-side Sync observations completed in at most 36.370 seconds. This value
is not generalized to Set or Swim. Because Swim demonstrated late status
changes after a terminal flag, Sync completion also retains a 60-second
post-terminal observation interval and an in-band final projection read. All
Sync captures remained free of late target or collateral edges throughout
their 180-second windows.

The official Web App bundle used for discovery had SHA-256
`933e2fc35fd5e5fe26477f0199873bedaf4c266d510f6e8259e3684da18317fd`.
It exposed no member-position writer: the relevant chips were hidden,
membership-row `USE` was neither read nor written, and no membership-row `ACT`
or `LISTORD` write existed. There is no verified writable/readable field or
finite option map, so member positioning is omitted.

Every failed state was restored through a freshly reloaded official UI. The
same-connection restores each contained one exact parent `STATUS=OFF` write and
a correlated `200`; independent TCP and WebSocket reads matched the applicable
quiet baseline exactly. The complete sanitized record, including the one
unrelated between-run transition, fresh quiet gate, accepted run numbers, and
limitations, is in the linked evidence document.

## pyintellicenter Design

### Read helpers

Correct `_mixins/circuit_group.py` around the parent/row relationship:

- `get_circuit_group_members(parent_objnam: str) -> list[PoolObject]` returns
  `OBJTYP=CIRCGRP` rows whose `PARENT` matches the parent circuit, sorted by
  nonnegative numeric `LISTORD` with negative/malformed/missing values last and
  `objnam` as a total deterministic tiebreaker.
- `get_circuits_in_group(group_or_row_objnam: str) -> list[PoolObject]`
  resolves each member row's singular `CIRCUIT` reference, preserving row order
  and skipping missing references safely.
- `circuit_group_has_color_lights(parent_objnam: str) -> bool` evaluates the
  resolved child circuits without implying command eligibility.
- `get_color_light_groups() -> list[PoolObject]` returns parent group circuits
  that contain color lights, never membership rows. Action eligibility remains
  the narrower complete `OBJTYP=CIRCUIT/SUBTYP=LITSHO` predicate.

For compatibility, `get_circuits_in_group()` also accepts a legacy standalone
`CIRCGRP` object with a space-separated `CIRCUIT` value. When passed a real
membership row with `PARENT`, it resolves the parent and aggregates all sibling
rows. Existing artificial fixtures therefore keep working while real hardware
gets correct results.

`get_circuit_groups() -> list[PoolObject]` returns only unique parent
`OBJTYP=CIRCUIT` objects whose `SUBTYP` is `CIRCGRP` or `LITSHO`, in model
order. `OBJTYP=CIRCGRP` always means a membership row; `SUBTYP=CIRCGRP` on a
`CIRCUIT` means a parent group. It never promotes an orphan or malformed
membership row. This is an intentional correction to a pre-1.0 public helper.
Legacy compatibility is confined to a direct
`get_circuits_in_group(legacy_objnam)` call for an exact standalone fixture
shape; legacy rows do not appear in group enumeration or color-group results.
Add tests and documentation that make this boundary explicit.

### Command helper and completion substrate

Add one dedicated public helper for the action that passed the sender-side
gate:

```python
async def run_light_group_sync(group_objnam: str) -> dict[str, Any]:
```

The cached target shape is rejected before any network request. There is no
public Set or Swim command entry point. The helper then captures the current
connection, takes a controller-wide mutation lifecycle lock, and performs a
fresh, in-band preflight. Before the write it requires:

- exactly one `SYSTEM` with the raw wire token `VER=1.064` and `SERVICE=AUTO`;
- a parent `OBJTYP=CIRCUIT/SUBTYP=LITSHO` with exactly two membership rows;
- two distinct, fully resolved `CIRCUIT/SUBTYP=GLOW` children;
- a uniform all-off or all-on target power prestate, rejecting mixed state; and
- `SYNC`, `SET`, and `SWIM` all `OFF` on the target and every other parent
  `CIRCUIT` whose subtype is `LITSHO` or `CIRCGRP`.

The initial collateral-sensitive projection contains system version/mode;
required identity/type/subtype/status plus normalized optional parent/`USE` for
every `CIRCUIT`; action flags for every real group parent; and required
`PARENT`/`CIRCUIT`/`LISTORD` plus normalized optional `USE` for every `CIRCGRP`
membership row. It is one existing-shape wildcard `GetParamList` with a fixed
12-key union, not a per-object request whose size grows with installation
inventory. For those optional fields only, missing, `None`, exact key-name
echo, and `"00000"` normalize to one absent value and are compared to baseline.
Mandatory fields never accept those sentinels. This matches ordinary
parentless/non-color circuits instead of requiring unsupported attributes to
become real. Dynamic temperature, RPM, flow, and schedule telemetry is
excluded.

The connection layer adds a non-replacing raw observer that assigns one
monotonic sequence number when each notification is accepted, before the
existing callback queue. The observer is installed before the first wildcard
projection read. It holds a bounded pre-baseline buffer and fails closed on
overflow; once that response validates, buffered frames are replayed against
the baseline in sequence. It parses every `NotifyList` entry in wire order,
fails closed on malformed frames where relevance cannot be excluded, and never
lets duplicate change-then-restore entries collapse into a clean frame. Its
first irreversible violation sets a one-shot failure signal synchronously so
the active request or timer wait wakes immediately. Exact-object
`RequestParamList` subscriptions are
split into batches at the existing 50-key ceiling. Every initialization
response must contain every requested object exactly once, no duplicate or
extra entry, every mandatory key with a real value, and every optional key as a
normalizable value or omission; its normalized projection must equal the
baseline slice rather than being applied blindly. After
the same one-second settle interval exercised in discovery, the helper repeats
the wildcard preflight on the captured connection and requires it to match the
first projection. Any intervening projected deviation fails even if it later
returns to baseline.

The connection send primitive accepts separate private pre-send and post-send
hooks. While the connection request lock is held, the pre-send hook records the
event-loop monotonic deadline origin and marks dispatch started immediately
before synchronous TCP write or awaited WebSocket send. A pre-send callback
failure leaves that flag false and prevents the transport call. The post-send
hook captures the notification sequence immediately after TCP write returns or
WebSocket send finishes. Only notifications whose sequence is greater than
that causal post-send watermark can establish onset. This excludes a
notification received after observer registration but before the packet, and
conservatively excludes frames processed while awaited WebSocket send is
suspended; those frames still undergo invariant checks. The controller races
the action task against the pre-send signal and immediately arms the absolute
60-second deadline, so a stalled WebSocket send is bounded without using its
pre-send sequence as false causal evidence.

The helper serializes exact mixed-case `SetParamList` directly with one parent
object and `{"SYNC": "ON"}`. It requires a correlated
`response == "200"`, a post-watermark parent `SYNC=ON` edge, and a later parent
`SYNC=OFF` edge within 60 seconds. Leading status/action order may vary. The
all-off discovery runs produced post-watermark parent/child `STATUS=ON`
updates, but production success proves the target statuses through the
monotonic tracker plus mandatory final projection rather than making each
status push a separate lifecycle edge. The all-on prestate does not require
redundant status notifications.

The observer enforces normalized invariants from dispatch start until removal:

- an all-on target object never leaves `STATUS=ON`;
- after each all-off target object reaches `STATUS=ON`, it never returns off;
- every circuit `OBJTYP`, `SUBTYP`, and normalized optional `PARENT`, plus
  target `SET`, `SWIM`, and normalized optional `USE`, never deviate from
  baseline;
- every unrelated circuit `STATUS` and normalized optional `USE` remains at baseline, so an
  unrelated schedule/panel transition conservatively fails the action rather
  than weakening causal attribution;
- every other group action flag remains `OFF`; and
- system mode and all membership topology/order/normalized optional `USE`
  remain unchanged.

Target `SYNC` may make only its qualifying `OFF -> ON -> OFF` transition. A
later `SYNC=ON` re-entry after terminal is a permanent failure even if another
`OFF` and clean final read follow.

The tracker also retains the cached all-object type inventory. A notification
introducing an unknown `CIRCUIT`, `CIRCGRP`, or `SYSTEM`—or an unknown object
with projected keys but no trustworthy type—is an irreversible topology
failure even if it disappears before the next wildcard read. A dynamic type map
lets well-formed partial updates for currently irrelevant objects remain
outside the projection, but an explicit transition into `CIRCUIT`, `CIRCGRP`,
or `SYSTEM` fails irreversibly even if the same or a later frame restores it.

After the terminal edge, the observer remains armed for a 60-second quiet
interval. The helper then performs one fresh in-band projection read on the
same captured connection. It must prove the target parent and both children
`STATUS=ON`, all group action flags `OFF`, and every other projected value,
including every circuit's `OBJTYP` and `SUBTYP`, equal to the
post-subscription baseline. A clean read never substitutes for a missing onset
or terminal edge.

Add a phase-aware `ICLightGroupError(ICError)` for failures after dispatch
begins. It records `phase`, an always-true `dispatch_started`, `response_received`,
`acknowledged`, and `onset_seen`; the original cause remains chained. Cached
eligibility-shape rejection uses `ValueError`; fresh projection, subscription,
preflight, connection, and read failures before dispatch retain an ordinary
`ICError` type. This avoids misusing request-response
`ICTimeoutError` for a missing lifecycle edge and lets consumers distinguish an
explicit rejection, uncertain delivery, acknowledged-but-incomplete action,
and failed final verification. `phase` names the gate that failed, so an onset
push may coexist with `phase="acknowledgement"` when its correlated response
never arrives.

The helper returns the complete correlated transport acknowledgement exactly
as supplied—including its real `messageID`, `response`, and any opaque vendor
fields—only after authoritative completion. It does not require or invent a
response-side command echo; tests prove unchanged passthrough with a realistic
full response rather than a bare `{"response":"200"}`. It never retries a state-changing request and never optimistically
mutates model state. It explicitly gives the state-changing request the same
60-second response bound as the dispatch-start lifecycle instead of inheriting the
connection's shorter default. Sync marks an exclusive mutation lifecycle
pending before waiting for already-started case-insensitive `SetParamList`
work. Those earlier writes drain first; later `send_cmd()` calls,
`request_changes()`, coalesced flushes, and a second Sync fail immediately with
an ordinary pre-dispatch `ICError` rather than queueing for roughly two minutes.
Both coalescing entry points perform that check synchronously before appending a
future or mutation, so a later convenience call cannot hide behind the
coalesce lock and replay after Sync. Pending requests retain their own proposed
changes; canceling one before batch detachment removes that request and rebuilds
the aggregate in admission order, preventing a canceled latest-value override
from surviving the lifecycle boundary. Once a batch is detached, cancellation
never causes a retry or requeue of its possibly dispatched mutation.
Read-only traffic and model callbacks continue. A private captured-connection
send primitive preserves metrics/error translation without reacquiring the
lock and is used only by the Sync helper while it owns the lifecycle. One fresh
opaque identity lease authorizes the explicitly delegated action task without
confusing that child for the lock-owning task; cleanup awaits every child and
invalidates the lease before releasing ownership. A
separately created raw `ICConnection` or the physical panel remains outside
that boundary; a projected external change makes the action incomplete.

Immediately after capturing the live connection, the helper synchronously
captures a one-shot close future bound to that exact connection generation.
Every wildcard read, subscription initialization, action response, settle,
onset, terminal, and post-terminal wait races it and the tracker's first-failure
signal; disconnect or invariant failure therefore aborts the current
pre/post-dispatch phase immediately, never after only a generic deadline.
Reusing the instance creates a distinct future without clearing the old
completed one, and a replacement generation/connection cannot contribute
completion frames. Although raw observer state survives transport replacement,
the action's observer closure checks the captured future before every frame and
stops forwarding once it is done. Simultaneous readiness is handled in the
fixed order closure, tracker failure, deadline, then response/action success.

Do not add `set_light_group_member_position()`. Discovery found no official
writer, durable readable field, or finite option set. Complete membership is
not provisional: the capture did not prove that `LITSHO` alone is a sufficient
and safe capability predicate.

## Coordinator Tracking

Replace the current unsupported `CIRCGRP_TYPE` tracking keys with verified row
semantics:

- always track `PARENT`, `CIRCUIT`, and `LISTORD`;
- do not add `USE` as configuration state because no member-position
  read/write contract passed;
- do not expose `ACT`, `SYNC`, `SET`, or `SWIM` as durable entity state; the
  helper subscribes to verified action flags as internal momentary monitoring
  data;
- remove `SNAME` and `STATUS` from membership-row tracking.

The parent group remains a normal `CIRCUIT_TYPE` object and continues using the
existing circuit tracking and `PoolLight`/`PoolCircuit` creation paths.

## Home Assistant Design

### Momentary group actions

Extend `light.py`'s existing entity-service registration with:

- `color_sync` -> `PoolLight.async_color_sync()`.

The method is available through the service registry but validates at call time
that cached firmware's raw `sw_version` token is exactly `1.064` and its entity
is a `LITSHO` parent with exactly two distinct resolved `GLOW` children. This
state-changing evidence gate intentionally does not use the integration's
display/upgrade `parse_ic_version()` helper: prefixes, suffixes, or whitespace
were not captured and remain unsupported even if a semantic parser could
interpret them. The library repeats all validation from fresh raw reads.
Unsupported targets raise a translated
`light_group_command_unsupported` error before state-changing I/O.

Valid calls await `run_light_group_sync()` through a group-specific error
wrapper. Pre-write connection/read failures and explicit panel rejection use
`light_group_command_failed`. A dispatch with no response uses
`light_group_command_uncertain`. An acknowledged or observed-started action
whose lifecycle/final verification fails uses
`light_group_command_incomplete` and tells the user to inspect the lights.
`ICLightGroupError` phase fields, rather than a generic timeout assumption,
select the truthful translation.

Color Sync is an action, not a persistent Home Assistant effect. It does not
enter `effect_list`, and the entity does not invent an effect after a press.
Color Set and Color Swim are not registered because their local safety gates
failed.

Add service metadata and translations for all supported locales, following the
existing Capture/Thumper/Hold/Recall service pattern. Document that the service
call waits for the physical action lifecycle, 60-second post-terminal interval,
and final read and therefore normally blocks a calling script for roughly 96
seconds and can exceed 120 seconds at the timeout boundary. While it runs, new
object mutations through the same Home Assistant controller fail immediately
rather than being delayed; read updates continue. The physical panel remains
available for urgent control, with the explicit consequence that a projected
change can make Color Sync report incomplete.

### Member position selects

Do not create member-position selects. The deployed official client provided
no writer or finite option map, and membership-row `USE` was not proven as a
durable writable setting. Existing membership rows remain model-only objects
and never create entities.

## Data Flow

```text
Group service -> PoolLight -> pyintellicenter group command -> parent CIRCUIT
  -> fresh preflight + scoped subscription + pre-send tracker
  -> correlated acknowledgement + sender-side SYNC lifecycle
  -> 60-second post-terminal interval + required in-band final projection
  -> existing PoolLight state
```

## Error Handling

- Disconnected coordinators make entities unavailable through `PoolEntity`.
- Invalid firmware/target shape is rejected before network I/O; mixed prestates
  are rejected by the fresh preflight before the write.
- Pre-write failure, explicit rejection, uncertain dispatch, and
  acknowledged/started-but-incomplete failure become distinct translated
  `HomeAssistantError` messages.
- Empty, mixed-capability, missing, or unresolved group membership rejects
  commands before network I/O.
- Set and Swim are absent on both transports and rejected before any
  state-changing I/O if an internal compatibility boundary receives them.
- A `200` without authoritative completion is a protocol failure.
- Sync requires both post-watermark sender-side `SYNC` edges, a 60-second
  post-terminal interval, and one bounded in-band final read; missing edges,
  transient/late changes, or mismatched/collateral state are failures and are
  not retried.
- A timeout never triggers an automatic `STATUS=OFF` recovery because that
  could unexpectedly turn lights off. The translated error tells the user that
  the group may require a manual off/on clear.
- One controller-wide lifecycle drains already-started writes before Color Sync
  and then rejects every later case-insensitive `SetParamList` sent through the
  same controller, including public `send_cmd()`, direct changes, coalesced
  writes, and a second Sync. It never silently delays them through the long
  observation window.
- Command services never operate on a plain `CIRCGRP` group or ordinary light.

## Testing

### pyintellicenter tests

- real-hardware parent plus multiple membership-row aggregation;
- deterministic `LISTORD` ordering, including duplicate numeric and multiple
  negative/malformed-order tiebreaks;
- missing parent and missing child references;
- compatibility with legacy space-separated fixtures;
- color-capability detection against resolved children;
- exact mixed-case `SetParamList` serialization for Sync without `ACT` or
  `STATUS`, a realistic full correlated response shape, plus proof that no Set
  or Swim serializer is exposed;
- sender-side `SYNC` field and 60-second bound on both transports; split
  pre-send deadline/post-send watermark behavior including a WebSocket frame
  during send suspension; pre-write rejection of other raw firmware tokens,
  member counts/subtypes, and mixed prestates;
- invalid command/target rejection without network calls;
- empty, mixed, missing, and unresolved membership rejection;
- additive enqueue-sequenced observer behavior, notification between observer
  registration and write exclusion, notification before response retention,
  stale queued notification exclusion, and leading-order-independent lifecycle
  completion;
- observer-before-first-read bounded buffering, batched subscriptions with
  initialization validation, hardware-realistic optional circuit `PARENT`/`USE`
  and membership-row `USE` omission/key-echo/null-reference normalization at
  wildcard, subscription-initialization, and notification gates, strict required
  membership-row `PARENT` coverage in full responses and placeholder rejection
  whenever present in notifications, one-second settling, and a
  full matching normalized wildcard second preflight;
- fail-fast controller isolation against another group action, public mixed-case
  and uppercase `send_cmd()`, direct changes, and coalesced mutations, while
  read-only requests remain live;
- Sync all-off and all-on completion; no-leading-edge and no-terminal-edge
  rejection; 60-second post-terminal enforcement; transient target/action/
  collateral flip-and-restore rejection; final-read mismatch, disconnect/
  reconnect/captured-instance replacement/cancellation cleanup, no retry, and
  no optimistic mutation;
- collateral projection coverage for every circuit's required
  `OBJTYP`/`SUBTYP`/`STATUS` and normalized optional `PARENT`/`USE`, every
  membership row's required topology/optional normalized `USE`, group flags,
  and system mode while excluding legitimate dynamic telemetry;
- phase-aware error metadata for explicit rejection, uncertain dispatch,
  acknowledged lifecycle failure, and final-verification failure;
- no member-position helper or option-map API.

### intellicenter tests

- membership rows never create light or switch entities;
- parent `LITSHO` continues to create exactly one light entity;
- Sync service registration and exact controller calls;
- no Color Set or Color Swim service and no member-position select entities;
- ordinary lights, plain circuit groups, other firmware, non-two-member groups,
  and non-`GLOW` children reject action services;
- translated unsupported, pre-write failed, dispatch-uncertain, and
  acknowledged/started-incomplete failures;
- coordinator row tracking excludes unsupported `SNAME`/`STATUS`;
- coordinator row tracking does not promote `USE` or action flags to durable
  entity state;
- regression coverage for the hardware-shaped fixture from the issue comment.

Run targeted tests throughout development, then the full lint, format, type,
security, and pytest suites in both repositories. Finish with one snapshot/
restore live smoke test and independent adversarial reviews from `agy` and
Cursor `agent`.

## Documentation

- Explain that group on/off uses the existing parent light entity.
- Document Color Sync on TCP and WebSocket as a momentary entity service.
- State the initial firmware `1.064`, two-member `GLOW` eligibility boundary
  and roughly 96-second normal service duration.
- State that Color Set, Color Swim, and member-position selects are unavailable
  because their protocol gates did not pass.
- Correct any documentation that describes a `CIRCGRP` row as a complete group.

## PR and Release Topology

- pyintellicenter branch: `feature/issue-93-light-group-sync`, related to #93 but
  not closing the Home Assistant issue.
- integration branch: repository-local `feature/issue-93-light-group-sync`,
  closing #93 only for the verified capabilities named in the final PR
  title/body.
- Both branches start from their repositories' fetched `origin/main` commits in
  external isolated worktrees.
- Prefer existing stable generic controller primitives where they keep protocol
  details inside pyintellicenter. If the integration calls a new public helper,
  merge and release the library first, then update `manifest.json`,
  `pyproject.toml`, and `uv.lock` atomically to the first compatible version.
- Opening the feature PR does not authorize merging, publishing to PyPI,
  tagging, or releasing. Those are explicit maintainer checkpoints. The
  integration branch may be developed against the local library worktree, but
  its dependency lock and green PR wait for the published library release.
- Never use a Git branch dependency in the Home Assistant manifest and never
  leave the requirement compatible with a library version missing an imported
  API.

## Acceptance Criteria

- Parent circuits and membership rows are modeled according to captured
  hardware, with legacy fixture compatibility covered by tests.
- Sync ships on TCP and WebSocket only for firmware `1.064` groups containing
  exactly two distinct `GLOW` children, with a correlated acknowledgement,
  post-send-watermark lifecycle edges, a 60-second post-terminal interval,
  invariant projection, and authoritative final read.
- Set, Swim on both transports, and member-position selects remain absent and
  are rejected before state-changing I/O where applicable.
- No row-derived duplicate light or switch entities exist.
- Automated tests cover malformed data, unsupported targets, failures, dynamic
  discovery, and exact captured commands.
- Both repositories pass full verification, the hardware snapshot is restored,
  and all confirmed `agy`/Cursor findings are resolved or documented before PR
  handoff.
