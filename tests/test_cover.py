"""Test the Pentair IntelliCenter cover platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyintellicenter import (
    EXTINSTR_TYPE,
    NORMAL_ATTR,
    POSIT_ATTR,
    STATUS_ATTR,
    PoolModel,
    PoolObject,
)
import pytest

from custom_components.intellicenter.const import DOMAIN
from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP
from custom_components.intellicenter.cover import PoolCover, _sync_disabled_covers

pytestmark = pytest.mark.asyncio

# STATUS is the "Cover Enabled" flag in the panel's Settings > Covers page.
# POSIT is the cover's physical position. Confirmed by capturing the panel's
# own SETPARAMLIST traffic: enabling a cover in the UI writes STATUS and
# never touches POSIT.


@pytest.fixture
def pool_model_with_cover() -> PoolModel:
    """Return a PoolModel with an enabled cover."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "COVER1",
                "params": {
                    "OBJTYP": EXTINSTR_TYPE,
                    "SUBTYP": "COVER",
                    "SNAME": "Pool Cover",
                    "STATUS": "ON",  # enabled
                    "POSIT": "OFF",
                    "NORMAL": "ON",  # Normally closed
                },
            },
        ]
    )
    return model


@pytest.fixture
def pool_object_cover_normally_closed() -> PoolObject:
    """Return a PoolObject representing an enabled, normally-closed cover."""
    return PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "ON",  # enabled
            "POSIT": "OFF",
            "NORMAL": "ON",  # Normally closed
        },
    )


@pytest.fixture
def pool_object_cover_normally_open() -> PoolObject:
    """Return a PoolObject representing an enabled, normally-open cover."""
    return PoolObject(
        "COVER2",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Spa Cover",
            "STATUS": "ON",  # enabled
            "POSIT": "OFF",
            "NORMAL": "OFF",  # Normally open
        },
    )


async def test_cover_setup_creates_entities(
    hass: HomeAssistant,
    pool_model_with_cover: PoolModel,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover platform creates entities for enabled covers."""
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
    """Test cover platform does not create an entity for a panel-disabled cover."""
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "COVER1",
                "params": {
                    "OBJTYP": EXTINSTR_TYPE,
                    "SUBTYP": "COVER",
                    "SNAME": "Pool Cover",
                    "STATUS": "OFF",  # disabled in Settings > Covers
                    "POSIT": "OFF",
                    "NORMAL": "ON",
                },
            },
        ]
    )
    mock_coordinator.model = model

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.cover import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    assert entities_added == []


async def test_cover_setup_includes_cover_when_status_unset(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A cover with no STATUS value yet (e.g. before backfill) is still created.

    Only a confirmed STATUS=OFF should hide the entity - defaulting to
    "hidden" on ambiguous data would silently drop entities on a timing
    hiccup rather than a real panel setting.
    """
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "COVER1",
                "params": {
                    "OBJTYP": EXTINSTR_TYPE,
                    "SUBTYP": "COVER",
                    "SNAME": "Pool Cover",
                },
            },
        ]
    )
    mock_coordinator.model = model

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.cover import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)

    assert len(entities_added) == 1


