"""Pentair Intellicenter covers."""

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import (
    EXTINSTR_TYPE,
    NORMAL_ATTR,
    STATUS_ATTR,
    ModelController,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Load pool covers based on a config entry."""
    controller: ModelController = hass.data[DOMAIN][entry.entry_id].controller

    covers = []

    obj: PoolObject
    for obj in controller.model.objectList:
        if obj.objtype == EXTINSTR_TYPE and obj.subtype == "COVER":
            covers.append(PoolCover(entry, controller, obj))

    async_add_entities(covers)


# -------------------------------------------------------------------------------------


class PoolCover(PoolEntity, CoverEntity):
    """Representation of a Pentair pool cover."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
    ):
        """Initialize."""
        super().__init__(
            entry,
            controller,
            poolObject,
            extraStateAttributes=[NORMAL_ATTR],
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
        status = self._poolObject[STATUS_ATTR] == "ON"
        normal = self._poolObject[NORMAL_ATTR] == "ON"
        return status == normal

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # To open the cover, we need to set STATUS opposite of NORMAL
        normal = self._poolObject[NORMAL_ATTR] == "ON"
        self.requestChanges({STATUS_ATTR: "OFF" if normal else "ON"})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # To close the cover, we need to set STATUS same as NORMAL
        normal = self._poolObject[NORMAL_ATTR] == "ON"
        self.requestChanges({STATUS_ATTR: "ON" if normal else "OFF"})

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""
        myUpdates = updates.get(self._poolObject.objnam, {})
        return myUpdates and {STATUS_ATTR, NORMAL_ATTR} & myUpdates.keys()
