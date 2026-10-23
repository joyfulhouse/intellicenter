"""Restriction diagnostics without guessed assignment schemas or device writes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pyintellicenter import PoolModel, PoolObject
import pytest

from custom_components.intellicenter.binary_sensor import PumpBinarySensor
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator
from custom_components.intellicenter.cover import PoolCover
from custom_components.intellicenter.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.intellicenter.light import PoolLight
from custom_components.intellicenter.restrictions import RestrictionIndex
from custom_components.intellicenter.switch import PoolCircuit


@pytest.fixture
def coordinator(hass: HomeAssistant) -> IntelliCenterCoordinator:
    """Use the actual model, dependency index and coordinator dispatch."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "restriction_test"
    entry.data = {}
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.1")
    coordinator._handler._is_connected = True
    return coordinator


def add(coordinator: IntelliCenterCoordinator, name: str, **params) -> PoolObject:
    """Add a purpose-built object to the real tracked model."""
    obj = coordinator.model.add_object(name, params)
    assert obj is not None
    return obj


def codes(items) -> set[str]:
    """Compare facts independently of their stable serialized ordering."""
    return {item.code for item in items}


def assessment(coordinator: IntelliCenterCoordinator, target: str = "C1"):
    return coordinator.restrictions.assess(target, connected=coordinator.connected)


@pytest.mark.parametrize(
    ("status", "freeze", "active", "unknown"),
    [
        ("ON", "ON", True, False),
        ("OFF", "ON", False, False),
        ("ON", "OFF", False, False),
        ("OFF", "OFF", False, False),
        (None, "ON", False, True),
        ("ON", None, False, True),
        ("STATUS", "ON", False, True),
        ("ON", "FREEZE", False, True),
        (True, "ON", False, True),
        ("ON", {"bad": "value"}, False, True),
    ],
)
def test_freeze_helper_evidence(coordinator, status, freeze, active, unknown):
    """App 79113 requires CIRCUIT plus both STATUS and FREEZE set to ON."""
    add(
        coordinator,
        "C1",
        OBJTYP="CIRCUIT",
        SUBTYP="GENERIC",
        STATUS=status,
        FREEZE=freeze,
    )
    result = assessment(coordinator)
    assert ("freeze_protection_context" in codes(result.reasons)) is active
    assert ("freeze_state_unknown" in codes(result.unknown_dependencies)) is unknown
    # Unimplemented assignment/purifier domains must never imply an all-clear.
    assert result.state == ("active" if active else "unknown")
    assert {"purifier_context_unsupported", "cover_assignments_unverified"} <= codes(
        result.unknown_dependencies
    )


@pytest.mark.parametrize(
    ("status", "position", "normal", "enabled", "measured"),
    [
        ("ON", "ON", "ON", True, "closed"),
        ("OFF", "ON", "ON", False, "closed"),
        ("ON", "OFF", "OFF", True, "closed"),
        ("ON", "ON", "OFF", True, "open"),
        ("ON", "OFF", "ON", True, "open"),
        ("ON", None, "ON", True, "unknown"),
        ("ON", "ON", None, True, "unknown"),
        ("ON", "ON", "NORMAL", True, "unknown"),
        ("ON", "POSIT", "OFF", True, "unknown"),
        ("STATUS", "ON", "ON", None, "closed"),
        ("ON", [], {}, True, "unknown"),
    ],
)
def test_cover_measurement_preserves_position_fix(
    coordinator, status, position, normal, enabled, measured
):
    """Disabled is not open; malformed polarity and omitted POSIT are unknown."""
    add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="OFF")
    cover = add(
        coordinator,
        "CV1",
        OBJTYP="EXTINSTR",
        SUBTYP="COVER",
        STATUS=status,
        POSIT=position,
        NORMAL=normal,
    )
    result = assessment(coordinator)
    observed = result.covers[0]
    assert observed.enabled is enabled
    assert observed.position == measured
    assert (
        PoolCover(coordinator, cover).is_closed
        == {"closed": True, "open": False, "unknown": None}[measured]
    )
    assert not result.reasons
    assert "cover_assignments_unverified" in codes(result.unknown_dependencies)


