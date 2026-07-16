# Light Group Modeling and Color Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct pyintellicenter's real parent/membership-row group model and expose the verified Color Sync action on complete IntelliCenter light-group entities over TCP and WebSocket in Home Assistant.

**Architecture:** Keep group identity and control on the parent `CIRCUIT/SUBTYP=LITSHO`; treat `OBJTYP=CIRCGRP` objects only as ordered membership rows. A dedicated `run_light_group_sync(group_objnam)` method captures one live connection, establishes an exclusive controller mutation lifecycle, installs a raw enqueue-time sequenced observer before the first fresh projection, starts the monotonic deadline inside the request lock immediately before transport initiation, and captures a separate causal onset watermark immediately after the transport accepts the send. One wildcard `GetParamList` request fetches the complete safety projection with a fixed key set below the protocol ceiling; exact-object subscriptions are split into bounded batches. The helper sends the exact mixed-case command once, requires sender-side `SYNC=ON` and `SYNC=OFF` by the dispatch-start 60-second deadline, observes the complete safety projection for another 60 seconds, and performs a mandatory final in-band read on that same connection. Home Assistant adds one momentary `color_sync` entity service to the existing parent light, maps action certainty from a phase-aware error, and never turns the action into an effect or optimistic state.

**Tech Stack:** Python 3.13/3.14, asyncio, pyintellicenter TCP/WebSocket transports, pytest/pytest-asyncio, Ruff, mypy, Home Assistant 2026.5.4, HACS/hassfest, uv, GitHub Actions, PyPI.

## Global Constraints

- Implement in two isolated feature worktrees based on freshly fetched upstream commits. The known anchors on 2026-07-15 are pyintellicenter `origin/main=9ee8d55694c14713f39886866f21f68902b8ca7d` and intellicenter `origin/main=4f943e90a715997e8db1c50a7613c3aa843a86c5`; if either upstream moved, record the new fetched commit and re-run the baseline before editing.
- This plan ships only Color Sync. The public library API is exactly `async def run_light_group_sync(group_objnam: str) -> dict[str, Any]`; do not add a generic action-token API, Color Set, Color Swim, a member-position writer, or a member-position select.
- The action request is exactly mixed-case `SetParamList`, one parent object, and only `{"SYNC": "ON"}`. Do not route it through uppercase `SETPARAMLIST`, `request_changes()`, the coalescing serializer, `ACT`, `STATUS`, `SET`, or `SWIM`.
- Same-connection evidence on firmware `1.064` passed Sync from uniform `OFF` and uniform `ON` prestates over TCP and WebSocket. The sender-side action field is `SYNC`; terminal observations ranged from 35.286805 to 36.238773 seconds with no collateral projection change.
- Gate the action capability to the exact evidence envelope: fresh firmware exactly `1.064`, one real `CIRCUIT/LITSHO` parent, and exactly two distinct resolved `CIRCUIT/GLOW` children. The general read helpers may continue to classify `INTELLI` and `MAGIC2` as color-capable and may read groups of other cardinalities, but the state-changing Sync helper and Home Assistant service must reject them until separately captured.
- The 60-second action deadline starts at the pre-send hook, not before lock acquisition or after acknowledgement. Both positive post-watermark onset and terminal must occur by that deadline. After terminal, observe for a separate mandatory 60-second interval, then perform a mandatory in-band final projection read. The rejected TCP Swim replay regressed 9.046 seconds after its apparent terminal, so the full minute is an intentionally conservative state-changing safety gate.
- Accept only uniform target prestates: parent and every resolved child all `OFF`, or all `ON`. Reject mixed, missing, or noncanonical status before the write. Sync's expected final power projection is parent plus every child `ON` for either accepted prestate.
- Before the write require exactly one cached/fresh `SYSTEM`, `VER=1.064`, `SERVICE=AUTO`, a real `CIRCUIT/LITSHO` parent, exactly two membership rows, both child references resolved and distinct, both children `CIRCUIT/GLOW`, and every `SYNC`/`SET`/`SWIM` flag on every group parent `OFF`.
- Build the topology and fixed wildcard projection request synchronously, install the raw observer, and only then fetch the first complete fresh safety projection. Until that first response becomes the validated baseline, the tracker stores projected frames in a bounded pre-baseline buffer and fails closed on overflow; baseline installation replays the buffer in sequence. Subscribe to the exact discovered projection in batches of at most `MAX_ATTRIBUTES_PER_QUERY`, validate every subscription initialization response against the baseline, wait the empirically exercised one-second settle, and repeat the complete wildcard `GetParamList` preflight. The observer is active before both the first read and subscription. The settled projection must exactly equal the first baseline, and any projected notification or subscription-initialization deviation after baseline installation rejects before the write even if a later frame or second read restores the original value.
- Do not classify action edges from a boolean arm. A connection-owned monotonic notification sequence is assigned at enqueue time. Under the connection request lock, an internal before-write hook records the event-loop time immediately before TCP `transport.write()` or initiation of WebSocket `send()` and starts the 60-second deadline. A separate after-write hook captures the current sequence immediately after synchronous TCP `transport.write()` returns or awaited WebSocket `send()` completes. Only notifications whose sequence is strictly greater than that post-send watermark are eligible action edges. This excludes frames received while the request waits behind another connection request and, conservatively, frames processed while WebSocket `send()` is suspended; those ambiguous frames still undergo invariant checks but never prove onset.
- Retain eligible post-send-watermark notifications that precede the correlated acknowledgement. A response `200`, command echo, initial `ON`, status alone, or a final fresh read without a positive causal onset is not completion.
- From dispatch start until observer removal, enforce every normalized projected invariant monotonically: an all-on target object may never report `OFF`; an all-off target object may not return to `OFF` after it first reports `ON`; every circuit `OBJTYP`/`SUBTYP` and normalized optional `PARENT` plus every target optional `USE`/required `SET`/`SWIM` stay at baseline; every unrelated `CIRCUIT` `STATUS`/optional `USE` stays at baseline; every non-target group flag, every membership row's topology/optional `USE`, and `SYSTEM` firmware/service stay at baseline. Target `SYNC` may make only the qualifying post-watermark `OFF -> ON -> OFF` lifecycle and may not re-enter `ON` after terminal. A transient violation is final even if a later frame restores the value.
- The final projection is fetched with the same wildcard `GetParamList` on the exact captured connection after the full 60-second post-terminal observation interval. It includes normalized optional `PARENT`/`USE` plus required identity/status fields for every `CIRCUIT`, topology/optional `USE` for every membership row, all group flags, and system firmware/service. Missing, key-echo, and protocol null-reference representations for optional fields normalize to one absence value and are compared to baseline; mandatory topology/status/action fields never accept placeholders. The final projection must exactly satisfy those baseline invariants plus target parent/two-child `STATUS=ON` and target `SYNC=OFF`; it never substitutes for onset or terminal edges.
- Never retry a state-changing request and never issue an automatic recovery/off command after timeout or protocol failure. Surface ambiguity to the caller and leave physical inspection/recovery to the user.
- The action observer must be enqueue-time and additive. It must not replace Home Assistant's model callback, process stale frames already in the callback queue, or remain registered after success, error, disconnect, reconnect, cancellation, or timeout. Immediately after capturing the connection, synchronously capture that exact generation's one-shot close future and race it against subscription settling and every lifecycle/observation wait so disconnect never sleeps until a generic deadline or disappears behind same-instance reconnect. Because observer state survives transport replacement, the registered closure checks `connection_closed.done()` before forwarding every frame; once closed, no new-generation frame can mutate or complete the old tracker. In any simultaneous wait tie, closure wins before response/edge processing.
- One controller-wide mutation lifecycle lock must cover both fresh preflights, subscription/settling, write, terminal wait, post-terminal observation, and final read. Sync marks its lifecycle pending before awaiting that lock, so already-started public `SetParamList` work drains before preflight, while every later case-insensitive public `SetParamList` call—including `request_changes()` and coalesced flushes—fails immediately with an ordinary pre-dispatch `ICError` instead of waiting up to two minutes. A second Sync likewise fails busy before dispatch. The private captured-connection unlocked primitive is used only by Sync while it owns the lifecycle. A caller that directly constructs and writes through a separate raw `ICConnection` is outside the controller boundary; document that boundary. Read-only requests, keepalives, and model notifications continue through the connection request lock. An urgent physical-panel action remains possible but causes Sync to fail if it changes a projected invariant.
- After dispatch begins, replace generic protocol/timeout outcomes with `ICLightGroupError(ICError)` carrying `phase`, an always-true `dispatch_started`, `response_received`, `acknowledged`, and `onset_seen`. Unsupported cached topology raises `ValueError`; all network/projection/busy failures known to occur before dispatch remain ordinary `ICError` subclasses. `phase` names the gate that failed, not the latest edge seen, so `phase="acknowledgement"` may truthfully coexist with `onset_seen=True` when a push precedes a missing response. Home Assistant must distinguish unsupported, prewrite/explicit rejection, dispatched-with-no-response uncertainty, and acknowledged-or-started incomplete outcomes.
- Membership rows remain model-only. Track only `PARENT`, singular `CIRCUIT`, and `LISTORD` in the Home Assistant coordinator; never create a row-derived entity or expose row `SNAME`, `STATUS`, `USE`, or action flags as durable entity state.
- Preserve direct compatibility for an exact legacy standalone `CIRCGRP` fixture passed to `get_circuits_in_group()`, but never enumerate that artificial row as a real group or color-light group.
- Do not edit the evidence or design documents while executing this plan. Do not include private hosts, object identifiers, equipment names, raw frames, credentials, or discovery captures in either repository.
- Once the library API and focused contract tests are stable, integration implementation may proceed in parallel using a temporary uncommitted editable install of the pyintellicenter feature worktree. Never commit a path/git dependency. Regenerating and committing the integration dependency lock and opening the integration PR must wait for a maintainer-confirmed pyintellicenter merge and published `0.1.22` PyPI artifact.
- Opening feature/release PRs is planned work. Merging PRs, creating tags, and publishing PyPI or GitHub releases are explicit user/maintainer checkpoints; stop and request confirmation at each checkpoint rather than treating those actions as authorized implementation steps. A later separately approved release PR advances the integration from `3.10.0b2` to `3.10.0b3`.

---

## File Structure

### pyintellicenter repository

- Create `src/pyintellicenter/_light_group.py`: private topology/projection dataclasses, exact query construction, snapshot validation, and the Sync lifecycle tracker.
- Modify `src/pyintellicenter/_mixins/circuit_group.py`: corrected public read helpers plus the dedicated `run_light_group_sync()` orchestration method.
- Modify `src/pyintellicenter/_mixins/_base.py`: static-only declarations for the connection-bound send helper, mutation lock, connection, and transport used by the mixin.
- Modify `src/pyintellicenter/connection.py`: connection-owned monotonic enqueue sequencing, raw observer fanout, internal pre-send deadline/post-send watermark hooks under the request lock, and an awaitable connection-closed signal shared by TCP and WebSocket.
- Modify `src/pyintellicenter/controller.py`: controller-wide mutation lock and a captured-connection send primitive; drain already-started writers and fail later direct/coalesced writes during Sync.
- Modify `src/pyintellicenter/exceptions.py` and `src/pyintellicenter/__init__.py`: add/export phase-aware `ICLightGroupError` and later prepare version `0.1.22` for maintainer-approved publication.
- Create `tests/test_circuit_group.py`: real topology, ordering, malformed rows, color detection, and legacy compatibility.
- Create `tests/test_light_group_sync.py`: exact-two-member preflight, exact command, phase-aware errors, both transports/prestates, split dispatch-start deadline/post-send watermark, 60-second observation, complete transient invariants, final projection, locking, and cleanup.
- Modify `tests/test_connection.py`: observer fanout, stale-queue exclusion, removal, exception isolation, and close signaling.
- Modify `tests/test_controller.py`: captured-connection sends and fail-fast mutation-isolation regressions.
- Modify `tests/test_typing_public_api.py`: downstream type visibility for `run_light_group_sync()` and `ICLightGroupError`.
- Modify `docs/API.md`, `docs/USAGE.md`, `CHANGELOG.md`, `pyproject.toml`, and `uv.lock`: corrected public contract, user guidance, changelog, and release metadata.

### intellicenter repository

- Modify `custom_components/intellicenter/coordinator.py`: correct membership-row tracking keys.
- Modify `custom_components/intellicenter/light.py`: complete-group preflight, `color_sync` registration, and `PoolLight.async_color_sync()`.
- Modify `custom_components/intellicenter/services.yaml`: one `color_sync` light entity service.
- Modify `custom_components/intellicenter/strings.json` and all 12 files under `custom_components/intellicenter/translations/`: service copy plus unsupported, failed/rejected, uncertain-dispatch, and incomplete-action translations.
- Modify `custom_components/intellicenter/manifest.json`, `pyproject.toml`, and `uv.lock`: require/relock released pyintellicenter `0.1.22`; later advance integration release metadata to `3.10.0b3`.
- Modify `tests/conftest.py`, `tests/test_light.py`, `tests/test_library_contract.py`, and `tests/test_versions.py`: real topology fixtures, entity/service behavior, installed library contract, and dependency/version drift.
- Modify `README.md` and `CHANGELOG.md`: document Color Sync as a blocking momentary action and the corrected group model.

---

### Task 1: Create isolated implementation worktrees and capture green baselines

**Files:**
- No repository files changed.

**Interfaces:**
- Consumes: fetched upstream commits described in Global Constraints.
- Produces: `/Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-issue-93-sync` on `feature/issue-93-light-group-sync` and `/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter-issue-93-sync` on the same branch name.

- [ ] **Step 1: Fetch without touching either primary checkout's worktree state**

Run:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter fetch origin
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter fetch origin
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter rev-parse origin/main
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter rev-parse origin/main
```

Expected: two commit IDs. Record them in the implementation log; do not reset either primary checkout.

- [ ] **Step 2: Verify branch/path availability and create worktrees**

Run:

```bash
test ! -e /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-issue-93-sync
test ! -e /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter-issue-93-sync
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter branch --list feature/issue-93-light-group-sync
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter branch --list feature/issue-93-light-group-sync
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-issue-93-sync \
  -b feature/issue-93-light-group-sync origin/main
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter-issue-93-sync \
  -b feature/issue-93-light-group-sync origin/main
```

Expected: both preflight commands are silent and both worktrees are created. If a path or branch exists, inspect and choose a new issue-specific name rather than deleting unknown work.

- [ ] **Step 3: Establish the pyintellicenter baseline**

Run from the pyintellicenter worktree:

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
```

Expected: the complete existing suite passes and all static gates are clean.

- [ ] **Step 4: Establish the integration baseline**

Run from the intellicenter worktree:

```bash
uv sync --frozen
uv run pytest tests/ -q
uv run ruff check custom_components/
uv run ruff format --check custom_components/
uv run mypy custom_components/intellicenter/
uv run bandit -r custom_components/intellicenter/ -ll
```

Expected: the complete existing suite passes and all static/security gates are clean. Stop and diagnose any baseline failure before feature edits.

---

### Task 2: Correct the pyintellicenter parent/row group model

**Files:**
- Create: `tests/test_circuit_group.py`
- Modify: `src/pyintellicenter/_mixins/circuit_group.py`
- Modify: `docs/API.md`

**Interfaces:**
- Consumes: `PoolModel`, `PoolObject`, `CIRCUIT_TYPE`, `CIRCGRP_TYPE`, `PARENT_ATTR`, `CIRCUIT_ATTR`, `LISTORD_ATTR`.
- Produces:
  - `get_circuit_groups() -> list[PoolObject]`
  - `get_circuit_group_members(parent_objnam: str) -> list[PoolObject]`
  - `get_circuits_in_group(group_or_row_objnam: str) -> list[PoolObject]`
  - `circuit_group_has_color_lights(parent_objnam: str) -> bool`
  - `get_color_light_groups() -> list[PoolObject]`

- [ ] **Step 1: Write failing real-topology and compatibility tests**

Create focused tests with these exact assertions:

