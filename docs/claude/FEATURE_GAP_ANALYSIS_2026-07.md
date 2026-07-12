# Feature Gap Analysis — Unimplemented IntelliCenter Controls

**Date:** 2026-07-12
**Method:** Four independent tracks, cross-validated:
1. Codex (GPT) full codebase sweep of the integration + pyintellicenter (319 type/attribute pairs audited)
2. Claude coverage map (attributes package vs `DEFAULT_ATTRIBUTES_MAP` vs platform `_build_entities`)
3. External research: nodejs-poolController feature set, official IntelliCenter Web App User's Guide (same local protocol), user feature requests (jlvaillant #26/#28/#33/#46, joyfulhouse #19/#27)
4. Live protocol probes against a real unit (full object inventory + attribute dumps)

## Headline numbers

- The protocol library defines **20 object types / 319 type-attribute pairs**; the coordinator tracks **11 types**, and `PoolModel` **drops untracked types entirely** (coordinator.py `DEFAULT_ATTRIBUTES_MAP`).
- **71 of 89** public `ICModelController` helpers are never called by the integration (most are benign — platforms read attributes directly — but the unused *setters* and helpers for untracked attributes mark real gaps).
- The official Web App speaks the same objnam/param JSON protocol on ports 6680/6681, so everything in its user guide is presumed reachable locally.

## Consensus top gaps (all tracks agree)

| # | Feature | Surface | Evidence / notes |
|---|---------|---------|------------------|
| 1 | **Schedule enable/disable switch** + schedule detail attributes (circuit, days, start/stop, per-schedule heat mode + setpoint) | switch + attributes on existing binary_sensor | `SCHED.STATUS` (enabled) is distinct from `ACT` (running) — **confirmed live**: Chlorinator schedule showed `STATUS=ON, ACT=OFF`. Library has `is_schedule_enabled()` + full getters, unused. Only SNAME/ACT/VACFLO tracked today. Web app/njsPC do full schedule CRUD. |
| 2 | **Delays: status + Cancel Delays action** | binary_sensor + button | Heater cooldown / valve-rotation delays; njsPC implements `cancelDelay`. Explains "spa won't turn off" confusion. Nothing exposed today. Protocol write semantics need device verification. |
| 3 | **True circuit/light groups (CIRCGRP)** + atomic multi-circuit ops, light Sync/Swim/Set | light/switch | CIRCGRP tracked but no builder branch handles `objtype == CIRCGRP` (only CIRCUIT-subtype CIRCGRP). `set_multiple_circuit_states()` unused. Direct user requests: jlvaillant #26, #46. |
| 4 | **Egg timer (TIME) + Don't Stop (DNTSTP)** per circuit | number + switch (disabled by default) | `TIME` already tracked but dead (coordinator.py). Live values confirmed (Pool 720 min, Backwash 2 min). Web app: 0–12h or Don't Stop. |
| 5 | **Non-featured circuit switches** | switch (disabled by default) | switch.py only creates entities for `FEATR=ON` circuits; e.g. "AUX 4" on the live unit has no entity. Opt-in exposure avoids entity spam. |
| 6 | **Dimmer brightness / fixed colors / MagicStream extras** | light | `LIMIT` attr observed live on GLOW circuits (7/10). Web app: 50/75/100% dimming for dimmer subtypes, fixed color selection, MagicStream Capture/Thumper/Hold/Recall. Requested in jlvaillant #28. |
| 7 | **Chemistry: LSI sensor + aggregate chem alert + superchlorinate duration + chlorinator status** | sensor/binary_sensor/number | `SINDEX` untracked though `get_saturation_index()` exists; `get_chem_alerts()`/`has_chem_alert()` unused; IntelliChlor `TIMOUT` (boost duration) + `CHLOR` (on/off) untracked. |
| 8 | **Solar heat modes + Spa Manual Heat** | water_heater/climate/switch | Heat source incl. Solar Only / Solar Preferred; `MANHT` on BODY/SYSTEM untracked. Live unit has Solar sensor + Solar function circuits. `set_heat_mode()` helper unused. |
| 9 | **Hardware diagnostics: MODULE/PANEL firmware, SYSTEM.UPDATE flag, SENSE PROBE/CALIB** | sensors (diagnostic) | MODULE has per-module `VER`; `UPDATE` = firmware-available flag; raw-vs-calibrated probe comparison diagnoses sensor drift. All untracked. `GetHardwareDefinition` never consumed. |
| 10 | **Pump priming config (PRIMFLO/PRIMTIM) + body live TEMP + BOOST** | number/sensor/switch | Attributes defined but untracked; write semantics need hardware verification. |
| 11 | **Firmware advisory: detect version, warn on known-issue firmware** | HA Repairs issue (+ existing Firmware Version sensor) | We already parse `VER` ("IC: 1.064 ..."); compare against a curated, sourced known-issues table and raise a Repairs warning (e.g. protocol quirks like the 1.064 `TIMOUT` token, versions with documented local-protocol instability, out-of-date firmware). Also candidates: `SYSTEM.UPDATE` firmware-available flag (untracked today). |

## Deliberately excluded

- **PERMIT** (users/passwords): the protocol returns panel passwords in cleartext — keep out of HA state and diagnostics.
- **Valve position/mode**: no feedback path exists (see `docs/valve-control-implementation.md` correction banner); indirect watchdog is the sanctioned approach. A valve *role* (ASSIGN) config editor is possible but is configuration, not control.
- **History/usage graphs, notifications delivery, firmware update trigger**: Pentair-cloud or panel-local only; HA long-term statistics already covers history.

## Unknowns needing device probing before implementation

- Writing `SCHED.STATUS` / schedule CRUD over the local socket (njsPC does it via RS-485; web app does it via this protocol — near-certain but unverified on our unit)
- Delay-cancel command shape
- Whether Service/Timeout mode can be *set* remotely (we only read it)
- `FEATR`/`PRESS` object semantics (placeholders on the test unit)
- Sun-relative schedule starts (`START=SRIS/SSET` accepted on write?)

## Suggested implementation order

1. Schedule enable switch + schedule detail attributes (small, high value, one probe needed)
2. Egg timer + freeze-protection surfacing (attributes already tracked — cheapest wins)
3. Chemistry LSI + chem alert + superchlorinate duration
4. Delay status + cancel button (after probing)
5. Circuit/light groups
6. Dimmer brightness + light extras
7. Diagnostics tier (MODULE firmware, UPDATE flag, PROBE/CALIB)
8. Solar heat modes / manual heat (needs a system with solar to verify)

Full Codex report (object-type table, all 71 unused methods, 253 unexposed attribute pairs) is preserved in the session records; regenerate with the audit method above if needed.
