"""Pentair Intellicenter binary sensors."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.intellicenter.pyintellicenter.attributes import (
    BODY_ATTR,
    CIRCUIT_TYPE,
    HEATER_TYPE,
)
from custom_components.intellicenter.water_heater import HEATER_ATTR, HTMODE_ATTR

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import STATUS_ATTR, ModelController, PoolObject

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Load pool sensors based on a config entry."""

    controller: ModelController = hass.data[DOMAIN][entry.entry_id].controller

    sensors = []

    obj: PoolObject
    for obj in controller.model.objectList:
        if obj.objtype == CIRCUIT_TYPE and obj.subtype == "FRZ":
            sensors.append(
                PoolBinarySensor(entry, controller, obj, icon="mdi:snowflake")
            )
        elif obj.objtype == HEATER_TYPE:
            sensors.append(
                HeaterBinarySensor(
                    entry,
                    controller,
                    obj,
                )
            )
        elif obj.objtype == "SCHED":
            sensors.append(
                PoolBinarySensor(
                    entry,
                    controller,
                    obj,
                    attribute_key="ACT",
                    name="+ (schedule)",
                    enabled_by_default=False,
                    extraStateAttributes={"VACFLO"},
                )
            )
        elif obj.objtype == "PUMP":
            sensors.append(PoolBinarySensor(entry, controller, obj, valueForON="10"))
    async_add_entities(sensors)


# -------------------------------------------------------------------------------------


class PoolBinarySensor(PoolEntity, BinarySensorEntity):
    """Representation of a Pentair Binary Sensor."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
        valueForON="ON",
        **kwargs,
    ):
        """Initialize."""
        super().__init__(entry, controller, poolObject, **kwargs)
        self._valueForON = valueForON

    @property
    def is_on(self):
        """Return true if sensor is on."""
        return self._poolObject[self._attribute_key] == self._valueForON


# -------------------------------------------------------------------------------------


class HeaterBinarySensor(PoolEntity, BinarySensorEntity):
    """Representation of a Heater binary sensor."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
        **kwargs,
    ):
        """Initialize."""
        super().__init__(entry, controller, poolObject, **kwargs)
        self._bodies = set(poolObject[BODY_ATTR].split(" "))
        self._attr_icon = "mdi:fire-circle"

    @property
    def is_on(self) -> bool:
        """Return true if sensor is on."""
        for bodyObjnam in self._bodies:
            body = self._controller.model[bodyObjnam]
            if (
                body[STATUS_ATTR] == "ON"
                and body[HEATER_ATTR] == self._poolObject.objnam
                and body[HTMODE_ATTR] != "0"
            ):
                return True
        return False

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""

        for objnam in self._bodies & updates.keys():
            if {STATUS_ATTR, HEATER_ATTR, HTMODE_ATTR} & updates[objnam].keys():
                return True
        return False
