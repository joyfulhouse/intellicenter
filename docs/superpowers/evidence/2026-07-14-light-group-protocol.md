# Evidence: Light Group Protocol Discovery (Issue #93)

**Date:** 2026-07-14 to 2026-07-15
**Firmware:** `1.064`
**Scope:** Color Sync, Color Set, Color Swim, and light-group member positioning

This record contains only sanitized protocol facts. It deliberately excludes
network endpoints, object and equipment identifiers, friendly names, browser
headers and cookies, message identifiers, credentials, and raw frames.

## Baseline and Target Topology

Independent passive reads over TCP and WebSocket produced the same baseline:

- the controller was in `SERVICE=AUTO`;
- exactly one complete `CIRCUIT/SUBTYP=LITSHO` parent qualified for discovery;
- two `CIRCGRP` membership rows referenced that parent;
- both rows resolved to distinct `CIRCUIT/SUBTYP=GLOW` children; and
- the parent, rows, and children were identical across transports.

The non-empty, fully resolved membership remained mandatory throughout
discovery. No result establishes that the `LITSHO` subtype alone is a safe
capability predicate.

## Official Web App Actions

The deployed official client asset inspected during discovery was
`bundle.web.js` with SHA-256
`933e2fc35fd5e5fe26477f0199873bedaf4c266d510f6e8259e3684da18317fd`.
Each accepted official run used the exact mixed-case command
`SetParamList`, contained one parent object, and supplied only the dedicated
action parameter shown below. Neither `ACT` nor `STATUS` appeared in an action
request.

| Action | Accepted runs | Parent params | Response |
| --- | --- | --- | --- |
| Sync | 3 and 4 | `{"SYNC": "ON"}` | correlated `200` |
| Set | 2 and 3 | `{"SET": "ON"}` | correlated `200` |
| Swim | 1 and 2 | `{"SWIM": "ON"}` | correlated `200` |

All six accepted runs produced the same semantic lifecycle, although the
leading notification order and even the action-active attribute depended on
the receiving client:

1. the official browser connection reported parent `SWIM=ON`, while the
   simultaneous local observer reported parent `SYNC=ON`;
2. the parent and both referenced children reported `STATUS=ON`; and
3. the official browser later reported parent `SWIM=OFF`, while the local
   observer later reported parent `SYNC=OFF`.

The field-name difference was repeatable for every accepted Sync, Set, and
Swim run. Completion therefore cannot depend on a universal action-active key
or a fixed leading order. A production contract must establish the sender-side
field for its own subscription path, observe its post-command `ON` edge, and
later observe the matching `OFF` edge. A `200` response or an initial action
echo alone is not completion.

Fresh reads after each accepted action found only three persistent changes:
the parent and its two children changed from `STATUS=OFF` to `STATUS=ON`.
Membership rows and all other inventory remained unchanged. Each accepted run
was restored through the official UI and checked twice against its starting
snapshot. Measured browser action-active durations were 36.199 and 36.370
seconds for Sync, 102.975 and 103.112 seconds for Set, and 75.719 and 75.413
seconds for Swim. The official observer window was 180 seconds. These two
runs per action establish firmware-specific observations, not a general
lighting-program duration.

Official Sync runs 1 and 2 and Set run 1 were excluded because an unrelated
generic circuit changed during their observation windows. Those runs cannot
prove the collateral-change invariant and contributed no protocol conclusion.
The later accepted runs started from a restored baseline and repeated the
official contract twice per action.

## Member-Position Gate

The exact official client bundle exposed no member-position writer:

- light-group position chips were hidden;
- membership-row `USE` was neither read nor written by the UI; and
- no membership-row `ACT` or `LISTORD` write existed.

Consequently there was no official operation from which to establish a safe
writable field, a durable readable field, or a finite option table. No direct
protocol write was guessed. Member-position replay was not performed, and the
member-position helper and Home Assistant selects are omitted.

## Local Replay Results

Each initial replay began with the parent and both children `STATUS=OFF`, sent
the same mixed-case command and one-object parameter payload once over a local
transport, and used a 60-second experimental gate. Message identifiers and the
cloud/local transport envelope necessarily differed, so this was semantic
replay rather than byte-for-byte browser replay. A timed-out state-changing
request was not retried. The accepted official Swim timings later proved that
60 seconds was not a safe universal production bound.

