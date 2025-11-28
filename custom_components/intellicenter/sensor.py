"""Pentair Intellicenter sensors.

This module provides sensor entities for various pool measurements including:
- Temperature sensors (air, water)
- Pump sensors (power, RPM, GPM)
- Chemistry sensors (pH, ORP, salt level, water quality)

Note: IntelliChem configuration values (ALK, CALC, CYACID) are in number.py
as they are user-entered configuration, not sensor readings.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    GPM_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MAX_ATTR,
    MAXF_ATTR,
    MIN_ATTR,
    MINF_ATTR,
    ORPTNK_ATTR,
    ORPVAL_ATTR,
    PHTNK_ATTR,
    PHVAL_ATTR,
    PUMP_TYPE,
    PWR_ATTR,
    QUALTY_ATTR,
    RPM_ATTR,
    SALT_ATTR,
    SENSE_TYPE,
    SOURCE_ATTR,
    SYSTEM_TYPE,
    VER_ATTR,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity
from .const import CONST_GPM, CONST_RPM
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool sensors based on a config entry."""
    coordinator = entry.runtime_data

    sensors: list[PoolSensor] = []

    obj: PoolObject
    for obj in coordinator.model:
        if obj.objtype == SENSE_TYPE:
            sensors.append(
                PoolSensor(
                    coordinator,
                    obj,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    attribute_key=SOURCE_ATTR,
                )
            )
        elif obj.objtype == PUMP_TYPE:
            if obj[PWR_ATTR]:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=SensorDeviceClass.POWER,
                        unit_of_measurement=UnitOfPower.WATT,
                        attribute_key=PWR_ATTR,
                        name="+ power",
                        rounding_factor=25,
                    )
                )
            if obj[RPM_ATTR]:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_RPM,
                        attribute_key=RPM_ATTR,
                        name="+ rpm",
                    )
                )
            if obj[GPM_ATTR]:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_GPM,
                        attribute_key=GPM_ATTR,
                        name="+ gpm",
                    )
                )
            # Pump operational limits (diagnostic sensors)
            if MAX_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_RPM,
                        attribute_key=MAX_ATTR,
                        name="+ Max RPM",
                        icon="mdi:speedometer",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if MIN_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_RPM,
                        attribute_key=MIN_ATTR,
                        name="+ Min RPM",
                        icon="mdi:speedometer-slow",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if (
                MAXF_ATTR in obj.attribute_keys
                and obj[MAXF_ATTR]
                and int(obj[MAXF_ATTR]) > 0
            ):
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_GPM,
                        attribute_key=MAXF_ATTR,
                        name="+ Max GPM",
                        icon="mdi:water-pump",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
            if (
                MINF_ATTR in obj.attribute_keys
                and obj[MINF_ATTR]
                and int(obj[MINF_ATTR]) > 0
            ):
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        unit_of_measurement=CONST_GPM,
                        attribute_key=MINF_ATTR,
                        name="+ Min GPM",
                        icon="mdi:water-pump-off",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
        elif obj.objtype == BODY_TYPE:
            sensors.append(
                PoolSensor(
                    coordinator,
                    obj,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    attribute_key=LSTTMP_ATTR,
                    name="+ last temp",
                )
            )
            sensors.append(
                PoolSensor(
                    coordinator,
                    obj,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    attribute_key=LOTMP_ATTR,
                    name="+ desired temp",
                )
            )
        elif obj.objtype == CHEM_TYPE:
            if obj.subtype == "ICHEM":
                if PHVAL_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=SensorDeviceClass.PH,
                            attribute_key=PHVAL_ATTR,
                            name="+ (pH)",
                        )
                    )
                if ORPVAL_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=ORPVAL_ATTR,
                            name="+ (ORP)",
                            unit_of_measurement="mV",
                        )
                    )
                if QUALTY_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=QUALTY_ATTR,
                            name="+ (Water Quality)",
                        )
                    )
                if PHTNK_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=PHTNK_ATTR,
                            name="+ (pH Tank Level)",
                            entity_category=EntityCategory.DIAGNOSTIC,
                        )
                    )
                if ORPTNK_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=ORPTNK_ATTR,
                            name="+ (ORP Tank Level)",
                            entity_category=EntityCategory.DIAGNOSTIC,
                        )
                    )
                # Note: ALK, CALC, CYACID are configuration values (user-entered)
                # and are handled as number entities in number.py
            elif obj.subtype == "ICHLOR":
                if SALT_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
                            attribute_key=SALT_ATTR,
                            name="+ (Salt)",
                        )
                    )
        elif obj.objtype == SYSTEM_TYPE:
            # Firmware version (diagnostic sensor, non-numeric string value)
            if VER_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=None,
                        attribute_key=VER_ATTR,
                        name="Firmware Version",
                        icon="mdi:chip",
                        entity_category=EntityCategory.DIAGNOSTIC,
                        state_class=None,  # Non-numeric value
                    )
                )
    async_add_entities(sensors)


# -------------------------------------------------------------------------------------


class PoolSensor(PoolEntity, SensorEntity):
    """Representation of a Pentair sensor.

    Supports temperature, power, and chemistry measurements with optional
    value rounding for sensors with high update frequency.
    """

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        device_class: SensorDeviceClass | None,
        rounding_factor: int = 0,
        entity_category: EntityCategory | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
        **kwargs: Any,
    ) -> None:
        """Initialize a pool sensor.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this sensor represents
            device_class: The device class for this sensor
            rounding_factor: If non-zero, round values to this factor
            entity_category: The entity category (e.g., DIAGNOSTIC)
            state_class: The state class (default: MEASUREMENT, None for non-numeric)
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(coordinator, pool_object, **kwargs)
        self._attr_device_class = device_class
        self._rounding_factor = rounding_factor
        if state_class is not None:
            self._attr_state_class = state_class
        if entity_category:
            self._attr_entity_category = entity_category

    @property
    def native_value(self) -> float | int | str | None:
        """Return the native value of the sensor.

        Some sensors (like variable speed pumps) can vary constantly,
        so rounding their value to a nearest multiplier of 'rounding_factor'
        smooths the curve and limits the number of updates in the log.
        """
        raw_value = self._pool_object[self._attribute_key]
        if raw_value is None:
            return None

        try:
            value = int(raw_value)
            if self._rounding_factor:
                value = int(
                    round(value / self._rounding_factor) * self._rounding_factor
                )
            return value
        except (ValueError, TypeError):
            # Return as-is if not convertible to int (e.g., pH values as float)
            try:
                return float(raw_value)
            except (ValueError, TypeError):
                return str(raw_value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            return self.pentairTemperatureSettings()
        return self._attr_native_unit_of_measurement