```python
def add_real_group(model: PoolModel) -> None:
    model.add_object("GROUP", {"OBJTYP": "CIRCUIT", "SUBTYP": "LITSHO"})
    model.add_object(
        "ROW_B",
        {"OBJTYP": "CIRCGRP", "PARENT": "GROUP", "CIRCUIT": "CHILD_B", "LISTORD": "2"},
    )
    model.add_object(
        "ROW_BAD",
        {"OBJTYP": "CIRCGRP", "PARENT": "GROUP", "CIRCUIT": "MISSING", "LISTORD": "bad"},
    )
    model.add_object(
        "ROW_A",
        {"OBJTYP": "CIRCGRP", "PARENT": "GROUP", "CIRCUIT": "CHILD_A", "LISTORD": "1"},
    )
    model.add_object("CHILD_A", {"OBJTYP": "CIRCUIT", "SUBTYP": "GLOW"})
    model.add_object("CHILD_B", {"OBJTYP": "CIRCUIT", "SUBTYP": "GLOW"})


def test_real_group_enumerates_parent_not_members(controller: ICModelController) -> None:
    add_real_group(controller.model)
    controller.model.add_object(
        "PLAIN_PARENT", {"OBJTYP": "CIRCUIT", "SUBTYP": "CIRCGRP"}
    )
    controller.model.add_object(
        "ORPHAN", {"OBJTYP": "CIRCGRP", "CIRCUIT": "CHILD_A"}
    )

    assert [obj.objnam for obj in controller.get_circuit_groups()] == [
        "GROUP",
        "PLAIN_PARENT",
    ]


def test_members_are_numeric_order_then_stable_malformed_tail(
    controller: ICModelController,
) -> None:
    add_real_group(controller.model)
    assert [obj.objnam for obj in controller.get_circuit_group_members("GROUP")] == [
        "ROW_A",
        "ROW_B",
        "ROW_BAD",
    ]


def test_parent_and_real_row_resolve_ordered_sibling_children(
    controller: ICModelController,
) -> None:
    add_real_group(controller.model)
    assert [obj.objnam for obj in controller.get_circuits_in_group("GROUP")] == [
        "CHILD_A",
        "CHILD_B",
    ]
    assert [obj.objnam for obj in controller.get_circuits_in_group("ROW_B")] == [
        "CHILD_A",
        "CHILD_B",
    ]


def test_legacy_standalone_row_resolves_directly_but_is_never_enumerated(
    controller: ICModelController,
) -> None:
    controller.model.add_object("A", {"OBJTYP": "CIRCUIT", "SUBTYP": "GLOW"})
    controller.model.add_object("B", {"OBJTYP": "CIRCUIT", "SUBTYP": "LIGHT"})
    controller.model.add_object(
        "LEGACY", {"OBJTYP": "CIRCGRP", "CIRCUIT": "A B"}
    )

    assert [obj.objnam for obj in controller.get_circuits_in_group("LEGACY")] == [
        "A",
        "B",
    ]
    assert controller.get_circuit_groups() == []
    assert controller.get_color_light_groups() == []


def test_color_group_results_are_real_parents(controller: ICModelController) -> None:
    add_real_group(controller.model)
    assert controller.circuit_group_has_color_lights("GROUP") is True
    assert [obj.objnam for obj in controller.get_color_light_groups()] == ["GROUP"]
```

Add cases for missing parent, wrong parent type/subtype, missing/non-string references, missing children, nonnumeric/negative `LISTORD`, duplicate valid orders, multiple malformed orders inserted in reverse object-name order, and a group containing only non-color lights. Missing references are skipped by the read helper; strict command eligibility is tested separately.

- [ ] **Step 2: Run the focused file and verify red**

Run:

```bash
uv run pytest tests/test_circuit_group.py -v
```

Expected: failures show the current implementation returns membership rows as groups and does not aggregate sibling rows.

- [ ] **Step 3: Implement the minimal corrected helpers**

Use a private parent subtype set and a total numeric/object-name sort. Negative,
missing, and malformed values sort after valid orders; duplicate valid orders and
multiple malformed rows use `objnam` as the deterministic tiebreaker rather than
depending on model insertion order:

```python
_GROUP_PARENT_SUBTYPES = frozenset({"CIRCGRP", "LITSHO"})


def _member_order(member: PoolObject) -> tuple[int, int, str]:
    value = member[LISTORD_ATTR]
    try:
        order = int(value)
    except (TypeError, ValueError):
        return (1, 0, member.objnam)
    if order < 0:
        return (1, 0, member.objnam)
    return (0, order, member.objnam)
```

Implement enumeration and membership exactly as follows:

```python
def get_circuit_groups(self) -> list[PoolObject]:
    return [
        obj
        for obj in self._model
        if obj.objtype == CIRCUIT_TYPE and obj.subtype in _GROUP_PARENT_SUBTYPES
    ]


def get_circuit_group_members(self, parent_objnam: str) -> list[PoolObject]:
    return sorted(
        (
            obj
            for obj in self._model.get_by_type(CIRCGRP_TYPE)
            if obj[PARENT_ATTR] == parent_objnam
        ),
        key=_member_order,
    )
```

For `get_circuits_in_group()`, branch on the addressed object:

1. A real parent `CIRCUIT` uses its ordered membership rows.
2. A real `CIRCGRP` row with a non-empty string `PARENT` resolves that parent and all siblings.
3. A standalone legacy `CIRCGRP` row without `PARENT` splits its string `CIRCUIT` value and resolves existing references in listed order.
4. Every other shape returns `[]`.

For real rows, accept only a singular non-whitespace string `CIRCUIT`; skip a missing child safely. `circuit_group_has_color_lights()` remains an `any(child.supports_color_effects)` read query. `get_color_light_groups()` filters only the real parents returned by `get_circuit_groups()`.

- [ ] **Step 4: Update the API reference with the corrected object roles**

Replace the circuit-group example with:

```python
# Parent CIRCUIT objects are groups; CIRCGRP objects are membership rows.
groups = controller.get_circuit_groups()
rows = controller.get_circuit_group_members(groups[0].objnam)
children = controller.get_circuits_in_group(groups[0].objnam)
color_groups = controller.get_color_light_groups()
```

State explicitly that the legacy standalone row behavior exists only for direct `get_circuits_in_group()` compatibility and is not group enumeration.

- [ ] **Step 5: Run the focused and existing controller tests green**

Run:

```bash
uv run pytest tests/test_circuit_group.py tests/test_controller.py -q
uv run ruff check src/pyintellicenter/_mixins/circuit_group.py tests/test_circuit_group.py
uv run ruff format --check src/pyintellicenter/_mixins/circuit_group.py tests/test_circuit_group.py
```

Expected: all pass. Replace the obsolete row-enumeration assertions in `tests/test_controller.py`; do not preserve two contradictory group contracts.

- [ ] **Step 6: Commit the model correction**

```bash
git add src/pyintellicenter/_mixins/circuit_group.py tests/test_circuit_group.py tests/test_controller.py docs/API.md
git commit -m "fix: model circuit group parents and membership rows"
```

---

### Task 3: Add connection-owned raw observer sequencing, split dispatch timing/watermark hooks, and generation-bound close signaling

**Files:**
- Modify: `src/pyintellicenter/connection.py`
- Modify: `tests/test_connection.py`

**Interfaces:**
- Consumes: the existing primary `NotificationCallback` queue.
- Produces:
  - `NotificationObserver = Callable[[int, dict[str, Any]], None]` (typing-only alias)
  - `BeforeWriteCallback = Callable[[int, float], None]` (private typing alias for pre-send sequence plus monotonic dispatch-start time)
  - `AfterWriteCallback = Callable[[int], None]` (private typing alias for the causal post-send notification watermark)
  - `ICConnection.add_notification_observer(observer: NotificationObserver) -> Callable[[], None]`
  - `ICConnection.send_request(..., _before_write_callback: BeforeWriteCallback | None = None, _after_write_callback: AfterWriteCallback | None = None) -> dict[str, Any]`
  - `ICConnection._capture_closed_future() -> asyncio.Future[None]` (internal, one-shot, bound synchronously to the current connection generation)
- Invariant: one sequence state belongs to the exact `ICConnection`, survives protocol transport replacement, and increments before raw observer fanout and the primary callback queue. While holding `_request_lock`, the before-write callback receives `(current_sequence, asyncio.get_running_loop().time())` immediately before the TCP write or WebSocket send invocation and starts the deadline. The after-write callback receives the then-current sequence immediately after synchronous TCP `transport.write()` returns or awaited WebSocket `send()` completes; that second value, not the pre-send sequence, is the onset watermark. Later queue consumption never reinvokes raw observers. Every `asyncio.timeout_at()`/`call_at()` deadline uses the same event-loop clock domain.

- [ ] **Step 1: Write failing observer and close-signal tests**

Add tests that prove all of these behaviors:

```python
@pytest.mark.asyncio
async def test_notification_observer_does_not_replace_primary_callback() -> None:
    primary = MagicMock()
    observer = MagicMock()
    connection = ICConnection("host")
    protocol = ICProtocol(
        notification_callback=primary,
        notification_observer_state=connection._notification_observer_state,
    )
    protocol.connection_made(MagicMock())
    connection._protocol = protocol

    remove = connection.add_notification_observer(observer)
    message = {"command": "NotifyList", "objectList": []}
    protocol._handle_notification(message)

    observer.assert_called_once_with(1, message)
    await asyncio.sleep(0)
    primary.assert_called_once_with(message)
    remove()


@pytest.mark.asyncio
async def test_observer_added_after_enqueue_never_sees_stale_queued_frame() -> None:
    primary = MagicMock()
    connection = ICConnection("host")
    protocol = ICProtocol(
        notification_callback=primary,
        notification_observer_state=connection._notification_observer_state,
    )
    protocol.connection_made(MagicMock())
    connection._protocol = protocol
    stale = {"command": "NotifyList", "objectList": [{"objnam": "OLD", "params": {}}]}
    fresh = {"command": "NotifyList", "objectList": [{"objnam": "NEW", "params": {}}]}
    protocol._handle_notification(stale)

    observer = MagicMock()
    connection.add_notification_observer(observer)
    await asyncio.sleep(0)
    observer.assert_not_called()

    protocol._handle_notification(fresh)
    observer.assert_called_once_with(2, fresh)
```

Also assert removal is idempotent, one failing observer does not block another observer or the primary callback, an observer works when the primary callback is `None`, sequences increase across every accepted notification, replacing a TCP/WebSocket protocol on the same `ICConnection` does not reset the sequence, and both transports receive the same connection-owned observer state. For closure generations, capture the future synchronously while connected and prove it completes for unexpected disconnect, explicit `disconnect()`, `_abort_connection()`, and failed connect. Then reconnect the same `ICConnection` immediately: the old captured future must remain done, `_capture_closed_future()` must return a distinct pending future for the new generation, and no late waiter may miss the old close.

Add transport-level unit tests whose fake event-loop clock and fake writer record event order. Direct access to the internal `connection._request_lock` is intentional in this substrate test; coordinate with `asyncio.Event` barriers, never timing sleeps. The test must (1) acquire that lock, (2) start a request task, (3) enqueue an unrelated notification and record its sequence while the request is blocked, (4) release the lock, (5) await the request, and (6) assert the pre-send sequence is at least that notification's sequence. For TCP, `_before_write_callback(sequence, started_at)` must run while `_request_lock` is owned immediately before `transport.write(packet)`, and `_after_write_callback(sequence)` immediately after it returns with no scheduling yield; a later notification gets a strictly greater sequence than the post-write watermark. For WebSocket, the before hook runs immediately before invocation of `ws.send(packet)` and the after hook only after the awaited send completes. Use barriers inside fake `ws.send()` to enqueue a notification during its suspension and prove its sequence is greater than the pre-send sequence but less than or equal to the after-send watermark. Assert `started_at` is the running loop's clock value sampled at the pre-send point. Deliberately offset a monkeypatched `time.monotonic()` and prove it has no effect on `timeout_at()` boundaries.

For both transports, add a before-callback-that-raises case proving `transport.write()`/`ws.send()` and the after callback are never invoked, the pending request ID/future is cleared without an unhandled-future warning, `_request_lock` is released, and the next request succeeds. Add an after-callback-that-raises case proving the transport was invoked exactly once, pending state and lock still clean up, and the next request succeeds; this is a post-initiation failure, never evidence that no write occurred.

- [ ] **Step 2: Run focused tests and verify red**

```bash
uv run pytest tests/test_connection.py -k "observer or closed or before_write or after_write or watermark" -v
```

Expected: sequenced observers, the split write callbacks, and the generation-bound close future are missing.

- [ ] **Step 3: Implement additive enqueue-time fanout**

Add a private `_NotificationObserverState` owned by `ICConnection` with `sequence: int = 0` and one mutable observer list. Pass that exact state into each newly created `ICProtocol`/`ICWebSocketTransport`; never initialize or reset sequence in a transport. At the start of `_handle_notification()`, before checking the primary callback or queue, increment the shared sequence and execute a tuple snapshot:

```python
state = self._notification_observer_state
sequence = state.sequence = state.sequence + 1
for observer in tuple(state.observers):
    try:
        observer(sequence, msg)
    except Exception:
        _LOGGER.exception("Error in notification observer")
```

Then run the existing primary-callback queue path unchanged. `add_notification_observer()` appends once to the connection state and returns an idempotent closure that removes only that observer. This ordering is the stale-frame guarantee: old queued frames are delivered only by `_notification_consumer()`, which invokes the primary callback and never re-runs observer fanout.

- [ ] **Step 4: Add separate pre-send deadline and post-send watermark hooks**

Make `_before_write_callback` and `_after_write_callback` private named keyword-only parameters at every internal `send_request()` layer so neither can leak into the serialized protocol object. Sample `started_at = asyncio.get_running_loop().time()` and read the connection state's current sequence only after acquiring `_request_lock`. Put both hooks inside the existing pending-request `try/finally`, after pending state is installed.

In TCP, invoke `_before_write_callback(sequence, started_at)` synchronously immediately before `self._transport.write(packet)`, then read the sequence again and invoke `_after_write_callback(sequence)` synchronously immediately after `write()` returns. In WebSocket, invoke the before hook immediately before `await self._ws.send(packet)`, then read the sequence again and invoke the after hook only after that await returns. A before-hook exception prevents transport initiation; an after-hook exception is post-initiation. The normal finalizer clears pending state in either case. The pre-send time starts the deadline and intentionally bounds a stalled WebSocket send. The post-send sequence is the conservative causal onset watermark and intentionally excludes any frame processed while the WebSocket send await was suspended. Do not record the time before request-lock acquisition, and never mix it with `time.monotonic()`; compute action and observation deadlines with the running loop clock and enforce them with `asyncio.timeout_at()` in that same domain.

- [ ] **Step 5: Implement a one-shot per-generation close future without changing public disconnect callbacks**

Store `self._closed_future: asyncio.Future[None] | None`. Immediately before each real connect attempt, create a fresh future from the running loop and never clear or reuse an older one. Complete the current future idempotently on failed connect, `_on_disconnect()`, `_abort_connection()`, and explicit `disconnect()`. Add:

```python
def _capture_closed_future(self) -> asyncio.Future[None]:
    """Return the one-shot close future for the current live generation."""
    future = self._closed_future
    if future is None or not self.connected:
        raise ICConnectionError("Connection is not live")
    return future
```

The action captures this object synchronously before any scheduling yield and never cancels the shared future when it stops racing it. A same-instance reconnect replaces only `self._closed_future`; already captured generation futures remain completed forever. Do not make a deliberate `disconnect()` invoke the user's existing unexpected-disconnect callback; the future is a separate internal lifecycle signal.

- [ ] **Step 6: Run connection regression gates green**

```bash
uv run pytest tests/test_connection.py tests/test_dead_link_detection.py tests/test_reconnect_hardening.py -q
uv run ruff check src/pyintellicenter/connection.py tests/test_connection.py
uv run ruff format --check src/pyintellicenter/connection.py tests/test_connection.py
uv run mypy src/pyintellicenter/connection.py
```

Expected: observer tests and every existing connection/reconnect test pass.

- [ ] **Step 7: Commit the observer substrate**

```bash
git add src/pyintellicenter/connection.py tests/test_connection.py
git commit -m "feat: add sequenced notification observers"
```

---

### Task 4: Establish a fail-fast exclusive mutation lifecycle and bind requests to one connection

**Files:**
- Modify: `src/pyintellicenter/controller.py`
- Modify: `src/pyintellicenter/_mixins/_base.py`
- Modify: `tests/test_controller.py`