async def test_cover_live_enable_creates_entity_without_reload(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A cover enabled on the panel after setup gets its entity live.

    async_setup_pool_entities's dynamic listener only reacts to genuinely new
    pool objects, not an attribute change on one it already knows about, so
    this must come from cover.py's own push-update listener instead of
    requiring an integration reload.
    """
    model = PoolModel(DEFAULT_ATTRIBUTES_MAP)
    model.add_objects(
        [
            {
                "objnam": "COVER1",
                "params": {
                    "OBJTYP": EXTINSTR_TYPE,
                    "SUBTYP": "COVER",
                    "SNAME": "Pool Cover",
                    "STATUS": "OFF",  # starts disabled
                    "POSIT": "OFF",
                    "NORMAL": "ON",
                },
            },
        ]
    )
    mock_coordinator.model = model
    mock_coordinator.controller.get_covers = MagicMock(return_value=[model["COVER1"]])

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    entities_added = []

    def capture_entities(entities):
        entities_added.extend(entities)

    from custom_components.intellicenter.cover import async_setup_entry

    await async_setup_entry(hass, mock_entry, capture_entities)
    assert entities_added == []  # disabled at setup - nothing created yet

    # Panel enables the cover; simulate the coordinator's push-update fan-out.
    model["COVER1"].update({STATUS_ATTR: "ON"})
    live_listener = mock_coordinator.async_add_listener.call_args[0][0]
    live_listener()

    assert len(entities_added) == 1
    assert entities_added[0]._pool_object.objnam == "COVER1"

    # A second call with no further change must not add a duplicate.
    live_listener()
    assert len(entities_added) == 1


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


async def test_cover_normally_closed_is_closed_when_posit_off(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-closed cover is open when POSIT=OFF."""

    # POSIT=OFF, NORMAL=ON (normally closed)
    # Cover is closed when POSIT == NORMAL (both ON or both OFF)
    # Here: OFF != ON, so cover is OPEN
    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    assert cover.is_closed is False


async def test_cover_normally_closed_is_closed_when_posit_on(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-closed cover is closed when POSIT=ON."""

    # Set POSIT=ON to match NORMAL=ON
    pool_object_cover_normally_closed.update({POSIT_ATTR: "ON"})

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # POSIT=ON, NORMAL=ON, so is_closed is True
    assert cover.is_closed is True


async def test_cover_normally_open_is_closed_when_posit_off(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-open cover is closed when POSIT=OFF."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)

    # POSIT=OFF, NORMAL=OFF, OFF == OFF, so is_closed is True
    assert cover.is_closed is True


async def test_cover_normally_open_is_open_when_posit_on(
    hass: HomeAssistant,
    pool_object_cover_normally_open: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test normally-open cover is open when POSIT=ON."""

    # Set POSIT=ON
    pool_object_cover_normally_open.update({POSIT_ATTR: "ON"})

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_open)

    # POSIT=ON, NORMAL=OFF, ON != OFF, so is_closed is False
    assert cover.is_closed is False


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
    assert POSIT_ATTR in args[1]
    assert args[1][POSIT_ATTR] == "OFF"


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
    assert POSIT_ATTR in args[1]
    assert args[1][POSIT_ATTR] == "ON"


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
    assert POSIT_ATTR in args[1]
    assert args[1][POSIT_ATTR] == "ON"


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
    assert POSIT_ATTR in args[1]
    assert args[1][POSIT_ATTR] == "OFF"


async def test_cover_is_updated_posit(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover isUpdated on position/enabled changes."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Should update on position change
    assert cover.isUpdated({"COVER1": {POSIT_ATTR: "ON"}}) is True

    # Should update on normal change
    assert cover.isUpdated({"COVER1": {NORMAL_ATTR: "OFF"}}) is True

    # Should update on enabled-flag change too (surfaced via extra_state_attributes)
    assert cover.isUpdated({"COVER1": {STATUS_ATTR: "OFF"}}) is True

    # Should update on multiple
    assert cover.isUpdated({"COVER1": {POSIT_ATTR: "ON", NORMAL_ATTR: "OFF"}}) is True


async def test_cover_is_not_updated_other_object(
    hass: HomeAssistant,
    pool_object_cover_normally_closed: PoolObject,
    mock_coordinator: MagicMock,
) -> None:
    """Test cover is not updated by other objects."""

    cover = PoolCover(mock_coordinator, pool_object_cover_normally_closed)

    # Should not update on other object changes
    assert cover.isUpdated({"COVER2": {POSIT_ATTR: "ON"}}) is False


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
    assert STATUS_ATTR in attrs  # Should include the enabled flag
    assert attrs[STATUS_ATTR] == "ON"


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
    because fixtures used the library's all-attributes default map). POSIT
    must be tracked too, or the position attribute never gets backfilled or
    updated in production even though STATUS (enabled) and NORMAL are.
    """
    assert EXTINSTR_TYPE in DEFAULT_ATTRIBUTES_MAP
    assert {STATUS_ATTR, NORMAL_ATTR, POSIT_ATTR} <= DEFAULT_ATTRIBUTES_MAP[
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


# -------------------------------------------------------------------------------------
# Registry sync: disabling/re-enabling entities already registered before a
# cover was disabled (or before this filter existed).
# -------------------------------------------------------------------------------------


def _register_cover_entity(
    hass: HomeAssistant,
    objnam: str,
    *,
    disabled_by: er.RegistryEntryDisabler | None = None,
) -> str:
    """Register a cover entity in the entity registry, as if created previously."""
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        Platform.COVER,
        DOMAIN,
        f"test_entry_{objnam}",
    )
    if disabled_by is not None:
        registry.async_update_entity(entry.entity_id, disabled_by=disabled_by)
    return entry.entity_id


async def test_sync_disabled_covers_disables_registered_entity(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A registered cover the panel now reports disabled gets disabled_by=INTEGRATION."""
    entity_id = _register_cover_entity(hass, "COVER1")

    disabled_cover = PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "OFF",
        },
    )
    mock_coordinator.controller.get_covers = MagicMock(return_value=[disabled_cover])

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    _sync_disabled_covers(hass, mock_entry)

    registry = er.async_get(hass)
    assert (
        registry.entities[entity_id].disabled_by is er.RegistryEntryDisabler.INTEGRATION
    )


async def test_sync_disabled_covers_reenables_when_panel_enables(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A previously integration-disabled cover is re-enabled once the panel enables it."""
    entity_id = _register_cover_entity(
        hass, "COVER1", disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )

    enabled_cover = PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "ON",
        },
    )
    mock_coordinator.controller.get_covers = MagicMock(return_value=[enabled_cover])

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    _sync_disabled_covers(hass, mock_entry)

    registry = er.async_get(hass)
    assert registry.entities[entity_id].disabled_by is None


async def test_sync_disabled_covers_respects_user_disabled(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A cover the user disabled manually is never touched, either direction."""
    entity_id = _register_cover_entity(
        hass, "COVER1", disabled_by=er.RegistryEntryDisabler.USER
    )

    disabled_cover = PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "OFF",
        },
    )
    mock_coordinator.controller.get_covers = MagicMock(return_value=[disabled_cover])

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    _sync_disabled_covers(hass, mock_entry)

    registry = er.async_get(hass)
    assert registry.entities[entity_id].disabled_by is er.RegistryEntryDisabler.USER


async def test_sync_disabled_covers_ignores_unregistered_cover(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
) -> None:
    """A disabled cover with no existing registry entry is simply skipped."""
    disabled_cover = PoolObject(
        "COVER1",
        {
            "OBJTYP": EXTINSTR_TYPE,
            "SUBTYP": "COVER",
            "SNAME": "Pool Cover",
            "STATUS": "OFF",
        },
    )
    mock_coordinator.controller.get_covers = MagicMock(return_value=[disabled_cover])

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.runtime_data = mock_coordinator

    # Should not raise
    _sync_disabled_covers(hass, mock_entry)
