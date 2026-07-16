# System Delay Protocol Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, without speculative writes, whether IntelliCenter firmware 1.064 exposes a reliable active-delay signal and a distinct acknowledged command for cancelling heater-cooldown and valve-rotation delays (issue #92).

**Architecture:** Build an issue-local, read-only observer around `ICConnection` so unsupported key echoes and ordered `NotifyList` frames remain visible on both TCP and WebSocket. Query `GetActiveStatusMessages` initially, at a bounded cadence no faster than every 15 seconds, and finally while retaining the push stream; correlate any non-empty answer with authoritative notifications. Identify the deployed official Web App bundle offline before considering any cancellation replay. The identified bundle contains no transient cancellation operation, so replay is now closed and only natural-delay read/push evidence remains. Record sanitized evidence and one decision-table result in the approved design spec; this plan deliberately produces no Home Assistant entity or production protocol helper.

**Tech Stack:** Python 3.13+, `pyintellicenter` raw `ICConnection`, asyncio, pytest, Chrome DevTools Protocol, IntelliCenter TCP 6681/WebSocket 6680, Markdown evidence.

## Global Constraints

- This is protocol discovery only. Do not implement the binary sensor, button, coordinator tracking, or public controller helpers in this plan.
- Use external worktrees based on fetched commits: pyintellicenter `9ee8d55694c14713f39886866f21f68902b8ca7d`; evidence/spec work stays on integration branch `docs/issues-92-93-plans` descended from `0886531f27d338191d8ab1642b6480ded4a4f553`.
- Never run `git worktree prune`, `git clean`, `git stash`, a reset command, or modify either primary checkout.
- Require `INTELLICENTER_HOST`; never supply a fallback host and never print the endpoint, property name, object identifiers, equipment names, location/contact fields, PINs, credentials, or raw browser trace.
- Keep raw captures outside Git beneath a mode-`0700` temporary directory. Files are mode `0600`; only sanitized excerpts enter the repository.
- Use `ICConnection`, not `ICModelController`, `PoolModel`, diagnostics output, or `get_all_objects()`. Those paths either request private fields or prune the unsupported `key == value` evidence this investigation needs.
- Install the notification callback before connecting. Use one experimental protocol client at a time, `keepalive_interval=3600`, `notification_queue_size=1000`, and batches of at most 50 requested attributes.
- All delay creation, official cancellation, and restoration occur through the official Web App/panel. Never create a delay by writing protocol attributes.
- The two issue tracks may build and test read-only tooling in parallel, but no #92 state-changing live phase may overlap a #93 live phase.
- Never replay either nodejs-poolController lead: its IntelliCenter v1 implementation sends no command, while its unverified WebSocket implementation writes `_5451.VALVE=OFF` and `_5451.HEATING=OFF`.
- Reject any captured command that writes `CIRCUIT.DLY`, `HEATER.DLY`, `VALVE.DLY`, `SYSTEM.HEATING`, or `SYSTEM.VALVE`, even transiently.
- A successful response requires a correlated response with `response == "200"` plus the captured authoritative state transition. A response alone, a command echo, or physical observation without readable state does not pass the state gate.
- Abort on service/timeout mode, freeze protection, schedule/automation interference, unrelated actuator movement, flow loss, heater fault, queue overflow, connection loss, malformed/rejected response, membership/configuration mutation, or failed restoration.
- Cancellation can stop a pump or begin valve movement immediately. Keep an operator able to use the physical panel throughout every state-changing phase.
- The button gate is closed for the identified asset/firmware, leaving only sensor-only or no feature. No implementation plan is written until the natural-delay evidence is added to the spec and reviewed.

---

## Execution Status (2026-07-15)

- The isolated observer is implemented and committed at
  `959fe2c35c487e065286119e55387e2fe02c983d` on
  `discovery/issue-92-delay-protocol`. Focused tests, the full 481-test suite,
  Ruff, formatting, mypy, lock drift, and diff checks passed.
- The observer now permits only `GetParamList`, `RequestParamList`, and
  `GetActiveStatusMessages`; it records initial, periodic, and final active
  status responses, retains `NotifyList`, skips missed polling slots instead of
  bursting, and privacy-aliases/resource-bounds nested answers and labels.