**Interfaces:**
- Consumes: `ICConnection.send_request()` and the existing `_coalesce_lock`.
- Produces:
  - `ICBaseController._mutation_lock: asyncio.Lock`
  - `ICBaseController._mutation_owner: asyncio.Task[Any] | None` plus an internal owner-recording lifecycle context manager
  - `ICBaseController._light_group_mutation_pending: bool` plus a Sync-only context that marks pending before it waits for already-started writers
  - `ICBaseController._light_group_mutation_lease: object | None`, a fresh opaque identity yielded only by the active Sync context
  - `_send_cmd_on_connection_unlocked(connection: ICConnection, cmd: str, extra: dict[str, Any] | None = None, *, _mutation_lease: object, request_timeout: float | None = None, _before_write_callback: BeforeWriteCallback | None = None, _after_write_callback: AfterWriteCallback | None = None) -> dict[str, Any]`
- Invariant: public `send_cmd()` acquires `_mutation_lock` whenever `cmd.casefold() == "setparamlist"`; `request_changes()` and `_flush_pending_changes()` inherit that coverage. Sync marks `_light_group_mutation_pending` before awaiting the same lock. Object writes already started before that mark drain first; every later public object write and second Sync fails immediately with an ordinary `ICError` rather than remaining queued through the long lifecycle. The captured-connection primitive is private and requires identity with the one active opaque lease plus pending/locked/connection checks. The owner may explicitly delegate one request task by passing that lease; a child task is never mistaken for the lock-owning task, and no caller can use a missing, stale, or merely equal token.

- [ ] **Step 1: Write failing connection-identity and mutation-order tests**

Add tests proving:

1. With the exact active lease, `_send_cmd_on_connection_unlocked(old_connection, ...)` raises `ICConnectionError` if `self._connection is not old_connection`, without sending on either connection.
2. Public raw `send_cmd("SETPARAMLIST", ...)`, `send_cmd("SetParamList", ...)`, `send_cmd("setparamlist", ...)`, and `send_cmd("sEtPaRaMlIsT", ...)` each fail immediately with an ordinary `ICError` and perform no I/O while `_light_group_mutation_pending` is true.
3. A direct `request_changes()` and coalesced `set_circuit_state()` propagate that busy failure. Both `_queue_property_change()` and `_queue_batch_changes()` check pending synchronously before creating/appending a request or mutating `_pending_changes`; a later convenience writer therefore fails before it can wait on `_coalesce_lock`, and pending changes/futures are not leaked or silently replayed later.
4. A public writer that acquired the lifecycle before Sync began completes normally; Sync sets pending before waiting, drains that already-started writer, and then acquires the lifecycle. No writer that starts after the pending mark can join the queue.
5. Read-only `send_cmd("GetParamList", ...)` does not take the mutation lock and remains governed by the connection request lock.
6. Two ordinary writes outside a pending Sync retain the existing batching and request-order behavior.
7. Calling `_send_cmd_on_connection_unlocked()` without the lifecycle lock/pending flag or with a missing, wrong, copied, or stale lease fails before network I/O; the explicitly delegated state-changing child task succeeds only with the exact active lease. A source scan finds no production caller except `run_light_group_sync()`.
8. Directly invoking a separately constructed `ICConnection.send_request()` is demonstrably outside this controller lock and is documented as such rather than claimed safe.
9. Cancellation while Sync is waiting for an already-started writer clears `_light_group_mutation_pending`; cancellation after ownership cancels/awaits every delegated child before invalidating the lease, then releases lease, owner, lock, and pending state exactly once.
10. Give each `_PendingRequest` an owned deep-enough copy of its proposed object/attribute changes and pass the initiating request into `_flush_pending_changes(owner_request)` from both queue helpers. When busy failure reaches the flush, every future captured in that flush completes with the same `ICError`, pending collections remain empty, and nothing is replayed after Sync. Catch `ICError` plus `OSError`, not only selected subclasses. If the flush-owner is cancelled after it detached the batch, cancel/consume the owner's own future, complete only captured peer futures with a stable ordinary `ICError` that states delivery is unknown, then re-raise the owner's `CancelledError`; never requeue/retry a possibly dispatched batch. Barrier-test at least two coalesced callers for both busy and post-initiation cancellation paths and assert no orphan-future warning.
11. Hold `_coalesce_lock`, mark Sync pending, and invoke each queue helper. Each must raise before touching `_pending_changes`/`_pending_requests`, complete before either lock is released, and leave nothing that can be sent afterward. Separately, admit a second request before the pending mark while another flush holds `_coalesce_lock`, cancel it before detachment, and prove cancellation synchronously removes that exact request, rebuilds `_pending_changes` in original admission order from surviving request-owned changes, consumes its future, and prevents its value from appearing in any post-Sync batch. Cover same-object/same-attribute latest-wins rollback as well as distinct objects.

Use `asyncio.Event` barriers rather than sleeps for acquisition and fail-fast assertions. Explicitly prove the busy public writer task completes with `ICError` before the held lifecycle is released; a test that merely observes no transport call is insufficient because it could hide unintended queuing.

- [ ] **Step 2: Run focused tests and verify red**

```bash
uv run pytest tests/test_controller.py -k "mutation_lifecycle or send_cmd_on_connection" -v
```

Expected: the new lock/helper do not exist and supported object mutations send immediately.

- [ ] **Step 3: Add the Sync-only captured-connection primitive without routing public sends through it**

Initialize `_mutation_lock`, `_mutation_owner = None`, `_light_group_mutation_pending = False`, and `_light_group_mutation_lease = None` in `ICBaseController.__init__()`. Add a normal private async context manager that acquires the lock, records `asyncio.current_task()` as owner, and clears ownership before releasing in `finally`. Add a separate Sync-only context manager that rejects if pending is already true, sets pending synchronously before awaiting the lock, records ownership after acquisition, creates/stores one fresh opaque `object()` lease, and yields that exact lease. It clears pending on acquisition failure/cancellation; after acquisition its caller must cancel/await delegated children before context exit, which invalidates the lease before clearing owner and releasing the lock. Keep public `send_cmd()` on a normal current-connection request path. Implement the separate Sync-only `_send_cmd_on_connection_unlocked()` with the same `_RequestContext` metrics and `ICResponseError -> ICCommandError` translation, but first require `self._light_group_mutation_pending`, `self._mutation_lock.locked()`, and `self._light_group_mutation_lease is _mutation_lease`, then verify identity and connectivity before sending:

```python
if self._connection is not connection or not connection.connected:
    raise ICConnectionError("Connection changed or is not connected")
```

Do not expose the lease, either write callback, or timeout passthrough on public `send_cmd()`. Forward the exact active lease, both hooks, and real `ICConnection.send_request(request_timeout=...)` parameter only through the Sync-only helper and connection API, never inside the serialized `extra`. This lets the owner explicitly authorize its one child request task without weakening the lifecycle boundary and guarantees every lifecycle request uses the same instance and response bound even if reconnection replaces `self._connection`.

- [ ] **Step 4: Apply the mutation lock without creating re-entrant acquisition**

Public `send_cmd()` checks `_light_group_mutation_pending` and raises an ordinary `ICError("Color Sync mutation lifecycle is in progress")` before I/O whenever `cmd.casefold() == "setparamlist"`; otherwise it wraps that writer's normal request path in the owner-recording mutation context. The check and uncontended lock acquisition contain no intervening event-loop yield. Leave `request_changes()` routing unchanged.

At the very start of both `_queue_property_change()` and `_queue_batch_changes()`, before constructing a future or changing either pending collection, perform the same synchronous pending check and raise the same busy `ICError`. Extend `_PendingRequest` with its normalized owned changes. Keep the request list as the attribution source of truth and rebuild `_pending_changes` by replaying surviving request changes in admission order whenever a still-pending caller is canceled; this preserves latest-wins semantics without retaining the canceled override.

Wrap each queue helper's flush/future waits in `CancelledError` cleanup. If its request is still present in `self._pending_requests`, synchronously remove it, rebuild the aggregate without any scheduling yield, cancel/consume its future, and re-raise. If an active flush already detached the request, cancel/consume only that caller's future and let the active flush finish its possibly dispatched batch and resolve peers; never requeue it. This pre-detachment path is part of Color Sync isolation because otherwise a canceled admitted mutation can survive the pending boundary and replay after the long lifecycle.

Pass each queue helper's initiating `_PendingRequest` to `_flush_pending_changes()`. Broaden its error fanout to catch `ICError` and `OSError`, setting that exception on every future captured by the flush so fail-fast busy behavior cannot strand coalesced callers. Handle `CancelledError` separately after capture: cancel/consume the initiating future, resolve only captured peer futures with a stable uncertainty `ICError`, then re-raise cancellation, with no requeue or retry. The Sync helper enters `_light_group_mutation_lifecycle() as mutation_lease` across its complete lifecycle and passes that lease to `_send_cmd_on_connection_unlocked()` for both fresh preflights, subscription batches, the single delegated write task, and final read.

Document the boundary on `send_cmd()`: case-insensitive `SetParamList` is the only object-writer command supported by this controller. Same-controller writers invoked after Color Sync begins fail fast and must be retried deliberately; they are never delayed and replayed after Sync. Read-only commands continue. A caller using an arbitrary undocumented vendor command through public `send_cmd()` or a separately constructed raw `ICConnection` receives no mutation-isolation guarantee.

Declare the exact host members in `_mixins/_base.py` under `TYPE_CHECKING`:

```python
_connection: ICConnection | None
_mutation_lock: asyncio.Lock
_mutation_owner: asyncio.Task[Any] | None
_light_group_mutation_pending: bool
_light_group_mutation_lease: object | None

def _mutation_lifecycle(self) -> AbstractAsyncContextManager[None]:
    raise NotImplementedError

def _light_group_mutation_lifecycle(self) -> AbstractAsyncContextManager[object]:
    raise NotImplementedError

@property
def transport(self) -> TransportType:
    raise NotImplementedError

async def _send_cmd_on_connection_unlocked(
    self,
    connection: ICConnection,
    cmd: str,
    extra: dict[str, Any] | None = None,
    *,
    _mutation_lease: object,
    request_timeout: float | None = None,
    _before_write_callback: BeforeWriteCallback | None = None,
    _after_write_callback: AfterWriteCallback | None = None,
) -> dict[str, Any]:
    raise NotImplementedError
```

- [ ] **Step 5: Run controller/coalescing/type gates green**

```bash
uv run pytest tests/test_controller.py tests/test_controller_namespace_compat.py tests/test_typing_public_api.py -q
uv run ruff check src/pyintellicenter/controller.py src/pyintellicenter/_mixins/_base.py tests/test_controller.py
uv run ruff format --check src/pyintellicenter/controller.py src/pyintellicenter/_mixins/_base.py tests/test_controller.py
uv run mypy src
```

Expected: all pass; type checking still sees `ICModelController` as concrete.

Also run:

```bash
rg -n '_send_cmd_on_connection_unlocked\(' src/pyintellicenter
```

Expected: only the method declaration/definition and the dedicated Color Sync mixin call sites; public `send_cmd()`, `request_changes()`, and coalescing never call the unlocked escape hatch.

- [ ] **Step 6: Commit the mutation boundary**

```bash
git add src/pyintellicenter/controller.py src/pyintellicenter/_mixins/_base.py tests/test_controller.py
git commit -m "fix: isolate controller mutation lifecycles"
```

---

### Task 5: Implement the production-shaped Color Sync lifecycle

**Files:**
- Create: `src/pyintellicenter/_light_group.py`
- Create: `tests/test_light_group_sync.py`
- Modify: `src/pyintellicenter/_mixins/circuit_group.py`
- Modify: `src/pyintellicenter/exceptions.py`
- Modify: `src/pyintellicenter/__init__.py`
- Modify: `tests/test_typing_public_api.py`

**Interfaces:**
- Consumes: corrected group helpers, sequenced observer/pre-send deadline/post-send watermark hooks, `ICConnection._capture_closed_future()`, `_light_group_mutation_lifecycle()`, `_send_cmd_on_connection_unlocked()`, and the existing controller `MAX_ATTRIBUTES_PER_QUERY = 50`.
- Produces:
  - `ICLightGroupError(ICError)` carrying `phase`, `dispatch_started`, `response_received`, `acknowledged`, and `onset_seen` for every failure after write/send initiation.
  - `run_light_group_sync(group_objnam: str) -> dict[str, Any]`.
  - Private `LightGroupTopology`, `LightGroupProjection`, `LightGroupSyncTracker`, `build_projection_query()`, `build_subscription_batches()`, `parse_projection()`, `validate_initial_projection()`, and `validate_final_projection()` in `_light_group.py`.
- Tracker wakeups: a one-shot first-failure signal set synchronously by the raw observer, a one-shot `write_started` signal set only after the pre-send hook's validation succeeds, a separate one-shot `watermark_ready` signal set by the post-send hook, and monotonic onset/terminal signals. Every lifecycle await races these signals with the captured generation-close future instead of discovering violations only at a later deadline.
- Constants: `SUBSCRIPTION_SETTLE_SECONDS = 1.0`, `SYNC_ACTION_DEADLINE_SECONDS = 60.0`, `SYNC_POST_TERMINAL_OBSERVATION_SECONDS = 60.0`, `MAX_PREBASELINE_NOTIFICATIONS = 1000`, action flags `("SYNC", "SET", "SWIM")`, supported firmware exact raw token `"1.064"`, supported action-child subtype `"GLOW"`, and supported action-child count `2`. The one-second settle is the value exercised by every accepted sender-side run, not a generalized firmware guarantee; firmware comparison deliberately does not trim or normalize an unobserved representation.

- [ ] **Step 1: Build a deterministic scripted-connection test fixture**

In `tests/test_light_group_sync.py`, create a `ScriptedConnection` that records `(command, kwargs)` calls, stores sequenced observers, returns independently supplied initial/settled/final wildcard `GetParamList` projections plus independently supplied `RequestParamList` batch initializations, and invokes both write callbacks at the scripted transport boundaries. It can suspend WebSocket send between callbacks and emit a sequenced frame in that gap. It must also emit a notification in the same scripted transport turn as the first response, while a request is blocked, during the one-second settle, before acknowledgement, during post-terminal observation, and during the final read; it returns a synchronously captured one-shot close future and can complete closure, tracker failure, and a request response in the same event-loop turn. Build a model/system-info pair for raw firmware token `1.064` with one `SYSTEM`, one `CIRCUIT/LITSHO` target, exactly two ordered `CIRCGRP` rows, exactly two distinct `CIRCUIT/GLOW` children, one unrelated parentless ordinary circuit with unsupported `PARENT`/`USE`, one other group parent, and one row belonging to that other group.

The fake must not infer success or advance clocks implicitly. Its scripted projections contain every mandatory field the production parser requires: system `OBJTYP/VER/SERVICE`; every `CIRCUIT` object's `OBJTYP/SUBTYP/STATUS`; `SYNC/SET/SWIM` on every real group parent; and every `CIRCGRP` row's `OBJTYP/PARENT/CIRCUIT/LISTORD`. Circuit `PARENT`/`USE` and row `USE` are optional normalized fields. Happy fixtures deliberately mix omission, `key == value`, and `"00000"` null-reference representations on not-applicable ordinary-circuit fields and on membership-row `USE`, while retaining real values where the firmware supplies them. Exercise those row-`USE` spellings independently in the first/second/final wildcard responses, `RequestParamList` initialization responses, and `NotifyList` frames. Missing-field tests remove mandatory fields deliberately. Row `PARENT` has explicit missing/key-echo/`"00000"` negatives in full wildcard and subscription-initialization responses; a partial `NotifyList` may omit it, but if present its key-echo/`"00000"` spellings fail. This proves it is never normalized as optional without misreading partial updates.

- [ ] **Step 2: Write the failing happy-path matrix**

Parameterize TCP/WebSocket and uniform `OFF`/`ON` baselines. For `OFF`, emit parent `SYNC=ON`, target parent/child statuses in varying leading order, then `SYNC=OFF`; for `ON`, emit only `SYNC=ON` and `SYNC=OFF`. Monkeypatch the settle and post-terminal observation constants to `0` in fast matrix tests. Separate deterministic clock tests assert the production deadline is exactly `before_write_time + 60.0` and the final read is not eligible until exactly `terminal_time + 60.0`; never make the suite sleep for a real minute.

