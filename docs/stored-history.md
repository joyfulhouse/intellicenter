# Stored panel history and Home Assistant ingestion

Tracking: [library #101](https://github.com/joyfulhouse/pyintellicenter/issues/101)
and the stored-history entry in [#188](https://github.com/joyfulhouse/intellicenter/issues/188).
Assessment date: 2026-10-25.

The integration records live entity observations after setup. It does not
retrieve panel history, restore earlier Recorder states, or import panel
statistics. Local `ReadHistoryMessage` availability, timestamps, units, series
identity, retention, and completion semantics remain unvalidated. The app's
static request builder establishes a research lead, not local support.

See the library's [evidence requirements](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/STORED_HISTORY.md)
before adding a consumer. Keep unknown support distinct from confirmed lack of
support. Existing live sensors and their state classes do not establish how
historical panel values were sampled or aggregated.

## Supported statistics surface assessment

The [Home Assistant 2026.10.0 Recorder implementation](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/recorder/statistics.py)
provides `async_add_external_statistics(hass, metadata, statistics)` for hourly
external statistics. It validates a `domain:object_id` statistic ID and requires
the metadata source to match that domain. Its `async_import_statistics` surface
requires Recorder-owned metadata (`source == recorder`) instead. These distinct
ownership rules must be respected. Recheck the API and metadata requirements
against the integration's supported HA versions before implementation.
In this HA version, imported start timestamps must be timezone-aware and aligned
to the top of the hour; Recorder normalizes them to UTC. Metadata must also
account for the `mean_type` and `unit_class` requirements taking effect in
2026.11. A successful queue submission is not evidence of a completed import.

External statistics are a possible downstream deliverable once source semantics
are known. They are not arbitrary historical entity states and do not restore
Recorder state history. Calling `async_write_ha_state()` with an old panel value
would publish it as a current observation, so the live coordinator/entity update
path must not be used for backfill. Direct writes to Recorder database tables
would bypass its supported ingestion and ownership rules.

## Decisions required before importing

| Area | Required decision/evidence |
|---|---|
| Eligibility | Identify numeric series that support meaningful hourly statistics. State changes, alerts, and quality flags cannot automatically become measurement statistics. |
| Identity | Stable integration-owned IDs scoped to the panel and source series; avoid collisions with live entity statistics and preserve identity through reconnect and entity renames. |
| Time | Validated UTC timestamps and interval boundaries, DST behavior, and hourly aggregation rules for irregular or partial samples. Never average averages without known interval weights. |
| Units and counters | Validated historical units, conversion policy, measurement versus cumulative semantics, resets/rollovers, and valid mean/sum/min/max fields under the chosen HA API. Live temperature mode is insufficient to interpret old samples. |
| Completeness | Explicit coverage and gaps, bounded retention, terminal/page semantics, duplicate/conflict policy, and checkpoint behavior. Missing samples must not be filled with zero or carried forward silently. |
| Lifecycle | Opt-in scope, import bounds, cancellation/unload, reconnect, restart and repeated-import behavior; test overlap with existing statistics and failure recovery. |

Only then design a bounded library-to-statistics adapter and test it against
supported HA versions, including metadata validation and import failures. A
read-only display would still need validated timestamps, series, units and
partial-result semantics, even if it did not aggregate statistics.

No ingestion service, entity, Recorder write, library version change, or package
publication is justified by the evidence currently available. Library #101 and
the overall #188 tracker remain open; this assessment records the remaining
dependency and does not claim completed history restoration.
