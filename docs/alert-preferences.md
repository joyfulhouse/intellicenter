# Panel Alert Preferences

Panel notification-preference configuration entities and actions are not yet
available. The required protocol support is tracked in
[pyintellicenter #102](https://github.com/joyfulhouse/pyintellicenter/issues/102),
with the detailed evidence and offline policy in the
[library report](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/ALERT_PREFERENCES.md).
The alert-preference entry in [#188](https://github.com/joyfulhouse/intellicenter/issues/188)
tracks this dependency; it does not imply that preference controls have shipped.

The existing Chemistry Alert and individual chemistry problem sensors report
active fault state. They remain useful independently of notification settings.
Changing a future notification preference must not acknowledge, suppress, or
clear those sensors. Transient delays and delay cancellation are separate work.

## Why Controls Are Unavailable

Static Pentair Pool 4.2.21 app evidence names `GetStatusMessageFlags` and
`SetStatusMessageFlags`, configurable/critical metadata helpers, and bulk
enable/disable exports. Exact populated arguments, device applicability,
critical/unknown flag behavior, and independent readback have not been validated.
An acknowledgement alone would not establish that a preference changed.
The [app audit PR #189](https://github.com/joyfulhouse/intellicenter/pull/189)
and owning library issue record the provenance and limits of this evidence.

No preference controls, guessed flag defaults, external metadata fetches or
new services are introduced while these contracts remain unknown. The current
published library requirement remains sufficient for the existing integration;
do not pin to an unpublished release to expose a proposed API.

## Requirements for Configuration Entities and Actions

Once a validated library API is published, the integration must:

- Create configuration entities only for explicit supported device/schema/flag
  combinations. Use stable device and flag identifiers for unique IDs; metadata
  labels must not determine identity. Missing support is unknown, not disabled.
  Critical and unrecognized flags must not become writable options.
- Await targeted updates and fresh verified readback. Surface rejection,
  preservation failures, stale baselines and uncertain outcomes to callers;
  never report success from an acknowledgement or optimistic local state.
  Bulk actions require separate evidence for critical/unknown flag preservation.
- Mark preference state unavailable on panel disconnect and require fresh
  preference reads after reconnect. Metadata caches cannot establish current
  panel state. Last-known descriptions may be retained with explicit staleness;
  missing/incompatible metadata must not reset values or enable writes.
- Keep metadata failure isolated from ordinary integration setup and active
  chemistry faults. Reconcile supported options when device/schema changes
  without reassigning entity identities or retaining writable stale options.
- Test published-library compatibility, unsupported firmware, unknown flags and
  schema, failure propagation, readback mismatch, offline metadata, disconnect
  during updates, reconnect freshness and entity lifecycle before delivery.

## Exact Remaining Evidence Request

Provide the app argument/response trace and sanitized correlated panel reads
identifying model, firmware, transport, target device and schema, together with
metadata provenance and critical/configurable flag mapping. A separately
authorized targeted update must demonstrate an independent before/after read
that preserves unrelated, critical and unknown flags, including rejection and
disconnect/mismatch outcomes. Establish patch versus replacement semantics and
cross-client conflict handling. This report does not authorize new live panel
mutations; implementation and merge authorization alone is insufficient for
those tests. Keep #102 open until its remaining device gates are satisfied.