Assert:

```python
scripted_ack = {
    "messageID": "4",
    "response": "200",
    "opaqueVendorField": {"kept": True},
}
connection.action_response = scripted_ack
ack = await controller.run_light_group_sync("GROUP")
assert ack == scripted_ack
assert [call.command for call in connection.calls] == [
    "GetParamList",
    "RequestParamList",
    "GetParamList",
    "SetParamList",
    "GetParamList",
]
assert connection.calls[3].kwargs == {
    "objectList": [{"objnam": "GROUP", "params": {"SYNC": "ON"}}]
}
assert connection.observers == []
```

Also assert each snapshot call is the exact wildcard request with `condition=""`, one `objnam="INCR"` entry, and the fixed union of only `OBJTYP`, `SUBTYP`, `PARENT`, `CIRCUIT`, `LISTORD`, `STATUS`, `USE`, `SYNC`, `SET`, `SWIM`, `VER`, and `SERVICE`. Its 12-key request is below `MAX_ATTRIBUTES_PER_QUERY` regardless of installation size. Assert every exact-object subscription batch is at most 50 aggregate keys and the batches cover every required object/key exactly once. Assert `request_changes` and `_queue_property_change` were not called, and the helper never writes `ACT`, `STATUS`, `SET`, or `SWIM`.

- [ ] **Step 3: Write failing pre-I/O and pre-write rejection tests**

Before any network I/O, reject with `ValueError` when cached firmware is absent/not the exact raw token `1.064`, the target is missing, is a membership row, is `CIRCUIT/SUBTYP=CIRCGRP`, is an ordinary light, has one/three/zero rows rather than exactly two, has duplicate child references, has a missing child, resolves the same child twice, or contains any child whose object type/subtype is not exact `CIRCUIT/GLOW`. Explicitly test raw variants such as `"IC: 1.064"`, `"1.064 "`, and `"1.064-build"` that a display/parser path might interpret semantically; the writer still rejects them because no state-changing capture covers those wire representations. Do not use `parse_ic_version()` for this writer gate.

After the first fresh `GetParamList` but before `SetParamList`, reject with an ordinary pre-dispatch `ICError` (never `ICLightGroupError`) when:

- zero or multiple systems appear;
- `VER` is not exactly `1.064` or `SERVICE` is not exactly `AUTO`;
- target/member/child object type or subtype mismatches the cached topology or child count is not exactly two;
- target statuses are mixed, missing, or noncanonical;
- any group action flag is missing or not `OFF`;
- any `CIRCUIT` is missing mandatory `OBJTYP`/`SUBTYP`/`STATUS`, any row is missing mandatory `OBJTYP`/`PARENT`/`CIRCUIT`/`LISTORD`, or the wildcard response omits/duplicates a required object or reveals fresh topology different from the cached model; optional circuit `PARENT`/`USE` and row `USE` may be absent/key-echo/null-reference and normalize to one absence value. Parameterize first, second, and final wildcard responses so row `USE` omission/key-echo/`"00000"` normalize equal while a real value is preserved and compared; at each gate, a row `PARENT` that is missing, key-echoed, or `"00000"` fails as mandatory;
- any wildcard object entry is malformed, duplicated, lacks a nonempty string `objnam`, or lacks a real non-placeholder string `OBJTYP`; in particular, reject an unknown entry whose type is absent/ambiguous because relevance cannot be excluded, while a well-formed explicit unrelated type may remain outside the projection;
- `RequestParamList` rejects any exact-object subscription batch, or its initialization `objectList` is missing/non-list/empty/duplicate/unexpected, omits or placeholders a mandatory key, contains a malformed optional value, fails required coverage, or differs from the normalized baseline slice; absence/key-echo/null-reference is accepted only for the declared optional fields. Explicit row fixtures prove `USE` omission/key-echo/`"00000"` normalize equal and a real value is retained, while row `PARENT` missing/key-echo/`"00000"` is rejected;
- a projected notification changes any baseline value between the first read and write, including a value that changes back before the second read;
- after the one-second settle, the second complete fresh projection differs from the first in any field, including a one-field mismatch with no notification.

Every case asserts no `SetParamList` call and no `ICLightGroupError`. Assert the exact second-preflight mismatch raises ordinary `ICError` with a stable preflight-mismatch message. Add pre-baseline tests proving the observer is already installed when the first request starts: a differing notification accepted after the first response frame but before its awaiting task resumes is buffered and rejects after baseline installation; an equal repeated value is harmless; more than `MAX_PREBASELINE_NOTIFICATIONS` fails closed without dropping evidence. A notification that introduces an unknown `CIRCUIT`, `CIRCGRP`, or `SYSTEM` (or an unknown object with projected keys but no trustworthy type) is an irreversible prewrite failure even if it disappears before the second snapshot. A cached irrelevant object remains ignored while its tracked type is irrelevant, including partial updates that omit `OBJTYP`; an explicit transition into `CIRCUIT`, `CIRCGRP`, or `SYSTEM` fails irreversibly even if the same frame or a later frame restores the old type. Include a race where a projected change arrives while the write request waits behind `_request_lock`: `_before_write_callback` detects the recorded prewrite failure, raises before transport initiation, leaves `write_started` false, and produces an ordinary pre-dispatch `ICError`.

Add raw-observer parser cases for a missing/non-list `NotifyList.objectList`, non-dict entries, missing/non-string object names, malformed parameters on any entry whose relevance cannot be excluded, placeholders in mandatory projected fields, malformed optional values, and duplicate relevant entries within one frame. Optional circuit `PARENT`/`USE` and row `USE` sentinel updates normalize before comparison rather than failing merely because the firmware echoed an unsupported key. Explicitly cover row `USE` omitted from a partial update and present as key echo, `"00000"`, or a real value, both before write and after dispatch; equivalent absence spellings remain equal, while a changed real value fails. At both phases, row `PARENT` missing from a full initialization/projection or present as key echo/`"00000"` fails as mandatory rather than normalizing. Process entries in wire order: a relevant value that changes and restores later in the same frame remains an irreversible failure. Cover each malformed class both before write and after dispatch and assert the first-failure signal wakes the lifecycle without waiting for a settle/action/observation deadline.

- [ ] **Step 4: Write failing action deadline, invariant, error-metadata, and final-projection tests**

Cover each authoritative gate independently:

- a notification received while `SetParamList` waits for the connection request lock is excluded by the later post-send watermark;
- on TCP, a notification after synchronous `transport.write()` returns but before acknowledgement is retained;
- on WebSocket, a frame processed while `ws.send()` is suspended is sequence-ordered and checked for invariant violations but cannot qualify as onset because the post-send callback has not established the causal watermark; a later `SYNC=OFF` alone still fails for missing onset, while a fresh `SYNC=ON` strictly after the post-send watermark can qualify;
- the before callback's event-loop time is the sole deadline origin and the after callback's sequence is the sole onset-watermark origin; request-lock wait time is excluded while WebSocket send-await time is included only in the deadline;
- status/onset leading order varies without failure;
- `SYNC=OFF` before a post-arm `SYNC=ON` never completes;
- acknowledgement without onset by `write_started_at + 60` fails in phase `onset`;
- onset without terminal by the same absolute deadline fails in phase `terminal`; acknowledgement latency never extends it;
- the state-changing request passes `request_timeout=SYNC_ACTION_DEADLINE_SECONDS` rather than inheriting the connection's 30-second default; a scripted response at 45 seconds can still succeed when onset/terminal also meet the absolute deadline, while no response by 60 seconds fails in `acknowledgement`;
- a WebSocket `send()` that stalls after the pre-send hook cannot outlive `write_started_at + 60`; the outer action deadline wakes, cancels/awaits the request task, and reports phase `acknowledgement` with `dispatch_started=True` and no response;
- an all-on target parent/child reporting `STATUS=OFF` fails immediately;
- an all-off target object may repeat `OFF` before it reaches `ON`, but `ON -> OFF` fails immediately;
- target parent/child `USE` changes and target `SET`/`SWIM` changes fail immediately;
- after terminal, any target `SYNC=ON` re-entry fails immediately even if a later `SYNC=OFF` and final read look clean;
- any unrelated `CIRCUIT` `PARENT`, `STATUS`, or `USE` change fails immediately, including a legitimate schedule/panel transition; document this conservative false-failure boundary rather than relaxing causal safety;
- any non-target group `SYNC`/`SET`/`SWIM`, any row `PARENT/CIRCUIT/LISTORD/USE`, or system `OBJTYP/VER/SERVICE` change fails immediately;
- a post-dispatch notification introducing an unknown relevant object/topology fails irreversibly even if a later remove/restore leaves the final wildcard inventory equal to baseline;
- each transient violation remains failed after an exact restore frame and a clean final read;
- repeated values that exactly equal allowed current/baseline values remain harmless;
- the second fresh preflight occurs only after the one-second subscription settle and must exactly match the first projection;
- the final `GetParamList` does not occur before the full 60-second post-terminal observation interval ends;
- final projection is mandatory even after clean pushes;
- final mismatch in any projected system, required `CIRCUIT OBJTYP/SUBTYP/STATUS`, normalized optional circuit `PARENT/USE`, group flag, required row topology, or normalized optional row `USE` field fails in phase `final_projection`; final row `USE` omission/key-echo/`"00000"` remains equal to baseline absence, a real-value difference fails, and final row `PARENT` missing/key-echo/`"00000"` fails as mandatory;
- a clean final projection cannot replace missing onset or terminal;
- a final read on a replaced connection is rejected;
- first wildcard read, each subscription initialization batch, the second preflight, action response, and final projection all race the captured close future; a simultaneous clean response and close always chooses close;
- disconnect/reconnect during subscription settling, onset wait, terminal wait, or post-terminal observation wakes the waiter immediately and preserves the applicable pre/post-dispatch phase/certainty metadata; explicitly test both rapid same-instance reconnect and real controller replacement while Sync owns the lifecycle, prove the synchronously captured old-generation future completes permanently, emit an immediate qualifying `SYNC` frame on the new generation, and prove the observer rejects/ignores it and closure wins every wait tie;
- an unsafe notification during the final read wins over an otherwise clean response, proving invariants remain live until observer removal;
- an invariant failure during the first wildcard read, any subscription batch, settle, second preflight, action response, onset, terminal, observation, or final read wakes immediately; when failure and success become ready together, failure wins, and when closure is also ready, closure wins;
- cancellation removes the observer and releases `_mutation_owner`, `_mutation_lock`, and `_light_group_mutation_pending` exactly once;
- timeout removes the observer, sends no retry, and sends no recovery write;
- a second Sync and an ordinary `request_changes()` both fail busy before dispatch while the first Sync owns the lifecycle; neither waits nor sends later, while a read-only request remains live.

For `ICLightGroupError`, assert every metadata combination separately:

| Scenario | `phase` | `dispatch_started` | `response_received` | `acknowledged` | `onset_seen` |
| --- | --- | --- | --- | --- | --- |
| write/send initiated, no correlated response | `acknowledgement` | `True` | `False` | `False` | `False` |
| explicit non-200 response | `acknowledgement` | `True` | `True` | `False` | `False` |
| onset push but response never arrives | `acknowledgement` | `True` | `False` | `False` | `True` |
| 200 acknowledgement but no onset | `onset` | `True` | `True` | `True` | `False` |
| onset but no terminal | `terminal` | `True` | `True` | `True` | `True` |
| invariant violation after terminal | `observation` | `True` | `True` | `True` | `True` |
| final projection mismatch | `final_projection` | `True` | `True` | `True` | `True` |

Here `phase` names the response/lifecycle gate that failed. A qualifying post-send-watermark onset can precede the correlated response, so the third row intentionally remains `phase="acknowledgement"`; Home Assistant's `acknowledged or onset_seen` precedence maps it to visibly-started/incomplete rather than uncertain delivery.

Use `asyncio.Event` barriers and injected/fake event-loop clock values to prove ordering. Do not use wall-clock sleeps except a single `await asyncio.sleep(0)` scheduling yield. At every tie assert the precedence `connection closed` > `tracker failed` > `operation succeeded`.

- [ ] **Step 5: Run the new tests and verify red**

```bash
uv run pytest tests/test_light_group_sync.py tests/test_typing_public_api.py -v
```

Expected: the module, exception, and public helper are absent.

- [ ] **Step 6: Implement strict topology and projection objects**

In `_light_group.py`, use frozen dataclasses whose fields are immutable tuples. `LightGroupTopology` owns the system objnam, target parent objnam, exactly two ordered target row entries, exactly two ordered distinct target children, all known `CIRCUIT` objnams, all real group-parent objnams, all membership-row objnams, and a stable `(objnam, objtype)` inventory for every cached object so notifications can distinguish known irrelevant objects from new topology. `LightGroupProjection` owns the exact system tuple; every circuit's `(objnam, objtype, subtype, parent: str | None, status, use: str | None)`; every group parent's action flags; and every row's `(objnam, objtype, parent, circuit, listord, use: str | None)`. The optional fields contain normalized semantic absence, never raw sentinel spelling.

`build_projection_query()` returns the exact existing wildcard shape used by `get_all_objects()`: `condition=""` and one `{"objnam": "INCR", "keys": [...]}` entry. Its fixed 12-key union is `OBJTYP`, `SUBTYP`, `PARENT`, `CIRCUIT`, `LISTORD`, `STATUS`, `USE`, `SYNC`, `SET`, `SWIM`, `VER`, and `SERVICE`; assert its key count is at most the imported `MAX_ATTRIBUTES_PER_QUERY` in both implementation and tests. Unlike `get_all_objects()`, retain the raw response long enough to distinguish mandatory malformed values from legitimate not-applicable sentinels. Define one private optional-field normalizer: missing, `None`, exact `key == value`, and exact protocol null reference `"00000"` become `None`; any other scalar string remains exact and a non-string/non-null value fails. Apply it only to circuit `PARENT`/`USE` and membership-row `USE`. The wildcard response is filtered into:

- system: `OBJTYP`, `VER`, `SERVICE`;
- every `CIRCUIT`, including target parent, target children, unrelated ordinary circuits, and other group parents: required `OBJTYP`, `SUBTYP`, `STATUS` plus normalized optional `PARENT`, `USE`;
- every real group parent additionally: `SYNC`, `SET`, `SWIM`;
- every `CIRCGRP` membership row, including rows outside the target: required `OBJTYP`, `PARENT`, `CIRCUIT`, `LISTORD` plus normalized optional `USE`.

`parse_projection()` first validates the complete wildcard envelope: `objectList` is a list; every entry is a dict with one unique nonempty string `objnam`, dict-shaped parameters, and a real non-placeholder string `OBJTYP`. It rejects an unknown entry with absent/non-string/placeholder type because relevance cannot be excluded. Only after that validation may it ignore entries with an explicit well-formed unrelated type. It requires every relevant object exactly once, every mandatory type-specific key to have a real non-placeholder string value, each optional value to normalize successfully, and the fresh relevant inventory/topology to equal the cache used to build eligibility. An optional sentinel is data, not a malformed response: compare its normalized `None` to the baseline and fail if it later becomes a real value (or vice versa), but never require an ordinary parentless/non-color circuit to invent `PARENT` or `USE`. Apply the same parser to first, second, and final wildcard reads, with hardware-realistic negative and normalization tests at all three gates: membership-row `USE` omission/key-echo/`"00000"` normalize to absence and a real string is retained, while membership-row `PARENT` remains mandatory and rejects missing/key-echo/`"00000"`. This preserves one authoritative snapshot request on large installations; do not multiply the key count by the number of wildcard response objects.

`build_subscription_batches()` instead targets exact discovered relevant object names with their type-specific keys. Split before adding an entry that would make the aggregate key count exceed `MAX_ATTRIBUTES_PER_QUERY`; an individual entry that cannot fit fails closed. Require a correlated `200` and list-shaped `objectList` for every batch. The response must contain every requested objnam exactly once, no unexpected object/key, every mandatory requested key once with a real value, and each optional requested key either as a normalizable sentinel/real value or omitted. Normalize and compare the complete initialization batch to the corresponding baseline slice. Empty, mandatory-partial, malformed, duplicate, extra, or normalized-mismatching responses are ordinary pre-dispatch `ICError` failures. Test ordinary parentless circuits whose `PARENT` is omitted, echoed, and `"00000"`; non-color circuits whose `USE` is omitted/echoed; and membership rows whose optional `USE` is omitted, echoed, `"00000"`, or real. Equivalent absence representations initialize successfully and real optional values compare exactly, while membership-row `PARENT` omission/key-echo/`"00000"` and any real optional-value change fail. The raw observer remains armed across all batches, so splitting subscriptions does not split or weaken either fresh snapshot.