- Inactive TCP and WebSocket `GetActiveStatusMessages` calls each returned a
  correlated `200` with an empty answer. Command existence is proven on
  firmware `1.064`; active schema and push delivery are not.
- Offline inspection of official `bundle.web.js` SHA-256
  `933e2fc35fd5e5fe26477f0199873bedaf4c266d510f6e8259e3684da18317fd`
  found only persistent heater/valve delay settings and no transient cancel
  operation. The button gate failed; Tasks 4 cancellation phases and Task 5
  replay are permanently skipped for this asset/firmware evidence.
- The only open live work is two operator-coordinated natural heater-cooldown
  captures covering both candidate transports, each long enough to cover active
  -> inactive, followed by two valve-delay captures covering both transports
  before any generic system-delay claim. Until those sanitized results pass
  adversarial review, no #92 production plan or PR exists.

---

### Task 1: Create the isolated discovery workspace

**Files:**
- No repository files changed.

**Interfaces:**
- Consumes: clean pyintellicenter base `9ee8d55694c14713f39886866f21f68902b8ca7d`.
- Produces: external worktree `/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-92` on branch `discovery/issue-92-delay-protocol` with a green baseline.

- [x] **Step 1: Confirm the target is unused without pruning existing metadata**

Run:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter \
  branch --list discovery/issue-92-delay-protocol
test ! -e /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-92
```

Expected: no branch output and `test` exits 0. If either check fails, choose a new issue-specific branch/path and record it in the execution log; do not delete or reuse unknown state.

- [x] **Step 2: Create the external worktree**

Run:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-92 \
  -b discovery/issue-92-delay-protocol \
  9ee8d55694c14713f39886866f21f68902b8ca7d
```

Expected: the new worktree is created at the requested commit.

- [x] **Step 3: Sync and verify the baseline**

Run from the new worktree:

```bash
uv sync --frozen --extra dev
uv run pytest -q
```

Expected: dependency sync has no lock drift and the full suite passes. Stop and report if it fails.

---

### Task 2: Build a narrow read-only delay observer (completed)

**Files:**
- Create: `scripts/capture_delay_protocol.py`
- Create: `tests/test_capture_delay_protocol.py`

**Interfaces:**
- Consumes: `ICConnection(host, transport=..., keepalive_interval=3600, notification_queue_size=1000)`, `set_notification_callback()`, and `send_request()`.
- Produces:
  - `sanitize_frame(frame: dict[str, Any], aliases: dict[str, str], answer_aliases: dict[tuple[str, str], str] | None = None) -> dict[str, Any]`
  - `validate_capture_path(path: Path, repo_root: Path) -> None`
  - `capture_phase(*, transport: Literal["tcp", "websocket"], label: str, seconds: int, output: Path) -> None`
  - CLI: `python scripts/capture_delay_protocol.py --transport {tcp,websocket} --label LABEL --seconds N --output ABSOLUTE_PATH`

- [x] **Step 1: Write failing safety tests**

Add tests that prove the observer preserves protocol evidence while removing private data:

Also cover nested `GetActiveStatusMessages.answer` dictionaries/lists,
identifier/reference aliasing, answer key/value token alias stability, malformed
scalars, depth/container/global-node budgets, fixed safe label patterns, read-only
command facade enforcement, mode-`0600` output, bounded query cadence, missed-slot
skipping, cleanup, and exception-message privacy.

```python
from pathlib import Path

import pytest

from scripts.capture_delay_protocol import sanitize_frame, validate_capture_path


def test_sanitize_frame_aliases_identifiers_and_removes_private_fields() -> None:
    frame = {
        "messageID": "17",
        "response": "200",
        "objectList": [{
            "objnam": "_5451",
            "params": {
                "OBJTYP": "SYSTEM",
                "SNAME": "private-id",
                "PROPNAME": "private-property",
                "PASSWRD": "1234",
                "DLY": "DLY",
                "SERVICE": "AUTO",
            },
        }],
    }

    aliases: dict[str, str] = {}
    sanitized = sanitize_frame(frame, aliases)

    assert sanitized == {
        "response": "200",
        "objectList": [{
            "objnam": "OBJECT_001",
            "params": {
                "OBJTYP": "SYSTEM",
                "DLY": "DLY",
                "SERVICE": "AUTO",
            },
        }],
    }


def test_validate_capture_path_rejects_repository_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="outside the repository"):
        validate_capture_path(repo / "capture.jsonl", repo)


def test_observer_source_contains_no_mutation_command() -> None:
    source = Path("scripts/capture_delay_protocol.py").read_text()
    assert "SETPARAMLIST" not in source.upper()
    assert "request_changes" not in source
```

