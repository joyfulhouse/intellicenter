# Light Group Protocol Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and verify the exact IntelliCenter contracts for Color Sync, Color Set, Color Swim, and per-member light-group positioning before implementing issue #93.

**Architecture:** Use a purpose-built raw `ICConnection` observer to preserve parent `CIRCUIT`, membership-row `CIRCGRP`, and referenced-child state without the library's current incorrect grouping helpers. Capture each official Web App request and response, prove completion and restoration with fresh reads, then replay only the captured request independently over TCP and WebSocket. Amend the approved design with exact facts and stop before production group-model or Home Assistant changes.

**Tech Stack:** Python 3.13+, `pyintellicenter` raw `ICConnection`, asyncio, pytest, Chrome DevTools Protocol, IntelliCenter TCP 6681/WebSocket 6680, Markdown evidence.

## Global Constraints

- This is protocol discovery only. Do not correct `_mixins/circuit_group.py`, add public group helpers, change coordinator tracking, register Home Assistant services, or create selects in this plan.
- Use external worktrees based on fetched commits: pyintellicenter `9ee8d55694c14713f39886866f21f68902b8ca7d`; evidence/spec work stays on integration branch `docs/issues-92-93-plans` descended from `0886531f27d338191d8ab1642b6480ded4a4f553`.
- Never run `git worktree prune`, `git clean`, `git stash`, a reset command, or modify either primary checkout.
- Require `INTELLICENTER_HOST`; never use a fallback host and never print endpoint, property name, object identifiers, group/member/equipment names, location/contact fields, PINs, credentials, or raw browser trace.
- Keep captures outside Git in a mode-`0700` temporary directory with mode-`0600` files. Only sanitized, stable aliases enter repository evidence.
- Use raw `ICConnection`, not `ICModelController`, `get_all_objects()`, the current grouping helpers, integration diagnostics, or existing live scripts. Current helpers misclassify membership rows and `get_all_objects()` prunes unsupported echoes.
- Install notification callbacks before connecting. Use one observer at a time, `keepalive_interval=3600`, `notification_queue_size=1000`, and subscription batches below 50 aggregate attributes.
- Select only a parent `CIRCUIT/SUBTYP=LITSHO` with non-empty membership where every `CIRCGRP.PARENT` row resolves, every singular `CIRCGRP.CIRCUIT` child resolves, and every child is a supported color light. Empty, mixed, missing, or unresolved membership aborts all write discovery.
- The upstream `{ACT: SYNC|SET|SWIM, STATUS: ON}` shape is only a lead and remains explicitly unverified. Do not send it unless the official capture proves it exactly.
- All initial actions and member-position changes occur through the official Web App. Replay only an exact captured local request; never translate a cloud request into a guessed local command.
- The two issue tracks may build and test read-only tooling in parallel, but no #93 state-changing live phase may overlap a #92 live phase.
- A passing action requires a correlated `response == "200"`, a repeatable authoritative completion signal within a bounded window, no unrelated equipment change, and successful restoration. A response, optimistic state, command echo, or physical observation alone is insufficient.
- A passing member-position write requires a stable fresh read from a newly connected observer. A command echo is not state. Every option exposed later must have a captured protocol token.
- Test TCP and WebSocket independently. If their contracts differ, record transport-specific support; future production code must gate by the active transport.
- Abort on service/timeout mode, freeze protection, automation/schedule interference, unrelated actuator change, membership mutation, queue overflow, rejected/malformed response, connection loss, or inability to restore promptly.
- Preserve existing ordinary parent on/off behavior and existing verified standard light effects. Sync/Set/Swim remain momentary actions, never invented persistent effects.
- Group actions and member positioning are independently gated. Failure of member positioning does not block proven actions; no action or select implementation plan is written until amended evidence is reviewed.

---

### Task 1: Create the isolated discovery workspace

**Files:**
- No repository files changed.

**Interfaces:**
- Consumes: clean pyintellicenter base `9ee8d55694c14713f39886866f21f68902b8ca7d`.
- Produces: external worktree `/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-93` on branch `discovery/issue-93-light-group-protocol` with a green baseline.