`validate_initial_projection()` returns the accepted uniform prestate and requires all Global Constraints, including the exact untrimmed fresh raw `VER=1.064`, exactly two distinct resolved children, and both child subtypes `GLOW`. The second preflight uses dataclass equality against the first normalized projection, not a weaker topology-only comparison or raw-sentinel spelling comparison. `validate_final_projection()` requires the exact baseline system, every circuit's `OBJTYP/SUBTYP` and normalized optional `PARENT/USE`, every unrelated circuit's baseline `STATUS`, every row's mandatory topology and normalized optional `USE`, every non-target group flag, target `SET/SWIM`, target `SYNC=OFF`, and all three target statuses `ON`. Explicitly reject no-push final type/subtype changes, including loss of the target `LITSHO` or child `GLOW` eligibility. Dynamic telemetry outside this explicit query is intentionally excluded.

- [ ] **Step 7: Implement the edge-qualified tracker**

Before a baseline exists, `LightGroupSyncTracker.observe()` stores relevant `(sequence, frame)` items up to `MAX_PREBASELINE_NOTIFICATIONS`; the first overflow irreversibly records an ordinary pre-dispatch `ICError`. `set_prewrite_baseline()` loads the first validated projection and replays that buffer in sequence, rejecting any partial value different from the resulting baseline while accepting exact repeated values. The tracker owns `failure_event = asyncio.Event()` and one first-error slot; the single `_record_failure()` path stores only the first error and synchronously sets that event, so a raw-observer violation wakes the active lifecycle await immediately in every phase.

Parse each `NotifyList.objectList` entry in wire order rather than merging entries by object name. A missing/non-list object list, malformed entry/parameters where relevance cannot be excluded, placeholder mandatory value, or non-normalizable optional value fails closed. A present optional circuit `PARENT`/`USE` or row `USE` is normalized before comparison; an omitted optional key means no partial update, not a forced absence transition. Tests explicitly drive row `USE` omission/key-echo/`"00000"`/real-value notifications through this path and keep row `PARENT` strict: when present in a partial notification it must be real, and every full projection/subscription initialization must include it. Duplicate relevant updates are each applied in order, so change-then-restore within one frame cannot erase a violation. At every phase, an unknown objnam declaring relevant `OBJTYP` (`CIRCUIT`, `CIRCGRP`, or `SYSTEM`) is a topology change and fails irreversibly. An unknown objnam with projected keys but no real type also fails closed because relevance cannot be excluded. Maintain a small dynamic type map initialized from the cached all-object inventory: an object whose current type is irrelevant may ignore well-formed partial updates, but any explicit transition into a relevant type fails irreversibly, even if restored; a newly observed explicit irrelevant type may be tracked under the same rule.

After baseline, `observe()` compares every normalized projected partial update or subscription initialization to that baseline and calls `_record_failure()` on the first difference, even if restored. `mark_before_write(pre_send_sequence, started_at)` runs inside the pre-send transport hook: it first raises any recorded prewrite failure so the transport does not send, then stores the diagnostic pre-send sequence, write time, and absolute action deadline, and only then sets the one-shot `write_started` event/flag before returning to the immediate transport invocation. Classification uses that flag, never merely “callback reached”; if the hook raises during prewrite validation, the flag remains false and the failure stays an ordinary pre-dispatch `ICError`.

`mark_after_write(sequence)` runs inside the post-send hook and stores the sole onset watermark before setting a separate one-shot `watermark_ready` event. TCP calls it immediately after synchronous write return; WebSocket calls it only after the awaited send completes. After `write_started` but before `watermark_ready`, `observe()` still applies normalized collateral, topology, status-monotonicity, `SET`, and `SWIM` invariants immediately, but target `SYNC` updates are causally ambiguous and cannot establish onset/terminal or success. Once the watermark exists, only target action edges with `sequence > watermark` qualify. Observer failures are recorded rather than raised through the connection callback.

Completion state is monotonic:

```text
DISPATCH_START(time) -- transport accepts send --> WATERMARK(sequence)
WATERMARK -- later target SYNC=ON --> ONSET
ONSET -- target SYNC=OFF by dispatch-time+60 --> TERMINAL
TERMINAL -- 60 seconds with no invariant violation --> OBSERVATION_CLEAN
OBSERVATION_CLEAN -- mandatory same-connection projection validates --> COMPLETE
```

Target statuses may reach `ON` before or after onset, including during an awaited WebSocket send, but only strictly post-watermark `SYNC` edges qualify the action and final success requires all target statuses `ON`. Target `SYNC` during the pre-send/post-send ambiguity window is retained as nonqualifying evidence; a later `OFF` without a fresh qualifying `ON` never completes. `SYNC=OFF` before onset is an allowed repeated baseline value, never terminal. For all-on prestates, any later `OFF` is unsafe. For all-off prestates, track each object independently: repeated `OFF` is allowed only until that object first reaches `ON`; a later `OFF` is unsafe. All other projected fields follow exact normalized baseline invariants. Once failed, the tracker never clears the error.

- [ ] **Step 8: Implement `run_light_group_sync()` on one captured connection**

First define one guarded-await rule for the entire method. Immediately create one task waiting on `tracker.failure_event`; do not wrap or cancel the shared `connection_closed` future. For every request task and every settle/onset/terminal/observation wait, use `asyncio.wait()` against that operation, `connection_closed`, and the shared failure waiter. Inspect readiness in the fixed order close, failure, operation; on close/failure, cancel and await only the losing operation task. Recheck close and failure synchronously after an operation result and before consuming it. This rule applies to all three wildcard reads, every subscription initialization batch, and all timer/edge waits. It gives simultaneous readiness the deterministic precedence `connection closed` > `tracker failed` > `operation succeeded` and prevents any violation from sleeping until a protocol deadline. Convert the selected failure to ordinary `ICError` while `write_started` is false and phase-aware `ICLightGroupError` once it is true.

The state-changing request has an additional staged guard. First race its task against `tracker.write_started`, close, and failure so the exact pre-send boundary is observable even when WebSocket `send()` stalls. If the task completes while `write_started` is still false, propagate its pre-dispatch result/error. As soon as `write_started` is set, create a dedicated deadline-waiter task whose `asyncio.timeout_at(tracker.action_deadline)` uses the same loop-clock domain, and race close, failure, deadline, `tracker.watermark_ready`, action response, onset, and terminal. A stalled WebSocket send never sets `watermark_ready` but is still bounded from the pre-send time. Frames observed before watermark readiness undergo invariants but cannot set onset/terminal. The outer bound is authoritative and includes TCP/WebSocket transport initiation plus the response; the connection's explicit 60-second request timeout is only a second line of defense. On deadline, cancel/await the still-pending action task and classify a missing response as phase `acknowledgement`, otherwise missing onset/terminal by the first unmet gate. Simultaneous readiness uses close > failure > deadline > gate success, and `write_started=True` makes the outcome post-dispatch even when the WebSocket send never completes.

The method performs this exact sequence:

1. Validate cached firmware `1.064` and exact target shape—one `CIRCUIT/LITSHO`, exactly two rows, exactly two distinct resolved `CIRCUIT/GLOW` children—without I/O; raise `ValueError` if unsupported.
2. Enter `_light_group_mutation_lifecycle() as mutation_lease`, which marks pending before it waits for already-started writers, creates one opaque identity after ownership, and yields it; reject another pending Sync before I/O, then revalidate cached shape.
3. Capture `connection = self._connection`; reject if missing/disconnected, then immediately and synchronously assign `connection_closed = connection._capture_closed_future()` for that exact generation before any scheduling yield.
4. Build the fixed wildcard projection query and exact-object subscription batches synchronously from the cached model; assert every request respects `MAX_ATTRIBUTES_PER_QUERY`.
5. Construct the tracker and register an additive raw observer closure on the captured connection before the first network request. Before forwarding a frame it checks the captured `connection_closed`; if done, it records/wakes disconnection according to the current dispatch phase and never passes the frame to tracker state. There is no pre-observer fresh-read gap.
6. Send the first wildcard `GetParamList` through the guarded-await rule and `_send_cmd_on_connection_unlocked(connection, ..., _mutation_lease=mutation_lease)`, parse/validate it, and install it as the tracker prewrite baseline; replay the bounded buffered frames before proceeding.
7. Send every exact-object `RequestParamList` batch on that connection with that lease and guarded-await rule; require a correlated `200`, compare response initialization values to the baseline, and keep the raw observer active throughout.
8. Guardedly await exactly `SUBSCRIPTION_SETTLE_SECONDS`, then send the second identical wildcard `GetParamList` on the captured connection under the same rule. Require exact `LightGroupProjection` equality with the first baseline and no transient prewrite failure recorded by the observer or subscription responses.
9. Create the mixed-case `SetParamList` request task exactly once with `[{"objnam": group_objnam, "params": {"SYNC": "ON"}}]`, explicitly passing the same `mutation_lease`, `request_timeout=SYNC_ACTION_DEADLINE_SECONDS`, `tracker.mark_before_write` as `_before_write_callback`, and `tracker.mark_after_write` as `_after_write_callback`. The child is authorized by lease identity, not incorrectly required to equal `_mutation_owner`. Apply the staged action guard and classify by `tracker.write_started`, not by task creation or callback entry: a pre-send callback check failure propagates as an ordinary pre-dispatch `ICError`, while every failure after the flag is set becomes phase-aware. The outer absolute deadline begins at the pre-send hook and therefore bounds a stalled WebSocket send as well as response/onset/terminal; onset admission begins only at the post-send hook. The explicit connection request timeout prevents the connection's 30-second default from contradicting the response gate but never extends that outer bound.
10. Starting from the callback's recorded monotonic time, enforce one absolute 60-second deadline across acknowledgement, positive onset, and terminal. Retain qualifying notifications that arrive before acknowledgement. Record `response_received` for any correlated response/explicit response error and `acknowledged` only for an exact successful response.
11. At terminal, record its event-loop time and keep the raw observer active for exactly `SYNC_POST_TERMINAL_OBSERVATION_SECONDS`. Race the generation-bound close future captured in step 3 against the subscription settle and every onset/terminal/observation wait. Whenever `asyncio.wait()` returns closure together with any response/tracker event, handle closure first and discard the competing success edge. Automatic/manual controller reconnection may reuse the instance or replace `self._connection`, but the old generation future remains done and the guarded observer prevents any new-generation frame or response from satisfying this helper.
12. Send the mandatory final `GetParamList` with the same projection query, lease, captured connection, and guarded-await rule. Validate it against the baseline/final rules, including exact `OBJTYP/SUBTYP` equality for every circuit, then call `tracker.raise_if_failed()` again so an unsafe frame received during the read wins over a clean response.
13. Return the complete correlated acknowledgement dict exactly as supplied by the transport only after final validation and the last failure check. Correlation requires its real `messageID` and success requires `response == "200"`, but the helper neither requires nor invents a response-side command echo and preserves every opaque field; do not normalize it to the test-only shape `{"response": "200"}`.
14. In `finally`, cancel/await the delegated request, shared failure waiter, and other owned internal tasks, but never cancel the captured close future; invoke the idempotent observer remover while still inside the lifecycle context. Only then may context exit invalidate `mutation_lease` and clear owner/lock/pending. There is no `await` between the last failure check and observer removal, closing the final interleaving window.

Wrap a response timeout, disconnect, malformed acknowledgement, missing edge, invariant violation, or final mismatch after `tracker.write_started` becomes true in `ICLightGroupError`, chaining the cause and snapshotting the tracker flags. Use phases `acknowledgement`, `onset`, `terminal`, `observation`, and `final_projection` according to the failed gate. Unsupported cached shapes remain `ValueError`; busy lifecycle, first/second preflight, subscription/batching, callback-precheck, or connection failures while `write_started` is false remain ordinary `ICError` subclasses. Propagate `CancelledError`. Never retry and never send recovery writes.

- [ ] **Step 9: Export and type-check the public contract**

Add:

```python
type _LightGroupPhase = Literal[
    "acknowledgement",
    "onset",
    "terminal",
    "observation",
    "final_projection",
]


class ICLightGroupError(ICError):
    """A Color Sync failure after transport dispatch began."""

    def __init__(
        self,
        message: str,
        *,
        phase: _LightGroupPhase,
        response_received: bool,
        acknowledged: bool,
        onset_seen: bool,
    ) -> None:
        self._phase = phase
        self._response_received = response_received
        self._acknowledged = acknowledged
        self._onset_seen = onset_seen
        super().__init__(message)

    @property
    def phase(self) -> _LightGroupPhase:
        """Return the lifecycle phase that failed."""
        return self._phase

    @property
    def dispatch_started(self) -> bool:
        """Return whether transport write/send initiation occurred."""
        return True

    @property
    def response_received(self) -> bool:
        """Return whether a correlated controller response arrived."""
        return self._response_received

    @property
    def acknowledged(self) -> bool:
        """Return whether the controller positively acknowledged the action."""
        return self._acknowledged

    @property
    def onset_seen(self) -> bool:
        """Return whether a qualifying post-send-watermark onset was observed."""
        return self._onset_seen

    def __repr__(self) -> str:
        return (
            "ICLightGroupError("
            f"phase={self.phase!r}, "
            f"dispatch_started={self.dispatch_started!r}, "
            f"response_received={self.response_received!r}, "
            f"acknowledged={self.acknowledged!r}, "
            f"onset_seen={self.onset_seen!r})"
        )
```

Store phase plus the three variable certainty values as read-only public attributes; `dispatch_started` is an always-true read-only property because constructing this exception before dispatch is forbidden. Include all five fields in `__repr__` without identifiers or payloads. The `type` alias syntax is valid because pyintellicenter requires Python `>=3.13`; do not add a compatibility dependency. Export the class from `pyintellicenter.__init__` and `__all__`. Extend the downstream typing fixture to await `ICModelController.run_light_group_sync("GROUP")` and assign the result to `dict[str, Any]`; also import `ICLightGroupError` from the package root. Assert the old/non-scoped names are absent:

```python
assert not hasattr(ICModelController, "run_light_group_command")
assert not hasattr(ICModelController, "run_light_group_swim")
assert not hasattr(ICModelController, "set_light_group_member_position")
```

- [ ] **Step 10: Run focused lifecycle/type gates green**

```bash
uv run pytest tests/test_light_group_sync.py tests/test_circuit_group.py tests/test_connection.py tests/test_controller.py tests/test_typing_public_api.py -q
uv run ruff check src/pyintellicenter tests/test_light_group_sync.py tests/test_circuit_group.py
uv run ruff format --check src/pyintellicenter tests/test_light_group_sync.py tests/test_circuit_group.py
uv run mypy src
```

Expected: all pass. The exact payload, dispatch-start deadline/post-send watermark split, exact normalized preflight equality, full 60-second observation boundary, complete invariant matrix, realistic acknowledgement, phase metadata, mandatory final read, observer cleanup, and fail-fast mutation-isolation assertions are green.

- [ ] **Step 11: Commit the Color Sync contract**

```bash
git add src/pyintellicenter/_light_group.py src/pyintellicenter/_mixins/circuit_group.py src/pyintellicenter/exceptions.py src/pyintellicenter/__init__.py tests/test_light_group_sync.py tests/test_typing_public_api.py
git commit -m "feat: add verified light group color sync"
```

---

### Task 6: Document and fully verify the pyintellicenter feature PR

**Files:**
- Modify: `docs/API.md`
- Modify: `docs/USAGE.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: Tasks 2-5 public behavior.
- Produces: an independently reviewable pyintellicenter feature branch with version still `0.1.21` and changes recorded under `[Unreleased]`.

- [ ] **Step 1: Add exact API and usage documentation**

Document:

```python
groups = controller.get_circuit_groups()
rows = controller.get_circuit_group_members(groups[0].objnam)
children = controller.get_circuits_in_group(groups[0].objnam)

try:
    await controller.run_light_group_sync(groups[0].objnam)
except ValueError:
    # Firmware/topology/prestate is outside the supported action envelope.
    raise
