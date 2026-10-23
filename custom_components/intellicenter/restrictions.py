"""Read-only equipment context from panel state and existing model relationships.

Cover assignment reads and purifier interpretation are deliberately unknown until
those protocol surfaces are supported. A closed cover alone does not establish
that a particular circuit is assigned to it. Nothing here authorizes commands.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pyintellicenter import (
    BODY_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_ATTR,
    CIRCUIT_TYPE,
    EXTINSTR_TYPE,
    FREEZE_ATTR,
    NORMAL_ATTR,
    PARENT_ATTR,
    PMPCIRC_TYPE,
    POSIT_ATTR,
    PUMP_TYPE,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)

STATE_ATTRIBUTES = frozenset({STATUS_ATTR, FREEZE_ATTR, POSIT_ATTR, NORMAL_ATTR})
RELATION_ATTRIBUTES = frozenset({PARENT_ATTR, CIRCUIT_ATTR})


@dataclass(frozen=True, slots=True, order=True)
class ContextFact:
    """A confirmed reason or a dependency that prevents an assessment."""

    code: str
    objnam: str
    source: str


@dataclass(frozen=True, slots=True)
class CoverContext:
    """Measured cover state; applicability to the target remains unverified."""

    objnam: str
    enabled: bool | None
    position: Literal["closed", "open", "unknown"]


@dataclass(frozen=True, slots=True)
class RestrictionContext:
    """Confirmed context and unknown dependencies, independent of on/off state."""

    reasons: tuple[ContextFact, ...]
    unknown_dependencies: tuple[ContextFact, ...]
    covers: tuple[CoverContext, ...]

    @property
    def state(self) -> Literal["active", "unknown", "clear"]:
        """Unknown dependencies can coexist with a confirmed reason."""
        if self.reasons:
            return "active"
        return "unknown" if self.unknown_dependencies else "clear"

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible entity attributes and downloadable diagnostics."""
        return {
            "state": self.state,
            "reasons": [asdict(reason) for reason in self.reasons],
            "unknown_dependencies": [
                asdict(item) for item in self.unknown_dependencies
            ],
            "covers": [asdict(cover) for cover in self.covers],
        }


@dataclass(frozen=True, slots=True)
class _Topology:
    circuits: frozenset[str]
    dependencies: frozenset[str]
    unknowns: frozenset[ContextFact]


def supports_restriction_context(obj: PoolObject) -> bool:
    """Identify operational equipment, excluding the separate freeze diagnostic."""
    return obj.objtype in (CIRCUIT_TYPE, PUMP_TYPE) and obj.subtype != "FRZ"


def _on_off(value: Any) -> bool | None:
    if value == "ON":
        return True
    if value == "OFF":
        return False
    return None


def _reference(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value in ("00000", PARENT_ATTR, CIRCUIT_ATTR)
        or any(char.isspace() for char in value)
    ):
        return None
    return value


