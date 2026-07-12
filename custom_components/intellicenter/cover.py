"""Pentair Intellicenter covers.

This module provides cover entities for pool covers and other motorized covers.
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
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# -------------------------------------------------------------------------------------


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolCover]:
    """Build cover entities for the given candidate pool objects."""
    covers: list[PoolCover] = []
    for pool_obj in candidates:
        if (
            pool_obj.objtype == EXTINSTR_TYPE
            and pool_obj.subtype == "COVER"
            and pool_obj.status == STATUS_ON
        ):
            covers.append(PoolCover(coordinator, pool_obj))
    return covers


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
        """Return whether the panel is connected and the cover is enabled."""
        return super().available and self._pool_object.status == STATUS_ON

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, or None if the state is unknown."""
        raw_position = self._pool_object[POSIT_ATTR]
        if raw_position is None:
            # IntelliCenter 1.064 and other older firmware omit POSIT entirely
            # (GetParamList echoes the key back unset). Preserve the legacy
            # STATUS-derived position instead of reporting a fixed bogus state.
            raw_position = self._pool_object[STATUS_ATTR]

        # Without both attributes the position cannot be derived; report unknown
        # rather than fabricating "closed" (safety automations may key off this).
        raw_normal = self._pool_object[NORMAL_ATTR]
        if raw_position is None or raw_normal is None:
            return None
        # The cover is closed if:
        # - position is ON and NORMAL is ON (cover is normally closed)
        # - position is OFF and NORMAL is OFF (cover is normally open)
        return bool((raw_position == STATUS_ON) == (raw_normal == STATUS_ON))

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # To open the cover, set its position opposite of NORMAL.
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        position_attr = (
            POSIT_ATTR if self._pool_object[POSIT_ATTR] is not None else STATUS_ATTR
        )
        self.request_changes({position_attr: STATUS_OFF if normal else STATUS_ON})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # To close the cover, set its position to the same value as NORMAL.
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        position_attr = (
            POSIT_ATTR if self._pool_object[POSIT_ATTR] is not None else STATUS_ATTR
        )
        self.request_changes({position_attr: STATUS_ON if normal else STATUS_OFF})

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""
        return self._check_attributes_updated(
            updates, STATUS_ATTR, POSIT_ATTR, NORMAL_ATTR
        )