except ICLightGroupError as err:
    if err.acknowledged or err.onset_seen:
        # The action was acknowledged or visibly started but did not prove completion.
        raise
    if err.dispatch_started and not err.response_received:
        # Dispatch began, but whether the controller received it is unknown.
        raise
    # The controller returned an explicit rejection/malformed response.
    raise
except ICError:
    # Subscription/preflight failed before dispatch began.
    raise
```

State that the call commonly occupies roughly 96-97 seconds plus request latency on the observed firmware: a one-second subscription settle, roughly 35-36 seconds to physical terminal, a full 60-second post-terminal observation, then a final read. State that eligibility is deliberately limited to firmware `1.064`, exactly two distinct resolved `GLOW` children, and uniform all-off/all-on prestates; no automatic retry/recovery occurs. During that complete interval, new object-changing calls through the same controller fail immediately with `ICError` instead of being delayed; read-only commands and model updates continue. A physical-panel or separate raw-connection change is outside that isolation boundary and makes Sync incomplete if it changes the monitored projection. Document the five certainty attributes and warn that any error with `dispatch_started=True` requires physical inspection before retry.

- [ ] **Step 2: Add `[Unreleased]` changelog entries**

Under `Added`, record dedicated TCP/WebSocket Color Sync with same-connection authoritative completion and phase-aware certainty metadata. Under `Fixed`, record real parent/membership-row modeling and the intentional change in `get_circuit_groups()`. Under `Security` or `Changed`, record no-retry, fail-fast case-insensitive controller writer isolation, exact two-GLOW/firmware envelope, full-projection transient validation, the 60-second post-terminal observation, and mandatory final read. Explicitly list Set, Swim, and member position as not implemented.

- [ ] **Step 3: Scan source for forbidden writers and generic APIs**

Run:

```bash
if rg -n 'run_light_group_command|run_light_group_swim|set_light_group_member_position|"SET": "ON"|"SWIM": "ON"' src/pyintellicenter; then
  exit 1
fi
rg -n '"ACT"|"STATUS"' src/pyintellicenter/_light_group.py src/pyintellicenter/_mixins/circuit_group.py
```

Expected: the first command is silent in production source; negative tests and documentation may name omitted APIs. The second may show read/projection keys only; manually verify the sole action write contains only `SYNC=ON`.

- [ ] **Step 4: Run the complete pyintellicenter gate**

```bash
uv sync --frozen --extra dev
uv run pytest --cov=src/pyintellicenter --cov-report=term-missing
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv lock --check
git diff --check
git status --short
```

Expected: all tests pass, static/lock/diff checks are clean, and status lists only intended feature files.

- [ ] **Step 5: Commit the documentation/changelog**

```bash
git add docs/API.md docs/USAGE.md CHANGELOG.md
git commit -m "docs: document light group sync contract"
```

---

### Task 7: Obtain two adversarial reviews and open the pyintellicenter feature PR

**Files:**
- Modify only pyintellicenter source, tests, or documentation required to resolve accepted review findings; do not touch Home Assistant `custom_components`, integration dependency files, or release-version files in this task.

**Interfaces:**
- Consumes: green Task 6 branch.
- Produces: one reviewed pyintellicenter PR targeting `main`; no version bump in this feature PR.

- [ ] **Step 1: Ask `agy` for a safety/concurrency adversarial review**

Run from the pyintellicenter worktree:

```bash
agy --mode plan --sandbox --add-dir "$PWD" \
  --model 'Claude Opus 4.6 (Thinking)' --print-timeout 20m --print \
  'Adversarially review this issue #93 feature branch against origin/main. Find concrete correctness, race, protocol-safety, typing, compatibility, and test gaps. Focus on connection-owned enqueue-time monotonic sequencing, observer installation before the first wildcard projection with bounded pre-baseline replay, initialization-validated subscription batching under the 50-key ceiling, required-versus-normalized-optional projection fields including ordinary parentless/non-color circuits, the under-request-lock pre-send deadline and post-send causal watermark hooks, strict sequence > post-send watermark action admission including WebSocket send suspension, transient prewrite projection rejection, exact equality of fresh normalized projections around the one-second subscription settle, captured-connection/replacement identity, pending-before-wait lifecycle ownership, fail-fast later case-insensitive public SetParamList writers, pre-ACK notifications, explicit 60-second request timeout, realistic full acknowledgement shape, uniform ON/OFF prestates, sender-side SYNC edges including forbidden post-terminal re-entry, the dispatch-time 60-second onset/terminal deadline, the separate 60-second post-terminal observation, full normalized circuit/row invariants through observer removal, mandatory same-connection final projection, phase-aware ICLightGroupError metadata, no retry/recovery, exact mixed-case SetParamList payload, real CIRCUIT parent/CIRCGRP row modeling, and absence of Set/Swim/member-position APIs. Confirm action eligibility is the exact raw firmware token 1.064 plus exactly two distinct resolved GLOW children, with broader color/version parsing retained only for read/display helpers. Report findings by severity with file/line and an executable fix; do not edit files.'
```

Expected: a severity-ranked review, not implementation.

- [ ] **Step 2: Ask Cursor `agent` for an independent adversarial review**

```bash
agent --print --output-format text --mode ask --sandbox enabled --trust \
  --workspace "$PWD" --model 'claude-opus-4-8-thinking-high' \
  'Independently adversarially review this issue #93 pyintellicenter branch versus origin/main. Look for protocol extrapolation, missing authoritative gates, notification ordering/races, deadlocks, reconnect identity bugs, observer leaks, stale queue use, lifecycle-owner or fail-fast writer-isolation gaps, malformed projection handling, backwards-compatibility breaks, absent negative tests, and accidental Set/Swim/member-position support. Verify the raw observer is installed before the first wildcard GetParamList and bounded buffered frames are replayed; exact-object subscription batches stay at or below 50 keys and initialization responses normalize only optional circuit PARENT/USE and row USE while mandatory keys remain strict; complete fresh normalized projections match exactly around the one-second settle and transient restore still rejects; event-loop time is captured under the request lock immediately before transport initiation while the causal sequence watermark is captured after TCP write/WebSocket send completion; WebSocket send-window frames cannot qualify onset; the exact one-object mixed-case SetParamList SYNC payload uses an explicit 60-second response timeout and returns a realistic full acknowledgement; onset and terminal share the dispatch-start 60-second deadline and target SYNC cannot re-enter afterward; post-terminal observation is a separate 60 seconds; every normalized circuit/row, group-flag, and system invariant remains monitored through removal; final GetParamList is mandatory on the captured connection; errors expose correct phase/certainty; and there is no retry/recovery. Confirm exact raw firmware token 1.064 and exactly two distinct resolved GLOW children. Return only actionable findings with severity and file/line; do not edit.'
```

Expected: an independent severity-ranked review.

- [ ] **Step 3: Triage every finding with evidence**

Create a private review ledger containing reviewer, severity, finding, disposition, evidence, and commit. Accept technically valid findings with a failing regression test first; reject findings only with a specific code/test/protocol reason. Re-run the focused test that proves every accepted fix, then the complete Task 6 gate.

- [ ] **Step 4: Re-run both reviewers after material fixes**

Use the same commands with an added sentence asking whether each prior finding is closed. Expected: no unresolved critical/high finding and no untested race/safety claim.

- [ ] **Step 5: Push and open the feature PR**

```bash
git push -u origin feature/issue-93-light-group-sync
gh pr create --repo joyfulhouse/pyintellicenter --base main \
  --head feature/issue-93-light-group-sync \
  --title "feat: model real light groups and add Color Sync" \
  --body-file /tmp/pyintellicenter-issue-93-pr.md
```

The prepared PR body must summarize the corrected parent/row model, supported Sync matrix, exact lifecycle/error-certainty gates, evidence-scoped firmware `1.064`/exactly-two-`GLOW` eligibility, broader read-only color classification, negative scope, test commands, and both adversarial-review dispositions. Expected: an open feature PR with green GitHub Actions. Opening this feature PR is within the implementation workflow; merging it is not.

---

### Task 8: Prepare pyintellicenter 0.1.22 and stop at maintainer release checkpoints

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/pyintellicenter/__init__.py`
- Modify: `uv.lock`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: maintainer-confirmed merge of the pyintellicenter feature PR and green `main`.
- Produces: a separate release PR; after explicit maintainer merge/publish checkpoints, GitHub Release `v0.1.22` and installable PyPI `pyintellicenter==0.1.22`.

- [ ] **Step 1: Stop for the feature-merge checkpoint, then create a release worktree**

Do not merge the feature PR. Request maintainer/user confirmation that it has been reviewed and merged. Only after confirmation, fetch and verify `origin/main` contains the feature merge, then create the release worktree:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter fetch origin
git -C /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-release-0.1.22 \
  -b chore/release-0.1.22 origin/main
```

Expected: the new base contains the maintainer-merged feature commits. If confirmation is absent or the merge is not fetched, stop; integration coding may continue with the temporary editable install, but release/lock work may not.

- [ ] **Step 2: Bump all synchronized library version sources**

Set `project.version = "0.1.22"` in `pyproject.toml`, `__version__ = "0.1.22"` in `src/pyintellicenter/__init__.py`, and move `[Unreleased]` entries under `## [0.1.22] - 2026-07-15` in `CHANGELOG.md`. Then run:

```bash
uv lock
uv run pytest tests/test_version.py -q
git diff --check
```

Expected: `uv.lock` records 0.1.22 and version tests pass.

- [ ] **Step 3: Run the complete release gate and open the release PR**

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
git add pyproject.toml src/pyintellicenter/__init__.py uv.lock CHANGELOG.md
git commit -m "chore: release 0.1.22"
git push -u origin chore/release-0.1.22
gh pr create --repo joyfulhouse/pyintellicenter --base main \
  --head chore/release-0.1.22 --title "chore: release 0.1.22" \
  --body "Release real light-group modeling and verified Color Sync for issue #93."
```

Expected: green release PR. Do not tag from the unmerged branch.

- [ ] **Step 4: Stop for release-PR merge and publication authorization**

Do not merge the release PR, create a tag, or publish a GitHub Release. Request explicit maintainer/user confirmation for those actions. The current `.github/workflows/publish.yml` triggers only when a maintainer publishes GitHub Release `v0.1.22`, then builds once, publishes to TestPyPI, and publishes to PyPI. Record the maintainer-provided release URL/job result after that external checkpoint.

- [ ] **Step 5: Verify the released artifact independently**

```bash
uv run --isolated --no-project --with pyintellicenter==0.1.22 python -c \
  'from pyintellicenter import ICModelController, ICLightGroupError, __version__; assert __version__ == "0.1.22"; assert callable(ICModelController.run_light_group_sync); assert issubclass(ICLightGroupError, Exception); print(__version__)'
```

Expected: prints `0.1.22`. This read-only artifact check may run after the maintainer confirms publication. Do not begin the integration lock update or open the integration PR until it succeeds against PyPI rather than a local editable checkout.

---

### Task 9: Correct Home Assistant row tracking and group entity construction

**Files:**
- Modify: `custom_components/intellicenter/coordinator.py`
- Modify: `custom_components/intellicenter/light.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_light.py`
- Modify: `tests/test_library_contract.py`

**Interfaces:**
- Consumes: API-stable, focused-green pyintellicenter feature worktree from Task 5; publication is not required for local implementation.
- Produces: membership rows tracked as `{PARENT, CIRCUIT, LISTORD}`, existing parent light entities retained, no membership-row entity, a complete-group resolver for existing effect modeling, and a separate evidence-scoped Color Sync predicate inside `light.py`.

- [ ] **Step 1: Refresh the integration branch and install a temporary editable library without repository drift**

The Task 1 integration worktree may predate intervening `main` changes while the library API stabilized. Refresh it, sync its existing frozen environment, then overlay the pyintellicenter feature worktree as an uncommitted editable install:

```bash
git fetch origin
git rebase origin/main
uv sync --frozen
uv pip install --python .venv/bin/python --editable \
  /Users/bryanli/Projects/joyfulhouse/python/pyintellicenter-issue-93-sync
uv run --no-sync python -c \
  'from pathlib import Path; import pyintellicenter; assert "pyintellicenter-issue-93-sync" in str(Path(pyintellicenter.__file__).resolve())'
git diff --exit-code -- custom_components/intellicenter/manifest.json pyproject.toml uv.lock
```

Expected: tests can import the stable feature API while manifest, pyproject, and lock remain byte-for-byte unchanged. Do not run `uv lock`, commit a path/git dependency, or open the integration PR in this temporary state. Tasks 9-11 may now proceed in parallel with Task 7 review/Task 8 maintainer checkpoints because the worktrees do not share repository state.

- [ ] **Step 2: Write failing tracking and construction tests**

Assert the exact row map:

```python
assert DEFAULT_ATTRIBUTES_MAP[CIRCGRP_TYPE] == {
    PARENT_ATTR,
    CIRCUIT_ATTR,
    LISTORD_ATTR,
}
```

Build a complete parent/two-row/two-child topology and pass all objects to `_build_entities()`. Assert one entity uses the parent objnam, child lights retain their ordinary entities, and no row objnam appears. Add zero/one/three-row, missing-child, duplicate-child, mixed-capability, and legacy standalone-row cases. The parent remains an entity. General complete `INTELLI`/`MAGIC2`/`GLOW` membership may retain existing effect rendering, but local Color Sync eligibility must additionally require cached raw firmware token exactly `1.064`, exactly two distinct resolved children, and both children exactly `OBJTYP=CIRCUIT/SUBTYP=GLOW`. Add rejection tests for absent/other firmware and raw variants (`IC: 1.064`, trailing whitespace, build suffix) that `parse_ic_version()` might interpret for display/upgrade purposes; the writer predicate intentionally does not call that semantic parser. Also reject complete all-`INTELLI` or all-`MAGIC2` groups and a malformed non-`CIRCUIT` object carrying subtype `GLOW`.

- [ ] **Step 3: Run focused tests and verify red**

```bash
uv run --no-sync pytest tests/test_light.py tests/test_library_contract.py -k "group or circgrp" -v
```

Expected: row tracking still contains unsupported `SNAME`/`STATUS`/`USE`, and the current builder's vacuous `all()` accepts empty/incomplete membership.

- [ ] **Step 4: Correct tracking and eliminate vacuous capability checks**

Set the exact coordinator row map. In `light.py`, add a pure complete-group resolver that returns `None` unless the parent is `CIRCUIT/LITSHO`, membership is non-empty, every row resolves, the resolved count matches the row count, and child objnams are distinct:

```python
def _complete_light_group_children(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> tuple[PoolObject, ...] | None:
    if parent.objtype != CIRCUIT_TYPE or parent.subtype != "LITSHO":
        return None
    members = coordinator.controller.get_circuit_group_members(parent.objnam)
    children = coordinator.controller.get_circuits_in_group(parent.objnam)
    if (
        not members
        or len(children) != len(members)
        or len({child.objnam for child in children}) != len(children)
    ):
        return None
    return tuple(children)


def _is_complete_color_light_group(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> bool:
    children = _complete_light_group_children(coordinator, parent)
    return children is not None and all(
        child.supports_color_effects for child in children
    )


def _is_color_sync_eligible(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> bool:
    children = _complete_light_group_children(coordinator, parent)
    system_info = coordinator.system_info
    return bool(
        system_info is not None
        and system_info.sw_version == "1.064"
        and children is not None
        and len(children) == 2
        and all(
            child.objtype == CIRCUIT_TYPE and child.subtype == "GLOW"
            for child in children
        )
    )
```

Use `_is_complete_color_light_group()` only to preserve the existing group effect capability without a vacuous `all()`. Use `_is_color_sync_eligible()` only for the new state-changing action. `_build_entities()` continues to create the existing parent light exactly once. Membership rows fail both `is_a_light` and `is_a_light_show` and create no entity.

- [ ] **Step 5: Run focused consumer/model tests green**

```bash
uv run --no-sync pytest tests/test_light.py tests/test_library_contract.py tests/test_dynamic_entities.py -q
uv run --no-sync ruff check custom_components/intellicenter/coordinator.py custom_components/intellicenter/light.py tests/test_light.py tests/test_library_contract.py
uv run --no-sync ruff format --check custom_components/intellicenter/coordinator.py custom_components/intellicenter/light.py tests/test_light.py tests/test_library_contract.py
```

Expected: all pass and no row-derived entity is created.

- [ ] **Step 6: Commit the integration model boundary**

```bash
git add custom_components/intellicenter/coordinator.py custom_components/intellicenter/light.py tests/conftest.py tests/test_light.py tests/test_library_contract.py
git commit -m "fix: consume real light group membership model"
```

---

### Task 10: Expose only the Home Assistant Color Sync entity service

**Files:**
- Modify: `custom_components/intellicenter/light.py`
- Modify: `custom_components/intellicenter/services.yaml`
- Modify: `tests/test_light.py`
- Modify: `tests/test_library_contract.py`

**Interfaces:**
- Consumes: `_is_color_sync_eligible()` and `ICModelController.run_light_group_sync()`.
- Produces: entity service `intellicenter.color_sync` -> `PoolLight.async_color_sync()`.

- [ ] **Step 1: Write failing service registration and execution tests**

Update the registration assertion to include exactly `color_sync` after the four existing MagicStream services. Add:

```python
async def test_color_sync_calls_dedicated_library_helper(
    complete_group_light: PoolLight,
    mock_coordinator: MagicMock,
) -> None:
    await complete_group_light.async_color_sync()
    mock_coordinator.controller.run_light_group_sync.assert_awaited_once_with("GROUP")
    mock_coordinator.controller.request_changes.assert_not_awaited()
```

Also assert:

- ordinary `LIGHT`, `INTELLI`, `MAGIC2`, and `CIRCUIT/SUBTYP=CIRCGRP` entities raise `HomeAssistantError` with `translation_key="light_group_command_unsupported"` before the library call;
- zero/one/three-member, missing-child, duplicate-child, mixed-capability, all-`INTELLI`, and all-`MAGIC2` `LITSHO` parents raise the same unsupported error;
- missing firmware or any firmware other than exact `1.064` raises unsupported before the library call;
- a library-side `ValueError` caused by a race after the local check still maps to `light_group_command_unsupported`;
- any ordinary pre-dispatch `ICError` and an `ICLightGroupError` with a correlated explicit rejection (`response_received=True`, `acknowledged=False`, `onset_seen=False`) map to `light_group_command_failed`;
- an `ICLightGroupError` with dispatch started but no response/onset maps to `light_group_command_uncertain`;
- any `ICLightGroupError` with `acknowledged=True` or `onset_seen=True` maps to `light_group_command_incomplete`, taking precedence over the uncertain/rejected branches;
- the method does not mutate `effect`, `effect_list`, `_optimistic_state`, `STATUS`, or `USE`;
- no `color_set`, `color_swim`, or member-position service/method exists.

- [ ] **Step 2: Run focused service tests and verify red**

```bash
uv run --no-sync pytest tests/test_light.py tests/test_library_contract.py -k "color_sync or light_group" -v
```

Expected: service/method/library-contract assertions fail because Color Sync is absent.

- [ ] **Step 3: Register and implement the momentary service**

Replace the MagicStream-only registration mapping with an entity-service mapping that retains all existing entries and adds:

```python
"color_sync": "async_color_sync"
```

Import `ICError` and `ICLightGroupError` from the installed `pyintellicenter` package, then implement:

```python
async def async_color_sync(self) -> None:
    """Synchronize the supported two-light IntelliCenter group."""
    if not _is_color_sync_eligible(self.coordinator, self._pool_object):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="light_group_command_unsupported",
        )
    try:
        await self._controller.run_light_group_sync(self._pool_object.objnam)
    except ValueError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="light_group_command_unsupported",
        ) from err
    except ICLightGroupError as err:
        if err.acknowledged or err.onset_seen:
            translation_key = "light_group_command_incomplete"
        elif err.dispatch_started and not err.response_received:
            translation_key = "light_group_command_uncertain"
        else:
            translation_key = "light_group_command_failed"
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=translation_key,
        ) from err
    except ICError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="light_group_command_failed",
        ) from err
