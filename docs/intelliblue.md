# IntelliBlue delivery gate

IntelliBlue purifier entities and settings are not enabled. The owning request is
[pyintellicenter #103](https://github.com/joyfulhouse/pyintellicenter/issues/103),
tracked by [#188](https://github.com/joyfulhouse/intellicenter/issues/188).
The library's [evidence and proposed association contract](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/INTELLIBLUE.md)
records exact app anchors, required captures, firmware/hardware unknowns and
cloud/Bluetooth questions. The contract is a design handoff, not an available API.

## What can be observed today

Downloaded integration diagnostics include discovered objects with their raw
type, subtype and properties, system software version and connection state.
They can help identify an unfamiliar chemistry object, but do not identify it as
IntelliBlue or certify complete subscriptions or field freshness. Preserve raw
unknown values when reporting evidence. Review and sanitize downloaded data
before sharing; built-in redaction is not a complete purifier capture sanitizer.

The existing [restriction context](restriction-context.md) explicitly reports
`purifier_context_unsupported`. It does not create purifier entities or infer
that pumps are unrestricted. Communication loss excludes cached context;
connected-but-stale fields remain unverified. No restriction-context logic is
duplicated by this workstream.

## Requirements before enabling entities

1. Validate the exact chemistry subtype and the source and complete mapping of
   raw `OPSTATE` values with panel discovery/read/notification evidence. Associated
   pump state in app code does not by itself prove purifier-object state.
2. Validate body, pump and group references, including missing/stale references,
   membership changes, removal, reconnect and communication failure/recovery.
   Consume the library's eventual association API; do not guess relationships.
3. Establish supported panel/purifier/pump firmware and topology. The app checks
   caller-supplied thresholds and VSF/FLOW eligibility; its rollout flag does not
   establish local hardware support. Determine cloud registration and Bluetooth
   commissioning separately from ongoing local reads/offline behavior.
4. Add read-only state/diagnostic entities with stable IDs and lifecycle tests
   for unknown states, missing associations, stale data and transport loss.
   Keep communication faults distinct from ordinary protected operation. Keep
   purifier context separate from measured pump state and command enforcement.
5. Expose settings only with validated units, bounds, accepted readback and
   separately authorized observed behavior. The app's 02:00 cleaning default
   does not validate a setting. No winterize/clean/regenerate action follows
   from a state label or command acknowledgement.

The current evidence review found no panel captures in either repository,
related issue comments or the open app-analysis PRs (#108/#189). No configured
device resources were available in this sandbox and no live actions were taken.
The full implementation remains blocked on those specific inputs, not on merge
permission. Existing diagnostics and explicit unknown restriction context remain
the supported behavior. This documentation requires no new library dependency,
unpublished pin, package release or production deployment.
