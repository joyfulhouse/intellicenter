"""Pentair Intellicenter covers.

This module provides cover entities for pool covers and other motorized covers.

Attribute semantics (confirmed by capturing the panel web UI's own
SETPARAMLIST traffic — see joyfulhouse/pyintellicenter#44):

- ``STATUS`` is the "Cover Enabled" flag from Settings > Covers. It is
  configuration, never position.
- ``POSIT`` is the physical cover position. Older firmware (e.g. IC 1.064,
  verified live) omits POSIT entirely; on such panels there is NO live
  position signal, so position is unknown and position commands are refused
  rather than fabricated from STATUS (writing STATUS would toggle the
  cover's enabled flag in the panel's settings, not move the cover).
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    EXTINSTR_TYPE,
    NORMAL_ATTR,
    POSIT_ATTR,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity, async_setup_pool_entities
from .const import DOMAIN
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# -------------------------------------------------------------------------------------


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolCover]:
    """Build cover entities for the given candidate pool objects.

    Entities are created for every EXTINSTR/COVER object — including covers
    disabled in Settings > Covers — and gated through ``available`` instead.
    Creating them all keeps existing users' entity registry stable and means
    a cover enabled after setup comes alive on the next push (STATUS updates
    an existing object, which would never re-trigger entity creation).
    """
    return [
        PoolCover(coordinator, pool_obj)
        for pool_obj in candidates
        if pool_obj.objtype == EXTINSTR_TYPE and pool_obj.subtype == "COVER"
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool cover entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


# -------------------------------------------------------------------------------------


class PoolCover(PoolEntity, CoverEntity):
    """Representation of a Pentair pool cover."""

    _attr_device_class = CoverDeviceClass.SHADE

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a pool cover entity.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this cover represents
        """
        super().__init__(
            coordinator,
            pool_object,
            extra_state_attributes=[NORMAL_ATTR],
            icon="mdi:arrow-expand-horizontal",
        )
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        )

    @property
    def available(self) -> bool:
        """Return whether the panel is connected and the cover is enabled.

        STATUS is the Settings > Covers enabled flag; a disabled cover is a
        configuration placeholder, not controllable equipment.
        """
        return super().available and self._pool_object.status == STATUS_ON

    def _valid_position_state(self) -> tuple[bool, bool] | None:
        """Return (posit_is_on, normal_is_on), or None if either is invalid.

        Position comes exclusively from POSIT. Older firmware (e.g. IC 1.064)
        omits POSIT, leaving no live position signal. NORMAL is equally
        load-bearing: it decides the open/close *direction*, so a missing or
        malformed value must invalidate the state rather than silently read
        as OFF (which would reverse commands on a partially synced cover).
        """
        raw_position = self._pool_object[POSIT_ATTR]
        raw_normal = self._pool_object[NORMAL_ATTR]
        valid = (STATUS_ON, STATUS_OFF)
        if raw_position not in valid or raw_normal not in valid:
            return None
        return (raw_position == STATUS_ON, raw_normal == STATUS_ON)

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, or None if the state is unknown.

        Reports unknown rather than fabricating a state from the STATUS
        enabled flag or malformed values (safety automations may key off
        this).
        """
        state = self._valid_position_state()
        if state is None:
            return None
        posit_on, normal_on = state
        # The cover is closed if:
        # - POSIT is ON and NORMAL is ON (cover is normally closed)
        # - POSIT is OFF and NORMAL is OFF (cover is normally open)
        return posit_on == normal_on

    def _require_actuation_support(self) -> tuple[bool, bool]:
        """Return validated (posit_is_on, normal_is_on) or raise.

        Without a valid POSIT there is no position channel to write (falling
        back to STATUS would flip the cover's enabled flag in Settings >
        Covers instead of moving it), and without a valid NORMAL the command
        direction would be guessed.
        """
        state = self._valid_position_state()
        if state is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cover_position_unsupported",
            )
        return state

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _, normal_on = self._require_actuation_support()
        # To open the cover, set its position opposite of NORMAL.
        self.request_changes({POSIT_ATTR: STATUS_OFF if normal_on else STATUS_ON})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _, normal_on = self._require_actuation_support()
        # To close the cover, set its position to the same value as NORMAL.
        self.request_changes({POSIT_ATTR: STATUS_ON if normal_on else STATUS_OFF})

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""
        return self._check_attributes_updated(
            updates, STATUS_ATTR, POSIT_ATTR, NORMAL_ATTR
        )
