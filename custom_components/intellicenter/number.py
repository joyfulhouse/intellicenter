"""Pentair Intellicenter numbers.

This module provides number entities for:
- IntelliChlor output percentage control (CONFIG)
- IntelliChem pH and ORP setpoint control (CONFIG)
- IntelliChem water chemistry configuration (ALK, CALC, CYACID) (CONFIG)
- Body max temperature setpoint (HITMP)
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.number import (
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    DEFAULT_STEP,
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    ALK_ATTR,
    BODY_ATTR,
    BODY_TYPE,
    CALC_ATTR,
    CHEM_TYPE,
    CYACID_ATTR,
    HITMP_ATTR,
    ORPSET_ATTR,
    PHSET_ATTR,
    PRIM_ATTR,
    SEC_ATTR,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# IntelliChem setpoint ranges (per Pentair documentation)
PH_SETPOINT_MIN = 7.0
PH_SETPOINT_MAX = 7.6
PH_SETPOINT_STEP = 0.1

ORP_SETPOINT_MIN = 400
ORP_SETPOINT_MAX = 800
ORP_SETPOINT_STEP = 10

# IntelliChem water chemistry configuration ranges
ALK_MIN = 0
ALK_MAX = 300
ALK_STEP = 1

CALC_MIN = 0
CALC_MAX = 800
CALC_STEP = 1

CYACID_MIN = 0
CYACID_MAX = 200
CYACID_STEP = 1

# Temperature setpoint ranges (Fahrenheit)
TEMP_SETPOINT_MIN = 40
TEMP_SETPOINT_MAX = 104
TEMP_SETPOINT_STEP = 1

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool number entities based on a config entry."""
    coordinator = entry.runtime_data

    numbers: list[PoolNumber] = []

    pool_obj: PoolObject
    for pool_obj in coordinator.model:
        if pool_obj.objtype == CHEM_TYPE:
            if pool_obj.subtype == "ICHLOR" and PRIM_ATTR in pool_obj.attribute_keys:
                # IntelliChlor output percentage controls (CONFIG category)
                body_attr = pool_obj[BODY_ATTR]
                if body_attr is None:
                    continue
                intellichlor_bodies = body_attr.split(" ")

                # Only create number entities for bodies that are actually configured
                for index, body_id in enumerate(intellichlor_bodies):
                    body = coordinator.model[body_id]
                    if body is not None:
                        attribute_key = PRIM_ATTR if index == 0 else SEC_ATTR
                        numbers.append(
                            PoolNumber(
                                coordinator,
                                pool_obj,
                                unit_of_measurement=PERCENTAGE,
                                attribute_key=attribute_key,
                                name=f"+ Output % ({body.sname})",
                                entity_category=EntityCategory.CONFIG,
                                integer_only=True,
                            )
                        )

            elif pool_obj.subtype == "ICHEM":
                # IntelliChem pH setpoint control (CONFIG category)
                if PHSET_ATTR in pool_obj.attribute_keys:
                    numbers.append(
                        PoolNumber(
                            coordinator,
                            pool_obj,
                            min_value=PH_SETPOINT_MIN,
                            max_value=PH_SETPOINT_MAX,
                            step=PH_SETPOINT_STEP,
                            attribute_key=PHSET_ATTR,
                            name="+ pH Setpoint",
                            icon="mdi:ph",
                            device_class=NumberDeviceClass.PH,
                            mode=NumberMode.SLIDER,
                            entity_category=EntityCategory.CONFIG,
                        )
                    )

                # IntelliChem ORP setpoint control (CONFIG category)
                if ORPSET_ATTR in pool_obj.attribute_keys:
                    numbers.append(
                        PoolNumber(
                            coordinator,
                            pool_obj,
                            min_value=ORP_SETPOINT_MIN,
                            max_value=ORP_SETPOINT_MAX,
                            step=ORP_SETPOINT_STEP,
                            attribute_key=ORPSET_ATTR,
                            name="+ ORP Setpoint",
                            icon="mdi:test-tube",
                            unit_of_measurement="mV",
                            mode=NumberMode.SLIDER,
                            entity_category=EntityCategory.CONFIG,
                            integer_only=True,
                        )
                    )

                # IntelliChem water chemistry configuration (CONFIG category)
                # These are user-entered values, not sensor readings
                if ALK_ATTR in pool_obj.attribute_keys:
                    numbers.append(
                        PoolNumber(
                            coordinator,
                            pool_obj,
                            min_value=ALK_MIN,
                            max_value=ALK_MAX,
                            step=ALK_STEP,
                            attribute_key=ALK_ATTR,
                            name="+ Alkalinity",
                            icon="mdi:flask-outline",
                            unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
                            mode=NumberMode.BOX,
                            entity_category=EntityCategory.CONFIG,
                            integer_only=True,
                        )
                    )

                if CALC_ATTR in pool_obj.attribute_keys:
                    numbers.append(
                        PoolNumber(
                            coordinator,
                            pool_obj,
                            min_value=CALC_MIN,
                            max_value=CALC_MAX,
                            step=CALC_STEP,
                            attribute_key=CALC_ATTR,
                            name="+ Calcium Hardness",
                            icon="mdi:flask-outline",
                            unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
                            mode=NumberMode.BOX,
                            entity_category=EntityCategory.CONFIG,
                            integer_only=True,
                        )
                    )

                if CYACID_ATTR in pool_obj.attribute_keys:
                    numbers.append(
                        PoolNumber(
                            coordinator,
                            pool_obj,
                            min_value=CYACID_MIN,
                            max_value=CYACID_MAX,
                            step=CYACID_STEP,
                            attribute_key=CYACID_ATTR,
                            name="+ Cyanuric Acid",
                            icon="mdi:flask-outline",
                            unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
                            mode=NumberMode.BOX,
                            entity_category=EntityCategory.CONFIG,
                            integer_only=True,
                        )
                    )

    # Add body max temperature setpoints (HITMP) - CONFIG category
    for pool_obj in coordinator.model:
        if pool_obj.objtype == BODY_TYPE and HITMP_ATTR in pool_obj.attribute_keys:
            numbers.append(
                PoolNumber(
                    coordinator,
                    pool_obj,
                    min_value=TEMP_SETPOINT_MIN,
                    max_value=TEMP_SETPOINT_MAX,
                    step=TEMP_SETPOINT_STEP,
                    attribute_key=HITMP_ATTR,
                    name="+ Max Temperature",
                    icon="mdi:thermometer-high",
                    device_class=NumberDeviceClass.TEMPERATURE,
                    mode=NumberMode.SLIDER,
                    entity_category=EntityCategory.CONFIG,
                    integer_only=True,
                )
            )

    async_add_entities(numbers)


