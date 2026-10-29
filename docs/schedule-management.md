# Panel schedule management

Status as of 2026-10-25: existing schedule enable switches and running sensors
remain available. Panel-resident create/edit/delete actions and forms are
blocked on the validated library contract in
[pyintellicenter #99](https://github.com/joyfulhouse/pyintellicenter/issues/99).
This is the schedule workstream of [#188](https://github.com/joyfulhouse/intellicenter/issues/188),
not completion of the overall tracker.

## Current behavior and evidence limit

`PoolSchedule` switches write existing schedules' STATUS as ON/OFF and retain
their current unique IDs and disabled-by-default behavior. The running sensor
uses ACT, a distinct observation. Missing/malformed states remain unknown.
Circuit/day/time/heating details are observations, not an editable schema.
Time getters return panel values unchanged, without timezone conversion.

The Pentair Pool app contains schedule creation, parsing and deletion paths,
but static builders do not establish firmware support or a safe HA form.
The issue, repository history and app-analysis PRs contain no qualifying
schedule mutation round-trip capture. See the library's
[evidence matrix and capture requirements](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/SCHEDULE_MANAGEMENT.md)
for exact reproduction anchors and missing evidence. No new live writes were
performed for this workstream.

## Delivery requirements

1. Qualify firmware-specific create/edit/delete APIs in the library first.
   Resolve TIME/TIMOUT versus START/STOP, weekday encoding, overnight rollover,
   panel timezone/DST and sun-relative behavior, and heating references/units.
   Vacation configuration requires separate established semantics; the existing
   vacation on/off switch does not establish dates or duration.
2. Once a compatible library is published through an authorized release, expose
   actions with suitable forms for supported operations only. Select the config
   entry and panel object explicitly; names alone are ambiguous. Use capability
   validation for time expressions, circuit/body/heater references and optional
   heating fields. Do not accept arbitrary protocol keys in a form.
3. Await the library operation and propagate rejection and unavailable/unsupported
   errors as actionable HA errors. An uncertain create needs reconciliation and
   explicit resolution, not a retry button that blindly sends another create.
   An acknowledgement is not confirmation that equipment ran.
4. Let observed model membership and subscriptions create/retire entities through
   the existing lifecycle. Keep unique IDs of existing schedule switches/sensors;
   edits must not replace them. Do not optimistically invent a schedule or remove
   one after an unconfirmed delete. Preserve unknown fields and unknown state.
5. Test supported/unsupported firmware, field validation, timezone differences,
   rejection, uncertain outcomes, concurrent creates, reconnect, subscriptions,
   removal and identity preservation against the actual library interface.
   Run the published-library contract test and matching local-library tests before
   shipping a cross-repository feature; do not pin an unpublished version.

No CRUD service or form is registered by this documentation increment. Existing
synthetic tests verify current software behavior; they are not panel fixtures.
The exact remaining dependency is the authorized, sanitized firmware-specific
read/create/read/edit/read/delete and lifecycle evidence listed in the library
document, followed by its validated API implementation and compatible release.
Leave #99 open and record this evidence-based limitation in only the schedule
entry of #188.
