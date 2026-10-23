# Pentair Android App Local Protocol Findings

Static analysis on 2026-10-20 examined `com.pentair.pentairhome`, distributed
as Pentair Pool 4.2.21 (build 21615). Its Hermes bytecode was disassembled and
decompiled, and its Android resources and DEX code were decoded. No app/device
session or live panel commands were used in this investigation.

The [capability audit](pentair-app-capability-audit.md) covers functionality
gaps, hidden/conditional features, and unresolved development leads.

The [protocol report](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/PENTAIR_APP_LOCAL_PROTOCOL.md)
is maintained with the protocol library and includes artifact hashes,
reproducible tool commands, bytecode
function IDs/offsets, reconstructed JSON requests, and evidence limitations.
Its [APK analysis workflow](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/APK_REVERSE_ENGINEERING.md)
explains extraction, tool setup, call-path tracing, and decompiler pitfalls.

## Findings Relevant to the Integration

| Area | App evidence | Integration consequence |
|---|---|---|
| Discovery | `_http._tcp.local.` scan; resolved names containing `Pentair` | Supports the existing local discovery approach; service type does not mean raw TCP/6681 is HTTP |
| Transport | Local `ws://<panel-ip>:6680`; JSON WebSocket text messages | The protocol library already supports WebSocket as well as TCP/6681; the app's local URL constructor is distinct from its cloud credential path |
| Local access | Permission-record reads and passcode/role UI handling | Do not claim all local devices have identical authentication requirements; sanitize permission responses |
| Connection health | 8-second clock-read heartbeat with a 7-second watchdog | App policy, not a required polling cadence for Home Assistant |
| Reconnect | Local reconnect path emits a resubscription event | Useful reference when diagnosing state that stops updating after reconnection |
| Body temperature | `LSTTMP` appears in both body snapshots and subscriptions | Supports keeping last-known temperature distinct from live `TEMP` |
| Light actions | Selected-object writes set one of `SET`, `SYNC`, `SWIM` to `ON` | Confirms the payload family; does not expand tested firmware/topology coverage or prove physical completion |
| Light model | App normalizes action flags to `OFF` in its own model | App UI state is not evidence of a panel terminal notification |
| Firmware | `_5451.IN` install/decline builders and progress fields | Candidates for further schema validation; no firmware behavior was changed |
| FDR/FDP events | `_FDR.EVENTSTATUS` / `EVENTID` feed an event banner and scheduled-event details navigation | Separate feature-gated event workflow, not firmware-update progress |
| Alerts | `GetStatusMessageFlags` / `SetStatusMessageFlags` templates | Alert-setting operations; not established as active-delay status |
| History | `ReadHistoryMessage` builder plus date-range and response handling | Investigate local availability and historical series before proposing HA backfill |
| IntelliBlue | Feature-gated hybrid-purifier setup, pump associations, and state classification | Additional equipment family; provisioning includes Bluetooth/registration paths |
| Configuration | Sensor calibration, clock, manual priority, and conditional solar-relay save paths | Separate configuration opportunities from existing read-only diagnostics |

## Existing Protocol Gates

This analysis found no distinct transient system-delay cancellation operation
in the inspected local builders. It does not resolve the active-delay schema,
and it does not authorize substituting persistent delay settings for a cancel
action. Preserve the existing
[system-delay evidence requirements](superpowers/specs/2026-07-14-system-delay-status-cancel-design.md).

The light action builders provide independent static evidence for the known
request shape. They do not establish Color Set/Swim restoration semantics,
concurrent-action behavior, or support for additional firmware/topologies.
Keep the [existing light-group device evidence](superpowers/evidence/2026-07-14-light-group-protocol.md)
separate from what the app merely constructs.

These changes document the protocol findings; they introduce no production
code, entities, polling, or capability claims based solely on app templates.
