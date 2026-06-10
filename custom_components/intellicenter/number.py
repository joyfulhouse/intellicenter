"""Pentair Intellicenter numbers.

This module provides number entities for:
- IntelliChlor output percentage control (CONFIG)
- IntelliChem pH and ORP setpoint control (CONFIG)
- IntelliChem water chemistry configuration (ALK, CALC, CYACID) (CONFIG)
- Body max temperature setpoint (HITMP)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    ALK_ATTR,
    BODY_ATTR,
    BODY_TYPE,
    CALC_ATTR,
    CHEM_TYPE,
    CIRCUIT_ATTR,
    CYACID_ATTR,
    GPM_ATTR,
    HITMP_ATTR,
    MAX_ATTR,
    MAXF_ATTR,
    MIN_ATTR,
    MINF_ATTR,
    ORPSET_ATTR,
    PARENT_ATTR,
    PHSET_ATTR,
    PMPCIRC_TYPE,
    PRIM_ATTR,
    SEC_ATTR,
    SELECT_ATTR,
    SPEED_ATTR,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    PoolEntity,
    async_setup_pool_entities,
    body_temperature_limits,
)
from .const import CONST_GPM, CONST_RPM
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

# Temperature setpoint step; min/max come from body_temperature_limits() so the
# range follows the panel's METRIC/ENGLISH unit (40-104 F / 5-40 C).
TEMP_SETPOINT_STEP = 1

# Pump speed/flow ranges (defaults, actual limits come from pump MIN/MAX attributes)
PUMP_RPM_MIN_DEFAULT = 450
PUMP_RPM_MAX_DEFAULT = 3450
PUMP_RPM_STEP = 50

PUMP_GPM_MIN_DEFAULT = 15
PUMP_GPM_MAX_DEFAULT = 140
PUMP_GPM_STEP = 5

# -------------------------------------------------------------------------------------


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolNumber | PumpSpeedNumber]:
    """Build number entities for the given candidate pool objects."""
    # Materialize so the candidate objects can be iterated more than once below.
    candidate_objects = list(candidates)

    numbers: list[PoolNumber | PumpSpeedNumber] = []

    for pool_obj in candidate_objects:
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
                                mode=NumberMode.BOX,
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
                            mode=NumberMode.BOX,
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
                            mode=NumberMode.BOX,
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
    for pool_obj in candidate_objects:
        if pool_obj.objtype == BODY_TYPE and HITMP_ATTR in pool_obj.attribute_keys:
            numbers.append(
                PoolNumber(
                    coordinator,
                    pool_obj,
                    # min/max/unit are derived live from the panel's METRIC/
                    # ENGLISH mode via PoolNumber's temperature-aware
                    # properties; hardcoded Fahrenheit bounds made this entity
                    # unusable on METRIC systems (every valid Celsius setpoint
                    # was out of the 40-104 range).
                    step=TEMP_SETPOINT_STEP,
                    attribute_key=HITMP_ATTR,
                    name="+ Max Temperature",
                    icon="mdi:thermometer-high",
                    device_class=NumberDeviceClass.TEMPERATURE,
                    mode=NumberMode.BOX,
                    entity_category=EntityCategory.CONFIG,
                    integer_only=True,
                )
            )

    # Add pump circuit speed/flow setpoints (PMPCIRC) - CONFIG category
    # These allow control of variable speed pump settings per circuit
    for pool_obj in candidate_objects:
        if pool_obj.objtype == PMPCIRC_TYPE:
            # Get the parent pump to determine limits and type
            parent_objnam = pool_obj[PARENT_ATTR]
            parent_pump = coordinator.model[parent_objnam] if parent_objnam else None

            # Without the parent pump we cannot tell whether this circuit drives
            # an RPM-only, GPM-only, or dual-mode (VSF) pump. Building now would
            # lock in a guessed entity class and default limits that unique_id
            # de-duplication could never correct once the pump arrives. Skip and
            # let the coordinator re-dispatch this PMPCIRC when its parent pump
            # appears (issue #57), mirroring select.py's parent-capability guard.
            if parent_pump is None:
                continue

            # Get the associated circuit for naming
            circuit_objnam = pool_obj[CIRCUIT_ATTR]
            circuit = coordinator.model[circuit_objnam] if circuit_objnam else None
            circuit_name = (circuit.sname if circuit else None) or str(circuit_objnam)

            # Get limits from parent pump
            # Initialize RPM with defaults (most pumps support RPM)
            # Initialize GPM to 0 - only set if parent pump actually has MAXF_ATTR
            rpm_min = PUMP_RPM_MIN_DEFAULT
            rpm_max = PUMP_RPM_MAX_DEFAULT
            gpm_min = PUMP_GPM_MIN_DEFAULT
            gpm_max = 0  # Will be set from parent pump's MAXF_ATTR if supported

            if parent_pump:
                if MIN_ATTR in parent_pump.attribute_keys and parent_pump[MIN_ATTR]:
                    try:
                        rpm_min = int(parent_pump[MIN_ATTR])
                    except (ValueError, TypeError):
                        pass
                if MAX_ATTR in parent_pump.attribute_keys and parent_pump[MAX_ATTR]:
                    try:
                        rpm_max = int(parent_pump[MAX_ATTR])
                    except (ValueError, TypeError):
                        pass
                if MINF_ATTR in parent_pump.attribute_keys and parent_pump[MINF_ATTR]:
                    try:
                        val = int(parent_pump[MINF_ATTR])
                        if val > 0:
                            gpm_min = val
                    except (ValueError, TypeError):
                        pass
                if MAXF_ATTR in parent_pump.attribute_keys and parent_pump[MAXF_ATTR]:
                    try:
                        val = int(parent_pump[MAXF_ATTR])
                        if val > 0:
                            gpm_max = val
                    except (ValueError, TypeError):
                        pass

            # Determine pump capabilities from parent pump limits
            # VSF pumps have non-zero MAXF (flow) and MAX (RPM), supporting both modes
            # SPEED-only pumps (IntelliFlo VS) have MAX > 0 but MAXF = 0
            # FLOW-only pumps have MAXF > 0 but MAX = 0
            supports_rpm = rpm_max > 0
            supports_gpm = (
                gpm_max > 0
            )  # Only True if MAXF_ATTR was set from parent pump

            # Determine pump name for entity naming
            pump_name = (parent_pump.sname if parent_pump else None) or "Pump"

            if supports_rpm and supports_gpm:
                # VSF pump: Create single dynamic PumpSpeedNumber entity
                # that changes units/limits based on SELECT mode
                numbers.append(
                    PumpSpeedNumber(
                        coordinator,
                        pool_obj,
                        pump_name=pump_name,
                        circuit_name=circuit_name,
                        rpm_min=rpm_min,
                        rpm_max=rpm_max,
                        gpm_min=gpm_min,
                        gpm_max=gpm_max,
                    )
                )
            elif supports_rpm:
                # VS pump (RPM only): Create PoolNumber with SPEED attribute
                numbers.append(
                    PoolNumber(
                        coordinator,
                        pool_obj,
                        min_value=rpm_min,
                        max_value=rpm_max,
                        step=PUMP_RPM_STEP,
                        attribute_key=SPEED_ATTR,
                        name=f"+ RPM ({circuit_name})",
                        icon="mdi:speedometer",
                        unit_of_measurement=CONST_RPM,
                        mode=NumberMode.BOX,
                        entity_category=EntityCategory.CONFIG,
                        integer_only=True,
                    )
                )
            elif supports_gpm:
                # VF pump (GPM only): Create PoolNumber with GPM attribute
                numbers.append(
                    PoolNumber(
                        coordinator,
                        pool_obj,
                        min_value=gpm_min,
                        max_value=gpm_max,
                        step=PUMP_GPM_STEP,
                        attribute_key=GPM_ATTR,
                        name=f"+ GPM ({circuit_name})",
                        icon="mdi:water-pump",
                        unit_of_measurement=CONST_GPM,
                        mode=NumberMode.BOX,
                        entity_category=EntityCategory.CONFIG,
                        integer_only=True,
                    )
                )

    return numbers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool number entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


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
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement.

        Temperature entities report the panel's native unit (METRIC/ENGLISH)
        so Home Assistant converts the displayed value correctly.
        """
        if self._attr_device_class == NumberDeviceClass.TEMPERATURE:
            return self.pentairTemperatureSettings()
        return self._attr_native_unit_of_measurement

    @property
    def native_min_value(self) -> float:
        """Return the minimum value, panel-unit aware for temperatures."""
        if self._attr_device_class == NumberDeviceClass.TEMPERATURE:
            return body_temperature_limits(self.coordinator)[0]
        return self._attr_native_min_value

    @property
    def native_max_value(self) -> float:
        """Return the maximum value, panel-unit aware for temperatures."""
        if self._attr_device_class == NumberDeviceClass.TEMPERATURE:
            return body_temperature_limits(self.coordinator)[1]
        return self._attr_native_max_value

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


