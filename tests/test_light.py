"""Test the Pentair IntelliCenter light platform."""

from unittest.mock import MagicMock, call, patch

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    CIRCGRP_TYPE,
    CIRCUIT_TYPE,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.const import LIMIT_ATTR
from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
from custom_components.intellicenter.light import PoolLight

pytestmark = pytest.mark.asyncio


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


async def test_true_color_circuit_group_creates_enabled_light_entity(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """A true CIRCGRP containing a color light creates a group light."""
    group = pool_model.add_object(
        "LIGHT_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "All Pool Lights",
            "STATUS": "OFF",
            "USE": "WHITER",
            "CIRCUIT": "LIGHT1 LIGHT2",
        },
    )
    assert group is not None
    mock_coordinator.model = pool_model
    mock_entry = MagicMock()
    mock_entry.runtime_data = mock_coordinator
    entities_added: list[PoolLight] = []

    from custom_components.intellicenter.light import async_setup_entry

    with patch(
        "custom_components.intellicenter.light.entity_platform.async_get_current_platform"
    ):
        await async_setup_entry(hass, mock_entry, entities_added.extend)

    group_lights = [
        entity
        for entity in entities_added
        if entity._pool_object.objnam == "LIGHT_GROUP"
    ]
    assert len(group_lights) == 1
    assert group_lights[0].entity_registry_enabled_default is True
    assert group_lights[0].effect_list is not None
    assert {"Sync", "Swim", "Set color"}.issubset(group_lights[0].effect_list)


async def test_plain_true_circuit_group_does_not_create_light(
    hass: HomeAssistant,
    pool_model: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """A true CIRCGRP without color lights is left to the switch platform."""
    group = pool_model.add_object(
        "WATER_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "Water Features",
            "STATUS": "OFF",
            "CIRCUIT": "CIRC01 CIRC02",
        },
    )
    assert group is not None
    mock_coordinator.model = pool_model
    mock_entry = MagicMock()
    mock_entry.runtime_data = mock_coordinator
    entities_added: list[PoolLight] = []

    from custom_components.intellicenter.light import async_setup_entry

    with patch(
        "custom_components.intellicenter.light.entity_platform.async_get_current_platform"
    ):
        await async_setup_entry(hass, mock_entry, entities_added.extend)

    assert all(entity._pool_object.objnam != "WATER_GROUP" for entity in entities_added)


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

    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(**{ATTR_EFFECT: "Party"})
    await hass.async_block_till_done()

    # The on-command never fired and no optimistic state survives.
    mock_coordinator.controller.request_changes.assert_not_called()
    assert light._optimistic_state is None


# -------------------------------------------------------------------------------------
# Brightness and group control
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


def make_group_light(mock_coordinator: MagicMock, status: object = "OFF") -> PoolLight:
    """Create a color circuit-group light for focused unit tests."""
    group = PoolObject(
        "LIGHT_GROUP",
        {
            "OBJTYP": CIRCGRP_TYPE,
            "SNAME": "All Pool Lights",
            "STATUS": status,
            "USE": "WHITER",
            "CIRCUIT": "LIGHT1 LIGHT2",
        },
    )
    mock_coordinator.controller.get_circuits_in_group.side_effect = None
    mock_coordinator.controller.get_circuits_in_group.return_value = [
        mock_coordinator.model["LIGHT1"],
        mock_coordinator.model["LIGHT2"],
    ]
    from custom_components.intellicenter.light import PoolLightGroup

    return PoolLightGroup(mock_coordinator, group)


@pytest.mark.parametrize(
    ("effect_name", "effect_code"),
    [("Sync", "SYNC"), ("Swim", "SWIM"), ("Set color", "SET")],
)
async def test_group_light_sequence_effect_writes_act_and_turns_on_members(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
    effect_name: str,
    effect_code: str,
) -> None:
    """Momentary light-group operations write ACT then atomically turn on members."""
    light = make_group_light(mock_coordinator)
    light.hass = hass

    await light.async_turn_on(**{ATTR_EFFECT: effect_name})

    assert mock_coordinator.controller.request_changes.await_args == call(
        "LIGHT_GROUP", {"ACT": effect_code}
    )
    mock_coordinator.controller.set_multiple_circuit_states.assert_awaited_once_with(
        ["LIGHT1", "LIGHT2"], True
    )


async def test_group_light_standard_effect_uses_typed_helper(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """Standard colors and shows retain the pyintellicenter helper path."""
    light = make_group_light(mock_coordinator)
    light.hass = hass

    await light.async_turn_on(**{ATTR_EFFECT: "Party Mode"})

    mock_coordinator.controller.set_light_effect.assert_awaited_once_with(
        "LIGHT_GROUP", "PARTY"
    )
    mock_coordinator.controller.set_multiple_circuit_states.assert_awaited_once_with(
        ["LIGHT1", "LIGHT2"], True
    )


@pytest.mark.parametrize("status", [None, "", "READY", 1])
async def test_group_light_malformed_status_is_unknown(
    mock_coordinator: MagicMock,
    status: object,
) -> None:
    """A group without a valid ON/OFF status does not fabricate an off state."""
    assert make_group_light(mock_coordinator, status).is_on is None


async def test_group_light_without_members_refuses_control(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    mock_write_ha_state: MagicMock,
) -> None:
    """A partially synchronized group cannot silently issue an empty batch."""
    light = make_group_light(mock_coordinator)
    light.hass = hass
    mock_coordinator.controller.get_circuits_in_group.return_value = []
    mock_coordinator.controller.get_circuits_in_group.side_effect = None

    with pytest.raises(HomeAssistantError) as err:
        await light.async_turn_on(**{ATTR_EFFECT: "Sync"})

    assert err.value.translation_key == "circuit_group_members_missing"
    mock_coordinator.controller.request_changes.assert_not_awaited()
    mock_coordinator.controller.set_multiple_circuit_states.assert_not_awaited()


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
