# IntelliCenter 3.12.0 production release evidence

Assessment date: 2026-10-22. Tracking: homelab-tvz5.

## Scope and decision

Promote 3.12.0b2 to 3.12.0 with a stable pyintellicenter 0.3.0 exact pin.
The library is the 0.3.0b1 implementation with release metadata changes only.
No feature guards are relaxed by this promotion.

Production is Home Assistant Yellow running HA 2026.10.2, using TCP and
controller IC 1.064 / ICWEB 2021-10-19 1.007. The beta was installed through
HACS on October 20. The earlier deployment validation is recorded in closed
homelab-i50k. Its temporary JSON snapshots were absent during this assessment;
the recorded deployment results and retained HA history supply the baseline.

## Evidence interval and counter boundaries

- HA logbook records stop at 2026-10-20 18:43:52 UTC and completed startup at
  18:46:19 UTC. Integration entities initialized at about 18:45:14 UTC.
- Retained history was read through 2026-10-22 17:21:00 UTC. The conservative
  completed-startup soak interval is 46 hours, 34 minutes, 41 seconds.
- An intervening HA stop occurred on October 21 at 17:02:30 UTC; integration
  entities initialized at 17:03:41 UTC and HA completed startup at 17:06:12 UTC.
  Consequently this is two operating segments with a restart gap, not one
  uninterrupted connection test. The latest completed-startup segment is
  about 24 hours, 15 minutes.
- Current diagnostics reported 39 requests sent/completed, zero failures,
  zero reconnect attempts and one successful connection. Those counters cover
  the latest controller lifetime only. They are not cumulative across the soak
  and do not include all transport keepalive traffic.
- Connection history contains only `on` observations, including initialization
  records. Recorder does not certify continuity during HA downtime or prove
  that no brief unrecorded transport interruption occurred.

## Comparison with deployment baseline

- Config entry is loaded, connected, and still has 62 model objects. All 70
  enabled integration entities are present. There are no new unavailable or
  unknown states in the retained enabled-entity history; the two cover entities
  were and remain `unknown`.
- All six optional advanced-setting diagnostic sensors remain disabled by the
  integration. No calibration controls are enabled for this installation.
- System mode remains `auto`; Not in Auto is `off`.
- Pool/spa setpoints remain 86/100 F throughout retained history. Pool operation
  remains `off`; spa selected operation remains `Gas Heater`. Both expose
  `heating_status: off`. Spa last temperature remains 101 F while idle; this is
  retained body temperature, not proof of active circulation or heating.
- Two pool schedule cycles run from approximately 04:00 to 16:00 UTC on
  October 21 and 22. Chlorinator schedules run 10:00-13:00 UTC and spillway
  schedules 11:00-12:00 UTC. Corresponding switch and pump telemetry changes
  are recorded. Pump speed reaches 3450 RPM and power varies during operation;
  both return to zero while idle. GPM remains zero, so flow accuracy is not
  validated by this evidence.
- Body and live water temperature readings update during circulation. Chemistry
  updates include pH 6.1-6.4 and changing ORP while running, with zero readings
  when idle. The pH-low alert and zero chemistry readings predate the update.
  Transient ORP-high indications are recorded after each schedule starts; they
  are observations, not a water-quality certification or an established software
  regression.
- No IntelliCenter entries appear in the current system-log buffer. Retained
  Core logs start October 21 at 22:15 local time (October 22 05:15 UTC), so they
  cannot establish error absence for the entire soak. No IntelliCenter failure
  appears there. The retained logbook contains no pool/IntelliCenter-related
  error/failure/timeout entries; logbook is not a complete service-failure audit,
  and successful command/automation actuation is not established by that search.

## Validation limits and retained guards

All assessment requests were read-only. No equipment actuation, forced network
disconnect, manual/service-mode transition, MANOVR write, calibration, firmware
installation, or group commissioning was performed. No active heater cycle was
observed. Physical heater-source attribution for combo, cooling and multiple
sources remains outside this evidence (upstream issue #183).

The empty calibration hardware-support registry, firmware-installation gates,
group-commissioning gates, broader light-action restrictions, and explicit
unknown freeze/cover dependencies remain intact. Existing upstream hardware
investigation issues remain applicable; this release does not close them.

Fresh pre-promotion validation: integration 1,012 tests / 96% coverage; library
1,086 tests / 92% coverage. Ruff lint/format and mypy pass in both repositories;
the integration's Bandit medium/high check passes. Stable release checks must
also run against the final published library pin and release commits in CI.
