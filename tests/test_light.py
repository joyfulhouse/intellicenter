"""Test the Pentair IntelliCenter light platform."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    BODY_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_TYPE,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    USE_ATTR,
    ICError,
    ICLightGroupError,
    PoolModel,
    PoolObject,
)
import pytest
import yaml

from custom_components.intellicenter import light as light_platform
from custom_components.intellicenter.const import LIMIT_ATTR
from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
from custom_components.intellicenter.light import PoolLight, _build_entities

pytestmark = pytest.mark.asyncio

_SERVICES_YAML = (
    Path(__file__).parent.parent
    / "custom_components"
    / "intellicenter"
    / "services.yaml"
)


def _make_light_group_model(
    member_refs: tuple[str, ...],
    child_shapes: dict[str, tuple[str, str]],
) -> PoolModel:
    """Build one light-show parent with real membership rows and children."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_object(
        "GROUP",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "LITSHO",
            "SNAME": "Color Group",
            "STATUS": "OFF",
            "USE": "WHITER",
        },
    )
    for index, circuit_ref in enumerate(member_refs, start=1):
        model.add_object(
            f"GROUP_ROW_{index}",
            {
                "OBJTYP": CIRCGRP_TYPE,
                "PARENT": "GROUP",
                "CIRCUIT": circuit_ref,
                "LISTORD": str(index),
            },
        )
    for objnam, (objtype, subtype) in child_shapes.items():
        model.add_object(
            objnam,
            {
                "OBJTYP": objtype,
                "SUBTYP": subtype,
                "SNAME": objnam,
                "STATUS": "OFF",
                "USE": "WHITER",
            },
        )
    return model


def _set_firmware(mock_coordinator: MagicMock, version: str | None) -> None:
    """Set the cached raw firmware token used by the local action gate."""
    if version is None:
        mock_coordinator.system_info = None
        return
    system_info = MagicMock()
    system_info.sw_version = version
    mock_coordinator.system_info = system_info


def _group_light_for_model(
    mock_coordinator: MagicMock,
    model: PoolModel,
    firmware: str | None = "1.064",
) -> PoolLight:
    """Return the parent entity for a supplied group topology."""
    mock_coordinator.model = model
    _set_firmware(mock_coordinator, firmware)
    return next(
        entity
        for entity in _build_entities(mock_coordinator, list(model))
        if entity._pool_object.objnam == "GROUP"
    )


def _color_sync_state(light: PoolLight) -> tuple[object, ...]:
    """Capture every entity/model value Color Sync must leave untouched."""
    return (
        light.effect,
        light.effect_list,
        light._optimistic_state,
        light._pool_object[STATUS_ATTR],
        light._pool_object[USE_ATTR],
    )


async def _assert_color_sync_error(
    light: PoolLight, translation_key: str
) -> HomeAssistantError:
    """Assert one translated Color Sync failure and return it."""
    with pytest.raises(HomeAssistantError) as raised:
        await light.async_color_sync()
    assert raised.value.translation_domain == "intellicenter"
    assert raised.value.translation_key == translation_key
    return raised.value


async def test_coordinator_tracks_light_limit() -> None:
    """The model must request LIMIT or brightness never reaches entities."""
    assert LIMIT_ATTR in DEFAULT_ATTRIBUTES_MAP[CIRCUIT_TYPE]