| Action | TCP | WebSocket | Decision after initial replay |
| --- | --- | --- | --- |
| Sync | correlated `200`; five target pushes completed the local-observer lifecycle | correlated `200`; the same five-push lifecycle completed | advance on both transports |
| Set | correlated `200`; four leading target pushes, no terminal local `SYNC=OFF`, then persisted cross-group action flags | correlated `200`; the same four-push failure and persisted action flags | omit on both transports |
| Swim | correlated `200`; four leading target pushes; a 60-second fresh read found all action flags `OFF` and all three target statuses `ON` | correlated `200`; four leading target pushes, then timeout with action flags stuck `ON` | advance TCP to a longer same-connection run; omit WebSocket |

Each successful Sync observer sequence contained parent `STATUS=ON` and
`SYNC=ON` in either leading order, both child `STATUS=ON` updates, and later
parent `SYNC=OFF`. Each failed Set and WebSocket Swim sequence contained the
same four leading updates but no terminal `SYNC=OFF`. TCP Swim also contained
those four leading updates; its 60-second fresh read appeared to establish only
the missing terminal state. The later 180-second run below disproved that
provisional final-state conclusion. A read cannot substitute for a missing
positive post-command onset.

The Set failure left `SYNC`, `SET`, and `SWIM` persisted as `ON` on the target
and on another group with `SUBTYP=CIRCGRP`. The WebSocket Swim failure left the
same action flags stuck `ON`. The official UI completed Set cleanly, so this
does not prove that the official Set action is intrinsically unsafe. It proves
that the reproduced local request path is not safe or sufficiently understood
for production.

## Same-Connection Sender-Side Results

A production-shaped harness subscribed and sent on the same connection, armed
its observer before the single write, retained notifications that preceded the
acknowledgement, observed for 180 seconds, and then performed fresh full
inventory reads. It repeated the complete service, topology, action-flag, and
target-prestate preflight immediately after subscription settling.

| Action | Transport / prestate | Ack | Sender-side lifecycle | Fresh final state | Decision |
| --- | --- | --- | --- | --- | --- |
| Sync | TCP / all off | `200` at 0.002145 s | `SYNC=ON` at 0.219557 s; parent and children `STATUS=ON` at 1.255901–1.258996 s; `SYNC=OFF` at 35.286805 s | only the parent and two children changed to `STATUS=ON` | pass |
| Sync | TCP / all on | `200` at 0.002399 s | `SYNC=ON` at 0.275896 s; `SYNC=OFF` at 36.238773 s; no status edge was required or emitted | full inventory equaled the all-on baseline | pass |
| Sync | WebSocket / all off | `200` at 0.004273 s | `SYNC=ON` at 0.852700 s; parent and children `STATUS=ON` at 0.852716–0.852729 s; `SYNC=OFF` at 35.852674 s | only the parent and two children changed to `STATUS=ON` | pass |
| Sync | WebSocket / all on | `200` at 0.010514 s | `SYNC=ON` at 0.765173 s; `SYNC=OFF` at 35.773954 s; no status edge was required or emitted | full inventory equaled the all-on baseline | pass |
| Swim | TCP / all off | `200` at 0.008995 s | `SYNC=ON` at 0.593273 s; all target statuses `ON` at 0.602877–0.602899 s; `SYNC=OFF` at 74.567605 s; both children reverted to `STATUS=OFF` at 83.613525–83.614324 s | parent `STATUS=ON`, both children `STATUS=OFF` | fail and omit |

The local sender-side active field was `SYNC` for both transports and both
commands; the browser connection's different `SWIM` field therefore cannot be
used by the library waiter. No run produced a collateral-group action-flag
edge. Each passing Sync run had either exactly the expected three target
status deltas from an all-off baseline or no persistent delta from an all-on
baseline.

The TCP Swim result is decisive. Its terminal `SYNC=OFF` edge was followed
about nine seconds later by a mixed target state, so neither the terminal edge
nor the earlier 60-second clean read represented a stable supported outcome.
Swim was removed from the candidate matrix and no Swim-from-on write was
performed. This limits further state-changing discovery after a supported
contract had already failed.

Between the first sender-side Sync series and its official restore, one
unrelated generic circuit changed compared with the day-start snapshot. The
settled baseline/final inventory stored inside each action run proves that the
change did not occur during those action windows. Discovery nevertheless
paused, restored the target by role, and established a new quiet gate: TCP and
WebSocket snapshots at both ends of a 120-second interval were all identical
and contained no pushes. The subsequent WebSocket Sync and TCP Swim runs used
that baseline and retained their own per-run collateral comparisons.