# -------------------------------------------------------------------------------------


class PoolNumber(PoolEntity, NumberEntity):
    """Representation of a pool number entity."""

    _attr_icon = "mdi:gauge"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        min_value: float = DEFAULT_MIN_VALUE,
        max_value: float = DEFAULT_MAX_VALUE,
        step: float = DEFAULT_STEP,
        device_class: NumberDeviceClass | None = None,
        mode: NumberMode = NumberMode.AUTO,
        entity_category: EntityCategory | None = None,
        integer_only: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize a pool number entity.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this entity represents
            min_value: Minimum value for the number
            max_value: Maximum value for the number
            step: Step size for value changes
            device_class: The device class for this number entity
            mode: The input mode (slider, box, auto)
            entity_category: The entity category (e.g., CONFIG)
            integer_only: If True, return integer values instead of float
            **kwargs: Additional arguments passed to PoolEntity
        """
        super().__init__(coordinator, pool_object, **kwargs)
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._integer_only = integer_only
        if device_class:
            self._attr_device_class = device_class
        self._attr_mode = mode
        if entity_category:
            self._attr_entity_category = entity_category

    @property
    def native_value(self) -> float | int | None:
        """Return the current value."""
        value = self._safe_float_conversion(self._pool_object[self._attribute_key])
        if value is not None and self._integer_only:
            return int(value)
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value.

        Uses pyintellicenter convenience methods for validated setpoint changes.
        """
        controller = self._controller
        objnam = self._pool_object.objnam

        # Dispatch table for convenience methods
        # Maps attribute key to (method_name, value_converter)
        dispatch: dict[str, tuple[str, Callable[[float], float | int]]] = {
            PHSET_ATTR: ("set_ph_setpoint", lambda v: v),  # pH needs float
            ORPSET_ATTR: ("set_orp_setpoint", int),
            PRIM_ATTR: ("set_chlorinator_output", int),
            ALK_ATTR: ("set_alkalinity", int),
            CALC_ATTR: ("set_calcium_hardness", int),
            CYACID_ATTR: ("set_cyanuric_acid", int),
        }

        try:
            if self._attribute_key in dispatch:
                method_name, converter = dispatch[self._attribute_key]
                method = getattr(controller, method_name)
                await method(objnam, converter(value))
            elif self._attribute_key == SEC_ATTR:
                # Secondary chlorinator needs current primary preserved
                current = controller.get_chlorinator_output(objnam)
                primary = current.get("primary") or 0
                await controller.set_chlorinator_output(objnam, primary, int(value))
            else:
                # Fallback for other number entities (e.g., HITMP)
                self.request_changes({self._attribute_key: str(int(value))})
        except ValueError as err:
            _LOGGER.warning("Invalid setpoint value for %s: %s", objnam, err)
        except Exception:
            _LOGGER.exception("Failed to set value for %s", objnam)
