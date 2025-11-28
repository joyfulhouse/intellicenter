"""Pentair Intellicenter switches.

This module provides switch entities for pool circuits, bodies of water,
superchlorinate mode, and vacation mode.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_ATTR,
    HTMODE_ATTR,
    STATUS_ATTR,
    SUPER_ATTR,
    SYSTEM_TYPE,
    VACFLO_ATTR,
    VOL_ATTR,
    PoolObject,
)

from . import IntelliCenterConfigEntry, OnOffControlMixin, PoolEntity
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load Pentair switch entities based on a config entry."""
    coordinator = entry.runtime_data

    switches: list[PoolCircuit] = []

    pool_obj: PoolObject
    for pool_obj in coordinator.model:
        if pool_obj.objtype == BODY_TYPE:
            switches.append(PoolBody(coordinator, pool_obj))
        elif (
            pool_obj.objtype == CHEM_TYPE
            and pool_obj.subtype == "ICHLOR"
            and SUPER_ATTR in pool_obj.attribute_keys
        ):
            switches.append(
                PoolCircuit(
                    coordinator,
                    pool_obj,
                    attribute_key=SUPER_ATTR,
                    name="+ Superchlorinate",
                    icon="mdi:alpha-s-box-outline",
                )
            )
        elif (
            pool_obj.objtype == CIRCUIT_TYPE
            and not (pool_obj.is_a_light or pool_obj.is_a_light_show)
            and pool_obj.is_featured
        ):
            switches.append(
                PoolCircuit(coordinator, pool_obj, icon="mdi:alpha-f-box-outline")
            )
        elif pool_obj.objtype == CIRCUIT_TYPE and pool_obj.subtype == "CIRCGRP":
            switches.append(
                PoolCircuit(coordinator, pool_obj, icon="mdi:alpha-g-box-outline")
            )
        elif pool_obj.objtype == SYSTEM_TYPE:
            # Vacation mode uses convenience method
            switches.append(PoolVacation(coordinator, pool_obj))

    async_add_entities(switches)


class PoolCircuit(PoolEntity, OnOffControlMixin, SwitchEntity):
    """Representation of a standard pool circuit.

    Uses OnOffControlMixin for is_on, async_turn_on, async_turn_off.
    PoolEntity must come first to provide request_changes for the mixin.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        attribute_key: str | None = None,
        name: str | None = None,
        icon: str | None = None,
        enabled_by_default: bool = True,
    ) -> None:
        """Initialize a pool circuit switch."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=attribute_key or STATUS_ATTR,
            name=name,
            icon=icon,
            enabled_by_default=enabled_by_default,
        )


class PoolBody(PoolCircuit):
    """Representation of a body of water."""

    _attr_icon = "mdi:pool"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a Pool body from the underlying circuit."""
        super().__init__(coordinator, pool_object)
        self._extra_state_attrs = {VOL_ATTR, HEATER_ATTR, HTMODE_ATTR}


class PoolVacation(PoolEntity, SwitchEntity):
    """Representation of vacation mode using convenience methods.

    Uses pyintellicenter set_vacation_mode() for control operations.
    This is a configuration entity that controls system-wide vacation behavior.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:palm-tree"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = True
    _optimistic_state: bool | None = None

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize vacation mode switch."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=VACFLO_ATTR,
            name="Vacation mode",
        )

    @property
    def is_on(self) -> bool:
        """Return true if vacation mode is enabled."""
        if self._optimistic_state is not None:
            return self._optimistic_state
        return bool(self._controller.is_vacation_mode())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable vacation mode using convenience method."""
        self._optimistic_state = True
        self.async_write_ha_state()
        await self._controller.set_vacation_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable vacation mode using convenience method."""
        self._optimistic_state = False
        self.async_write_ha_state()
        await self._controller.set_vacation_mode(False)

    @callback
    def _clear_optimistic_state(self) -> None:
        """Clear optimistic state when real update is received."""
        self._optimistic_state = None
