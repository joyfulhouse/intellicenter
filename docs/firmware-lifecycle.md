# Firmware installation evidence and HA delivery gate

Firmware installation is not currently supported through Home Assistant.
The existing Firmware Update Available binary sensor, Firmware Version sensor
and curated Repairs advisories remain the supported surfaces. An availability
flag does not establish an installable target or permission to install.

The library's typed firmware observations, bounded watchers and gated lifecycle
were merged in [pyintellicenter #110](https://github.com/joyfulhouse/pyintellicenter/pull/110).
Its real-device install registry is empty. Synthetic lifecycle tests establish
client behavior, not panel eligibility, progress units or terminal states.
The owning request [pyintellicenter #106](https://github.com/joyfulhouse/pyintellicenter/issues/106)
remains open. This is the firmware-specific dependency handoff for
[tracker #188](https://github.com/joyfulhouse/intellicenter/issues/188).

## Evidence required before an update entity

The [library evidence matrix](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/FIRMWARE_UPDATES.md#evidence-intake-and-support-matrix-106)
specifies exact capture requirements and the current support matrix. The
2026-10-25 review of the owning issue, history, fixtures and linked app-analysis
PRs found static builders but no correlated panel installation session.
`_5451.IN=YES/NO` identifies install/decline builders; it does not establish
eligibility, cancellation, progress percentages or success. `_FDR.EVENTSTATUS`
and `EVENTID` belong to a separate event workflow.

Before implementing an HA install surface, validate an exact hardware and raw
source/target version contract: fresh eligibility and target-offer provenance,
acceptance/rejection, progress and failure meanings, bounded reconnect and
restored subscriptions, and a fresh target-version response after installation.
Device captures require applicable explicit authorization; permission to merge
software does not authorize an installation. Decline and cancel each need
independent evidence and must remain unavailable until validated separately.

## Integration acceptance criteria

| Area | Required behavior and meaningful regression coverage |
| --- | --- |
| Entity admission | Create an update entity only with validated semantics for installed/target versions and availability. Advertise install only for the exact supported, currently eligible contract; missing or stale prerequisites fail closed |
| Installation | Await the library command and propagate rejection and uncertain delivery distinctly. Never report success from acknowledgement, progress alone or socket loss |
| Progress | Expose percentage or indeterminate install state only where the device contract establishes the mapping; preserve unknown/missing values without inventing 0 or 100 |
| Reconnect | Continue through the normal connection handler within a justified bound; require restored fresh observations and explicit current-connection version verification. Reconnect must not replay install |
| Verification | Require a fresh target version different from baseline. Missing, unchanged, unexpected or conflicting versions retain an unresolved outcome; later read-only reconciliation may resolve it |
| Duplicate protection | Block concurrent install calls and automatic retries after rejection, timeout, disconnect or cancellation. Preserve an unresolved-operation guard across HA entry reload/restart, or use a separately validated fresh reconciliation procedure before another install |
| Cancellation | Cancelling an HA task, unloading an entry or closing a watcher only ends client observation; do not send decline or claim the panel stopped |
| Lifecycle | Remove watcher tasks/listeners on unload; bound buffering; test replacement connections, stale notifications, repeated setup/unload and interrupted verification |
| Existing entities | Retain current binary sensor/version sensor IDs and Repairs behavior; any migration requires a deliberate plan and entity-registry tests |

The library's `failed` phase currently means explicit request rejection, not a
validated device installation-failure code. Its `verified_version` is proof of
a freshly observed version, not proof that this client caused the change.
Its one-request guard is per controller instance; recreating the controller
cannot establish that a previous panel operation ended. These distinctions
must survive HA state and error translation.

## Dependency and release boundary

The integration currently pins published `pyintellicenter==0.3.1` consistently
in its manifest, project dependency and lock. This handoff changes no runtime
API or dependency. A future HA implementation must test against an available
published library containing the validated contract, including unsupported
panels, failure propagation, reconnect and fresh-version verification. Do not
pin an unpublished version to expose scaffolding. Package publication and
production deployment are separate work; neither is required for this handoff.