# -------------------------------------------------------------------------------------


class PumpSpeedNumber(PoolEntity, NumberEntity):
    """Dynamic pump speed setpoint that changes units/limits based on pump mode.

    VSF (Variable Speed/Flow) pumps use a unified setpoint model where the SPEED
    attribute holds either RPM or GPM value depending on the SELECT mode. This
    entity dynamically adjusts its unit of measurement, min/max values, and step
    size based on the current mode.

    When SELECT="RPM": shows RPM, limits from parent pump's MIN/MAX
    When SELECT="GPM": shows GPM, limits from parent pump's MINF/MAXF
    """

    _attr_icon = "mdi:speedometer"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        pump_name: str,
        circuit_name: str,
        rpm_min: int,
        rpm_max: int,
        gpm_min: int,
        gpm_max: int,
    ) -> None:
        """Initialize a pump speed number entity.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject (PMPCIRC) this entity represents
            pump_name: Name of the parent pump for entity naming
            circuit_name: Name of the circuit for entity naming
            rpm_min: Minimum RPM value (from parent pump MIN attribute)
            rpm_max: Maximum RPM value (from parent pump MAX attribute)
            gpm_min: Minimum GPM value (from parent pump MINF attribute)
            gpm_max: Maximum GPM value (from parent pump MAXF attribute)
        """
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=SPEED_ATTR,
            name=f"{pump_name} Speed ({circuit_name})",
        )

        self._rpm_min = rpm_min
        self._rpm_max = rpm_max
        self._gpm_min = gpm_min
        self._gpm_max = gpm_max

    @property
    def _current_mode(self) -> str:
        """Get current mode from SELECT attribute.

        Returns:
            "RPM" or "GPM" - defaults to "RPM" if not set
        """
        return str(self._pool_object[SELECT_ATTR] or "RPM")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement based on current mode."""
        return CONST_GPM if self._current_mode == "GPM" else CONST_RPM

    @property
    def native_min_value(self) -> float:
        """Return the minimum value based on current mode."""
        return float(self._gpm_min if self._current_mode == "GPM" else self._rpm_min)

    @property
    def native_max_value(self) -> float:
        """Return the maximum value based on current mode."""
        return float(self._gpm_max if self._current_mode == "GPM" else self._rpm_max)

    @property
    def native_step(self) -> float:
        """Return the step size based on current mode."""
        return float(PUMP_GPM_STEP if self._current_mode == "GPM" else PUMP_RPM_STEP)

    @property
    def native_value(self) -> int | None:
        """Return the current speed value, clamped to valid range for current mode.

        Uses the controller's get_pump_circuit_speed() method which handles
        the case where SELECT and SPEED updates arrive in separate NotifyList
        messages, preventing display of invalid values during mode transitions.
        """
        result: int | None = self._controller.get_pump_circuit_speed(
            self._pool_object.objnam
        )
        return result

    async def async_set_native_value(self, value: float) -> None:
        """Set the speed value via SPEED attribute."""
        self.request_changes({SPEED_ATTR: str(int(value))})

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if SPEED or SELECT changed.

        We need to update on SELECT changes because the unit of measurement
        and limits change when the mode switches.
        """
        if self._pool_object.objnam not in updates:
            return False
        changed = updates[self._pool_object.objnam]
        return SPEED_ATTR in changed or SELECT_ATTR in changed