```

Add only `color_sync` to `services.yaml`, targeting integration `intellicenter`, domain `light`. Do not add fields; the entity target is the sole input.

- [ ] **Step 4: Strengthen the installed-library contract**

Add `run_light_group_sync` to `CONTROLLER_METHODS`, `ICLightGroupError` to `REQUIRED_SYMBOLS`, and explicit callable/subclass/attribute checks. During parallel implementation this runs against the temporary editable worktree with `--no-sync`; Task 12 must rerun it against the released/locked wheel so mocks and the editable overlay cannot hide dependency drift.

- [ ] **Step 5: Run light/service contract tests green**

```bash
uv run --no-sync pytest tests/test_light.py tests/test_library_contract.py tests/test_versions.py -q
uv run --no-sync ruff check custom_components/intellicenter/light.py tests/test_light.py tests/test_library_contract.py
uv run --no-sync ruff format --check custom_components/intellicenter/light.py tests/test_light.py tests/test_library_contract.py
uv run --no-sync mypy custom_components/intellicenter/light.py
```

Expected: all pass; only Color Sync is newly registered.

- [ ] **Step 6: Commit the service implementation**

```bash
git add custom_components/intellicenter/light.py custom_components/intellicenter/services.yaml tests/test_light.py tests/test_library_contract.py
git commit -m "feat: expose light group Color Sync service"
```

---

### Task 11: Localize and document the Home Assistant feature

**Files:**
- Modify: `custom_components/intellicenter/strings.json`
- Modify: `custom_components/intellicenter/translations/de.json`
- Modify: `custom_components/intellicenter/translations/en.json`
- Modify: `custom_components/intellicenter/translations/es.json`
- Modify: `custom_components/intellicenter/translations/fr.json`
- Modify: `custom_components/intellicenter/translations/it.json`
- Modify: `custom_components/intellicenter/translations/ja.json`
- Modify: `custom_components/intellicenter/translations/ko.json`
- Modify: `custom_components/intellicenter/translations/nl.json`
- Modify: `custom_components/intellicenter/translations/pt.json`
- Modify: `custom_components/intellicenter/translations/ru.json`
- Modify: `custom_components/intellicenter/translations/zh-Hans.json`
- Modify: `custom_components/intellicenter/translations/zh-Hant.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `color_sync`, `light_group_command_unsupported`, `light_group_command_failed`, `light_group_command_uncertain`, and `light_group_command_incomplete` keys.
- Produces: complete service/error metadata in every currently supported locale and certainty-specific end-user timing/recovery guidance.

- [ ] **Step 1: Add canonical English source copy**

Use these exact English strings in `strings.json` and `translations/en.json`:

```json
"color_sync": {
  "name": "Synchronize light-group colors",
  "description": "Synchronizes exactly two GloBrite lights in a complete IntelliCenter light group on firmware 1.064. The call waits for the physical action, a 60-second post-action observation, and a final controller read."
}
```

```json
"light_group_command_unsupported": {
  "message": "Color Sync is available only on IntelliCenter firmware 1.064 for a complete light group with exactly two distinct GloBrite lights."
},
"light_group_command_failed": {
  "message": "Color Sync failed before dispatch or IntelliCenter explicitly rejected it. No action was confirmed."
},
"light_group_command_uncertain": {
  "message": "Color Sync dispatch started, but IntelliCenter returned no response. The action may have run. Inspect the lights and panel state before retrying."
},
"light_group_command_incomplete": {
  "message": "IntelliCenter acknowledged or visibly started Color Sync, but authoritative completion was not confirmed. Inspect the lights and panel state before retrying."
}
```

- [ ] **Step 2: Add the same five keys to all non-English locales**

Use the following exact localized values. Each row is ordered as service `name`; service `description`; unsupported `message`; failed/rejected `message`; uncertain-dispatch `message`; acknowledged/started-incomplete `message`. Preserve the product/protocol names `Color Sync`, `GloBrite`, `IntelliCenter`, firmware `1.064`, and the 60-second value exactly as shown.

- `de.json`: `Farben der Lichtgruppe synchronisieren`; `Synchronisiert genau zwei GloBrite-Leuchten in einer vollständigen IntelliCenter-Lichtgruppe mit Firmware 1.064. Der Aufruf wartet auf die physische Aktion, eine 60-sekündige Beobachtung nach der Aktion und eine abschließende Abfrage des Controllers.`; `Color Sync ist nur mit IntelliCenter-Firmware 1.064 für eine vollständige Lichtgruppe mit genau zwei verschiedenen GloBrite-Leuchten verfügbar.`; `Color Sync ist vor dem Senden fehlgeschlagen oder wurde von IntelliCenter ausdrücklich abgelehnt. Es wurde keine Aktion bestätigt.`; `Der Versand von Color Sync wurde begonnen, aber IntelliCenter hat nicht geantwortet. Die Aktion wurde möglicherweise ausgeführt. Prüfen Sie die Leuchten und den Bedienfeldstatus, bevor Sie es erneut versuchen.`; `IntelliCenter hat Color Sync bestätigt oder sichtbar gestartet, aber der zuverlässige Abschluss konnte nicht bestätigt werden. Prüfen Sie die Leuchten und den Bedienfeldstatus, bevor Sie es erneut versuchen.`
- `es.json`: `Sincronizar colores del grupo de luces`; `Sincroniza exactamente dos luces GloBrite de un grupo de luces IntelliCenter completo con firmware 1.064. La llamada espera la acción física, una observación de 60 segundos posterior a la acción y una lectura final del controlador.`; `Color Sync solo está disponible con el firmware 1.064 de IntelliCenter para un grupo de luces completo con exactamente dos luces GloBrite distintas.`; `Color Sync falló antes del envío o IntelliCenter lo rechazó explícitamente. No se confirmó ninguna acción.`; `Se inició el envío de Color Sync, pero IntelliCenter no respondió. Es posible que la acción se haya ejecutado. Inspeccione las luces y el estado del panel antes de volver a intentarlo.`; `IntelliCenter confirmó o inició visiblemente Color Sync, pero no se pudo confirmar de forma fiable que finalizara. Inspeccione las luces y el estado del panel antes de volver a intentarlo.`
- `fr.json`: `Synchroniser les couleurs du groupe de lumières`; `Synchronise exactement deux lumières GloBrite d'un groupe de lumières IntelliCenter complet avec le micrologiciel 1.064. L'appel attend l'action physique, une observation de 60 secondes après l'action et une lecture finale du contrôleur.`; `Color Sync est disponible uniquement avec le micrologiciel IntelliCenter 1.064 pour un groupe de lumières complet comportant exactement deux lumières GloBrite distinctes.`; `Color Sync a échoué avant l'envoi ou IntelliCenter l'a explicitement rejeté. Aucune action n'a été confirmée.`; `L'envoi de Color Sync a commencé, mais IntelliCenter n'a renvoyé aucune réponse. L'action a peut-être été exécutée. Inspectez les lumières et l'état du panneau avant de réessayer.`; `IntelliCenter a confirmé ou démarré visiblement Color Sync, mais la fin fiable de l'opération n'a pas pu être confirmée. Inspectez les lumières et l'état du panneau avant de réessayer.`
- `it.json`: `Sincronizza i colori del gruppo luci`; `Sincronizza esattamente due luci GloBrite di un gruppo luci IntelliCenter completo con firmware 1.064. La chiamata attende l'azione fisica, un'osservazione di 60 secondi dopo l'azione e una lettura finale del controller.`; `Color Sync è disponibile solo con il firmware IntelliCenter 1.064 per un gruppo luci completo con esattamente due luci GloBrite distinte.`; `Color Sync non è riuscito prima dell'invio oppure IntelliCenter lo ha rifiutato esplicitamente. Non è stata confermata alcuna azione.`; `L'invio di Color Sync è iniziato, ma IntelliCenter non ha risposto. L'azione potrebbe essere stata eseguita. Controllare le luci e lo stato del pannello prima di riprovare.`; `IntelliCenter ha confermato o avviato visibilmente Color Sync, ma non è stato possibile confermare in modo affidabile il completamento. Controllare le luci e lo stato del pannello prima di riprovare.`
- `ja.json`: `ライトグループの色を同期`; `ファームウェア 1.064 の IntelliCenter で、完全なライトグループ内の異なる 2 台の GloBrite ライトを同期します。この呼び出しは、実際の動作、動作後 60 秒間の監視、コントローラーの最終読み取りが完了するまで待機します。`; `Color Sync は、IntelliCenter ファームウェア 1.064 で、異なる GloBrite ライトが正確に 2 台ある完全なライトグループに対してのみ使用できます。`; `Color Sync は送信前に失敗したか、IntelliCenter によって明示的に拒否されました。動作は確認されていません。`; `Color Sync の送信は開始されましたが、IntelliCenter から応答がありませんでした。動作した可能性があります。再試行する前に、ライトとパネルの状態を確認してください。`; `IntelliCenter は Color Sync を確認または明らかに開始しましたが、確実な完了を確認できませんでした。再試行する前に、ライトとパネルの状態を確認してください。`
- `ko.json`: `조명 그룹 색상 동기화`; `펌웨어 1.064를 실행하는 IntelliCenter의 완전한 조명 그룹에서 서로 다른 GloBrite 조명 두 개를 정확히 동기화합니다. 이 호출은 실제 동작, 동작 후 60초 관찰 및 최종 컨트롤러 읽기가 완료될 때까지 기다립니다.`; `Color Sync는 IntelliCenter 펌웨어 1.064에서 서로 다른 GloBrite 조명이 정확히 두 개인 완전한 조명 그룹에만 사용할 수 있습니다.`; `Color Sync가 전송 전에 실패했거나 IntelliCenter가 명시적으로 거부했습니다. 확인된 동작이 없습니다.`; `Color Sync 전송이 시작되었지만 IntelliCenter가 응답하지 않았습니다. 동작이 실행되었을 수 있습니다. 다시 시도하기 전에 조명과 패널 상태를 확인하십시오.`; `IntelliCenter가 Color Sync를 확인했거나 눈에 띄게 시작했지만 신뢰할 수 있는 완료를 확인하지 못했습니다. 다시 시도하기 전에 조명과 패널 상태를 확인하십시오.`
- `nl.json`: `Kleuren van lichtgroep synchroniseren`; `Synchroniseert precies twee GloBrite-lampen in een complete IntelliCenter-lichtgroep met firmware 1.064. De aanroep wacht op de fysieke actie, een observatie van 60 seconden na de actie en een laatste uitlezing van de controller.`; `Color Sync is alleen beschikbaar met IntelliCenter-firmware 1.064 voor een complete lichtgroep met precies twee verschillende GloBrite-lampen.`; `Color Sync is vóór verzending mislukt of IntelliCenter heeft de opdracht expliciet geweigerd. Er is geen actie bevestigd.`; `De verzending van Color Sync is gestart, maar IntelliCenter heeft niet gereageerd. De actie is mogelijk uitgevoerd. Controleer de lampen en de paneelstatus voordat u het opnieuw probeert.`; `IntelliCenter heeft Color Sync bevestigd of zichtbaar gestart, maar de betrouwbare voltooiing kon niet worden bevestigd. Controleer de lampen en de paneelstatus voordat u het opnieuw probeert.`
- `pt.json`: `Sincronizar cores do grupo de luzes`; `Sincroniza exatamente duas luzes GloBrite de um grupo de luzes IntelliCenter completo com o firmware 1.064. A chamada aguarda a ação física, uma observação de 60 segundos após a ação e uma leitura final do controlador.`; `Color Sync está disponível apenas com o firmware 1.064 do IntelliCenter para um grupo de luzes completo com exatamente duas luzes GloBrite distintas.`; `Color Sync falhou antes do envio ou o IntelliCenter o rejeitou explicitamente. Nenhuma ação foi confirmada.`; `O envio de Color Sync foi iniciado, mas o IntelliCenter não respondeu. A ação pode ter sido executada. Inspecione as luzes e o estado do painel antes de tentar novamente.`; `O IntelliCenter confirmou ou iniciou visivelmente o Color Sync, mas não foi possível confirmar a conclusão de forma confiável. Inspecione as luzes e o estado do painel antes de tentar novamente.`
- `ru.json`: `Синхронизировать цвета группы освещения`; `Синхронизирует ровно два разных светильника GloBrite в полной группе освещения IntelliCenter с прошивкой 1.064. Вызов ожидает физическое действие, 60-секундное наблюдение после действия и окончательное чтение данных контроллера.`; `Color Sync доступна только с прошивкой IntelliCenter 1.064 для полной группы освещения, содержащей ровно два разных светильника GloBrite.`; `Сбой Color Sync произошёл до отправки либо IntelliCenter явно отклонил команду. Выполнение действия не подтверждено.`; `Отправка Color Sync началась, но IntelliCenter не ответил. Возможно, действие было выполнено. Перед повторной попыткой проверьте светильники и состояние панели.`; `IntelliCenter подтвердил или явно начал Color Sync, но достоверное завершение подтвердить не удалось. Перед повторной попыткой проверьте светильники и состояние панели.`
- `zh-Hans.json`: `同步灯光组颜色`; `在固件版本为 1.064 的 IntelliCenter 上，同步完整灯光组中恰好两个不同的 GloBrite 灯。此调用会等待实际操作、操作后的 60 秒观察和最终控制器读取完成。`; `Color Sync 仅适用于运行 IntelliCenter 固件 1.064 且包含恰好两个不同 GloBrite 灯的完整灯光组。`; `Color Sync 在发送前失败，或被 IntelliCenter 明确拒绝。未确认任何操作。`; `Color Sync 已开始发送，但 IntelliCenter 未返回响应。操作可能已运行。重试前请检查灯光和面板状态。`; `IntelliCenter 已确认或明显启动 Color Sync，但未能确认操作可靠完成。重试前请检查灯光和面板状态。`
- `zh-Hant.json`: `同步燈光群組色彩`; `在韌體版本為 1.064 的 IntelliCenter 上，同步完整燈光群組中恰好兩個不同的 GloBrite 燈。此呼叫會等待實際動作、動作後的 60 秒觀察及最終控制器讀取完成。`; `Color Sync 僅適用於執行 IntelliCenter 韌體 1.064 且包含恰好兩個不同 GloBrite 燈的完整燈光群組。`; `Color Sync 在傳送前失敗，或被 IntelliCenter 明確拒絕。未確認任何動作。`; `Color Sync 已開始傳送，但 IntelliCenter 未回應。動作可能已執行。重試前請檢查燈光與面板狀態。`; `IntelliCenter 已確認或明顯啟動 Color Sync，但無法確認操作可靠完成。重試前請檢查燈光與面板狀態。`