async def test_light_setup_creates_entities(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test light platform creates entities for lights in the model."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.light import async_setup_entry

    platform = MagicMock()
    with patch(
        "custom_components.intellicenter.light.entity_platform.async_get_current_platform",
        return_value=platform,
    ):
        await async_setup_entry(hass, mock_entry, capture_entities)

    assert [registered.args[0] for registered in platform.mock_calls] == [
        "capture",
        "thumper",
        "hold",
        "recall",
        "color_sync",
    ]

    # Should create entities for:
    # - LIGHT1 (IntelliBrite light)
    # - LIGHT2 (Regular light)
    # - SHOW1 (Light show)
    assert len(entities_added) == 3

    # Verify entity types
    light_names = [e._pool_object.sname for e in entities_added]
    assert "Pool Light" in light_names
    assert "Spa Light" in light_names
    assert "Party Show" in light_names


async def test_light_entity_properties(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolLight entity properties."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Test initial state
    assert light.is_on is False
    assert light.name == "Pool Light"
    assert light.unique_id == "test_entry_LIGHT1"


async def test_light_turn_on_basic(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a light without effects."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on()

    # Should request status change to ON
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"
    # Verify optimistic update was called
    mock_write_ha_state.assert_called()


async def test_light_turn_on_with_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning on a light with color effect."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: "Party Mode"})

    # Effect is set via convenience method
    mock_coordinator.controller.set_light_effect.assert_called_once_with(
        "LIGHT1", "PARTY"
    )

    # Light is turned on via request_changes
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "ON"


async def test_light_turn_off(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Test turning off a light."""
    # Set light to ON initially
    pool_object_light.update({STATUS_ATTR: "ON"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    assert light.is_on is True

    await hass.async_block_till_done()
    await light.async_turn_off()

    # Should request status change to OFF
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert STATUS_ATTR in args[1]
    assert args[1][STATUS_ATTR] == "OFF"


async def test_light_supports_effects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test light with color effects support."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Should have effect list
    assert light.effect_list is not None
    assert len(light.effect_list) > 0
    assert "Party Mode" in light.effect_list
    assert "Caribbean" in light.effect_list
    assert "White" in light.effect_list


async def test_light_no_effects_support(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Test light without color effects support."""
    # Create a regular light without color effect support
    regular_light_obj = PoolObject(
        "LIGHT2",
        {
            "OBJTYP": "CIRCUIT",
            "SUBTYP": "LIGHT",
            "SNAME": "Regular Light",
            "STATUS": "OFF",
        },
    )

    light = PoolLight(mock_coordinator, regular_light_obj, None)

    # Should not support effects
    assert light._light_effects is None


async def test_light_current_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test getting current effect."""
    # Set light to use PARTY effect
    pool_object_light.update({"USE": "PARTY"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    assert light.effect == "Party Mode"


async def test_light_sam_effect_resolves(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Regression test for issue #47: the SAm light show must resolve.

    IntelliCenter reports the SAm light show via USE=SAMMOD. When it was
    missing from LIGHT_EFFECTS, the effect property returned None and the HA
    entity showed null. It must now resolve to the "SAm" effect name.
    """
    pool_object_light.update({"USE": "SAMMOD"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    assert light.effect == "SAm"
    assert light.effect_list is not None
    assert "SAm" in light.effect_list


async def test_light_state_updates(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test light state updates from IntelliCenter."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Simulate update from IntelliCenter
    updates = {
        "LIGHT1": {
            STATUS_ATTR: "ON",
            "USE": "BLUER",
        }
    }

    # Check if entity should be updated
    assert light.isUpdated(updates) is True

    # Apply the update
    pool_object_light.update(updates["LIGHT1"])

    # Verify state changed
    assert light.is_on is True
    assert light.effect == "Blue"


async def test_light_show_entity(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test light show entity creation and properties."""
    mock_coordinator.model = pool_model

    show_obj = pool_model["SHOW1"]

    # For the light show, we need to add circuit references as children
    # Add a child circuit to the light show
    pool_model.add_object(
        "SHOW1_CIRC1",
        {
            "OBJTYP": "CIRCGRP",
            "CIRCUIT": "LIGHT1",
            "PARENT": "SHOW1",
        },
    )

    light_show = PoolLight(mock_coordinator, show_obj, LIGHT_EFFECTS)

    assert light_show.name == "Party Show"
    assert light_show.is_on is False


async def test_complete_light_group_builds_parent_and_children_without_rows(
    complete_light_group_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """A complete real topology creates one parent plus ordinary child lights."""
    mock_coordinator.model = complete_light_group_model

    entities = _build_entities(mock_coordinator, list(complete_light_group_model))
    objnams = [entity._pool_object.objnam for entity in entities]

    assert objnams.count("GROUP") == 1
    assert {"GLOW1", "GLOW2"} <= set(objnams)
    assert {"GROUP_ROW_1", "GROUP_ROW_2"}.isdisjoint(objnams)

    parent = complete_light_group_model["GROUP"]
    assert parent is not None
    children = light_platform._complete_light_group_children(mock_coordinator, parent)
    assert children is not None
    assert [child.objnam for child in children] == ["GLOW1", "GLOW2"]

    group_entity = next(
        entity for entity in entities if entity._pool_object.objnam == "GROUP"
    )
    assert group_entity.effect_list is not None


@pytest.mark.parametrize(
    (
        "member_refs",
        "child_shapes",
        "expected_complete",
        "expected_effects",
    ),
    [
        ((), {}, False, False),
        (("GLOW1",), {"GLOW1": (CIRCUIT_TYPE, "GLOW")}, True, True),
        (
            ("GLOW1", "GLOW2", "GLOW3"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "GLOW2": (CIRCUIT_TYPE, "GLOW"),
                "GLOW3": (CIRCUIT_TYPE, "GLOW"),
            },
            True,
            True,
        ),
        (("MISSING",), {}, False, False),
        (("GLOW1", "GLOW1"), {"GLOW1": (CIRCUIT_TYPE, "GLOW")}, False, False),
        (
            ("GLOW1", "PLAIN"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "PLAIN": (CIRCUIT_TYPE, "LIGHT"),
            },
            True,
            False,
        ),
    ],
    ids=("zero", "one", "three", "missing", "duplicate", "mixed"),
)
async def test_light_group_requires_complete_non_vacuous_membership(
    mock_coordinator: MagicMock,
    member_refs: tuple[str, ...],
    child_shapes: dict[str, tuple[str, str]],
    expected_complete: bool,
    expected_effects: bool,
) -> None:
    """Incomplete groups retain their parent but never gain effects vacuously."""
    model = _make_light_group_model(member_refs, child_shapes)
    mock_coordinator.model = model
    parent = model["GROUP"]
    assert parent is not None

    children = light_platform._complete_light_group_children(mock_coordinator, parent)
    assert (children is not None) is expected_complete
    assert (
        light_platform._is_complete_color_light_group(mock_coordinator, parent)
        is expected_effects
    )

    entities = _build_entities(mock_coordinator, list(model))
    group_entities = [
        entity for entity in entities if entity._pool_object.objnam == "GROUP"
    ]
    assert len(group_entities) == 1
    assert (group_entities[0].effect_list is not None) is expected_effects
    assert all(entity._pool_object.objtype != CIRCGRP_TYPE for entity in entities)


async def test_legacy_standalone_group_row_never_creates_an_entity(
    mock_coordinator: MagicMock,
) -> None:
    """A compatibility-only standalone row resolves children but is not a light."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    for objnam in ("GLOW1", "GLOW2"):
        model.add_object(
            objnam,
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": "GLOW",
                "SNAME": objnam,
                "STATUS": "OFF",
            },
        )
    model.add_object(
        "LEGACY_ROW",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "CIRCUIT": "GLOW1 GLOW2",
        },
    )
    mock_coordinator.model = model

    assert [
        circuit.objnam
        for circuit in mock_coordinator.controller.get_circuits_in_group("LEGACY_ROW")
    ] == ["GLOW1", "GLOW2"]
    assert {
        entity._pool_object.objnam
        for entity in _build_entities(mock_coordinator, list(model))
    } == {"GLOW1", "GLOW2"}


@pytest.mark.parametrize("subtype", ("INTELLI", "MAGIC2"))
async def test_complete_non_glow_color_group_keeps_effects_but_rejects_sync(
    mock_coordinator: MagicMock,
    subtype: str,
) -> None:
    """Broad read/display effects do not widen the evidence-scoped action gate."""
    model = _make_light_group_model(
        ("LIGHT1", "LIGHT2"),
        {
            "LIGHT1": (CIRCUIT_TYPE, subtype),
            "LIGHT2": (CIRCUIT_TYPE, subtype),
        },
    )
    mock_coordinator.model = model
    _set_firmware(mock_coordinator, "1.064")
    parent = model["GROUP"]
    assert parent is not None

    assert light_platform._is_complete_color_light_group(mock_coordinator, parent)
    assert not light_platform._is_color_sync_eligible(mock_coordinator, parent)


@pytest.mark.parametrize(
    "version",
    (None, "1.063", "1.065", "IC: 1.064", "1.064 ", "1.064-build7"),
)
async def test_color_sync_group_rejects_non_exact_raw_firmware(
    complete_light_group_model: PoolModel,
    mock_coordinator: MagicMock,
    version: str | None,
) -> None:
    """Only the captured raw firmware token is eligible for the writer."""
    mock_coordinator.model = complete_light_group_model
    _set_firmware(mock_coordinator, version)
    parent = complete_light_group_model["GROUP"]
    assert parent is not None

    assert not light_platform._is_color_sync_eligible(mock_coordinator, parent)


async def test_color_sync_group_accepts_exact_raw_firmware_and_two_glow_children(
    complete_light_group_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """The local action gate matches the only evidence-backed topology."""
    mock_coordinator.model = complete_light_group_model
    _set_firmware(mock_coordinator, "1.064")
    parent = complete_light_group_model["GROUP"]
    assert parent is not None

    assert light_platform._is_color_sync_eligible(mock_coordinator, parent)


@pytest.mark.parametrize("member_count", (0, 1, 3))
async def test_color_sync_group_rejects_wrong_member_count(
    mock_coordinator: MagicMock,
    member_count: int,
) -> None:
    """Color Sync requires exactly two distinct resolved members."""
    objnams = tuple(f"GLOW{index}" for index in range(member_count))
    model = _make_light_group_model(
        objnams,
        dict.fromkeys(objnams, (CIRCUIT_TYPE, "GLOW")),
    )
    mock_coordinator.model = model
    _set_firmware(mock_coordinator, "1.064")
    parent = model["GROUP"]
    assert parent is not None

    assert not light_platform._is_color_sync_eligible(mock_coordinator, parent)


@pytest.mark.parametrize(
    ("member_refs", "child_shapes"),
    [
        (("MISSING1", "MISSING2"), {}),
        (("GLOW1", "GLOW1"), {"GLOW1": (CIRCUIT_TYPE, "GLOW")}),
        (
            ("GLOW1", "PLAIN"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "PLAIN": (CIRCUIT_TYPE, "LIGHT"),
            },
        ),
        (
            ("GLOW1", "NOT_A_CIRCUIT"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "NOT_A_CIRCUIT": (BODY_TYPE, "GLOW"),
            },
        ),
    ],
    ids=("missing", "duplicate", "mixed", "non-circuit-glow"),
)
async def test_color_sync_group_rejects_malformed_or_unsupported_children(
    mock_coordinator: MagicMock,
    member_refs: tuple[str, ...],
    child_shapes: dict[str, tuple[str, str]],
) -> None:
    """Missing, duplicate, mixed, and fake GLOW children are never eligible."""
    model = _make_light_group_model(member_refs, child_shapes)
    mock_coordinator.model = model
    _set_firmware(mock_coordinator, "1.064")
    parent = model["GROUP"]
    assert parent is not None

    assert not light_platform._is_color_sync_eligible(mock_coordinator, parent)


async def test_light_is_not_updated_by_other_objects(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that light ignores updates to other objects."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Update for a different object
    updates = {
        "LIGHT2": {
            STATUS_ATTR: "ON",
        }
    }

    assert light.isUpdated(updates) is False


async def test_light_is_not_updated_by_irrelevant_attributes(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that light ignores irrelevant attribute updates."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Update with irrelevant attributes
    updates = {
        "LIGHT1": {
            "SOME_OTHER_ATTR": "value",
        }
    }

    assert light.isUpdated(updates) is False


# -------------------------------------------------------------------------------------
# Parameterized tests for light effects
# -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "effect_code,effect_name",
    [
        ("SAMMOD", "SAm"),
        ("PARTY", "Party Mode"),
        ("CARIB", "Caribbean"),
        ("SSET", "Sunset"),
        ("ROMAN", "Romance"),
        ("AMERCA", "American"),
        ("ROYAL", "Royal"),
        ("WHITER", "White"),
        ("REDR", "Red"),
        ("BLUER", "Blue"),
        ("GREENR", "Green"),
        ("MAGNTAR", "Magenta"),
    ],
)
async def test_light_effect_mapping(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    effect_code: str,
    effect_name: str,
) -> None:
    """Test that each effect code maps to correct effect name."""
    # Set light to use this effect
    pool_object_light.update({"USE": effect_code})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    assert light.effect == effect_name
    assert effect_name in light.effect_list


@pytest.mark.parametrize(
    "effect_name,expected_code",
    [
        ("Party Mode", "PARTY"),
        ("Caribbean", "CARIB"),
        ("Sunset", "SSET"),
        ("Romance", "ROMAN"),
        ("American", "AMERCA"),
        ("Royal", "ROYAL"),
        ("White", "WHITER"),
        ("Red", "REDR"),
        ("Blue", "BLUER"),
        ("Green", "GREENR"),
        ("Magenta", "MAGNTAR"),
    ],
)
async def test_light_turn_on_with_each_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    effect_name: str,
    expected_code: str,
) -> None:
    """Test turning on light with each effect sends correct code."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    await light.async_turn_on(**{ATTR_EFFECT: effect_name})

    # Effect is set via convenience method with correct code
    mock_coordinator.controller.set_light_effect.assert_called_once_with(
        "LIGHT1", expected_code
    )

    # Light is turned on via request_changes
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "LIGHT1"
    assert args[1][STATUS_ATTR] == "ON"


@pytest.mark.parametrize(
    "effect_code",
    [
        "PARTY",
        "CARIB",
        "SSET",
        "ROMAN",
        "AMERCA",
        "ROYAL",
        "WHITER",
        "REDR",
        "BLUER",
        "GREENR",
        "MAGNTAR",
    ],
)
async def test_light_state_update_with_each_effect(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    effect_code: str,
) -> None:
    """Test light state updates correctly for each effect code."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Simulate IntelliCenter update with this effect
    updates = {
        "LIGHT1": {
            STATUS_ATTR: "ON",
            "USE": effect_code,
        }
    }

    # Verify entity recognizes the update
    assert light.isUpdated(updates) is True

    # Apply update
    pool_object_light.update(updates["LIGHT1"])

    # Verify effect is correctly reported
    assert light.is_on is True
    assert light.effect == LIGHT_EFFECTS[effect_code]


async def test_light_invalid_effect_raises(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """An unknown effect raises a clean error and the light is NOT turned on.

    Previously the bad effect was silently dropped and the light still turned
    on; now the service call fails visibly before any state is changed.
    """
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass  # Required for async_create_task

    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(**{ATTR_EFFECT: "Invalid Effect"})
    await hass.async_block_till_done()

    # Neither the effect nor the on-command reached the controller, and no
    # optimistic state was rendered.
    mock_coordinator.controller.set_light_effect.assert_not_called()
    mock_coordinator.controller.request_changes.assert_not_called()
    assert light._optimistic_state is None


async def test_light_unknown_effect_code_returns_none(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that unknown effect code returns None for effect property."""
    # Set light to use an unknown effect code
    pool_object_light.update({"USE": "UNKNOWN"})

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    # Effect should be None for unknown codes
    assert light.effect is None


async def test_light_effect_command_failure_raises_and_stays_off(
    hass: HomeAssistant,
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Regression: a failed effect write surfaces and the light is not shown on.

    set_light_effect used to be guarded only by `except ValueError`, so a
    connection error escaped as a raw traceback AFTER the optimistic on-state
    was rendered - leaving the UI showing ON for a light that never received
    a command.
    """
    from pyintellicenter import ICConnectionError

    mock_coordinator.controller.set_light_effect.side_effect = ICConnectionError(
        "Not connected"
    )

    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)
    light.hass = hass

    with pytest.raises(HomeAssistantError) as err:
        await light.async_turn_on(**{ATTR_EFFECT: "Party Mode"})
    await hass.async_block_till_done()

    mock_coordinator.controller.set_light_effect.assert_awaited_once_with(
        "LIGHT1", "PARTY"
    )
    assert err.value.translation_key == "command_failed"
    # The on-command never fired and no optimistic state survives.
    mock_coordinator.controller.request_changes.assert_not_called()
    assert light._optimistic_state is None


# -------------------------------------------------------------------------------------
# Brightness control
# -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_limit", "expected_brightness"),
    [("50", 128), (75, 191), ("100", 255), ("0", 0)],
)
async def test_dimmer_reports_limit_as_brightness(
    mock_coordinator: MagicMock,
    raw_limit: object,
    expected_brightness: int,
) -> None:
    """DIMMER LIMIT percentages map back to Home Assistant brightness."""
    dimmer = PoolObject(
        "DIMMER1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "DIMMER",
            "SNAME": "Patio Dimmer",
            "STATUS": "ON",
            LIMIT_ATTR: raw_limit,
        },
    )

    light = PoolLight(mock_coordinator, dimmer)

    assert light.color_mode is ColorMode.BRIGHTNESS
    assert light.supported_color_modes == {ColorMode.BRIGHTNESS}
    assert light.brightness == expected_brightness


@pytest.mark.parametrize("raw_limit", [None, "LIMIT", "", "101", "-1", True, object()])
async def test_dimmer_missing_or_malformed_limit_is_unknown(
    mock_coordinator: MagicMock,
    raw_limit: object,
) -> None:
    """Missing, placeholder, and out-of-range LIMIT values report unknown."""
    dimmer = PoolObject(
        "DIMMER1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "DIMMER",
            "SNAME": "Patio Dimmer",
            "STATUS": "ON",
            LIMIT_ATTR: raw_limit,
        },
    )

    assert PoolLight(mock_coordinator, dimmer).brightness is None


@pytest.mark.parametrize(
    ("brightness", "expected_limit"),
    [(0, 50), (128, 50), (160, 75), (200, 75), (224, 100), (255, 100)],
)
async def test_dimmer_brightness_write_uses_nearest_panel_level(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    brightness: int,
    expected_limit: int,
) -> None:
    """DIMMER writes select the nearest supported 50/75/100 percent level."""
    dimmer = PoolObject(
        "DIMMER1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "DIMMER",
            "SNAME": "Patio Dimmer",
            "STATUS": "OFF",
            LIMIT_ATTR: "100",
        },
    )
    light = PoolLight(mock_coordinator, dimmer)
    light.hass = hass

    await light.async_turn_on(**{ATTR_BRIGHTNESS: brightness})
    await hass.async_block_till_done()

    mock_coordinator.controller.request_changes.assert_called_once_with(
        "DIMMER1", {LIMIT_ATTR: str(expected_limit), STATUS_ATTR: "ON"}
    )


@pytest.mark.parametrize("subtype", ["LIGHT", "INTELLI", "GLOW", "GLOWT", "MAGIC2"])
async def test_non_dimmable_subtypes_remain_onoff(
    mock_coordinator: MagicMock,
    subtype: str,
) -> None:
    """Only verified dimmable subtypes advertise brightness control."""
    pool_object = PoolObject(
        "LIGHTX",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": subtype,
            "SNAME": "Pool Light",
            "STATUS": "ON",
            LIMIT_ATTR: "50",
        },
    )

    light = PoolLight(
        mock_coordinator,
        pool_object,
        LIGHT_EFFECTS if subtype in {"INTELLI", "GLOW", "MAGIC2"} else None,
    )

    assert light.color_mode is ColorMode.ONOFF
    assert light.supported_color_modes == {ColorMode.ONOFF}
    assert light.brightness is None


async def test_limit_update_refreshes_dimmer(
    mock_coordinator: MagicMock,
) -> None:
    """LIMIT push updates refresh dimmer brightness state."""
    dimmer = PoolObject(
        "DIMMER1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "DIMMER",
            "SNAME": "Patio Dimmer",
            "STATUS": "ON",
            LIMIT_ATTR: "50",
        },
    )

    light = PoolLight(mock_coordinator, dimmer)

    assert light.isUpdated({"DIMMER1": {LIMIT_ATTR: "75"}}) is True


@pytest.mark.parametrize(
    ("method_name", "act_value"),
    [
        ("async_capture", "CAPTURE"),
        ("async_thumper", "THUMPER"),
        ("async_hold", "HOLD"),
        ("async_recall", "RECALL"),
    ],
)
async def test_magicstream_entity_services_write_act(
    mock_coordinator: MagicMock,
    method_name: str,
    act_value: str,
) -> None:
    """MagicStream entity services send their momentary command through ACT."""
    magicstream = PoolObject(
        "MAGIC1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "MAGIC2",
            "SNAME": "MagicStream",
            "STATUS": "ON",
            "USE": "WHITER",
        },
    )
    light = PoolLight(mock_coordinator, magicstream, LIGHT_EFFECTS)

    await getattr(light, method_name)()

    mock_coordinator.controller.request_changes.assert_awaited_once_with(
        "MAGIC1", {"ACT": act_value}
    )


async def test_magicstream_command_failure_is_translated(
    mock_coordinator: MagicMock,
) -> None:
    """MagicStream protocol failures surface as translated service errors."""
    from pyintellicenter import ICConnectionError

    magicstream = PoolObject(
        "MAGIC1",
        {
            "OBJTYP": CIRCUIT_TYPE,
            "SUBTYP": "MAGIC2",
            "SNAME": "MagicStream",
            "STATUS": "ON",
        },
    )
    mock_coordinator.controller.request_changes.side_effect = ICConnectionError(
        "offline"
    )
    light = PoolLight(mock_coordinator, magicstream, LIGHT_EFFECTS)

    with pytest.raises(HomeAssistantError) as err:
        await light.async_capture()

    assert err.value.translation_domain == "intellicenter"
    assert err.value.translation_key == "command_failed"


async def test_magicstream_service_refuses_other_light_subtypes(
    pool_object_light: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """MagicStream-only services fail cleanly for an IntelliBrite entity."""
    light = PoolLight(mock_coordinator, pool_object_light, LIGHT_EFFECTS)

    with pytest.raises(HomeAssistantError) as err:
        await light.async_thumper()

    assert err.value.translation_key == "magicstream_command_unsupported"
    mock_coordinator.controller.request_changes.assert_not_awaited()


async def test_color_sync_service_metadata_has_only_an_entity_target() -> None:
    """Color Sync metadata exposes no arguments beyond the light target."""
    services = yaml.safe_load(_SERVICES_YAML.read_text(encoding="utf-8"))

    assert set(services) == {"capture", "thumper", "hold", "recall", "color_sync"}
    assert services["color_sync"] == {
        "target": {
            "entity": {
                "integration": "intellicenter",
                "domain": "light",
            }
        }
    }


async def test_color_sync_calls_dedicated_library_helper_without_state_mutation(
    complete_group_light: PoolLight,
    mock_coordinator: MagicMock,
) -> None:
    """The service awaits only the scoped helper and invents no entity state."""
    sync = AsyncMock(return_value={"command": "SetParamList"})
    mock_coordinator.controller.run_light_group_sync = sync
    before = _color_sync_state(complete_group_light)

    await complete_group_light.async_color_sync()

    sync.assert_awaited_once_with("GROUP")
    mock_coordinator.controller.request_changes.assert_not_awaited()
    assert _color_sync_state(complete_group_light) == before


@pytest.mark.parametrize("subtype", ("LIGHT", "INTELLI", "MAGIC2", "CIRCGRP"))
async def test_color_sync_rejects_ordinary_non_group_entities_before_library_call(
    mock_coordinator: MagicMock,
    subtype: str,
) -> None:
    """Ordinary light-like entities cannot invoke the group writer."""
    sync = AsyncMock()
    mock_coordinator.controller.run_light_group_sync = sync
    _set_firmware(mock_coordinator, "1.064")
    light = PoolLight(
        mock_coordinator,
        PoolObject(
            "LIGHT",
            {
                "OBJTYP": CIRCUIT_TYPE,
                "SUBTYP": subtype,
                "SNAME": subtype,
                "STATUS": "OFF",
                "USE": "WHITER",
            },
        ),
        LIGHT_EFFECTS,
    )

    await _assert_color_sync_error(light, "light_group_command_unsupported")

    sync.assert_not_awaited()


@pytest.mark.parametrize(
    ("member_refs", "child_shapes"),
    [
        ((), {}),
        (("GLOW1",), {"GLOW1": (CIRCUIT_TYPE, "GLOW")}),
        (
            ("GLOW1", "GLOW2", "GLOW3"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "GLOW2": (CIRCUIT_TYPE, "GLOW"),
                "GLOW3": (CIRCUIT_TYPE, "GLOW"),
            },
        ),
        (("MISSING1", "MISSING2"), {}),
        (("GLOW1", "GLOW1"), {"GLOW1": (CIRCUIT_TYPE, "GLOW")}),
        (
            ("GLOW1", "PLAIN"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "PLAIN": (CIRCUIT_TYPE, "LIGHT"),
            },
        ),
        (
            ("LIGHT1", "LIGHT2"),
            {
                "LIGHT1": (CIRCUIT_TYPE, "INTELLI"),
                "LIGHT2": (CIRCUIT_TYPE, "INTELLI"),
            },
        ),
        (
            ("LIGHT1", "LIGHT2"),
            {
                "LIGHT1": (CIRCUIT_TYPE, "MAGIC2"),
                "LIGHT2": (CIRCUIT_TYPE, "MAGIC2"),
            },
        ),
        (
            ("GLOW1", "NOT_A_CIRCUIT"),
            {
                "GLOW1": (CIRCUIT_TYPE, "GLOW"),
                "NOT_A_CIRCUIT": (BODY_TYPE, "GLOW"),
            },
        ),
    ],
    ids=(
        "zero",
        "one",
        "three",
        "missing",
        "duplicate",
        "mixed",
        "intellibrite",
        "magicstream",
        "non-circuit-glow",
    ),
)
async def test_color_sync_rejects_unsupported_group_topologies_before_library_call(
    mock_coordinator: MagicMock,
    member_refs: tuple[str, ...],
    child_shapes: dict[str, tuple[str, str]],
) -> None:
    """Every topology outside the evidence-backed pair is rejected locally."""
    sync = AsyncMock()
    mock_coordinator.controller.run_light_group_sync = sync
    light = _group_light_for_model(
        mock_coordinator,
        _make_light_group_model(member_refs, child_shapes),
    )

    await _assert_color_sync_error(light, "light_group_command_unsupported")

    sync.assert_not_awaited()


@pytest.mark.parametrize(
    "firmware",
    (None, "1.063", "1.065", "IC: 1.064", "1.064 ", "1.064-build7"),
)
async def test_color_sync_rejects_non_exact_firmware_before_library_call(
    complete_light_group_model: PoolModel,
    mock_coordinator: MagicMock,
    firmware: str | None,
) -> None:
    """Semantic version lookalikes never widen the service's raw token gate."""
    sync = AsyncMock()
    mock_coordinator.controller.run_light_group_sync = sync
    light = _group_light_for_model(
        mock_coordinator, complete_light_group_model, firmware
    )

    await _assert_color_sync_error(light, "light_group_command_unsupported")

    sync.assert_not_awaited()


async def test_color_sync_maps_library_value_error_to_unsupported(
    complete_group_light: PoolLight,
    mock_coordinator: MagicMock,
) -> None:
    """A topology race caught by the library remains an unsupported outcome."""
    sync = AsyncMock(side_effect=ValueError("topology changed"))
    mock_coordinator.controller.run_light_group_sync = sync
    before = _color_sync_state(complete_group_light)

    await _assert_color_sync_error(
        complete_group_light, "light_group_command_unsupported"
    )

    sync.assert_awaited_once_with("GROUP")
    assert _color_sync_state(complete_group_light) == before


async def test_color_sync_maps_ordinary_library_error_to_failed(
    complete_group_light: PoolLight,
    mock_coordinator: MagicMock,
) -> None:
    """An ordinary pre-dispatch library failure reports definite failure."""
    sync = AsyncMock(side_effect=ICError("pre-dispatch failure"))
    mock_coordinator.controller.run_light_group_sync = sync
    before = _color_sync_state(complete_group_light)

    await _assert_color_sync_error(complete_group_light, "light_group_command_failed")

    sync.assert_awaited_once_with("GROUP")
    assert _color_sync_state(complete_group_light) == before


@pytest.mark.parametrize(
    (
        "response_received",
        "acknowledged",
        "onset_seen",
        "translation_key",
    ),
    [
        (True, False, False, "light_group_command_failed"),
        (False, False, False, "light_group_command_uncertain"),
        (False, True, False, "light_group_command_incomplete"),
        (False, False, True, "light_group_command_incomplete"),
    ],
    ids=("explicit-rejection", "no-response", "acknowledged", "onset"),
)
async def test_color_sync_maps_lifecycle_certainty_with_started_precedence(
    complete_group_light: PoolLight,
    mock_coordinator: MagicMock,
    response_received: bool,
    acknowledged: bool,
    onset_seen: bool,
    translation_key: str,
) -> None:
    """Acknowledgement/onset take precedence over rejection or uncertainty."""
    library_error = ICLightGroupError(
        "lifecycle failed",
        phase="acknowledgement",
        response_received=response_received,
        acknowledged=acknowledged,
        onset_seen=onset_seen,
    )
    sync = AsyncMock(side_effect=library_error)
    mock_coordinator.controller.run_light_group_sync = sync
    before = _color_sync_state(complete_group_light)

    raised = await _assert_color_sync_error(complete_group_light, translation_key)

    sync.assert_awaited_once_with("GROUP")
    assert raised.__cause__ is library_error
    assert _color_sync_state(complete_group_light) == before


async def test_only_color_sync_group_action_is_exposed() -> None:
    """Set, Swim, and member-position actions remain outside integration scope."""
    services = yaml.safe_load(_SERVICES_YAML.read_text(encoding="utf-8"))
    assert {"color_set", "color_swim", "member_position"}.isdisjoint(services)
    assert not hasattr(PoolLight, "async_color_set")
    assert not hasattr(PoolLight, "async_color_swim")
    assert not any("member" in name and "position" in name for name in dir(PoolLight))