- [x] **Step 2: Run the tests and verify red**

Run:

```bash
uv run pytest tests/test_capture_delay_protocol.py -v
```

Expected: collection fails because `scripts.capture_delay_protocol` does not exist.

- [x] **Step 3: Implement the safety boundary and exact allowlists**

The script must define these constants exactly; private keys are removed rather than masked so their presence cannot reveal installation shape:

```python
PRIVATE_KEYS = frozenset({
    "ADDRESS", "CITY", "COUNTRY", "EMAIL", "EMAIL2", "HNAME", "LOCX",
    "LOCY", "NAME", "PASSWRD", "PHONE", "PHONE2", "PROPNAME", "SNAME",
    "SOURCE", "STATE", "ZIP", "messageID",
})
REFERENCE_KEYS = frozenset({"objnam", "BODY", "CHILD", "CIRCUIT", "HEATER", "PARENT"})
READ_KEYS_BY_TYPE = {
    "SYSTEM": (
        "OBJTYP", "SUBTYP", "VER", "SERVICE", "READY", "STATUS", "MODE",
        "HEATING", "VALVE", "ACT", "ACT3", "ACT4", "VACTIM", "VACFLO",
    ),
    "BODY": (
        "OBJTYP", "SUBTYP", "STATUS", "MODE", "HTMODE", "HTSRC", "HEATER",
        "LOTMP", "HITMP", "SETTMP", "ACT1", "ACT2", "ACT3", "ACT4",
        "BOOST", "MANHT", "READY", "TEMP", "LSTTMP",
    ),
    "CIRCUIT": (
        "OBJTYP", "SUBTYP", "STATUS", "BODY", "FEATR", "FREEZE", "DLY",
        "READY", "TIME", "TIMOUT", "DNTSTP", "USE", "ACT", "PARENT",
        "CIRCUIT",
    ),
    "CIRCGRP": (
        "OBJTYP", "SUBTYP", "STATUS", "DLY", "READY", "USE", "ACT",
        "PARENT", "CIRCUIT",
    ),
    "HEATER": (
        "OBJTYP", "SUBTYP", "STATUS", "BODY", "DLY", "HEATING", "HTMODE",
        "MODE", "START", "STOP", "TIME", "TIMOUT", "READY",
    ),
    "VALVE": (
        "OBJTYP", "SUBTYP", "ASSIGN", "CIRCUIT", "DLY", "READY", "STATUS",
    ),
    "PUMP": (
        "OBJTYP", "SUBTYP", "STATUS", "BODY", "RPM", "GPM", "PWR", "READY",
    ),
}
```

Implement `sanitize_frame()` as a recursive copy that drops `PRIVATE_KEYS`, assigns stable `OBJECT_NNN` aliases for every non-null reference (`"00000"` remains unchanged), and preserves every other key/value including placeholder echoes. Implement `validate_capture_path()` by resolving both paths and raising when the output is equal to or beneath `repo_root`.

`capture_phase()` must:

1. fail before connecting when `INTELLICENTER_HOST` is absent;
2. set the callback before `connect()`;
3. enumerate only `OBJTYP`, `SUBTYP`, and `PARENT` to identify relevant objects;
4. query each relevant type with its allowlist using raw `GetParamList`;
5. subscribe to explicit discovered object names with `RequestParamList`, in batches below 50 aggregate keys;
6. issue read-only `GetActiveStatusMessages` once before `READY`, periodically
   no faster than every 15 seconds without catch-up bursts, and once at normal
   completion;