def test_multiple_covers_do_not_select_the_first_or_guess_assignment(coordinator):
    """App closure examples are sanitized relationships, not panel captures."""
    add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    add(
        coordinator,
        "CV1",
        OBJTYP="EXTINSTR",
        SUBTYP="COVER",
        STATUS="ON",
        POSIT="ON",
        NORMAL="OFF",
    )
    add(
        coordinator, "CV2", OBJTYP="EXTINSTR", SUBTYP="COVER", STATUS="OFF", NORMAL="ON"
    )
    result = assessment(coordinator)
    assert [
        (cover.objnam, cover.enabled, cover.position) for cover in result.covers
    ] == [("CV1", True, "open"), ("CV2", False, "unknown")]
    assert codes(result.reasons) == {"freeze_protection_context"}
    assert any(
        item.objnam == "CV2" and item.code == "cover_position_unknown"
        for item in result.unknown_dependencies
    )


@pytest.mark.parametrize("group_subtype", ["CIRCGRP", "LITSHO"])
async def test_group_and_pump_transitions_preserve_measured_state(
    hass, coordinator, group_subtype
):
    """Use established CIRCGRP and PMPCIRC relationships, without cover writes."""
    circuit = add(
        coordinator, "C1", OBJTYP="CIRCUIT", SUBTYP="GENERIC", STATUS="ON", FREEZE="OFF"
    )
    group = add(
        coordinator,
        "G1",
        OBJTYP="CIRCUIT",
        SUBTYP=group_subtype,
        STATUS="OFF",
        FREEZE="OFF",
    )
    row = add(coordinator, "ROW", OBJTYP="CIRCGRP", PARENT="G1", CIRCUIT="C1")
    pump = add(coordinator, "P1", OBJTYP="PUMP", SUBTYP="VSF", STATUS="10", RPM="1200")
    add(coordinator, "PR1", OBJTYP="PMPCIRC", PARENT="P1", CIRCUIT="G1")
    entities = [
        PoolCircuit(coordinator, circuit),
        (
            PoolLight(coordinator, group)
            if group_subtype == "LITSHO"
            else PoolCircuit(coordinator, group)
        ),
        PumpBinarySensor(coordinator, pump),
    ]
    coordinator._started = True
    coordinator._known_objnams = set(coordinator.model.objects)
    for entity in entities:
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
        await entity.async_added_to_hass()
    circuit.update({"FREEZE": "ON"})
    coordinator.async_set_updated_data({"C1": {"FREEZE": "ON"}})
    for entity in entities:
        entity.async_write_ha_state.assert_called_once()
        context = entity.extra_state_attributes["restriction_context"]
        assert context["state"] == "active"
        assert context["reasons"] == [
            {
                "code": "freeze_protection_context",
                "objnam": "C1",
                "source": "STATUS/FREEZE",
            }
        ]
    assert entities[0].is_on is True
    assert entities[1].is_on is False
    assert entities[2].is_on is True
    assert all(entity.available for entity in entities)
    # Replacing membership must remove the old child's reason immediately.
    other = add(coordinator, "C2", OBJTYP="CIRCUIT", STATUS="OFF", FREEZE="ON")
    row.update({"CIRCUIT": other.objnam})
    coordinator.async_set_updated_data(
        {"C2": {"STATUS": "OFF"}, "ROW": {"CIRCUIT": "C2"}}
    )
    assert not assessment(coordinator, "G1").reasons
    assert not assessment(coordinator, "P1").reasons
    # A remaining dangling reference becomes unknown rather than clear.
    coordinator.model.remove_object("C2")
    coordinator.async_set_updated_data({"C2": None})
    assert "equipment_missing" in codes(
        assessment(coordinator, "G1").unknown_dependencies
    )
    add(coordinator, "C2", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    coordinator.async_set_updated_data({"C2": {"STATUS": "ON", "FREEZE": "ON"}})
    assert codes(assessment(coordinator, "P1").reasons) == {"freeze_protection_context"}
    coordinator.model.remove_object("ROW")
    coordinator.async_set_updated_data({"ROW": None})
    assert "membership_unknown" in codes(
        assessment(coordinator, "G1").unknown_dependencies
    )
    assert entities[1].is_on is False
    assert entities[2].is_on is True


@pytest.mark.parametrize("member", [None, "CIRCUIT", "00000", "C1 C2", [], {}])
def test_invalid_membership_is_unknown(coordinator, member):
    add(
        coordinator, "G1", OBJTYP="CIRCUIT", SUBTYP="LITSHO", STATUS="OFF", FREEZE="OFF"
    )
    add(coordinator, "ROW", OBJTYP="CIRCGRP", PARENT="G1", CIRCUIT=member)
    result = assessment(coordinator, "G1")
    assert "member_reference_unknown" in codes(result.unknown_dependencies)
    assert not result.reasons


def test_wrong_types_cycles_and_missing_pump_body_context(coordinator):
    add(
        coordinator,
        "G1",
        OBJTYP="CIRCUIT",
        SUBTYP="CIRCGRP",
        STATUS="OFF",
        FREEZE="OFF",
    )
    row = add(coordinator, "ROW", OBJTYP="CIRCGRP", PARENT="G1", CIRCUIT="G1")
    assert "membership_cycle" in codes(
        assessment(coordinator, "G1").unknown_dependencies
    )
    add(coordinator, "P1", OBJTYP="PUMP", RPM="0")
    row.update({"CIRCUIT": "P1"})
    coordinator.restrictions.invalidate()
    assert "member_type_unsupported" in codes(
        assessment(coordinator, "G1").unknown_dependencies
    )
    add(coordinator, "BODY1", OBJTYP="BODY", STATUS="ON")
    add(coordinator, "PR1", OBJTYP="PMPCIRC", PARENT="P1", CIRCUIT="BODY1")
    coordinator.restrictions.invalidate()
    assert "body_freeze_context_unsupported" in codes(
        assessment(coordinator, "P1").unknown_dependencies
    )


async def test_disconnect_removal_and_reconnect(hass, coordinator):
    circuit = add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    add(
        coordinator,
        "CV1",
        OBJTYP="EXTINSTR",
        SUBTYP="COVER",
        STATUS="ON",
        POSIT="ON",
        NORMAL="ON",
    )
    entity = PoolCircuit(coordinator, circuit)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    await entity.async_added_to_hass()
    assert assessment(coordinator).reasons
    coordinator._handler._is_connected = False
    coordinator.async_set_connection_state(False)
    stale = assessment(coordinator)
    assert not stale.reasons
    assert not stale.covers
    assert "field_freshness_unverified" not in codes(stale.unknown_dependencies)
    assert "connection_unavailable" in codes(stale.unknown_dependencies)
    coordinator.model.remove_object("CV1")
    coordinator.async_set_updated_data({"CV1": None})
    # Reconnect with fresh state and a cover lacking a position channel.
    circuit.update({"FREEZE": "OFF"})
    add(coordinator, "CV2", OBJTYP="EXTINSTR", SUBTYP="COVER", STATUS="ON", NORMAL="ON")
    coordinator._handler._is_connected = True
    coordinator.async_set_connection_state(True)
    current = entity.extra_state_attributes["restriction_context"]
    assert current["reasons"] == []
    assert any(
        item["code"] == "field_freshness_unverified"
        for item in current["unknown_dependencies"]
    )
    assert [cover["objnam"] for cover in current["covers"]] == ["CV2"]
    assert any(
        item["code"] == "cover_position_unknown"
        for item in current["unknown_dependencies"]
    )
    assert entity.is_on is True


async def test_targeted_dispatch_no_model_scans_on_related_push(hass, coordinator):
    """Ordinary updates resolve neither topology nor a full equipment inventory."""
    target = add(
        coordinator, "C1", OBJTYP="CIRCUIT", SUBTYP="LIGHT", STATUS="ON", FREEZE="OFF"
    )
    unrelated = add(
        coordinator, "C2", OBJTYP="CIRCUIT", SUBTYP="GENERIC", STATUS="ON", FREEZE="OFF"
    )
    cover = add(
        coordinator,
        "CV1",
        OBJTYP="EXTINSTR",
        SUBTYP="COVER",
        STATUS="ON",
        POSIT="ON",
        NORMAL="ON",
    )
    light = PoolLight(coordinator, target)
    switch = PoolCircuit(coordinator, unrelated)
    coordinator._started = True
    coordinator._known_objnams = set(coordinator.model.objects)
    for entity in (light, switch):
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
        await entity.async_added_to_hass()
    with (
        patch.object(
            PoolModel, "__iter__", side_effect=AssertionError("full model scan")
        ),
        patch.object(PoolModel, "get_by_type", side_effect=AssertionError("type scan")),
    ):
        target.update({"FREEZE": "ON"})
        coordinator.async_set_updated_data({"C1": {"FREEZE": "ON"}})
        assert light.extra_state_attributes["restriction_context"]["state"] == "active"
        light.async_write_ha_state.assert_called_once()
        switch.async_write_ha_state.assert_not_called()
        cover.update({"POSIT": "OFF"})
        coordinator.async_set_updated_data({"CV1": {"POSIT": "OFF"}})
        assert (
            light.extra_state_attributes["restriction_context"]["covers"][0]["position"]
            == "open"
        )
        assert light.async_write_ha_state.call_count == 2
        switch.async_write_ha_state.assert_called_once()


async def test_read_only_context_does_not_block_commands_or_reconcile_optimism(
    hass, coordinator
):
    circuit = add(
        coordinator, "C1", OBJTYP="CIRCUIT", SUBTYP="GENERIC", STATUS="OFF", FREEZE="ON"
    )
    cover = add(
        coordinator,
        "CV1",
        OBJTYP="EXTINSTR",
        SUBTYP="COVER",
        STATUS="ON",
        POSIT="ON",
        NORMAL="ON",
    )
    entity = PoolCircuit(coordinator, circuit)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    await entity.async_added_to_hass()
    with patch.object(
        coordinator.controller, "request_changes", new_callable=AsyncMock
    ) as write:
        await entity.async_turn_on()
        write.assert_awaited_once_with("C1", {"STATUS": "ON"})
        assert entity.is_on is True
        # Cover context update must not clear pending measured-state reconciliation.
        cover.update({"POSIT": "OFF"})
        coordinator.async_set_updated_data({"CV1": {"POSIT": "OFF"}})
        assert entity.is_on is True
        assert circuit["STATUS"] == "OFF"
        assert not assessment(coordinator).reasons


async def test_downloaded_diagnostics_include_context(hass, coordinator):
    add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    entry = MagicMock(spec=ConfigEntry)
    entry.runtime_data = coordinator
    entry.entry_id = "restriction_test"
    entry.title = "Private Pool"
    entry.data = {"host": "192.0.2.1"}
    entry.options = {}
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["restriction_contexts"]["C1"]["state"] == "active"
    assert result["entry"]["title"] == "**REDACTED**"
    assert result["entry"]["data"]["host"] == "**REDACTED**"


def test_context_serialization_is_detached(coordinator):
    add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    result = assessment(coordinator)
    serialized = result.as_dict()
    serialized["reasons"][0]["code"] = "changed"
    serialized["unknown_dependencies"].clear()
    assert codes(result.reasons) == {"freeze_protection_context"}
    assert result.unknown_dependencies
    assert RestrictionIndex(coordinator.model).assess("C1", connected=True) == result


def test_connected_cached_fields_keep_freshness_explicit(coordinator):
    """A partial push cannot certify the age of unchanged cached fields."""
    circuit = add(coordinator, "C1", OBJTYP="CIRCUIT", STATUS="ON", FREEZE="ON")
    before = assessment(coordinator)
    assert before.state == "active"
    assert "field_freshness_unverified" in codes(before.unknown_dependencies)
    circuit.update({"STATUS": "OFF"})
    coordinator.async_set_updated_data({"C1": {"STATUS": "OFF"}})
    after = assessment(coordinator)
    assert after.state == "unknown"
    assert not after.reasons
    assert "field_freshness_unverified" in codes(after.unknown_dependencies)
    assert circuit["FREEZE"] == "ON"
    disconnected = coordinator.restrictions.assess("C1", connected=False)
    assert "connection_unavailable" in codes(disconnected.unknown_dependencies)
    assert not disconnected.reasons