## Production Contract Result

The same-connection gate passed only for Sync over TCP and WebSocket. The
implementation contract is:

- serialize the exact mixed-case `SetParamList` request with one fully
  validated parent object and the dedicated `{"SYNC": "ON"}` parameter;
- require a correlated `response == "200"`;
- require firmware `1.064`, `SERVICE=AUTO`, exactly two distinct resolved
  `GLOW` children, every relevant group action flag `OFF`, and a uniform
  all-off or all-on target prestate;
- establish scoped subscriptions, wait one second for initialization to settle,
  then repeat the entire fresh preflight and require its projection to match the
  first before the write;
- assign enqueue-time notification sequence numbers, start the absolute
  deadline immediately before transport initiation, and capture the causal
  onset watermark immediately after synchronous TCP write returns or awaited
  WebSocket send completes; retain pre-response notifications but never count
  a frame processed during WebSocket send suspension as onset;
- require a positive post-command/post-send-watermark `SYNC=ON` edge and start
  the absolute completion deadline at the pre-send dispatch boundary;
- require the later `SYNC=OFF` edge within a Sync-specific 60-second bound;
- enforce the captured transition invariants from dispatch start onward: an all-on
  target never leaves `ON`; an all-off target never returns to `OFF` after each
  object reaches `ON`; normalized optional target `USE`, required `SET` and
  `SWIM`, every unrelated circuit `STATUS`/normalized optional `USE`, group
  topology, and system mode never deviate from baseline;
- continue observing through a 60-second post-terminal quiet interval, then
  perform one in-band fresh read that requires the target parent and children
  `STATUS=ON`, all group flags `OFF`, every unrelated circuit
  `STATUS`/normalized optional `USE` unchanged, the circuit
  identity/type/subtype/normalized optional parent projection unchanged, and
  all membership topology/normalized optional `USE` and system mode unchanged;
- keep action flags as internal momentary monitoring data, separate from
  persistent Home Assistant effects or entity state; and
- reject Set and Swim, other firmware, other member counts/subtypes, mixed
  target prestates, incomplete topology, and unsupported action tokens before
  state-changing network I/O.

The 60-second value is Sync-specific, not the disproved universal experimental
gate: all six accepted official/sender-side Sync terminal observations were at
or below 36.370 seconds. The 60-second post-terminal interval is also within
the more than 143 seconds of clean post-terminal observation in every
same-connection Sync run. It is intentionally much longer than the single
9.045920-second late Swim failure. A missing onset or terminal edge is never
replaced by a fresh read.

The exact official request disproves the proposed
`{"ACT": token, "STATUS": "ON"}` shape. Production code must not serialize
that proposal.

## Restoration and Final Invariants

Every failed replay state was restored through a freshly reloaded official UI
using the exact parent `{"STATUS": "OFF"}` operation. Each restore capture
contained exactly one mixed-case `SetParamList` write, one parent object, and a
correlated `200`. Earlier final reads matched the day-start baseline exactly.
After the unrelated between-run circuit transition described above, both the
WebSocket Sync restore and the mixed TCP Swim restore matched the new quiet
baseline exactly over independent TCP and WebSocket reads. The controller
remained in `SERVICE=AUTO`, membership did not change, every action flag was
`OFF`, and the parent and both children were `STATUS=OFF`.

## Staged Scope and Limitations

The production candidate is Sync on TCP and WebSocket only. It includes no Set
or Swim action and no member-position selects.

These conclusions are intentionally narrow:

- they were established on firmware `1.064` and one complete two-member
  `LITSHO`/`GLOW` topology;
- Sync passed from both uniform all-off and uniform all-on prestates on each
  supported transport; mixed prestates remain unproven and must be rejected;
- TCP Swim was tested only from all-off and failed its stable final-state gate;
  no Swim prestate is supported;
- `INTELLI`, `MAGIC2`, other member counts, and other firmware may still be
  modeled by read helpers but are not eligible for this initial Sync writer;
- official captures establish command semantics and firmware-specific
  timings, not a general lighting-program duration;
- a fresh read may verify Sync only after both sender-side edges and the
  60-second post-terminal interval; it cannot replace a missing lifecycle
  edge; and
- an acknowledgement is never treated as proof of completion or safety.