7. write sanitized UTC timestamp, monotonic offset, fixed-pattern label,
   transport, event kind, and sanitized frame as JSONL;
8. print only `READY {label} {transport}` after subscription and the initial
   active-status read;
9. wait for the bounded duration and always disconnect in `finally`.

Open output with mode `0o600` and refuse relative paths. Do not log response representations or exception arguments because they can contain frames.

- [x] **Step 4: Run focused tests green**

Run:

```bash
uv run pytest tests/test_capture_delay_protocol.py -v
uv run ruff check scripts/capture_delay_protocol.py tests/test_capture_delay_protocol.py
uv run ruff format --check scripts/capture_delay_protocol.py tests/test_capture_delay_protocol.py
```

Expected: tests pass and Ruff reports clean files.

- [x] **Step 5: Commit discovery tooling locally**

Run:

```bash
git add scripts/capture_delay_protocol.py tests/test_capture_delay_protocol.py
git commit -m "test: capture active system status messages"
```

Expected: commit `959fe2c35c487e065286119e55387e2fe02c983d` on the discovery branch. This commit is evidence tooling, not a production or release PR.

---

### Task 3: Establish the passive baseline on both transports (completed)

**Files:**
- Raw, untracked: mode-`0700` temporary capture directory.
- No committed evidence yet.

**Interfaces:**
- Consumes: Task 2 CLI and the ignored pyintellicenter `.env` through `uv --env-file`.
- Produces: sanitized inactive TCP/WebSocket inventory and subscription traces, plus a recorded invariant snapshot.

- [x] **Step 1: Create a private capture directory**

Run:

```bash
umask 077
CAPTURE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/intellicenter-issue-92.XXXXXX")"
chmod 700 "$CAPTURE_DIR"
printf '%s\n' "$CAPTURE_DIR"
```

Expected: one temporary directory path; preserve it only in the private execution log.

- [x] **Step 2: Confirm operational preconditions through read-only UI/panel inspection**

Verify and record privately: panel `SERVICE=AUTO`; no freeze protection, active schedule transition, cleaner cycle, or unrelated automation; expected flow and heater health; and an operator is present. Unload Home Assistant only if its TCP client prevents the observer from connecting, and record that it must be reloaded during restoration.

- [x] **Step 3: Capture inactive baselines independently**

Run each command in its own terminal session and poll output at intervals no longer than 30 seconds:

```bash
uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
  python scripts/capture_delay_protocol.py \
  --transport tcp --label inactive-tcp --seconds 30 \
  --output "$CAPTURE_DIR/inactive-tcp.jsonl"

uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
  python scripts/capture_delay_protocol.py \
  --transport websocket --label inactive-websocket --seconds 30 \
  --output "$CAPTURE_DIR/inactive-websocket.jsonl"
```

Observed: each printed only its `READY` line and exited 0. Both active-status
responses were correlated `200` with empty answers; no equipment changed.

- [x] **Step 4: Run the privacy and structural gate**

Run:

```bash
test "$(stat -f '%Lp' "$CAPTURE_DIR")" = 700
find "$CAPTURE_DIR" -type f ! -perm 600 -print
rg -n '"(ADDRESS|CITY|COUNTRY|EMAIL|EMAIL2|HNAME|LOCX|LOCY|NAME|PASSWRD|PHONE|PHONE2|PROPNAME|SNAME|SOURCE|STATE|ZIP|messageID)"' "$CAPTURE_DIR" && exit 1 || true
```

Expected: no `find` or `rg` matches. Manually confirm aliases are stable and both transports report exactly one aliased `SYSTEM` object. Stop if the inventory is ambiguous.

---

### Task 4: Capture natural delay transitions; cancellation gate closed

**Files:**
- Sanitized observer traces: private capture directory until analysis.

**Interfaces:**
- Consumes: official UI/panel, Task 3 invariant snapshot, observer CLI.
- Produces: repeated heater and valve inactive-to-active-to-natural traces with
  active-status response/push correlation and restoration proof. It produces no
  cancellation trace because that independent gate has already failed.

In the same private shell that owns `CAPTURE_DIR`, define this launcher once:

```bash
capture_delay_phase() {
  transport="$1"
  label="$2"
  seconds="$3"
  uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
    python scripts/capture_delay_protocol.py \
    --transport "$transport" --label "$label" --seconds "$seconds" \
    --output "$CAPTURE_DIR/$label-$transport.jsonl"
}
```

The execution agent starts one listed invocation in a PTY, waits for `READY`, performs only that step's official UI actions, and polls at intervals of 30 seconds or less until completion.

- [x] **Step 1: Resolve the official Web App cancellation gate offline**

The deployed `bundle.web.js` asset with SHA-256
`933e2fc35fd5e5fe26477f0199873bedaf4c266d510f6e8259e3684da18317fd`
contains no transient `Cancel Systems Delay` operation. Its only related writers
change persistent heater/valve delay enables or durations, which this plan
forbids. Record the failed button gate and do not invoke, capture, or replay a
state-changing cancellation candidate.

- [ ] **Step 2: Record heater-only natural completion twice**

For runs `heater-natural-1` and `heater-natural-2`, start the observer for a duration longer than the configured cooldown, create normal heater demand only within the operator-approved settings, end demand through the official UI, allow the delay to complete naturally, and fresh-query the same objects at completion. Do not raise a setpoint beyond the operator-approved value merely to force firing.

Run separately:

```bash
capture_delay_phase tcp heater-natural-1 900
capture_delay_phase websocket heater-natural-2 900
```

Expected: two independent physical runs establish repeatability while covering
both candidate transports. Each contains the complete inactive -> active ->
inactive sequence or proves no readable active signal exists. A transport
difference requires a transport-scoped capability; it must not be generalized
away. These cross-transport single observations are not enough to claim a
transport-scoped capability: if they diverge, select unsupported/no capability
for this plan and require a separately amended, reviewed plan with repeated
runs inside each affected transport before reconsidering scoped support.

- [x] **Step 3: Skip heater cancellation captures**

Skipped because Step 1 failed the independent button gate. Do not manufacture a
local equivalent from persistent settings.

- [ ] **Step 4: Repeat natural runs twice for a valve-only delay**

Perform `valve-natural-1` and `valve-natural-2` through the official UI. Reject
the run if heater cooldown and valve rotation cannot be isolated or an unrelated
circuit moves. Correlate every non-empty active-status answer with the retained
`NotifyList`; query-only data does not pass the push-driven production sensor
gate.

Run separately:

```bash
capture_delay_phase tcp valve-natural-1 600
capture_delay_phase websocket valve-natural-2 600
```

Expected: two independent valve runs establish repeatability while covering
both candidate transports. A generic system-delay sensor may claim valve
coverage only if both transports produce the same authoritative push/model
mapping. If they diverge, omit valve coverage here; one observation per
transport cannot justify scoped support without a separately amended, reviewed
within-transport repeat plan.

- [x] **Step 5: Skip simultaneous cancellation**

Skipped because no cancellation command passed Step 1. Natural simultaneous
delays are not needed to decide the initial per-type sensor gate.

- [ ] **Step 6: Restore and verify twice**

Through the official UI, restore bodies, circuits, heater modes, setpoints, group/light states, Home Assistant loading state, and every delay configuration value. Fresh-query the invariant snapshot twice, excluding only naturally volatile temperature/RPM/GPM/power telemetry.

Expected: both comparisons match. A mismatch fails the discovery run and blocks replay.

---

### Task 5: Replay only a proven local non-mutating cancellation contract (skipped)

**Files:**
- Private replay traces only.

**Interfaces:**
- Consumes: the failed official bundle gate from Task 4.
- Produces: explicit “not replayable locally; no command exists in the identified
  asset” result.

No step below is authorized: Task 4 produced no exact transient command,
acknowledgement predicate, or completion predicate. The persistent-setting
writes remain forbidden.

- [x] **Step 1: Classify the official request offline**

Rejected: no transient request exists in the identified official asset. Continue
to Task 6 with only sensor-only/no-feature outcomes available.

- [x] **Step 2: Replay once over TCP (skipped)**

Not run. Step 1 did not produce a command, so no TCP state-changing request is
permitted.