class RestrictionIndex:
    """Share topology indexing across entities and reuse targeted dispatch.

    Index once after structural changes, then resolve/cache only the target's
    reachable membership rows. Attribute-only pushes never scan the model.
    """

    def __init__(self, model: PoolModel) -> None:
        self._model = model
        self._rows: dict[str, list[PoolObject]] | None = None
        self._covers: tuple[str, ...] = ()
        self._topologies: dict[str, _Topology] = {}

    def invalidate(self) -> None:
        """Invalidate topology when objects or relationship fields change."""
        self._rows = None
        self._topologies.clear()

    def _ensure_index(self) -> None:
        if self._rows is not None:
            return
        rows: dict[str, list[PoolObject]] = defaultdict(list)
        covers: list[str] = []
        for obj in self._model:
            if obj.objtype == EXTINSTR_TYPE and obj.subtype == "COVER":
                covers.append(obj.objnam)
            elif obj.objtype in (CIRCGRP_TYPE, PMPCIRC_TYPE):
                if parent := _reference(obj[PARENT_ATTR]):
                    rows[parent].append(obj)
        self._rows = rows
        self._covers = tuple(sorted(covers))

    def _topology(self, objnam: str) -> _Topology:
        self._ensure_index()
        if objnam in self._topologies:
            return self._topologies[objnam]
        assert self._rows is not None
        circuits: set[str] = set()
        dependencies: set[str] = set(self._covers)
        unknowns: set[ContextFact] = set()
        pending = [(objnam, frozenset[str]())]
        visited: set[str] = set()
        while pending:
            current, ancestors = pending.pop()
            dependencies.add(current)
            if current in ancestors:
                unknowns.add(ContextFact("membership_cycle", current, "PARENT/CIRCUIT"))
                continue
            if current in visited:
                continue
            visited.add(current)
            obj = self._model[current]
            if obj is None:
                unknowns.add(
                    ContextFact("equipment_missing", current, "PARENT/CIRCUIT")
                )
                continue
            if obj.objtype == CIRCUIT_TYPE:
                circuits.add(current)
            elif obj.objtype == BODY_TYPE:
                unknowns.add(
                    ContextFact("body_freeze_context_unsupported", current, "FREEZE")
                )
                continue
            elif obj.objtype != PUMP_TYPE:
                unknowns.add(
                    ContextFact("equipment_type_unsupported", current, "OBJTYP")
                )
                continue
            is_pump = obj.objtype == PUMP_TYPE
            if not is_pump and obj.subtype not in ("CIRCGRP", "LITSHO"):
                continue
            row_type = PMPCIRC_TYPE if is_pump else CIRCGRP_TYPE
            members = [
                row for row in self._rows.get(current, ()) if row.objtype == row_type
            ]
            if not members:
                unknowns.add(
                    ContextFact("membership_unknown", current, "PARENT/CIRCUIT")
                )
            for row in members:
                dependencies.add(row.objnam)
                reference = _reference(row[CIRCUIT_ATTR])
                if reference is None:
                    unknowns.add(
                        ContextFact("member_reference_unknown", row.objnam, "CIRCUIT")
                    )
                    continue
                dependencies.add(reference)
                target = self._model[reference]
                valid_types = (CIRCUIT_TYPE, BODY_TYPE) if is_pump else (CIRCUIT_TYPE,)
                if target is not None and target.objtype not in valid_types:
                    unknowns.add(
                        ContextFact("member_type_unsupported", reference, "OBJTYP")
                    )
                    continue
                pending.append((reference, ancestors | {current}))
        topology = _Topology(
            frozenset(circuits), frozenset(dependencies), frozenset(unknowns)
        )
        self._topologies[objnam] = topology
        return topology

    def dependencies(self, objnam: str) -> dict[str, set[str] | None]:
        """Include missing referenced IDs so their arrival can resolve context."""
        return {
            dependency: set(STATE_ATTRIBUTES | RELATION_ATTRIBUTES)
            for dependency in self._topology(objnam).dependencies
        }

    def assess(self, objnam: str, *, connected: bool) -> RestrictionContext:
        """Assess current cached panel state without inferring command enforcement."""
        unknowns = {
            ContextFact("purifier_context_unsupported", objnam, "IntelliBlue"),
            ContextFact("cover_assignments_unverified", objnam, "PARENT/CIRCUIT"),
        }
        if not connected:
            unknowns.add(ContextFact("connection_unavailable", objnam, "connection"))
            return RestrictionContext((), tuple(sorted(unknowns)), ())
        # The model has no field timestamps or snapshot-completeness marker.
        unknowns.add(ContextFact("field_freshness_unverified", objnam, "model"))
        topology = self._topology(objnam)
        unknowns.update(topology.unknowns)
        reasons: set[ContextFact] = set()
        for circuit in sorted(topology.circuits):
            obj = self._model[circuit]
            if obj is None:
                unknowns.add(ContextFact("equipment_missing", circuit, "STATUS/FREEZE"))
                continue
            status, freeze = _on_off(obj[STATUS_ATTR]), _on_off(obj[FREEZE_ATTR])
            if status is None or freeze is None:
                unknowns.add(
                    ContextFact("freeze_state_unknown", circuit, "STATUS/FREEZE")
                )
            elif status and freeze:
                reasons.add(
                    ContextFact("freeze_protection_context", circuit, "STATUS/FREEZE")
                )
        covers: list[CoverContext] = []
        for cover in self._covers:
            obj = self._model[cover]
            if obj is None:
                unknowns.add(ContextFact("equipment_missing", cover, "POSIT/NORMAL"))
                continue
            enabled = _on_off(obj[STATUS_ATTR])
            position, normal = _on_off(obj[POSIT_ATTR]), _on_off(obj[NORMAL_ATTR])
            measured: Literal["closed", "open", "unknown"] = "unknown"
            if position is not None and normal is not None:
                measured = "closed" if position == normal else "open"
            if enabled is None:
                unknowns.add(ContextFact("cover_enabled_unknown", cover, "STATUS"))
            if measured == "unknown":
                unknowns.add(
                    ContextFact("cover_position_unknown", cover, "POSIT/NORMAL")
                )
            covers.append(CoverContext(cover, enabled, measured))
        return RestrictionContext(
            tuple(sorted(reasons)), tuple(sorted(unknowns)), tuple(covers)
        )
