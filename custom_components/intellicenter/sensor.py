"""Pentair Intellicenter sensors.

This module provides sensor entities for various pool measurements including:
- Temperature sensors (air, water)
- Pump sensors (power, RPM, GPM)
- Chemistry sensors (pH, ORP, salt level, water quality)
- Dosing volume sensors (cumulative pH and ORP chemical volumes in mL)

Note: IntelliChem configuration values (ALK, CALC, CYACID) are in number.py
as they are user-entered configuration, not sensor readings.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    EntityCategory,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    GPM_ATTR,
    LSTTMP_ATTR,
    MAX_ATTR,
    MAXF_ATTR,
    MIN_ATTR,
    MINF_ATTR,
    ORPTNK_ATTR,
    ORPVAL_ATTR,
    ORPVOL_ATTR,
    PHTNK_ATTR,
    PHVAL_ATTR,
    PHVOL_ATTR,
    PUMP_TYPE,
    PWR_ATTR,
    QUALTY_ATTR,
    RPM_ATTR,
    SALT_ATTR,
    SENSE_TYPE,
    SERVICE_ATTR,
    SOURCE_ATTR,
    SYSTEM_TYPE,
    VER_ATTR,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    PoolEntity,
    async_setup_pool_entities,
    safe_int,
)
from .const import CONST_GPM, CONST_RPM
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# -------------------------------------------------------------------------------------


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolSensor]:
    """Build sensor entities for the given candidate pool objects."""
    sensors: list[PoolSensor] = []

    for obj in candidates:
        if obj.objtype == SENSE_TYPE:
            sensors.append(
                PoolSensor(
                    coordinator,
                    obj,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    attribute_key=SOURCE_ATTR,
                )
            )
        elif obj.objtype == BODY_TYPE:
            # "Last Temp" = the body's last recorded (latched) temperature.
            # Unlike the physical SENSE water probe (which cools in an
            # above-ground pipe when the pump stops), LSTTMP holds the last
            # circulating temperature, so it stays accurate when idle (#75).
            if LSTTMP_ATTR in obj.attribute_keys:
                sensors.append(
                    PoolSensor(
                        coordinator,
                        obj,
                        device_class=SensorDeviceClass.TEMPERATURE,
                        attribute_key=LSTTMP_ATTR,
                        name="+ Last Temp",
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
            # safe_int: a malformed MAXF/MINF must skip this sensor, not raise
            # ValueError inside platform setup and take down every sensor.
            if MAXF_ATTR in obj.attribute_keys and (safe_int(obj[MAXF_ATTR]) or 0) > 0:
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
            if MINF_ATTR in obj.attribute_keys and (safe_int(obj[MINF_ATTR]) or 0) > 0:
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
                            icon="mdi:react",
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
                            icon="mdi:test-tube",
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
                            icon="mdi:barrel",
                            entity_category=EntityCategory.DIAGNOSTIC,
                            value_offset=-1,
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
                            icon="mdi:barrel",
                            entity_category=EntityCategory.DIAGNOSTIC,
                            value_offset=-1,
                        )
                    )
                # Cumulative dosing volume sensors (mL)
                if PHVOL_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=PHVOL_ATTR,
                            name="+ (pH Dosing Volume)",
                            icon="mdi:beaker-outline",
                            unit_of_measurement="mL",
                            entity_category=EntityCategory.DIAGNOSTIC,
                            state_class=SensorStateClass.TOTAL_INCREASING,
                        )
                    )
                if ORPVOL_ATTR in obj.attribute_keys:
                    sensors.append(
                        PoolSensor(
                            coordinator,
                            obj,
                            device_class=None,
                            attribute_key=ORPVOL_ATTR,
                            name="+ (ORP Dosing Volume)",
                            icon="mdi:beaker-outline",
                            unit_of_measurement="mL",
                            entity_category=EntityCategory.DIAGNOSTIC,
                            state_class=SensorStateClass.TOTAL_INCREASING,
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
                            icon="mdi:shaker-outline",
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
            # System operating mode (Auto / Service / Time out). Shown as a
            # primary sensor (not diagnostic) to mirror the IntelliCenter app's
            # dashboard mode banner.
            if SERVICE_ATTR in obj.attribute_keys:
                sensors.append(SystemModeSensor(coordinator, obj))
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool sensors based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


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
        value_offset: int = 0,
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
            value_offset: Fixed offset added to raw values (e.g., -1 for tank levels)
            entity_category: The entity category (e.g., DIAGNOSTIC)
            state_class: The state class (default: MEASUREMENT, None for non-numeric)
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(coordinator, pool_object, **kwargs)
        self._attr_device_class = device_class
        self._rounding_factor = rounding_factor
        self._value_offset = value_offset
        if state_class is not None:
            self._attr_state_class = state_class
        if entity_category:
            self._attr_entity_category = entity_category

    @property
    def native_value(self) -> float | int | str | None:
        """Return the native value of the sensor.

        Integer values are adjusted by value_offset (e.g., -1 for tank levels
        to correct IntelliCenter's off-by-one reporting) then optionally rounded
        to the nearest multiple of rounding_factor (used by pump sensors to
        smooth high-frequency updates).
        """
        raw_value = self._pool_object[self._attribute_key]
        if raw_value is None:
            return None

        try:
            value = int(raw_value) + self._value_offset
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


# The documented IntelliCenter system operating modes. Only "auto" is
# hardware-confirmed (the SYSTEM object reports SERVICE='AUTO' in normal
# automatic operation); the exact "service"/"timeout" protocol strings are
# inferred from Pentair documentation and have not been observed on hardware.
SYSTEM_MODE_OPTIONS = ["auto", "service", "timeout"]


class SystemModeSensor(PoolSensor):
    """System operating-mode sensor (Auto / Service / Time out).

    IntelliCenter reports the operating mode on the SYSTEM object via the
    SERVICE attribute. It is exposed as an enum sensor; the per-state labels
    are localized via ``translation_key`` (``entity.sensor.system_mode.state``).
    The entity name itself is set explicitly -- like the Firmware Version sensor
    -- because ``PoolEntity.name`` overrides Home Assistant's translation-based
    naming, so a ``translation_key`` name would never be consulted.

    Only the ``AUTO`` value is hardware-confirmed; ``service`` and ``timeout``
    are the documented modes (Pentair manuals) but their exact protocol strings
    are inferred. Raw values are normalized case- and space-insensitively, and
    any value outside the known options is reported as unknown so the enum
    sensor never raises on an unexpected string.
    """

    _attr_translation_key = "system_mode"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize the system mode sensor."""
        super().__init__(
            coordinator,
            pool_object,
            device_class=SensorDeviceClass.ENUM,
            attribute_key=SERVICE_ATTR,
            name="System Mode",
            icon="mdi:cog-sync",
            # ENUM sensors must not declare a state_class.
            state_class=None,
        )
        self._attr_options = SYSTEM_MODE_OPTIONS

    @property
    def native_value(self) -> str | None:
        """Return the normalized system mode, or None if unrecognized.

        The raw SERVICE value is normalized case- and space-insensitively so
        variants like "AUTO", "Service", or "TIME OUT" map onto the documented
        ``auto``/``service``/``timeout`` options. A value outside that set is
        reported as ``None`` (unknown) rather than returned verbatim, because
        Home Assistant raises ``ValueError`` when an enum sensor's state is not
        one of its declared ``options``.
        """
        raw_value = self._pool_object[self._attribute_key]
        if raw_value is None:
            return None
        normalized = str(raw_value).strip().lower().replace(" ", "")
        return normalized if normalized in SYSTEM_MODE_OPTIONS else None