- [ ] **Step 1: Confirm the target is unused**

Run:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter \
  branch --list discovery/issue-93-light-group-protocol
test ! -e /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-93
```

Expected: no branch output and `test` exits 0. Choose a new issue-specific branch/path rather than deleting unknown state if either is occupied.

- [ ] **Step 2: Create the external worktree**

Run:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-discovery-issue-93 \
  -b discovery/issue-93-light-group-protocol \
  9ee8d55694c14713f39886866f21f68902b8ca7d
```

Expected: worktree created at the requested base.

- [ ] **Step 3: Sync and verify the baseline**

Run from the new worktree:

```bash
uv sync --frozen --extra dev
uv run pytest -q
```

Expected: dependencies resolve without lock drift and all tests pass. Stop and report on failure.

---

### Task 2: Build a narrow topology-aware group observer

**Files:**
- Create: `scripts/capture_light_group_protocol.py`
- Create: `tests/test_capture_light_group_protocol.py`

**Interfaces:**
- Consumes: raw `ICConnection` request/notification APIs and `COLOR_EFFECT_SUBTYPES`.
- Produces:
  - `sanitize_frame(frame: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]`
  - `build_complete_light_groups(entries: list[dict[str, Any]]) -> list[LightGroupTarget]`
  - `validate_capture_path(path: Path, repo_root: Path) -> None`
  - `capture_phase(*, transport: Literal["tcp", "websocket"], label: str, seconds: int, output: Path) -> None`
  - CLI: `python scripts/capture_light_group_protocol.py --transport {tcp,websocket} --label LABEL --seconds N --output ABSOLUTE_PATH`

`LightGroupTarget` is a frozen dataclass with `parent_objnam: str`, `member_objnams: tuple[str, ...]`, and `child_objnams: tuple[str, ...]`. Members are ordered by numeric `LISTORD`, with malformed/missing values last in stable inventory order. This records the historical discovery observer only: all captured target rows had valid unique numeric orders, so the fallback was never evidence-bearing. The reviewed production model later adopts `objnam` as a total deterministic tiebreaker for duplicate/negative/malformed orders.

- [ ] **Step 1: Write failing sanitizer and topology tests**

Add these exact behavior tests, using helper entry factories where repetition would obscure assertions:

```python
from pathlib import Path
from typing import Any

import pytest

from scripts.capture_light_group_protocol import (
    LightGroupTarget,
    build_complete_light_groups,
    sanitize_frame,
)


def entry(objnam: str, **params: Any) -> dict[str, Any]:
    return {"objnam": objnam, "params": params}


def test_sanitize_frame_preserves_group_tokens_but_removes_private_data() -> None:
    frame = {
        "messageID": "9",
        "response": "200",
        "objectList": [{
            "objnam": "GRP02",
            "params": {
                "OBJTYP": "CIRCUIT",
                "SUBTYP": "LITSHO",
                "SNAME": "private-group-name",
                "ACT": "SYNC",
                "STATUS": "ON",
            },
        }],
    }

    assert sanitize_frame(frame, {}) == {
        "response": "200",
        "objectList": [{
            "objnam": "OBJECT_001",
            "params": {
                "OBJTYP": "CIRCUIT",
                "SUBTYP": "LITSHO",
                "ACT": "SYNC",
                "STATUS": "ON",
            },
        }],
    }


def test_complete_group_orders_rows_and_resolves_every_child() -> None:
    entries = [
        entry("GRP02", OBJTYP="CIRCUIT", SUBTYP="LITSHO"),
        entry("ROW02", OBJTYP="CIRCGRP", PARENT="GRP02", CIRCUIT="C0004", LISTORD="2"),
        entry("ROW01", OBJTYP="CIRCGRP", PARENT="GRP02", CIRCUIT="C0002", LISTORD="1"),
        entry("C0002", OBJTYP="CIRCUIT", SUBTYP="INTELLI"),
        entry("C0004", OBJTYP="CIRCUIT", SUBTYP="GLOW"),
    ]

    assert build_complete_light_groups(entries) == [
        LightGroupTarget("GRP02", ("ROW01", "ROW02"), ("C0002", "C0004"))
    ]


@pytest.mark.parametrize("entries", [
    [entry("GRP02", OBJTYP="CIRCUIT", SUBTYP="LITSHO")],
    [
        entry("GRP02", OBJTYP="CIRCUIT", SUBTYP="LITSHO"),
        entry("ROW01", OBJTYP="CIRCGRP", PARENT="GRP02", CIRCUIT="MISSING"),
    ],
    [
        entry("GRP02", OBJTYP="CIRCUIT", SUBTYP="LITSHO"),
        entry("ROW01", OBJTYP="CIRCGRP", PARENT="GRP02", CIRCUIT="PUMP01"),
        entry("PUMP01", OBJTYP="PUMP", SUBTYP="VSF"),
    ],
])
def test_incomplete_empty_or_mixed_group_is_not_a_target(entries: list[dict[str, Any]]) -> None:
    assert build_complete_light_groups(entries) == []


def test_observer_source_contains_no_write_command() -> None:
    source = Path("scripts/capture_light_group_protocol.py").read_text()
    assert "SETPARAMLIST" not in source.upper()
    assert "request_changes" not in source
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
uv run pytest tests/test_capture_light_group_protocol.py -v
```

