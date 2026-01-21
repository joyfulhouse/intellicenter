"""Pentair IntelliCenter climate entities for pool/spa temperature control.

This module provides climate entities for bodies of water (pool/spa) that have
heat pumps capable of both heating AND cooling (UltraTemp systems). For bodies
with heating-only equipment (gas heaters, solar), use the water_heater entity.

Climate entities support:
- Dual setpoints (heating and cooling)
- HVAC modes: heat, cool, heat_cool, off
- Current temperature monitoring
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_ATTR,
    BODY_TYPE,
    HEATER_ATTR,
    HEATER_TYPE,
    HITMP_ATTR,
    HTMODE_ATTR,
    LISTORD_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    STATUS_OFF,
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
    """Set up climate entities for bodies with cooling support."""
    coordinator = entry.runtime_data

    # Find all heaters sorted by UI order
    heaters = sorted(
        coordinator.model.get_by_type(HEATER_TYPE),
        key=lambda h: int(h[LISTORD_ATTR]) if h[LISTORD_ATTR] else 100,
    )

    bodies = coordinator.model.get_by_type(BODY_TYPE)

    climate_entities = []
    body: PoolObject
    for body in bodies:
        # Check if this body supports cooling (has UltraTemp heat pump)
        if not coordinator.controller.body_supports_cooling(body.objnam):
            continue

        # Build list of heaters that support this body
        heater_list = []
        heater: PoolObject
        for heater in heaters:
            if body.objnam in heater[BODY_ATTR].split(" "):
                heater_list.append(heater.objnam)

        if heater_list:
            climate_entities.append(PoolClimate(coordinator, body, heater_list))

    async_add_entities(climate_entities)


class PoolClimate(PoolEntity, ClimateEntity):
    """Climate entity for pool/spa with heating and cooling support.

    This entity is created for bodies of water that have UltraTemp heat pumps,
    which can both heat and cool water. It exposes dual setpoints:
    - target_temperature_low: Heating setpoint (LOTMP) - heat UP to this temp
    - target_temperature_high: Cooling setpoint (HITMP) - cool DOWN to this temp
    """

    _attr_icon = "mdi:thermometer-water"
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        heater_list: list[str],
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(
            coordinator,
            pool_object,
            extra_state_attributes=[HEATER_ATTR, HTMODE_ATTR],
        )
        self._heater_list = heater_list
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
        ]

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        base_id = super().unique_id
        return f"{base_id}_climate"

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return self.pentairTemperatureSettings()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        system_info = self.coordinator.system_info
        return 5.0 if system_info and system_info.uses_metric else 40.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        system_info = self.coordinator.system_info
        return 40.0 if system_info and system_info.uses_metric else 104.0

    @property
    def current_temperature(self) -> float | None:
        """Return the current water temperature."""
        return self._safe_float_conversion(self._pool_object[LSTTMP_ATTR])

    @property
    def target_temperature_low(self) -> float | None:
        """Return the heating setpoint (temperature to heat UP to)."""
        return self._safe_float_conversion(self._pool_object[LOTMP_ATTR])

    @property
    def target_temperature_high(self) -> float | None:
        """Return the cooling setpoint (temperature to cool DOWN to)."""
        return self._safe_float_conversion(self._pool_object[HITMP_ATTR])

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        status = self._pool_object[STATUS_ATTR]
        heater = self._pool_object[HEATER_ATTR]

        # If body is off or no heater assigned, mode is OFF
        if status == STATUS_OFF or heater == NULL_OBJNAM:
            return HVACMode.OFF

        # Check the heat mode to determine if heating/cooling is enabled
        htmode = self._pool_object[HTMODE_ATTR]
        if htmode == "0":
            return HVACMode.OFF

        # When heater is active, default to heat_cool mode
        # IntelliCenter manages the actual heating vs cooling decision
        return HVACMode.HEAT_COOL

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action."""
        status = self._pool_object[STATUS_ATTR]
        heater = self._pool_object[HEATER_ATTR]

        if status == STATUS_OFF or heater == NULL_OBJNAM:
            return HVACAction.OFF

        htmode = self._pool_object[HTMODE_ATTR]
        if htmode == "0":
            return HVACAction.IDLE

        # Check if actively heating
        if self._controller.is_body_heating(self._pool_object.objnam):
            return HVACAction.HEATING

        # Could add cooling detection here if IntelliCenter exposes it
        # For now, return IDLE when heater is enabled but not actively heating
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            self.request_changes({HEATER_ATTR: NULL_OBJNAM})
        else:
            # Turn on heating/cooling by selecting the first available heater
            if self._heater_list:
                self.request_changes({HEATER_ATTR: self._heater_list[0]})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures."""
        low_temp = kwargs.get(ATTR_TEMPERATURE + "_low")
        high_temp = kwargs.get(ATTR_TEMPERATURE + "_high")

        if low_temp is not None:
            try:
                temp_value = int(low_temp)
                await self._controller.set_heating_setpoint(
                    self._pool_object.objnam, temp_value
                )
            except (ValueError, TypeError):
                _LOGGER.exception("Invalid heating setpoint value '%s'", low_temp)

        if high_temp is not None:
            try:
                temp_value = int(high_temp)
                await self._controller.set_cooling_setpoint(
                    self._pool_object.objnam, temp_value
                )
            except (ValueError, TypeError):
                _LOGGER.exception("Invalid cooling setpoint value '%s'", high_temp)

    async def async_turn_on(self) -> None:
        """Turn on the climate entity."""
        if self._heater_list:
            self.request_changes({HEATER_ATTR: self._heater_list[0]})

    async def async_turn_off(self) -> None:
        """Turn off the climate entity."""
        self.request_changes({HEATER_ATTR: NULL_OBJNAM})

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated."""
        my_updates = updates.get(self._pool_object.objnam, {})
        return bool(
            my_updates
            and {
                STATUS_ATTR,
                HEATER_ATTR,
                HTMODE_ATTR,
                LOTMP_ATTR,
                HITMP_ATTR,
                LSTTMP_ATTR,
            }
            & my_updates.keys()
        )
