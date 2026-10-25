# Physical heater activity evidence limits

Issue: [#183](https://github.com/joyfulhouse/intellicenter/issues/183).
This bounded correction preserves existing heater diagnostic entity IDs.

## What the entities mean

Body water-heater `heating_status` describes panel-reported body activity,
separate from the selected operation. A body reporting heating does not prove
which physical source is operating. `HEATER` selects a source; HCOMBO uses
body `MODE` and can leave `HEATER=NULL`. Solar preference and multiple sources
make selected-source attribution especially ambiguous. Neither selection,
temperature demand, nor body activity verifies gas combustion.

The physical heater diagnostic now reports:

| Available observations | Diagnostic state |
| --- | --- |
| Every relevant body is explicitly off or on with decimal zero `HTMODE` | off |
| Any relevant body reports nonzero `HTMODE`, including cooling | unknown |
| Missing/malformed activity, unknown body status, missing/malformed heater `BODY` association, no known relevant bodies, or an associated body absent from the model | unknown |

Relevant bodies are the heater's live `BODY` associations plus any body that
selects its object ID. A body selecting another source is still relevant when
associated with this heater: it might be solar-preferred, hybrid, or switching
sources. An idle body cannot mask another body's unknown activity. Decimal
activity validation matches the bounded body-activity handling; arbitrary
strings must not become heating merely because they differ from `"0"`.

There is currently no evidence-backed positive physical-source predicate, so
this diagnostic does not report on. Active cooling also remains unknown because
body selection and a heater's `COOL` setting do not establish active physical
source identity. Existing body activity and climate entities retain their
current behavior. Automations requiring physical firing should account for
unknown and await source evidence.

## Evidence and subscriptions

The current issue has no hardware captures. The 3.12.0 production soak observed
no active heater cycle and explicitly excludes physical source attribution.
The app audit in [PR #189](https://github.com/joyfulhouse/intellicenter/pull/189)
is static evidence, not device validation. The library describes `HTSRC` as a
source field but that comment
does not establish its values or behavior through real transitions. This fix
does not interpret `HTSRC`, add subscriptions, or claim flame confirmation.

Existing body `STATUS`, `HTMODE`, and `HEATER` subscriptions and dependency
routing cover every input to this diagnostic. Heater `BODY` structural changes
already rebuild dependencies. No coordinator or protocol-library edits are
needed. In particular, changing selected source reevaluates the diagnostic
but cannot convert unknown body heating into a physical firing claim.

### Follow-up evidence review (2026-10-25)

The current repository histories, #183 and merged PR #197, the production
soak report, and the app-analysis branches were reviewed again. No capture
establishing physical-source transitions was found. Configured MCP resource
and resource-template catalogs were empty; repository-memory recall was not
exposed in this session. No live panel was contacted.

Two existing leads are useful but insufficient:

- [pyintellicenter #15 user snapshots](https://github.com/joyfulhouse/pyintellicenter/issues/15#issuecomment-3779171689)
  contain `HTSRC=H0001`, `HEATER=H0001`, `HTMODE=4`, `MODE=5` and `STATUS=ON`
  before and after setpoint edits. They establish that a panel returned those
  fields together. They do not include source changes, timestamps, notify
  frames, confirmed equipment subtype, or independent activity observations.
  They cannot establish whether `HTSRC` is selected, requested or active source.
- [pyintellicenter app analysis](https://github.com/joyfulhouse/pyintellicenter/blob/docs/pentair-apk-reverse-engineering/docs/PENTAIR_APP_LOCAL_PROTOCOL.md)
  records body `HTSRC` in query/subscription templates (Hermes function 79341,
  offset `0x0132ed4b`) and dashboard subscription builders (79647,
  `0x0133c34a`). Heater templates also request `READY`, `STATUS`, `HTMODE`,
  `HEATING` and `COOL`. Requesting these fields does not prove that a firmware
  returns them, sends timely notifications, or assigns physical-source semantics.

There is consequently no evidence-backed reason to extend production
subscriptions or change the diagnostic predicate. The integration continues
to use published pyintellicenter 0.3.1 without a library API change or release.
Additional tests use synthetic model updates, not captured hardware fixtures.
They cover all four HCOMBO selections and retained source fields while activity
becomes active, missing, or idle.

Source fields can remain stale across a partial update and must never turn an
active or incomplete body into a positive physical-source claim. The model
does not provide a per-field age guarantee for these body inputs; an unchanged
cached `STATUS`/`HTMODE` value is not proof of a fresh measurement. Establishing
freshness after reconnect or a dropped notification is part of the capture
gate below, not a timeout inferred from synthetic tests.

## Remaining capture matrix

Capture synchronized, sanitized panel/app observations and raw read/notify
frames for body `STATUS`, `HTMODE`, `HEATER`, `MODE`, `HTSRC`, heater `BODY`,
subtype, and `COOL`. Retain timestamps, firmware versions, consistent anonymized
object IDs and associations, and distinguish missing fields from explicit NULL.
Request observations from an operator's normally authorized operation; this
implementation does not run equipment or require production credentials.

| Installation / transition | Evidence needed |
| --- | --- |
| HCOMBO Gas Only / Heat Pump Only / Hybrid / Dual | Idle, startup delay, active operation, satisfied demand, shutdown; HEATER=NULL behavior |
| Reversible heat pump | Idle, heating, cooling, mode reversal, and shutdown |
| Gas plus solar / solar-preferred | Solar available/unavailable, fallback, and actual source changes while selection stays fixed |
| Multiple physical sources and shared pool/spa | Each source alone, simultaneous operation where supported, and body/source switching |
| Reconnect / incomplete updates | Initial snapshots, attribute backfill and notify ordering across each transition |

Correlate reported source values with independently observed physical equipment
activity. Document what that observation establishes: an app icon alone cannot
verify a burner flame. Establish whether source telemetry is exclusive or a
bitmask/list and whether it is timely and reliably subscribed before defining
any positive per-device predicate. Keep #183 open until this investigation is
reviewed with hardware evidence.