Expected: collection fails because the observer module does not exist.

- [ ] **Step 3: Implement exact allowlists and topology validation**

Use these query keys:

```python
PRIVATE_KEYS = frozenset({
    "ADDRESS", "CITY", "COUNTRY", "EMAIL", "EMAIL2", "HNAME", "LOCX",
    "LOCY", "NAME", "PASSWRD", "PHONE", "PHONE2", "PROPNAME", "SNAME",
    "SOURCE", "STATE", "ZIP", "messageID",
})
REFERENCE_KEYS = frozenset({"objnam", "BODY", "CHILD", "CIRCUIT", "PARENT"})
READ_KEYS_BY_TYPE = {
    "SYSTEM": ("OBJTYP", "SUBTYP", "VER", "SERVICE"),
    "CIRCUIT": (
        "OBJTYP", "SUBTYP", "PARENT", "STATUS", "ACT", "USE", "SYNC",
        "SWIM", "SET", "LISTORD", "LIMIT", "READY",
    ),
    "CIRCGRP": (
        "OBJTYP", "SUBTYP", "PARENT", "CIRCUIT", "LISTORD", "USE", "DLY",
        "ACT", "STATUS", "READY",
    ),
}
```

Implement stable `OBJECT_NNN` reference aliasing and the same outside-repository output validation described by the interfaces. `build_complete_light_groups()` must accept only real parent `CIRCUIT/SUBTYP=LITSHO` objects, require at least one row, require each row's singular non-whitespace `CIRCUIT` reference, resolve every child, and require every child `OBJTYP=CIRCUIT` with `SUBTYP` in `COLOR_EFFECT_SUBTYPES`. It must never treat an orphan/legacy row as a group.

`capture_phase()` must fail when `INTELLICENTER_HOST` is absent, set the callback before connecting, enumerate only the three allowlisted types, choose exactly one complete target (fail safely on zero or multiple targets), subscribe to the aliased target's real parent/rows/children, record raw responses and ordered pushes only after sanitization, print only `READY {label} {transport}`, wait the bounded duration, and disconnect in `finally`. Output is absolute, outside Git, and opened mode `0o600`.

- [ ] **Step 4: Run focused tests green**

Run:

```bash
uv run pytest tests/test_capture_light_group_protocol.py -v
uv run ruff check scripts/capture_light_group_protocol.py tests/test_capture_light_group_protocol.py
uv run ruff format --check scripts/capture_light_group_protocol.py tests/test_capture_light_group_protocol.py
```

Expected: all tests pass and Ruff is clean.

