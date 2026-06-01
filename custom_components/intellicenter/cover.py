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
        if pool_obj.objtype == EXTINSTR_TYPE and pool_obj.subtype == "COVER":
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
    def is_closed(self) -> bool:
        """Return true if cover is closed."""
        # The cover is closed if:
        # - STATUS is ON and NORMAL is ON (cover is normally closed)
        # - STATUS is OFF and NORMAL is OFF (cover is normally open)
        status = self._pool_object[STATUS_ATTR] == STATUS_ON
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        return bool(status == normal)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # To open the cover, we need to set STATUS opposite of NORMAL
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        self.request_changes({STATUS_ATTR: STATUS_OFF if normal else STATUS_ON})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # To close the cover, we need to set STATUS same as NORMAL
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        self.request_changes({STATUS_ATTR: STATUS_ON if normal else STATUS_OFF})

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""
        return self._check_attributes_updated(updates, STATUS_ATTR, NORMAL_ATTR)
