"""Pentair Intellicenter switches."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_ATTR,
    HTMODE_ATTR,
    SUPER_ATTR,
    SYSTEM_TYPE,
    VACFLO_ATTR,
    VOL_ATTR,
    ModelController,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Load a Pentair switch based on a config entry."""
    controller: ModelController = entry.runtime_data.controller

    switches = []

    obj: PoolObject
    for obj in controller.model.objectList:
        if obj.objtype == BODY_TYPE:
            switches.append(PoolBody(entry, controller, obj))
        elif (
            obj.objtype == CHEM_TYPE
            and obj.subtype == "ICHLOR"
            and SUPER_ATTR in obj.attributes
        ):
            switches.append(
                PoolCircuit(
                    entry,
                    controller,
                    obj,
                    attribute_key=SUPER_ATTR,
                    name="+ Superchlorinate",
                    icon="mdi:alpha-s-box-outline",
                )
            )
        elif (
            obj.objtype == CIRCUIT_TYPE
            and not (obj.isALight or obj.isALightShow)
            and obj.isFeatured
        ):
            switches.append(
                PoolCircuit(entry, controller, obj, icon="mdi:alpha-f-box-outline")
            )
        elif obj.objtype == CIRCUIT_TYPE and obj.subtype == "CIRCGRP":
            switches.append(
                PoolCircuit(entry, controller, obj, icon="mdi:alpha-g-box-outline")
            )
        elif obj.objtype == SYSTEM_TYPE:
            switches.append(
                PoolCircuit(
                    entry,
                    controller,
                    obj,
                    VACFLO_ATTR,
                    name="Vacation mode",
                    icon="mdi:palm-tree",
                    enabled_by_default=False,
                    entity_category=EntityCategory.CONFIG,
                )
            )

    async_add_entities(switches)


# -------------------------------------------------------------------------------------


class PoolCircuit(PoolEntity, SwitchEntity):
    """Representation of an standard pool circuit."""

    @property
    def is_on(self) -> bool:
        """Return the state of the circuit."""
        return self._poolObject[self._attribute_key] == self._poolObject.onStatus

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        self.requestChanges({self._attribute_key: self._poolObject.offStatus})

    def turn_on(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        self.requestChanges({self._attribute_key: self._poolObject.onStatus})


# -------------------------------------------------------------------------------------


class PoolBody(PoolCircuit):
    """Representation of a body of water."""

    def __init__(self, entry: ConfigEntry, controller, poolObject):
        """Initialize a Pool body from the underlying circuit."""
        super().__init__(entry, controller, poolObject)
        self._extra_state_attributes = [VOL_ATTR, HEATER_ATTR, HTMODE_ATTR]
        self._attr_icon = "mdi:pool"
