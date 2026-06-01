"""Pentair Intellicenter select entities.

This module provides select entities for pump circuit mode selection
(RPM vs GPM for variable speed/flow pumps).
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    CIRCUIT_ATTR,
    MAX_ATTR,
    MAXF_ATTR,
    PARENT_ATTR,
    PMPCIRC_TYPE,
    SELECT_ATTR,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity, async_setup_pool_entities
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# Pump mode options
PUMP_MODE_RPM = "RPM"
PUMP_MODE_GPM = "GPM"
PUMP_MODES = [PUMP_MODE_RPM, PUMP_MODE_GPM]


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PumpModeSelect]:
    """Build pump-mode select entities for the given candidate pool objects."""
    selects: list[PumpModeSelect] = []

    pool_obj: PoolObject
    for pool_obj in candidates:
        # Create pump mode selector only for PMPCIRC objects where the parent pump
        # supports BOTH RPM (MAX_ATTR > 0) and GPM (MAXF_ATTR > 0) modes
        if pool_obj.objtype == PMPCIRC_TYPE and SELECT_ATTR in pool_obj.attribute_keys:
            # Get the parent pump to check capabilities
            parent_objnam = pool_obj[PARENT_ATTR]
            parent_pump = coordinator.model[parent_objnam] if parent_objnam else None

            # Check if parent pump supports both RPM and GPM
            supports_rpm = False
            supports_gpm = False
            if parent_pump:
                # Check MAX_ATTR for RPM support
                if MAX_ATTR in parent_pump.attribute_keys and parent_pump[MAX_ATTR]:
                    try:
                        supports_rpm = int(parent_pump[MAX_ATTR]) > 0
                    except (ValueError, TypeError):
                        pass
                # Check MAXF_ATTR for GPM support
                if MAXF_ATTR in parent_pump.attribute_keys and parent_pump[MAXF_ATTR]:
                    try:
                        supports_gpm = int(parent_pump[MAXF_ATTR]) > 0
                    except (ValueError, TypeError):
                        pass

            # Only create selector if pump supports both modes
            if not (supports_rpm and supports_gpm):
                continue

            # Get the associated circuit for naming
            circuit_objnam = pool_obj[CIRCUIT_ATTR]
            circuit = coordinator.model[circuit_objnam] if circuit_objnam else None
            circuit_name = circuit.sname if circuit else circuit_objnam

            # Get pump name from parent pump (PMPCIRC objects don't have meaningful sname)
            pump_name = parent_pump.sname if parent_pump else "Pump"

            selects.append(
                PumpModeSelect(
                    coordinator,
                    pool_obj,
                    pump_name=pump_name,
                    circuit_name=circuit_name,
                )
            )

    return selects


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load Pentair select entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


class PumpModeSelect(PoolEntity, SelectEntity):
    """Select entity for pump circuit mode (RPM/GPM)."""

    _attr_icon = "mdi:swap-horizontal"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        pump_name: str,
        circuit_name: str,
    ) -> None:
        """Initialize the pump mode select entity."""
        super().__init__(coordinator, pool_object)
        self._pump_name = pump_name
        self._circuit_name = circuit_name
        self._attr_options = PUMP_MODES

    @property
    def unique_id(self) -> str:
        """Return a unique id for the entity."""
        return f"{self._entry_id}_{self._pool_object.objnam}_{SELECT_ATTR}"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self._pump_name} Mode ({self._circuit_name})"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        value = self._pool_object[SELECT_ATTR]
        if value is not None and str(value) in PUMP_MODES:
            return str(value)
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option and refresh speed value.

        After changing the pump mode, we proactively request the fresh SPEED
        value from IntelliCenter. This ensures the PumpSpeedNumber entity
        displays the correct value immediately rather than waiting for
        IntelliCenter to push the update (which may come in a separate message).
        """
        if option not in PUMP_MODES:
            _LOGGER.warning("Invalid pump mode option: %s", option)
            return

        self.request_changes({SELECT_ATTR: option})

        # Request fresh SPEED value after mode change
        # This triggers an update that will be pushed to PumpSpeedNumber
        await self._controller.refresh_pump_circuit_speed(self._pool_object.objnam)

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        if self._pool_object.objnam not in updates:
            return False
        return SELECT_ATTR in updates[self._pool_object.objnam]