- [x] **Step 3: Restore, then replay once over WebSocket (skipped)**

Not run. Step 1 did not produce a command, so no WebSocket state-changing
request is permitted.

- [x] **Step 4: Perform final restoration (not applicable; no replay occurred)**

No replay state existed to restore. The passive baseline remained unchanged.

---

### Task 6: Sanitize, decide, and amend the approved specification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-14-system-delay-status-cancel-design.md`
- Create only if useful: `docs/superpowers/evidence/2026-07-14-system-delay-protocol.md`

**Interfaces:**
- Consumes: Tasks 3–5 traces.
- Produces: sanitized state/command contract, firmware and transport scope, passive capability predicate, selected decision-table row, and an explicit next-plan boundary.

- [ ] **Step 1: Write the sanitized evidence summary**

Record exact field names and tokens, aliased targets, ordered state deltas, response code predicate, completion predicate, repeat counts, supported delay types, firmware `1.064`, tested transports, configuration invariants, and restoration result. Do not include raw frames, endpoint, object names, property/equipment names, browser headers/cookies, message IDs, or credentials.

- [ ] **Step 2: Select exactly one decision-table result**

Choose sensor-only or unsupported; both button-bearing outcomes are already
eliminated for the identified asset/firmware. A sensor requires one durable
readable inactive/active mapping, a corresponding authoritative push/model
signal, repeat coverage for every claimed delay type, and an independent passive
capability predicate. If any predicate is absent, omit the entity even if an
active query happened to return useful data.

- [ ] **Step 3: Update the design from conditional language to captured facts**

Add a dated `Discovery Result` section to the spec with the selected result and exact future public interfaces, or state that issue #92 is unsupported on firmware 1.064 and why. Explicitly retain the disproved `DLY`, `HEATING`, and `VALVE` regression guards.

- [ ] **Step 4: Run evidence privacy and diff checks**

Run from the integration planning worktree:

```bash
rg -n '\b(TBD|TODO|FIXME|XXX)\b|\.\.\.|<[^>]+>' \
  docs/superpowers/specs/2026-07-14-system-delay-status-cancel-design.md \
  docs/superpowers/evidence/2026-07-14-system-delay-protocol.md 2>/dev/null || true
rg -n '(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|PASSWRD|PROPNAME|EMAIL|PHONE|ADDRESS|messageID)' \
  docs/superpowers/specs docs/superpowers/evidence 2>/dev/null && exit 1 || true
git diff --check
```

Expected: no placeholder/privacy match and a clean diff check.

- [ ] **Step 5: Commit only sanitized documentation**

Run:

```bash
git add docs/superpowers/specs/2026-07-14-system-delay-status-cancel-design.md
test ! -f docs/superpowers/evidence/2026-07-14-system-delay-protocol.md || \
  git add docs/superpowers/evidence/2026-07-14-system-delay-protocol.md
git diff --cached --check
git commit -m "docs: record issue 92 protocol discovery"
```

Expected: no raw capture/tooling file is staged.

- [ ] **Step 6: Stop for specification review**

Report the selected decision, exact evidence limitations, restoration status, and commit. Do not write or execute a feature implementation plan until this amended specification is reviewed.

---

## Self-Review

**1. Spec coverage:** The plan records the independently failed cancellation
gate and forbids every replay/configuration write. Remaining work separately
observes repeated natural heater and valve transitions, correlates bounded
`GetActiveStatusMessages` reads with retained pushes, verifies both transports,
establishes passive setup predicates independently, restores normal UI state,
sanitizes evidence, selects sensor-only or unsupported, and stops before feature
implementation.

**2. Placeholder scan:** Every branch has an explicit terminal result. The plan
contains no speculative command value and deliberately refuses to manufacture
one; no replay input passed the official asset gate.

**3. Type/interface consistency:** The observer uses public `ICConnection`
methods, raw read-only `GetParamList`/`RequestParamList`/
`GetActiveStatusMessages`, explicit `Literal["tcp", "websocket"]`, stable object
and answer alias dictionaries, and bounded resource/cadence guards. Later steps
never substitute `request_changes()` for an unknown command and never treat a
`200` acknowledgement as active state.