Run a key-parity check after editing:

```bash
for file in custom_components/intellicenter/translations/*.json; do
  jq -e '.services.color_sync.name and .services.color_sync.description and .exceptions.light_group_command_unsupported.message and .exceptions.light_group_command_failed.message and .exceptions.light_group_command_uncertain.message and .exceptions.light_group_command_incomplete.message' "$file" >/dev/null
done
```

Expected: all 12 files exit 0. Do not leave English fallback text in a non-English file.

- [ ] **Step 3: Document behavior and negative scope**

Update the Light Shows feature row to mention the Color Sync action over TCP/WebSocket. Add a service example:

```yaml
action:
  - service: intellicenter.color_sync
    target:
      entity_id: light.pool_light_group
```

Explain that the call usually takes roughly 96-97 seconds plus request latency on the observed firmware, waits synchronously through a 60-second post-terminal observation and final read, and supports only firmware `1.064`, exactly two distinct GloBrite members, and uniform all-off/all-on state. During the action, other IntelliCenter object mutations requested through this Home Assistant connection fail immediately rather than queueing behind it; read-only updates continue, and urgent physical-panel control remains available but may cause the action to report incomplete. Explain the distinction between explicit failure, uncertain no-response dispatch, and acknowledged/started incomplete outcomes; for the latter two, tell users to inspect the lights/panel before retrying. Explicitly state Color Set, Color Swim, and member-position controls are not exposed.

- [ ] **Step 4: Add integration changelog entries under `[Unreleased]`**

Under `Added`, record the `intellicenter.color_sync` service. Under `Fixed`, record that real `CIRCUIT` parents are no longer confused with `CIRCGRP` membership rows. Under `Changed`, record the pyintellicenter 0.1.22 floor and the blocking authoritative lifecycle.

- [ ] **Step 5: Validate JSON, metadata, docs, and dependency drift**

```bash
for file in custom_components/intellicenter/strings.json custom_components/intellicenter/translations/*.json; do
  python -m json.tool "$file" >/dev/null
done
uv run --no-sync pytest tests/test_light.py tests/test_library_contract.py tests/test_versions.py -q
if rg -n 'color_set|color_swim|member_position' custom_components/intellicenter; then
  exit 1
fi
git diff --check
```

Expected: JSON and tests pass, forbidden service/API names are absent from production integration files, and diff whitespace is clean. Negative tests and README scope documentation may name omitted features.

- [ ] **Step 6: Commit localization and docs**

```bash
git add custom_components/intellicenter/strings.json custom_components/intellicenter/translations README.md CHANGELOG.md
git commit -m "docs: localize and document Color Sync"
```

---

### Task 12: Verify, adversarially review, and open the integration feature PR

**Files:**
- Modify only files required to resolve accepted review findings.

**Interfaces:**
- Consumes: released pyintellicenter 0.1.22 and green Tasks 9-11.
- Produces: one reviewed intellicenter feature PR targeting `main`, with integration version still `3.10.0b2`.

- [ ] **Step 1: Stop for the published-wheel checkpoint, then replace the editable overlay**

Do not regenerate the lock or open this PR until Task 8's read-only isolated check proves `pyintellicenter==0.1.22` is on PyPI. After maintainer publication is confirmed, first remove the temporary editable overlay by restoring the frozen environment. Using `apply_patch`, set the pyintellicenter dependency string in both `custom_components/intellicenter/manifest.json` and `pyproject.toml` to exact floor `pyintellicenter>=0.1.22`; then regenerate from the registry and prove the installed distribution is not editable:

```bash
uv sync --frozen
uv lock --upgrade-package pyintellicenter
uv sync --frozen
uv run python -c \
  'from importlib import metadata; import pyintellicenter; assert pyintellicenter.__version__ == "0.1.22"; direct = metadata.distribution("pyintellicenter").read_text("direct_url.json"); assert direct is None or "editable" not in direct'
uv run pytest tests/test_library_contract.py tests/test_versions.py -q
git diff --check
git add custom_components/intellicenter/manifest.json pyproject.toml uv.lock
git commit -m "chore: require pyintellicenter 0.1.22"
```

Expected: manifest, pyproject, and lock agree on the released registry artifact; no worktree path/git source exists in the diff or `direct_url.json`.

- [ ] **Step 2: Run the complete local integration gate**

```bash
uv sync --frozen
uv run pytest tests/ -v --tb=short --cov=custom_components/intellicenter
uv run ruff check custom_components/
uv run ruff format --check custom_components/
uv run mypy custom_components/intellicenter/
uv run bandit -r custom_components/intellicenter/ -ll
uv lock --check
git diff --check
git status --short
```

Expected: every local CI-equivalent gate passes; status lists only issue #93 files.

- [ ] **Step 3: Ask `agy` for the Home Assistant adversarial review**

```bash
agy --mode plan --sandbox --add-dir "$PWD" \
  --model 'Claude Opus 4.6 (Thinking)' --print-timeout 20m --print \
  'Adversarially review this intellicenter issue #93 branch against origin/main. Verify that real CIRCUIT/LITSHO parents and CIRCGRP membership rows are modeled without duplicate entities; only color_sync is registered; eligibility is exact firmware 1.064 plus exactly two distinct resolved GLOW children while broader color helpers remain read/effect-only; ordinary/incomplete/one-or-three-member groups reject before the library call; the service awaits run_light_group_sync and separately maps unsupported ValueError, prewrite/explicit rejection, dispatched-no-response uncertainty, and acknowledged-or-started incomplete ICLightGroupError outcomes with acknowledged/onset precedence; no effect or optimistic state is invented; coordinator row tracking is exactly PARENT/CIRCUIT/LISTORD; all five locale keys and metadata are complete; pyintellicenter>=0.1.22 is a non-editable registry dependency consistent in manifest, pyproject, and lock; and Set, Swim, and member position remain absent. Report actionable findings by severity with file/line and an executable fix; do not edit.'
```

- [ ] **Step 4: Ask Cursor `agent` for an independent Home Assistant review**

```bash
agent --print --output-format text --mode ask --sandbox enabled --trust \
  --workspace "$PWD" --model 'claude-opus-4-8-thinking-high' \
  'Independently adversarially review this issue #93 Home Assistant branch versus origin/main. Search for duplicate row-derived entities, vacuous all() membership checks, action eligibility beyond exact firmware 1.064/exactly two distinct GLOW children, unsupported service exposure, mock-hidden or editable library drift, wrong ICLightGroupError certainty precedence/translations, optimistic/effect state leakage, missing five-key locale/service metadata, lockfile/version drift, weak negative tests, and accidental Color Set/Swim/member-position scope. Confirm the dedicated run_light_group_sync call and non-editable released 0.1.22 wheel. Return only actionable severity-ranked findings with file/line; do not edit.'
```

- [ ] **Step 5: Resolve/re-review every finding**

Use the same evidence-led ledger process as Task 7. Add a failing regression test before each accepted code fix, run its focused gate, then the complete Step 2 gate. Re-run both reviewers after material changes; no critical/high finding may remain unresolved.

- [ ] **Step 6: Stop for explicit live-smoke authorization, then perform one controlled production-path smoke**

This changes physical lights and is not implied by permission to implement/open PRs. Stop and obtain explicit user authorization for the named private test panel and target. If authorized, configure the private Home Assistant/test instance first for TCP and then WebSocket. Confirm firmware `1.064`, `SERVICE=AUTO`, exactly two distinct GloBrite children, uniform all-off or all-on state, and all group flags off. Invoke `intellicenter.color_sync` exactly once per transport; require the service to remain pending through terminal, the full 60-second post-terminal observation, and final read, then succeed without any projected collateral change. Restore only through the official UI if the target changed. Abort on any invariant failure, timeout, disconnect, or inability to restore. Record only sanitized timing/certainty facts in the PR body; never commit identifiers or raw frames. If authorization is withheld, mark the gate not run and stop before release rather than simulating success.

- [ ] **Step 7: Push and open the integration feature PR**

```bash
git push -u origin feature/issue-93-light-group-sync
gh pr create --repo joyfulhouse/intellicenter --base main \
  --head feature/issue-93-light-group-sync \
  --title "feat: add verified light-group Color Sync" \
  --body-file /tmp/intellicenter-issue-93-pr.md
```

The PR body must link the pyintellicenter feature/release, state the exact firmware-1.064/two-GloBrite supported envelope and omitted matrix, explain the four failure-certainty translations, summarize both external reviews and authorized live smoke, and list exact verification commands. Expected: open PR with green CI, hassfest, and HACS checks. This step is forbidden until Step 1 proves the published wheel and registry lock.

---

### Task 13: Release intellicenter 3.10.0b3 after the feature merges

**Files:**
- Modify: `custom_components/intellicenter/manifest.json`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: maintainer-confirmed integration feature merge and published pyintellicenter 0.1.22.
- Produces: separate release PR; after explicit maintainer merge/publication checkpoints, GitHub pre-release `v3.10.0b3`.

- [ ] **Step 1: Stop for the integration-merge checkpoint, then create a release worktree**

Do not merge the integration feature PR. Request maintainer/user confirmation that it has merged, then fetch and verify `origin/main` contains it before creating the worktree:

```bash
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter fetch origin
git -C /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter worktree add \
  /Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter-release-3.10.0b3 \
  -b chore/release-3.10.0b3 origin/main
```

Expected: base contains the maintainer-merged issue #93 feature. Stop if merge confirmation or fetched ancestry is absent.

- [ ] **Step 2: Synchronize release metadata**

Set both manifest and pyproject versions to `3.10.0b3`; promote `[Unreleased]` entries to `## [3.10.0b3] - 2026-07-15`; run `uv lock` so the root package version changes while pyintellicenter remains 0.1.22.

- [ ] **Step 3: Run release gates and open the release PR**

```bash
uv sync --frozen
uv run pytest tests/ -q
uv run ruff check custom_components/
uv run ruff format --check custom_components/
uv run mypy custom_components/intellicenter/
uv run bandit -r custom_components/intellicenter/ -ll
uv run pytest tests/test_versions.py -q
git diff --check
git add custom_components/intellicenter/manifest.json pyproject.toml uv.lock CHANGELOG.md
git commit -m "chore: release 3.10.0b3"
git push -u origin chore/release-3.10.0b3
gh pr create --repo joyfulhouse/intellicenter --base main \
  --head chore/release-3.10.0b3 --title "chore: release 3.10.0b3" \
  --body "Pre-release with corrected light-group modeling and verified TCP/WebSocket Color Sync for issue #93."
```

Expected: green release PR with exact manifest/pyproject/lock version parity.

- [ ] **Step 4: Stop for release-PR merge and GitHub pre-release publication**

Do not merge the release PR, create a tag, or publish a GitHub pre-release. Request explicit maintainer/user authorization and confirmation. After the maintainer publishes `v3.10.0b3`, wait for `.github/workflows/release.yml` to attach `intellicenter.zip`, then perform the read-only archive inspection to confirm it contains the updated manifest, `services.yaml`, strings/translations, and no `.env`, cache, or test files.

---

## Final Acceptance Checklist

- [ ] `get_circuit_groups()` returns only real parent `CIRCUIT` objects; ordered `CIRCGRP` rows and resolved children are available through corrected helpers.
- [ ] Direct legacy standalone-row resolution remains tested, but legacy/orphan rows never enumerate as groups or entities.
- [ ] `run_light_group_sync()` is the only group-action API; there is no generic command token, Set, Swim, or member-position writer.
- [ ] TCP and WebSocket, uniform OFF and ON, pre-ACK notification, leading-order variation, and sender-side `SYNC` edges are tested.
- [ ] Writer eligibility is exactly firmware `1.064`, one `CIRCUIT/LITSHO` parent, and exactly two distinct resolved `CIRCUIT/GLOW` children; broader color helpers remain read/effect-only.
- [ ] A raw observer is installed before the first wildcard projection; its bounded pre-baseline buffer is replayed, subscription batches and initialization values are validated, the post-settle fresh projection matches exactly, and any transient projected prewrite change aborts before dispatch.
- [ ] The connection-owned sequence is monotonic; event-loop time starts the deadline under the request lock immediately before TCP write/WebSocket send initiation, the causal sequence watermark is captured immediately after TCP write/WebSocket send completion, and only `sequence > post_send_watermark` qualifies action edges.
- [ ] Success requires an exact `200`, positive onset and terminal by `write_started_at + 60`, a separate 60-second post-terminal observation, and a mandatory clean final `GetParamList` on the captured connection.
- [ ] From dispatch start through observer removal, target monotonic status rules (including no post-terminal `SYNC` re-entry), all required circuit identity/status fields, normalized optional circuit `PARENT/USE`, all group flags, required row topology, normalized optional row `USE`, and system fields reject even transient-restored violations.
- [ ] Observer fanout is additive/enqueue-time/stale-safe and cleans up on every exit; captured-connection and disconnect/reconnect races are tested.
- [ ] Sync marks its owner-aware lifecycle pending before waiting for already-started case-insensitive public `SetParamList` writers; later writers/Sync calls fail fast instead of queueing, direct raw `ICConnection` use is explicitly outside that boundary, and no state-changing request is retried or automatically recovered.
- [ ] `ICLightGroupError` reports phase/dispatch/response/acknowledgement/onset certainty, and Home Assistant separately maps unsupported, failed/rejected, uncertain dispatch, and acknowledged/started incomplete outcomes.
- [ ] Home Assistant creates no row entity and exposes only `intellicenter.color_sync` on the evidence-scoped parent light, without effect or optimistic state.
- [ ] Coordinator membership-row tracking is exactly `PARENT`, `CIRCUIT`, `LISTORD`.
- [ ] All 12 locale files, service metadata, README, changelogs, installed-library contract, and dependency/version drift tests pass.
- [ ] Exact firmware-`1.064`/two-`GLOW` action eligibility and broader read-only color classification are accepted in both adversarial reviews.
- [ ] A maintainer-published, non-editable pyintellicenter 0.1.22 wheel is locked before the integration PR opens; every merge/tag/PyPI/GitHub release and live-smoke mutation occurs only at its explicit user/maintainer checkpoint.
- [ ] Full local gates, `agy`, Cursor `agent`, GitHub Actions, hassfest, and HACS are green with no unresolved critical/high finding.
