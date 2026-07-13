"""Pentair Intellicenter binary sensors.

This module provides binary sensor entities for:
- Freeze protection circuits
- Heater status
- Schedule status
- Pump status
- IntelliChem alarm indicators (diagnostic)
"""

from __future__ import annotations

from collections.abc import Iterable
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
    ACT_ATTR,
    BODY_ATTR,
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_ATTR,
    CIRCUIT_TYPE,
    DAY_ATTR,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    LOTMP_ATTR,
    ORPHI_ATTR,
    ORPLO_ATTR,
    PHHI_ATTR,
    PHLO_ATTR,
    PUMP_STATUS_ON,
    PUMP_TYPE,
    SCHED_TYPE,
    SERVICE_ATTR,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    SYSTEM_TYPE,
    TIME_ATTR,
    TIMOUT_ATTR,
    VACFLO_ATTR,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity, async_setup_pool_entities
from .const import CHLOR_ATTR, DNTSTP_ATTR, SINGLE_ATTR
from .coordinator import IntelliCenterCoordinator
from .sensor import normalize_system_mode

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

_CHEM_ALERT_ENTITY_KEY = "CHEM_ALERT"


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[
    PoolBinarySensor
    | ChemAlertBinarySensor
    | ChlorinatorBinarySensor
    | HeaterBinarySensor
    | ScheduleBinarySensor
    | SystemModeBinarySensor
]:
    """Build binary sensor entities for the given candidate pool objects."""
    sensors: list[
        PoolBinarySensor
        | ChemAlertBinarySensor
        | ChlorinatorBinarySensor
        | HeaterBinarySensor
        | ScheduleBinarySensor
        | SystemModeBinarySensor
    ] = []

    for obj in candidates:
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
                ScheduleBinarySensor(
                    coordinator,
                    obj,
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
            sensors.append(ChemAlertBinarySensor(coordinator, obj))
            # IntelliChem alarm indicators (diagnostic entities)
            if PHHI_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolBinarySensor(
                        coordinator,
                        obj,
                        attribute_key=PHHI_ATTR,
                        name="+ (pH High Alarm)",
                        icon="mdi:alert-plus-outline",
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
                        icon="mdi:alert-minus-outline",
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
                        icon="mdi:alert-plus-outline",
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
                        icon="mdi:alert-minus-outline",
                        device_class=BinarySensorDeviceClass.PROBLEM,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
        elif obj.objtype == CHEM_TYPE and obj.subtype == "ICHLOR":
            sensors.append(ChlorinatorBinarySensor(coordinator, obj))
        elif obj.objtype == SYSTEM_TYPE and SERVICE_ATTR in obj.attribute_keys:
            # Panel operating-mode problem indicator: on whenever the panel is
            # not in normal automatic operation (Service or Time Out), e.g.
            # left in service mode after maintenance or a power outage.
            sensors.append(SystemModeBinarySensor(coordinator, obj))
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool binary sensors based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


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


class ChemAlertBinarySensor(PoolEntity, BinarySensorEntity):
    """Aggregate IntelliChem alarm state."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:flask-empty-remove-outline"
    _alert_attributes = (PHHI_ATTR, PHLO_ATTR, ORPHI_ATTR, ORPLO_ATTR)

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize the aggregate alert sensor."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=_CHEM_ALERT_ENTITY_KEY,
            name="+ Chemistry Alert",
        )

    @property
    def _inputs_valid(self) -> bool:
        """Return whether every helper input has a known on/off value."""
        return all(
            self._pool_object[attribute] in (STATUS_ON, STATUS_OFF)
            for attribute in self._alert_attributes
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether any chemistry alarm is active."""
        if not self._inputs_valid:
            return None
        return self._controller.has_chem_alert(self._pool_object.objnam)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return active alert names alongside the standard metadata."""
        attributes = super().extra_state_attributes
        if self._inputs_valid:
            attributes["active_alerts"] = self._controller.get_chem_alerts(
                self._pool_object.objnam
            )
        return attributes

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return whether any contributing alarm attribute changed."""
        return self._check_attributes_updated(updates, *self._alert_attributes)


class ChlorinatorBinarySensor(PoolEntity, BinarySensorEntity):
    """IntelliChlor operating status."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-sync"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize the chlorinator status sensor."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=CHLOR_ATTR,
            name="+ Running",
        )

    @property
    def is_on(self) -> bool | None:
        """Return running state, or unknown for missing/malformed values."""
        value = self._pool_object[self._attribute_key]
        if value not in (STATUS_ON, STATUS_OFF):
            return None
        return bool(value == STATUS_ON)


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

    @property
    def _bodies(self) -> set[str]:
        """Return the objnams of the bodies this heater serves, derived live.

        Reading BODY from the live pool object (instead of freezing it at
        construction - the issue-#57 staleness class) means a heater rewired
        to a different body keeps reporting correctly without a reload.
        """
        body_attr = self._pool_object[BODY_ATTR]
        return set(body_attr.split(" ")) if body_attr else set()

    @property
    def is_on(self) -> bool:
        """Return true if the heater is actively heating."""
        for body in self.coordinator.model.get_by_type(BODY_TYPE):
            if (
                body[STATUS_ATTR] == STATUS_ON
                and body[HEATER_ATTR] == self._pool_object.objnam
                # A missing HTMODE means "unknown", not "heating": None != "0"
                # is True, so an explicit not-in check is required.
                and body[HTMODE_ATTR] not in (None, "0")
            ):
                return True
        return False

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter.

        Checks both:
        1. If any body's heating-related attributes changed
        2. If the heater object itself was updated (e.g., availability change)

        Args:
            updates: Dictionary of object updates

        Returns:
            True if this heater sensor's state may have changed
        """
        # Check if any body's heating-related attributes changed. Include the
        # heater's live BODY list as a fallback for objects not yet in the model.
        body_objnams = self._bodies | {
            body.objnam for body in self.coordinator.model.get_by_type(BODY_TYPE)
        }
        for objnam in body_objnams & updates.keys():
            if {STATUS_ATTR, HEATER_ATTR, HTMODE_ATTR} & updates[objnam].keys():
                return True

        # Also check if the heater object itself was updated
        if self._pool_object.objnam in updates:
            return True

        return False


# -------------------------------------------------------------------------------------


class ScheduleBinarySensor(PoolEntity, BinarySensorEntity):
    """Representation of a schedule status sensor.

    Shows whether a schedule is currently active (running).
    Named as "Schedule (Object Name)" for grouping in the UI.
    """

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a schedule binary sensor."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=ACT_ATTR,
            enabled_by_default=False,
        )

    @property
    def name(self) -> str:
        """Return the name as 'Schedule (Object Name)'."""
        sname = self._pool_object.sname or "Unknown"
        return f"Schedule ({sname})"

    @property
    def is_on(self) -> bool | None:
        """Return true if the schedule is currently active."""
        value = self._pool_object[self._attribute_key]
        if value not in (STATUS_ON, STATUS_OFF):
            return None
        return bool(value == STATUS_ON)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return schedule configuration details when available."""
        attributes = super().extra_state_attributes
        objnam = self._pool_object.objnam

        circuit = self._controller.get_schedule_circuit(objnam)
        if circuit is not None:
            attributes[CIRCUIT_ATTR] = circuit
            circuit_object = self.coordinator.model[circuit]
            if circuit_object is not None and circuit_object.sname is not None:
                attributes["CIRCUIT_NAME"] = circuit_object.sname

        helper_values = {
            DAY_ATTR: self._controller.get_schedule_days(objnam),
            TIME_ATTR: self._controller.get_schedule_start_time(objnam),
            TIMOUT_ATTR: self._controller.get_schedule_stop_time(objnam),
        }
        for key, value in helper_values.items():
            if value is not None:
                attributes[key] = value

        for key in (
            HEATER_ATTR,
            LOTMP_ATTR,
            SINGLE_ATTR,
            DNTSTP_ATTR,
            VACFLO_ATTR,
        ):
            value = self._pool_object[key]
            if value is not None:
                attributes[key] = value

        return attributes

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true when running state or schedule details change."""
        return self._check_attributes_updated(
            updates,
            ACT_ATTR,
            CIRCUIT_ATTR,
            DAY_ATTR,
            TIME_ATTR,
            TIMOUT_ATTR,
            HEATER_ATTR,
            LOTMP_ATTR,
            SINGLE_ATTR,
            DNTSTP_ATTR,
            STATUS_ATTR,
            VACFLO_ATTR,
        )


# -------------------------------------------------------------------------------------


class SystemModeBinarySensor(PoolEntity, BinarySensorEntity):
    """Problem sensor: on when the panel is not in normal automatic operation.

    IntelliCenter suspends schedules (and therefore automatic valve and pump
    control) while the panel is in Service or Time Out mode -- a state it can
    be left in after maintenance or a power outage, silently stopping
    circulation. This sensor mirrors the ``System Mode`` enum sensor's source
    attribute (``SERVICE`` on the SYSTEM object, normalized through
    ``normalize_system_mode()``) as a ``PROBLEM`` binary sensor so standard
    problem-entity dashboards and alert automations pick it up without
    custom template YAML.

    ``is_on`` is True for ``service``/``timeout``, False for ``auto``, and
    None (unknown) for unrecognized protocol values -- an unexpected string
    must not raise a false alarm.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cog-off-outline"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        **kwargs: Any,
    ) -> None:
        """Initialize the Not in Auto problem sensor.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The SYSTEM PoolObject
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=SERVICE_ATTR,
            name="Not in Auto",
            **kwargs,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True when the panel mode is Service or Time Out."""
        mode = normalize_system_mode(self._pool_object[self._attribute_key])
        if mode is None:
            return None
        return mode != "auto"