- [ ] **Step 5: Commit discovery tooling locally**

Run:

```bash
git add scripts/capture_light_group_protocol.py tests/test_capture_light_group_protocol.py
git commit -m "test: add safe light group protocol observer"
```

Expected: a local discovery commit, not a production/release PR.

---

### Task 3: Establish topology and invariant snapshots on both transports

**Files:**
- Raw, untracked: mode-`0700` temporary capture directory.

**Interfaces:**
- Consumes: Task 2 observer and private `.env` via `uv --env-file`.
- Produces: independently captured TCP/WebSocket topology, target alias mapping held privately, and initial parent/member/child invariants.

- [ ] **Step 1: Create a private capture directory**

Run:

```bash
umask 077
CAPTURE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/intellicenter-issue-93.XXXXXX")"
chmod 700 "$CAPTURE_DIR"
printf '%s\n' "$CAPTURE_DIR"
```

Expected: one private temporary directory path.

- [ ] **Step 2: Confirm operational preconditions**

Through read-only panel/Web App inspection, verify `SERVICE=AUTO`, no automation or schedule is changing the target lights, and the selected private group contains only intended color lights. Record privately the parent power/effect, membership order and row attributes, referenced child power/effect, and the visual state needed for restoration.

- [ ] **Step 3: Capture independent passive baselines**

Run sequentially, polling long-running sessions every 30 seconds or less:

```bash
uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
  python scripts/capture_light_group_protocol.py \
  --transport tcp --label inactive-tcp --seconds 30 \
  --output "$CAPTURE_DIR/inactive-tcp.jsonl"

uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
  python scripts/capture_light_group_protocol.py \
  --transport websocket --label inactive-websocket --seconds 30 \
  --output "$CAPTURE_DIR/inactive-websocket.jsonl"
```

Expected: both runs choose the same logical aliased topology and make no equipment change.

- [ ] **Step 4: Run privacy and topology gates**

Run:

```bash
test "$(stat -f '%Lp' "$CAPTURE_DIR")" = 700
find "$CAPTURE_DIR" -type f ! -perm 600 -print
rg -n '"(ADDRESS|CITY|COUNTRY|EMAIL|EMAIL2|HNAME|LOCX|LOCY|NAME|PASSWRD|PHONE|PHONE2|PROPNAME|SNAME|SOURCE|STATE|ZIP|messageID)"' "$CAPTURE_DIR" && exit 1 || true
```

Expected: no permission/privacy output. Manually confirm membership is non-empty and identical across transports; all rows and children resolve; every child is a supported color light. Abort writes on any mismatch.

---

### Task 4: Capture and repeat official group actions

**Files:**
- Raw browser and observer traces: private capture directory only.

**Interfaces:**
- Consumes: official Web App session and Task 3 invariant snapshot.
- Produces: exact official request/response/notification/fresh-read sequence for Sync, Set, and Swim, plus per-action restoration proof.

In the same private shell that owns `CAPTURE_DIR`, define this launcher once:

```bash
capture_group_phase() {
  label="$1"
  uv run --env-file /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter/.env \
    python scripts/capture_light_group_protocol.py \
    --transport websocket --label "$label" --seconds 180 \
    --output "$CAPTURE_DIR/$label.jsonl"
}
```

Start one invocation in a PTY, wait for `READY`, perform only its named official UI action, and poll at intervals of 30 seconds or less.

- [ ] **Step 1: Start official Web App frame capture**

Use Chrome DevTools Protocol with an already authenticated official Web App session. Begin recording immediately before each action and retain privately only the outbound action frame, its correlated response, and minimum surrounding notifications. If the official request cannot be captured without credentials/PII, record the action gate as failed; do not infer a request from upstream source.

- [ ] **Step 2: Capture Color Sync twice**

For `official-sync-1` and `official-sync-2`, start a bounded observer, invoke Color Sync exactly once in the official UI, wait for completion, fresh-read parent/rows/children, then restore parent/member/child state through the official UI and verify against the invariant snapshot.

