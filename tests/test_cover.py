"""Test the Pentair IntelliCenter cover platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    EXTINSTR_TYPE,
    NORMAL_ATTR,
    POSIT_ATTR,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
from custom_components.intellicenter.cover import PoolCover

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pool_model_with_cover() -> PoolModel:
    """Return a PoolModel with a cover."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "COVER1",
                "params": {
                    "OBJTYP": EXTINSTR_TYPE,
                    "SUBTYP": "COVER",
                    "SNAME": "Pool Cover",
                    "STATUS": "ON",
                    "POSIT": "OFF",
                    "NORMAL": "ON",  # Normally closed
                },
            },
        ]
    )
    return model


@pytest.fixture
def pool_object_cover_normally_closed() -> PoolObject:
    """Return a PoolObject representing a normally-closed cover."""
    return PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "ON",
            "POSIT": "OFF",
            "NORMAL": "ON",  # Normally closed
        },
    )


@pytest.fixture
def pool_object_cover_normally_open() -> PoolObject:
    """Return a PoolObject representing a normally-open cover."""
    return PoolObject(
        "COVER2",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Spa Cover",
            "STATUS": "ON",
            "POSIT": "OFF",
            "NORMAL": "OFF",  # Normally open
        },
    )


async def test_cover_setup_creates_entities(
    hass: HomeAssistant,
    pool_model_with_cover: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover platform creates entities for covers."""
    # Set up the mock coordinator's model
    mock_coordinator.model = pool_model_with_cover

    # Create a mock entry with runtime_data
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.cover import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    # Should create cover entity for COVER1
    assert len(entities_added) == 1
    assert entities_added[0]._pool_object.sname == "Pool Cover"


async def test_cover_setup_skips_disabled_cover(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A STATUS=OFF (disabled) cover still gets an entity, gated unavailable.

    Creating the entity keeps the registry stable and lets a cover enabled
    after setup come alive on the next push (STATUS updates an existing
    object, which never re-triggers entity creation).
    """
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_object(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Disabled Cover",
            "STATUS": "OFF",
            "POSIT": "ON",
            "NORMAL": "ON",
        },
    )
    mock_coordinator.model = model
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator
    entities_added = []

    from custom_components.intellicenter.cover import async_setup_entry

    await async_setup_entry(hass, mock_entry, entities_added.extend)

    assert len(entities_added) == 1
    mock_coordinator.connected = True
    assert entities_added[0].available is False


