"""Pentair Intellicenter water heaters.

This module provides water heater entities for pool and spa heating control.
Supports multiple heater types (gas, solar, heat pump) and remembers the
last used heater for convenient turn-on operations.

Multi-mode heaters (subtype HCOMBO, e.g. Pentair UltraTemp ETi Hybrid) require
MODE-based control instead of HEATER assignment. IntelliCenter ignores HEATER
attribute changes for HCOMBO heaters; the body's MODE attribute must be set to
a HeaterType value (e.g. HYBRID_DUAL=10) to activate heating.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from pyintellicenter import (
    BODY_ATTR,
    BODY_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    LISTORD_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MODE_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    STATUS_OFF,
    HeaterType,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity
from .coordinator import IntelliCenterCoordinator

# IntelliCenter subtype for multi-mode combo heaters (e.g. UltraTemp ETi Hybrid)
_HCOMBO_SUBTYPE = "HCOMBO"

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool water heater entities based on a config entry."""
    coordinator = entry.runtime_data

    # here we try to figure out which heater, if any, can be used for a given
    # body of water

    # first find all heaters
    # and sort them by their UI order (if they don't have one, use 100 and place them last)
    heaters = sorted(
        coordinator.model.get_by_type(HEATER_TYPE),
        key=lambda h: int(h[LISTORD_ATTR]) if h[LISTORD_ATTR] else 100,
    )

    bodies = coordinator.model.get_by_type(BODY_TYPE)

    water_heaters = []
    body: PoolObject
    for body in bodies:
        heater_list = []
        heater: PoolObject
        for heater in heaters:
            # if the heater supports this body, add it to the list
            if body.objnam in heater[BODY_ATTR].split(" "):
                heater_list.append(heater.objnam)
        if heater_list:
            water_heaters.append(PoolWaterHeater(coordinator, body, heater_list))

    async_add_entities(water_heaters)


# -------------------------------------------------------------------------------------


class PoolWaterHeater(PoolEntity, WaterHeaterEntity, RestoreEntity):
    """Representation of a Pentair water heater."""

    LAST_HEATER_ATTR = "LAST_HEATER"
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        heater_list: list[str],
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            pool_object,
            extra_state_attributes=[HEATER_ATTR, HTMODE_ATTR],
        )
        self._heater_list = heater_list
        self._last_heater: str | None = self._pool_object[HEATER_ATTR]
        self._is_multimode: bool = self._detect_multimode()

    def _detect_multimode(self) -> bool:
        """Return True if any heater in this entity's list is a multi-mode (HCOMBO) heater."""
        for heater_id in self._heater_list:
            heater_obj = self.coordinator.model[heater_id]
            if heater_obj is not None and heater_obj.subtype == _HCOMBO_SUBTYPE:
                return True
        return False

    @property
    def _is_heater_active(self) -> bool:
        """Return True if the body is on and a heater is assigned or mode is active."""
        if self._pool_object[STATUS_ATTR] == STATUS_OFF:
            return False
        if self._pool_object[HEATER_ATTR] != NULL_OBJNAM:
            return True
        if self._is_multimode:
            mode = self._pool_object[MODE_ATTR]
            return bool(mode and mode not in ("0", "1"))
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the entity."""
        state_attributes = super().extra_state_attributes

        if self._last_heater != NULL_OBJNAM:
            state_attributes[self.LAST_HEATER_ATTR] = self._last_heater

        if self._is_heater_active:
            htmode = self._pool_object[HTMODE_ATTR]
            state_attributes["heating_status"] = "heating" if htmode != "0" else "idle"

        return state_attributes

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        base_id = super().unique_id
        return f"{base_id}{LOTMP_ATTR}"

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Return the list of supported features."""
        return (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return self.pentairTemperatureSettings()

    @property
    def min_temp(self) -> float:
        """Return the minimum value."""
        system_info = self.coordinator.system_info
        return 5.0 if system_info and system_info.uses_metric else 4.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        system_info = self.coordinator.system_info
        return 40.0 if system_info and system_info.uses_metric else 104.0

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._safe_float_conversion(self._pool_object[LSTTMP_ATTR])

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._safe_float_conversion(self._pool_object[LOTMP_ATTR])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures using convenience method."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if target_temperature is not None:
            try:
                temp_value = int(target_temperature)
                # Use pyintellicenter convenience method
                await self._controller.set_setpoint(
                    self._pool_object.objnam, temp_value
                )
            except (ValueError, TypeError):
                _LOGGER.exception("Invalid temperature value '%s'", target_temperature)

    @property
    def current_operation(self) -> str:
        """Return current operation.

        This reflects the configured heater mode, independent of whether the
        body is currently running (STATUS). A user can pre-select a heater for
        a body even when it's off (e.g., setting the Spa heater while in Pool
        mode). The real-time heating activity is exposed via the heating_status
        extra state attribute.

        For multi-mode (HCOMBO) heaters, operation is controlled via MODE_ATTR
        on the body rather than HEATER_ATTR assignment.
        """
        heater = self._pool_object[HEATER_ATTR]
        if heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if heater_obj is not None and heater_obj.sname is not None:
                return str(heater_obj.sname)
        if self._is_multimode:
            mode = self._pool_object[MODE_ATTR]
            if mode and mode not in ("0", "1"):
                heater_obj = self.coordinator.model[self._heater_list[0]]
                if heater_obj is not None and heater_obj.sname is not None:
                    return str(heater_obj.sname)
        return str(STATE_OFF)

    @property
    def operation_list(self) -> list[str]:
        """Return the list of available operation modes."""
        operations: list[str] = [str(STATE_OFF)]
        for heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if heater_obj is not None and heater_obj.sname is not None:
                operations.append(heater_obj.sname)
        return operations

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        if operation_mode == STATE_OFF:
            self._turn_off()
        elif self._is_multimode:
            self.request_changes({MODE_ATTR: str(HeaterType.HYBRID_DUAL.value)})
        else:
            for heater in self._heater_list:
                heater_obj = self.coordinator.model[heater]
                if heater_obj is not None and operation_mode == heater_obj.sname:
                    self.request_changes({HEATER_ATTR: heater})
                    break

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        if self._is_multimode:
            self.request_changes({MODE_ATTR: str(HeaterType.HYBRID_DUAL.value)})
        else:
            heater = (
                self._last_heater
                if self._last_heater and self._last_heater != NULL_OBJNAM
                else self._heater_list[0]
            )
            self.request_changes({HEATER_ATTR: heater})

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        self._turn_off()

    def _turn_off(self) -> None:
        """Turn off the water heater."""
        if self._is_multimode:
            self.request_changes({MODE_ATTR: str(HeaterType.OFF.value)})
        else:
            self.request_changes({HEATER_ATTR: NULL_OBJNAM})

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        updated = self._check_attributes_updated(
            updates, STATUS_ATTR, HEATER_ATTR, HTMODE_ATTR, LOTMP_ATTR, LSTTMP_ATTR, MODE_ATTR
        )

        if updated and self._pool_object[HEATER_ATTR] != NULL_OBJNAM:
            self._last_heater = self._pool_object[HEATER_ATTR]

        return updated

    async def async_added_to_hass(self) -> None:
        """Entity is added to Home Assistant."""
        await super().async_added_to_hass()

        if self._last_heater == NULL_OBJNAM:
            # Our current state is OFF so
            # let's see if we find a previous value stored in our state
            last_state = await self.async_get_last_state()

            if last_state:
                value = last_state.attributes.get(self.LAST_HEATER_ATTR)
                if value and value != NULL_OBJNAM:
                    self._last_heater = value