Run separately:

```bash
capture_group_phase official-sync-1
capture_group_phase official-sync-2
```

- [ ] **Step 3: Capture Color Set twice**

Repeat the exact sequence for `official-set-1` and `official-set-2`, restoring before and after every run.

Run separately:

```bash
capture_group_phase official-set-1
capture_group_phase official-set-2
```

- [ ] **Step 4: Capture Color Swim twice**

Repeat the exact sequence for `official-swim-1` and `official-swim-2`, restoring before and after every run.

Run separately:

```bash
capture_group_phase official-swim-1
capture_group_phase official-swim-2
```

- [ ] **Step 5: Classify action semantics before replay**

For each action, record whether the request targets the parent or another object; whether it uses `ACT`, a dedicated `SYNC`/`SET`/`SWIM` key, or another command; whether `STATUS=ON` is required; whether the group may begin off; exact `200` acknowledgement; authoritative completion frame/fresh-read; duration bound; and every changed parent/row/child field. An action with no authoritative completion signal or unrelated change fails independently.

---

### Task 5: Verify member-position read/write and finite options

**Files:**
- Private capture traces only.

**Interfaces:**
- Consumes: official member-position UI and Task 3 target topology.
- Produces: exact writable row/field, stable readable field, complete finite token map, notification/fresh-read contract, or an omitted-select result.

Use the Task 4 `capture_group_phase` launcher with labels `member-original`, `member-option-N`, `member-repeat-1`, `member-repeat-2`, and `member-restored`. Replace `N` only with the one-based ordinal displayed in the private official UI option list; record the label-to-human-name mapping only in the private execution log.

- [ ] **Step 1: Capture the original row position**

Choose one member row through the private alias mapping. Record its current official UI option and raw readable attributes, change nothing, disconnect, reconnect with a fresh observer, and confirm the same readable token persists.

- [ ] **Step 2: Capture every official UI option**

One option at a time, invoke the official UI change, capture outbound request and correlated response, wait for a matching row push, disconnect/reconnect, and fresh-read the row. Restore the original option and verify before testing the next token. Build a complete human-label-to-token table; if any visible option lacks a stable token, the select gate fails.

- [ ] **Step 3: Prove a second non-original value twice**

Select one non-original option, perform and restore it twice, and require the same target, writable field, response, row push or fresh-read fallback, and persisted token. Reject transient action echoes.

- [ ] **Step 4: Verify no collateral configuration changed**

Fresh-query all membership rows and parent/children after restoration. Require membership, `LISTORD`, every other member position, parent power/effect, and child power/effect to match the invariant snapshot.

---

### Task 6: Replay only captured local contracts over TCP and WebSocket

**Files:**
- Private replay traces only.

**Interfaces:**
- Consumes: exact local requests and completion predicates from Tasks 4–5.
- Produces: per-action/per-position transport support matrix.

- [ ] **Step 1: Reject non-local or ambiguous requests**

Do not replay cloud-only requests, requests with private authentication semantics, ambiguous targets, missing correlated `200` responses, or missing authoritative completion. Never convert the upstream proposed `{ACT: token, STATUS: ON}` lead into a request unless it exactly matches the official frame.

- [ ] **Step 2: Replay Sync, Set, and Swim once over TCP**

For each independently passing action: restore first, start the observer, send the exact captured local command once through `ICConnection.send_request()` over TCP, require the captured completion, fresh-read, and restore. A timeout is terminal; never retry a state-changing request.

- [ ] **Step 3: Replay Sync, Set, and Swim once over WebSocket**

Repeat from a restored invariant snapshot over WebSocket. Record any transport difference instead of normalizing it away.

- [ ] **Step 4: Replay one member-position transition and restoration on each transport**

Only if Task 5 passed, write the same proven non-original option once over TCP and once over WebSocket, with restoration between transports. Require a matching row push; when the captured transport produces no push, disconnect/reconnect and require a fresh read. Restore the original token and verify all group invariants.

