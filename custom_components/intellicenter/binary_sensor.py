"""Pentair Intellicenter binary sensors.

This module provides binary sensor entities for:
- Freeze protection circuits
- Heater status
- Schedule status
- Pump status
- IntelliChem alarm indicators (diagnostic)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_ATTR,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    ORPHI_ATTR,
    ORPLO_ATTR,
    PHHI_ATTR,
    PHLO_ATTR,
    PUMP_STATUS_ON,
    PUMP_TYPE,
    SCHED_TYPE,
    STATUS_ATTR,
    STATUS_ON,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool binary sensors based on a config entry."""
    coordinator = entry.runtime_data

    sensors: list[PoolBinarySensor | HeaterBinarySensor] = []

    obj: PoolObject
    for obj in coordinator.model:
        if obj.objtype == CIRCUIT_TYPE and obj.subtype == "FRZ":
            sensors.append(
                PoolBinarySensor(
                    coordinator,
                    obj,
                    icon="mdi:snowflake",
                    device_class=BinarySensorDeviceClass.COLD,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
        elif obj.objtype == HEATER_TYPE:
            sensors.append(
                HeaterBinarySensor(
                    coordinator,
                    obj,
                )
            )
        elif obj.objtype == SCHED_TYPE:
            sensors.append(
                PoolBinarySensor(
                    coordinator,
                    obj,
                    attribute_key="ACT",
                    name="+ (schedule)",
                    icon="mdi:clock-outline",
                    entity_category=EntityCategory.CONFIG,
                    extra_state_attributes=["VACFLO"],
                )
            )
        elif obj.objtype == PUMP_TYPE:
            sensors.append(
                PoolBinarySensor(
                    coordinator,
                    obj,
                    value_for_on=PUMP_STATUS_ON,
                    device_class=BinarySensorDeviceClass.RUNNING,
                )
            )
        elif obj.objtype == CHEM_TYPE and obj.subtype == "ICHEM":
            # IntelliChem alarm indicators (diagnostic entities)
            if PHHI_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolBinarySensor(
                        coordinator,
                        obj,
                        attribute_key=PHHI_ATTR,
                        name="+ (pH High Alarm)",
                        icon="mdi:alert-circle",
                        device_class=BinarySensorDeviceClass.PROBLEM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if PHLO_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolBinarySensor(
                        coordinator,
                        obj,
                        attribute_key=PHLO_ATTR,
                        name="+ (pH Low Alarm)",
                        icon="mdi:alert-circle",
                        device_class=BinarySensorDeviceClass.PROBLEM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if ORPHI_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolBinarySensor(
                        coordinator,
                        obj,
                        attribute_key=ORPHI_ATTR,
                        name="+ (ORP High Alarm)",
                        icon="mdi:alert-circle",
                        device_class=BinarySensorDeviceClass.PROBLEM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if ORPLO_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolBinarySensor(
                        coordinator,
                        obj,
                        attribute_key=ORPLO_ATTR,
                        name="+ (ORP Low Alarm)",
                        icon="mdi:alert-circle",
                        device_class=BinarySensorDeviceClass.PROBLEM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
    async_add_entities(sensors)


# -------------------------------------------------------------------------------------


class PoolBinarySensor(PoolEntity, BinarySensorEntity):
    """Representation of a Pentair Binary Sensor.

    Used for freeze protection, schedule status, pump running status,
    and IntelliChem alarm indicators.
    """

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        value_for_on: str = STATUS_ON,
        device_class: BinarySensorDeviceClass | None = None,
        entity_category: EntityCategory | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a pool binary sensor.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this sensor represents
            value_for_on: The attribute value that indicates "on" state
            device_class: The device class for this sensor
            entity_category: The entity category (e.g., DIAGNOSTIC)
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(coordinator, pool_object, **kwargs)
        self._value_for_on = value_for_on
        if device_class:
            self._attr_device_class = device_class
        if entity_category:
            self._attr_entity_category = entity_category

    @property
    def is_on(self) -> bool:
        """Return true if sensor is on."""
        return bool(self._pool_object[self._attribute_key] == self._value_for_on)


# -------------------------------------------------------------------------------------


class HeaterBinarySensor(PoolEntity, BinarySensorEntity):
    """Representation of a Heater binary sensor.

    Tracks whether a heater is actively heating any body of water.
    """

    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:fire-circle"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        **kwargs: Any,
    ) -> None:
        """Initialize a heater binary sensor.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject (heater) this sensor represents
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(coordinator, pool_object, **kwargs)
        body_attr = pool_object[BODY_ATTR]
        self._bodies: set[str] = set(body_attr.split(" ")) if body_attr else set()

    @property
    def is_on(self) -> bool:
        """Return true if the heater is actively heating."""
        for body_objnam in self._bodies:
            body = self.coordinator.model[body_objnam]
            if body is None:
                continue
            if (
                body[STATUS_ATTR] == STATUS_ON
                and body[HEATER_ATTR] == self._pool_object.objnam
                and body[HTMODE_ATTR] != "0"
            ):
                return True
        return False

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter.

        Checks both:
        1. If any monitored body's heating-related attributes changed
        2. If the heater object itself was updated (e.g., availability change)

        Args:
            updates: Dictionary of object updates

        Returns:
            True if this heater sensor's state may have changed
        """
        # Check if any monitored body had heating-related updates
        for objnam in self._bodies & updates.keys():
            if {STATUS_ATTR, HEATER_ATTR, HTMODE_ATTR} & updates[objnam].keys():
                return True

        # Also check if the heater object itself was updated
        if self._pool_object.objnam in updates:
            return True

        return False
