# Remaining light-group actions: evidence handoff

Tracking: [library #100](https://github.com/joyfulhouse/pyintellicenter/issues/100)
and [HA #188](https://github.com/joyfulhouse/intellicenter/issues/188).

## Delivered scope

Home Assistant exposes `intellicenter.color_sync` on eligible light-group
parents. The library owns the firmware `1.064`, exactly two distinct
`CIRCUIT/GLOW` children, TCP/WebSocket capability gate and fresh readiness checks.
The integration awaits `run_light_group_sync()` and maps phase-aware failures;
an acknowledgement does not establish completion or a physical lighting result.

[Library PR #109](https://github.com/joyfulhouse/pyintellicenter/pull/109)
already added immutable per-action capability decisions and offline diagnostics.
Reuse that implementation rather than adding a second action runner. Its
[evidence and capture contract](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/LIGHT_GROUP_ACTIONS.md)
documents the remaining device requirements. The diagnostic fixtures are
regression reconstructions, not newly captured device evidence. Passing an
offline review cannot enable another action, firmware, or topology.

## Why Set, Swim, and broader Sync remain unavailable

The [device investigation](superpowers/evidence/2026-07-14-light-group-protocol.md)
and [#93 closing record](https://github.com/joyfulhouse/intellicenter/issues/93#issuecomment-4988595557)
remain authoritative:

| Observation | Consequence |
| --- | --- |
| Browser observed `SWIM=ON/OFF`; local initiating connections observed `SYNC=ON/OFF` for the same operation. | Observer/UI fields cannot replace initiating-connection onset and terminal evidence. |
| Local Set on both transports and WebSocket Swim lacked a terminal edge and persisted action flags, including cross-group flags. | A successful request or app-side flag reset cannot establish a completed local operation. |
| TCP Swim acknowledged at 0.008995 s, reached terminal at 74.567605 s, then children reverted OFF at 83.613525 and 83.614324 s. | The apparent terminal and earlier clean read did not establish stable state; final state was parent ON, children OFF. |
| Validated Sync used firmware `1.064` and two GLOW children only. | Other firmware, member counts, and light subtypes remain unsupported. |

Pentair Pool 4.2.21/build 21615 static handlers 80713/80714/80715 construct
selected-parent `SET`, `SYNC`, and `SWIM` writes. That corroborates request
construction only. App model normalization to OFF supplies no device completion
evidence. No per-member position writer or finite option set has been established.

## Required evidence before an HA action can be added

A separately authorized device investigation must retain exact firmware,
topology, transport, subscription path, and applicable prestates for repeated
runs. It must correlate the initiating connection's request, enqueue watermark,
acknowledgement, positive onset and matching terminal edge with another observer,
authoritative reads, physical results, and final/restored state. Resolve both the
client-dependent signal mapping and TCP Swim's late child reversion explicitly.
Include concurrent/collateral activity, service/topology changes, cancellation,
connection loss, and uncertain outcomes. Do not retry an uncertain mutation.

Preserve Sync's same-connection lifecycle, exclusive mutation lease, 60-second
dispatch deadline, full 60-second post-terminal observation, final authoritative
projection and phase-aware errors while investigating. Changing a timeout alone
does not resolve Swim's stable-state failure. Any future Set/Swim lifecycle needs
its own validated timing and final-state contract.

Only after the library establishes and tests a supported contract should HA add
an awaited action with failure propagation and capability/lifecycle regressions.
Use a published compatible library dependency when one is needed. Existing Sync
needs no dependency change for this handoff.

The repository and GitHub evidence review for #100 found no newer device record
superseding these failures, and this sandbox has no configured MCP evidence
resources. No live panel writes or deployment were performed. Library #100
remains open for the device gate; #188 records this investigation outcome without
claiming delivery of Set/Swim or closing the overall tracker.