async def test_cover_entity_properties(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test PoolCover entity properties."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.name == "Pool Cover"
    assert cover.unique_id == "test_entry_COVER1"
    assert cover._attr_icon == "mdi:arrow-expand-horizontal"


async def test_cover_supported_features(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover supported features."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    features = cover.supported_features

    assert features & CoverEntityFeature.OPEN
    assert features & CoverEntityFeature.CLOSE


async def test_cover_normally_closed_is_open_when_position_off(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-closed cover is open when POSIT=OFF."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.is_closed is False


async def test_cover_normally_closed_is_closed_when_position_on(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-closed cover is closed when POSIT=ON."""

    pool_object_cover_normally_closed.update({POSIT_ATTR: "ON"})

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.is_closed is True


async def test_cover_normally_open_is_closed_when_position_off(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-open cover is closed when POSIT=OFF."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)

    assert cover.is_closed is True


async def test_cover_normally_open_is_open_when_position_on(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-open cover is open when POSIT=ON."""

    pool_object_cover_normally_open.update({POSIT_ATTR: "ON"})

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)

    assert cover.is_closed is False


async def test_cover_position_and_enabled_availability_are_independent(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test POSIT drives position while STATUS gates entity availability."""
    mock_coordinator.connected = True
    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.available is True
    assert cover.is_closed is False

    pool_object_cover_normally_closed.update({POSIT_ATTR: "ON"})
    assert cover.is_closed is True

    pool_object_cover_normally_closed.update({STATUS_ATTR: "OFF"})
    assert cover.available is False
    assert cover.is_closed is True

    pool_object_cover_normally_closed.update({STATUS_ATTR: "ON"})
    assert cover.available is True


async def test_cover_position_unknown_without_posit(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """Without POSIT (old firmware) position is unknown — never STATUS-derived.

    STATUS is the Settings > Covers enabled flag (packet-capture confirmed),
    so deriving position from it would fabricate state.
    """
    cover_obj = PoolObject(
        "COVER3",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Legacy Cover",
            "STATUS": "ON",
            "NORMAL": "ON",
        },
    )
    cover = PoolCover(mock_coordinator, cover_obj)

    assert cover.is_closed is None

    cover_obj.update({STATUS_ATTR: "OFF"})
    assert cover.is_closed is None


async def test_cover_open_normally_closed(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test opening a normally-closed cover."""

    mock_coordinator.controller.request_changes = AsyncMock()

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)
    cover.hass = hass  # Required for async_create_task

    await cover.async_open_cover()

    # To open a normally-closed cover (NORMAL=ON), set POSIT opposite = OFF
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "COVER1"
    assert args[1] == {POSIT_ATTR: "OFF"}


async def test_cover_close_normally_closed(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test closing a normally-closed cover."""

    mock_coordinator.controller.request_changes = AsyncMock()

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)
    cover.hass = hass  # Required for async_create_task

    await cover.async_close_cover()

    # To close a normally-closed cover (NORMAL=ON), set POSIT same = ON
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "COVER1"
    assert args[1] == {POSIT_ATTR: "ON"}


async def test_cover_open_normally_open(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test opening a normally-open cover."""

    mock_coordinator.controller.request_changes = AsyncMock()

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)
    cover.hass = hass  # Required for async_create_task

    await cover.async_open_cover()

    # To open a normally-open cover (NORMAL=OFF), set POSIT opposite = ON
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "COVER2"
    assert args[1] == {POSIT_ATTR: "ON"}


async def test_cover_close_normally_open(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test closing a normally-open cover."""

    mock_coordinator.controller.request_changes = AsyncMock()

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)
    cover.hass = hass  # Required for async_create_task

    await cover.async_close_cover()

    # To close a normally-open cover (NORMAL=OFF), set POSIT same = OFF
    mock_coordinator.controller.request_changes.assert_called_once()
    args = mock_coordinator.controller.request_changes.call_args[0]
    assert args[0] == "COVER2"
    assert args[1] == {POSIT_ATTR: "OFF"}


@pytest.mark.parametrize(
    "method_name",
    ["async_open_cover", "async_close_cover"],
)
async def test_cover_commands_refused_without_posit(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    method_name: str,
) -> None:
    """Without POSIT there is no position channel; commands must refuse.

    Falling back to writing STATUS would toggle the cover's enabled flag in
    Settings > Covers instead of moving it.
    """
    cover_obj = PoolObject(
        "COVER3",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Legacy Cover",
            "STATUS": "ON",
            "NORMAL": "ON",
        },
    )
    mock_coordinator.controller.request_changes = AsyncMock()
    cover = PoolCover(mock_coordinator, cover_obj)
    cover.hass = hass

    with pytest.raises(HomeAssistantError) as err:
        await getattr(cover, method_name)()

    assert err.value.translation_domain == "intellicenter"
    assert err.value.translation_key == "cover_position_unsupported"
    # assert_not_called (not assert_not_awaited): if the guard were removed,
    # the call might be scheduled without being awaited yet, and
    # assert_not_awaited would falsely pass.
    mock_coordinator.controller.request_changes.assert_not_called()


@pytest.mark.parametrize(
    ("posit", "normal"),
    [
        ("ON", None),  # NORMAL missing: direction would be guessed
        ("ON", "NORMAL"),  # malformed echo-back value
        ("POSIT", "ON"),  # malformed POSIT echo-back value
    ],
)
async def test_cover_commands_refused_with_invalid_state(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    posit: str | None,
    normal: str | None,
) -> None:
    """Commands are refused unless BOTH POSIT and NORMAL are valid ON/OFF.

    A missing NORMAL must not silently read as OFF — that would reverse the
    open/close direction on a partially synced cover.
    """
    params = {
        "OBJTYP": EXTINSTR_TYPE,
        "SUBTYP": "COVER",
        "SNAME": "Partial Cover",
        "STATUS": "ON",
    }
    if posit is not None:
        params["POSIT"] = posit
    if normal is not None:
        params["NORMAL"] = normal
    cover_obj = PoolObject("COVER4", params)
    mock_coordinator.controller.request_changes = AsyncMock()
    cover = PoolCover(mock_coordinator, cover_obj)
    cover.hass = hass

    assert cover.is_closed is None
    with pytest.raises(HomeAssistantError):
        await cover.async_open_cover()
    mock_coordinator.controller.request_changes.assert_not_called()


async def test_cover_is_updated_status(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover isUpdated on status change."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Should update on status change
    assert cover.isUpdated({"COVER1": {STATUS_ATTR: "ON"}}) is True

    # Should update on position change
    assert cover.isUpdated({"COVER1": {POSIT_ATTR: "ON"}}) is True

    # Should update on normal change
    assert cover.isUpdated({"COVER1": {NORMAL_ATTR: "OFF"}}) is True

    # Should update on both
    assert cover.isUpdated({"COVER1": {STATUS_ATTR: "ON", NORMAL_ATTR: "OFF"}}) is True


async def test_cover_is_not_updated_other_object(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover is not updated by other objects."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Should not update on other object changes
    assert cover.isUpdated({"COVER2": {STATUS_ATTR: "ON"}}) is False


async def test_cover_is_not_updated_unrelated_attribute(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover is not updated by unrelated attributes."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Should not update on unrelated attribute changes
    assert cover.isUpdated({"COVER1": {"UNRELATED": "value"}}) is False


async def test_cover_state_updates(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover state updates from IntelliCenter."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Initial state: POSIT=OFF, NORMAL=ON -> is_closed = False (open)
    assert cover.is_closed is False

    # Simulate update from IntelliCenter
    updates = {"COVER1": {POSIT_ATTR: "ON"}}
    assert cover.isUpdated(updates) is True

    # Apply the update
    pool_object_cover_normally_closed.update(updates["COVER1"])

    # Verify state changed: POSIT=ON, NORMAL=ON -> is_closed = True
    assert cover.is_closed is True


async def test_cover_extra_state_attributes(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover extra state attributes."""

    mock_coordinator.controller.system_info = MagicMock()

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    attrs = cover.extra_state_attributes

    assert "OBJNAM" in attrs
    assert attrs["OBJNAM"] == "COVER1"
    assert NORMAL_ATTR in attrs  # Should include NORMAL attribute
    assert attrs[NORMAL_ATTR] == "ON"


async def test_cover_device_class(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test that covers have the correct device class."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.device_class == CoverDeviceClass.SHADE


async def test_production_attribute_map_admits_covers() -> None:
    """Regression: EXTINSTR must be in the production tracking map.

    PoolModel only admits objtypes present in its attribute map. Without an
    EXTINSTR entry, cover objects were silently dropped on real hardware and
    the platform never created any entities (tests previously passed only
    because fixtures used the library's all-attributes default map).
    """
    assert EXTINSTR_TYPE in DEFAULT_ATTRIBUTES_MAP
    assert {STATUS_ATTR, POSIT_ATTR, NORMAL_ATTR} <= DEFAULT_ATTRIBUTES_MAP[
        EXTINSTR_TYPE
    ]

    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    admitted = model.add_object(
        "COVER9",
        {"OBJTYP": EXTINSTR_TYPE, "SUBTYP": "COVER", "SNAME": "Cover", "STATUS": "ON"},
    )
    assert admitted is not None
    assert model["COVER9"] is not None


async def test_cover_unknown_position_when_attributes_missing(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """is_closed must be None (unknown), not a fabricated 'closed', without data."""
    cover_obj = PoolObject(
        "COVER3",
        {"OBJTYP": EXTINSTR_TYPE, "SUBTYP": "COVER", "SNAME": "Bare Cover"},
    )
    cover = PoolCover(mock_coordinator, cover_obj)

    assert cover.is_closed is None
