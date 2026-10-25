# Pentair App Capability and Functionality Audit

Analysis date: 2026-10-20. Target: Pentair Pool Android 4.2.21 (21615),
package `com.pentair.pentairhome`. Compared with the current local integration
and library source, not the older July feature-gap backlog.

Implementation and investigation requests are tracked in
[intellicenter #188](https://github.com/joyfulhouse/intellicenter/issues/188).
That tracker links nine library issues and three HA feature requests, each
with self-contained evidence, implementation guidance, and acceptance criteria.

See the [app analysis report](pentair-app-local-protocol.md) and the
[artifact and reproduction reference](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/PENTAIR_APP_LOCAL_PROTOCOL.md).
Function IDs below refer to that exact Hermes artifact. No app execution,
device session, firmware installation, or equipment configuration was performed.

## Evidence Levels

- **Implemented in app code**: a UI/controller or request-construction path
  exists. This does not establish successful operation on a real panel.
- **Conditional**: code explicitly depends on a feature flag, firmware,
  hardware, role, or configuration. Conditional does not mean unfinished.
- **Lead**: a template, field, or helper is present, but reachability or
  end-to-end behavior remains unverified.

This is a static capability inventory, not a claim of complete understanding
of every app path. In particular, a short callback, an unused-looking string,
or a shared component is insufficient evidence of an abandoned feature.

The integration comparison uses source commit `7724f95411cf09590ca93c1ab3baa40230d60de0`
and library commit `cb738874e54c89e312925521246c82a91b020d93`. The linked issues
contain source permalinks; treat this dated audit as a baseline, not a live
feature-status dashboard. Track subsequent delivery in issue #188.

## Main Functional Gaps

| Capability | Current integration | App evidence and remaining work |
|---|---|---|
| Panel schedules | Enable/disable and status/details | Schedule creation/editing UI and deletion templates exist. Add supported create/edit/delete workflows for panel-resident schedules. Functions 80769, 80771, 80781, 80862. |
| Light actions | Existing effects and narrowly validated Color Sync | Color Set and Swim handlers exist (80713-80715). Sync currently requires firmware 1.064 and two GLOW members. Broader coverage needs device evidence. |
| Group and equipment configuration | Operates existing equipment/groups | CreateGroup/EditGroup, equipment deletion and association builders exist (79341). Membership/timing and commissioning remain separate work from ordinary control. |
| Alert preferences | Chemistry alerts and update availability | Read/write alert preference builders (83391), with configuration-driven alert handling. Add preference management after tracing arguments and supported options. |
| Firmware installation | Availability and curated advisories | Install/decline and progress paths exist. A complete update workflow is missing; `_FDR` is a separate event feature, described below. |
| Remote/access administration | No corresponding management workflow found | Remote inventory/removal, permission records, role UI, and user-management screens. Local panel roles and cloud invitations must be treated separately. |

Source comparison: `switch.py`, `binary_sensor.py`, `light.py`, `services.yaml`,
and library `_mixins/schedule.py`, `_mixins/system.py`, `_mixins/circuit_group.py`.
Generic parameter writes are not equivalent to a supported user workflow.

## Less-Visible and Conditional Capabilities

### Stored History Retrieval

The IntelliCenter history screen is backed by a real request path, not just
chart labels. Function 83343 defines `ReadHistoryMessage` with `timeStart`
and `timeEnd`. Functions 83255 and 83287 populate the time window, 83261 sends
through the shared manager, and 83258 consumes returned `objectList` data.
The initial window uses seven-day/end-of-day helpers. The controller includes
pH handling, units, body selection, chart selection, and fullscreen navigation.

Opportunity: retrieve pre-existing history rather than relying exclusively
on HA Recorder samples collected since integration setup. No history API or
backfill workflow was found in the current library/integration. Local server
availability, retention, series schema, timestamp units, and pagination remain
unverified; the shared sender alone does not prove local history storage.

### IntelliBlue / Hybrid Purifier

This is explicitly conditional functionality. Function 80684 maps
`featureFlagsReducer.hyp1.itelliblueEnabled` (spelling as shipped) into
`shouldShowHypScreens`. The advanced-settings UI consumes that flag.

There is substantial implementation behind it:

- A hybrid-purifier setup/edit container (83919) handles body selection,
  affiliated pumps, cleaning time, provisioning, and deletion.
- Functions 83937 and 83939 construct chemistry-object create/edit requests
  with `BODY`, `PUMP`, and `TIME`; 80005 supplies CreateObject/SetParamList
  templates and a default cleaning time of 02:00.
- The setup eligibility helper (80457) compares firmware thresholds supplied
  by its caller and checks pump support (80458 checks VSF/FLOW). Successful
  eligibility can navigate to Bluetooth setup. No universal minimum version
  is established by this helper alone.
- Pump/circuit/group helpers inspect `OPSTATE` through equipment associations
  (80019, 80021, 80032). The app classifies purifier states into purifying,
  bypass, and protected categories (80005, 80023-80025).
- Protected-state handling includes regeneration, winterizing, initialization,
  cleaning, maintenance, testing, and communication failures. Chemical soak
  and inactive states are classified by the bypass helper.

Opportunity: a new equipment family plus explanations of why associated
pumps/circuits are restricted. No dedicated IntelliBlue support was found in
the current integration/library. These state names do not establish commands
to start those modes. Provisioning also calls registration/Bluetooth paths;
the entire workflow must not be described as local-only.

### Cover Restrictions and Freeze-Protection Explanations

The app has logic beyond displaying cover position. Functions 79202, 79206,
and 79212 calculate cover-related circuit/group/light restrictions; 82183
renders cover enablement, body, state, and circuit-assignment configuration.
The dashboard includes a cover-status message with a firmware comparison
named `isFwVersionGreater3002` (79489).

Freeze-related logic reads circuit status/`FREEZE` (79113) and provides
dashboard warnings and dedicated interaction handlers. Our integration already
has cover entities and freeze diagnostic entities. The additional opportunity
is configuration and a clear explanation of restricted controls, rather than
counting covers or freeze detection as entirely missing. Whether enforcement
occurs in the app, panel, or both requires device testing.

### Calibration, Clock, Overrides, and Solar Relay Configuration

General settings contains functional controls and a save path, not merely
read-only fields. Function 83088 assembles changes for:

- Water, solar, and air sensor `CALIB`, including dual-body sensors.
- Clock source, format, date/time, timezone, and daylight-saving configuration.
- Pump/valve and pump/heater delay configuration (`VALVE`, `HEATING`).
- Manual operation priority (`MANOVR`) and Manual Heat (`MANHT`).
- Solar-relay configuration (`SASHP`, `SASHP2`).

Functions 83020 and 83136 condition solar-relay UI on a comparison involving
`OCP_VERSION_2029` and on body/heater topology. These are conditional settings;
this audit does not assert the precise inclusive firmware boundary.

Our integration exposes raw probe/calibration information and Manual Heat.
It does not expose the full configuration workflow above. Persistent delay
settings are not transient delay-cancellation commands. Sensor calibration
editing and manual-priority visibility are useful candidates independent of
the larger commissioning UI.

### FDR/FDP Event Awareness

The earlier report grouped `_FDR` with firmware fields. Further tracing shows
a separate event feature: function 79486 reads `EVENTSTATUS`/`EVENTID`, compares
status with `running`, and sets dashboard event state. Function 79485 navigates
to `PoolApp_Menu_FDP_Scheduled_Events_Details`. Function 79651 derives
`isFDREnable` from `featureConfigReducer.cecConfig.isEnable`; 79489 uses that
gate for the event banner.

Opportunity: expose an active-event indicator and explain event-related
behavior. The local event fields are established static evidence. Enrollment,
event details, event control, and their cloud dependencies have not been traced
end to end. Do not represent these fields as firmware-update progress or infer
an event-cancel command.

### Versioned Alert Definitions

Beyond Get/SetStatusMessageFlags, the app includes helpers for configurable
and critical alerts, device alert data, CDN compatibility, and schema filtering
(83477-83499). The inspected module declares supported schema version `1.0`.

Opportunity: richer alert descriptions and capability-aware preferences.
This suggests alert metadata can vary independently of the Android app, but
the metadata source, caching, and local/offline behavior still need tracing.
It does not establish a local active-alert or delay-status schema.

## Partial Development and Unresolved Leads

The clearest hidden feature found is the IntelliBlue flag. Its substantial
handlers argue against calling it a mere placeholder. Firmware/topology gates
and the FDR enable flag likewise show conditional availability, not proof of
unfinished development. No specific abandoned or unfinished IntelliCenter
feature is confirmed by this pass.

Track these as leads until their complete paths are understood:

| Lead | Evidence | What remains unresolved |
|---|---|---|
| Vacation configuration beyond on/off | Schedule templates reference VACFLO/VACTIM/START/STOP | Exact semantics and UI mapping. Do not infer vacation date ranges or duration from field names alone. |
| Additional chemistry/heater controls | Queries include tank, water-balance, COOL/BOOST and timing fields | Which are writable, which are already supported, and which need specific hardware. |
| Historical series/backfill | History request and response handlers | Whether served locally, series meanings, retention and completeness. |
| FDR/FDP event actions | Event status and navigation | Enrollment/control transport and authorization, if exposed at all. |
| Downloaded alert metadata | CDN/schema helpers | Source and fallback behavior; actual preference options. |

The APK also includes IC1, IntelliFlo/IF3, Color Sync/CLW, and other product
modules. Their graphs, cleaning, calibration, scheduling, or provisioning
features are not automatically IntelliCenter capabilities. Small named
callbacks inspected during this pass delegate to closures; their size alone
does not identify a stub.

## Priorities and Existing Coverage

Prioritize panel schedules, remaining light actions, and alert preferences for
day-to-day parity. Stored history, calibration editing, and restriction reasons
are valuable additions uncovered by deeper inspection. IntelliBlue is a larger
hardware-dependent integration project. Event awareness and broader setup
workflows need additional tracing before implementation scope is reliable.

Already implemented: dimming, egg timers, Don't Stop, non-featured circuits,
solar heating modes, Manual Heat, saturation index, superchlorination duration,
pump priming controls, vacation on/off, and firmware advisories. The July gap
report should not be used as the current implementation checklist.

## Reproduction Anchors

Use the report's Hermes disassembly procedure and find these function headers.
Offsets are bytecode offsets in the analyzed artifact, not file line numbers.

| Evidence | Function | Offset |
|---|---|---|
| Hybrid templates, defaults, state names | 80005 | `0x01352d3f` |
| Hybrid protected-state classification | 80024 | `0x013539e7` |
| IntelliBlue feature flag | 80684 | `0x0136f413` |
| Cover configuration UI | 82183 | `0x013ade11` |
| General-settings save builder | 83088 | `0x013d5f00` |
| General-settings conditional UI | 83136 | `0x013d876f` |
| Initial history request | 83255 | `0x013e0170` |
| History response handler | 83258 | `0x013e027c` |
| History sender | 83261 | `0x013be046` |
| History date-range request | 83287 | `0x013e0c83` |
| History command template | 83343 | `0x013e4025` |
| Alert schema helpers/version | 83477 | `0x013e9c7d` |
| Hybrid create builder | 83937 | `0x013faa37` |
| Hybrid edit builder | 83939 | `0x013fab71` |
| FDR/FDP details navigation | 79485 | `0x01335b45` |
| FDR event-state handler | 79486 | `0x01335c53` |
| FDR enable flag | 79651 | `0x0133cde6` |