- [ ] **Step 5: Perform final restoration twice**

Restore through the official UI and compare the full parent/member/child snapshot twice. Reload Home Assistant if it was deliberately unloaded for a single-client TCP limitation.

---

### Task 7: Sanitize, decide, and amend the approved specification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-14-light-group-actions-design.md`
- Create only if useful: `docs/superpowers/evidence/2026-07-14-light-group-protocol.md`

**Interfaces:**
- Consumes: Tasks 3–6 results.
- Produces: exact action payloads/acknowledgements/completion contracts, transport matrix, finite position mapping if proven, capability predicates, and the staged implementation scope.

- [ ] **Step 1: Write sanitized evidence**

Retain firmware `1.064`, exact field names/tokens, aliased topology, ordered response/notification/fresh-read deltas, repeat counts, duration bounds, transport, collateral-change checks, and restoration results. Remove endpoint, real object names, friendly names, browser headers/cookies, message IDs, credentials, and raw frames.

- [ ] **Step 2: Decide each capability independently**

For Sync, Set, and Swim, mark supported only when official capture, repeatability, local replay, authoritative completion, topology safety, and restoration all pass. Mark member positioning supported only when the writable/readable field, full finite option table, persisted fresh read, both transport results or explicit transport gate, and restoration pass.

- [ ] **Step 3: Resolve remaining design facts**

Update the spec with:

- exact public command/position signatures and verified payloads;
- acknowledgement and bounded completion predicates;
- active transport capability predicate;
- whether `LITSHO` alone is sufficient or complete membership remains mandatory;
- whether row `USE` is the position field and its exact option tokens;
- row push versus fresh-read behavior;
- confirmation that existing standard group effects remain separate from momentary Sync/Set/Swim;
- selected staged implementation plans and any omitted capability.

- [ ] **Step 4: Run placeholder, privacy, and diff checks**

Run from the integration planning worktree:

```bash
rg -n '\b(TBD|TODO|FIXME|XXX)\b|\.\.\.|<[^>]+>' \
  docs/superpowers/specs/2026-07-14-light-group-actions-design.md \
  docs/superpowers/evidence/2026-07-14-light-group-protocol.md 2>/dev/null || true
rg -n '(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|PASSWRD|PROPNAME|EMAIL|PHONE|ADDRESS|messageID)' \
  docs/superpowers/specs docs/superpowers/evidence 2>/dev/null && exit 1 || true
git diff --check
```

Expected: no placeholder/privacy matches and a clean diff.

- [ ] **Step 5: Commit only sanitized documentation**

Run:

```bash
git add docs/superpowers/specs/2026-07-14-light-group-actions-design.md
test ! -f docs/superpowers/evidence/2026-07-14-light-group-protocol.md || \
  git add docs/superpowers/evidence/2026-07-14-light-group-protocol.md
git diff --cached --check
git commit -m "docs: record issue 93 protocol discovery"
```

Expected: no raw capture, `.env`, browser trace, or discovery script is staged in the integration worktree.

- [ ] **Step 6: Stop for specification review**

Report the independently passing capabilities, exact limitations, transport support, restoration result, and commit. Do not write or execute library/integration feature plans until this amended specification is reviewed.

---

## Self-Review

**1. Spec coverage:** The plan uses the corrected parent/row/child model, rejects unsafe topology, captures official request/response/notifications, repeats all three actions, fresh-reads and restores every phase, enumerates finite member options, verifies TCP and WebSocket independently, treats action and select gates independently, sanitizes evidence, and stops before feature code.

**2. Placeholder scan:** Unknown protocol values are evidence inputs, never guessed implementation blanks. Every unknown has an explicit capture method and a terminal omit/fail result. The plan does not send the upstream proposed payload unless official evidence matches it.

**3. Type/interface consistency:** `LightGroupTarget` retains ordered rows and children; only raw `ICConnection` methods are used; action replay preserves the captured command instead of assuming `request_changes()`; member state requires push or disconnected fresh read; momentary commands remain separate from persistent standard effects.
