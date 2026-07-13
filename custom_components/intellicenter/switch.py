"""Pentair Intellicenter switches.

This module provides switch entities for pool circuits, bodies of water,
superchlorinate mode, and vacation mode.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    BODY_TYPE,
    BOOST_ATTR,
    CHEM_TYPE,
    CIRCGRP_TYPE,
    HEATER_ATTR,
    HTMODE_ATTR,
    SCHED_TYPE,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    SUPER_ATTR,
    SYSTEM_TYPE,
    VACFLO_ATTR,
    VOL_ATTR,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    OnOffControlMixin,
    PoolEntity,
    async_setup_pool_entities,
    is_user_circuit,
)
from .const import DNTSTP_ATTR, DOMAIN, MANHT_ATTR
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[SwitchEntity]:
    """Build switch entities for the given candidate pool objects."""
    switches: list[SwitchEntity] = []
    for pool_obj in candidates:
        if pool_obj.objtype == BODY_TYPE:
            switches.append(PoolBody(coordinator, pool_obj))
            switches.append(HeatBoostSwitch(coordinator, pool_obj))
            if pool_obj.subtype == "SPA":
                switches.append(ManualHeatSwitch(coordinator, pool_obj))
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
        elif is_user_circuit(pool_obj):
            if not (pool_obj.is_a_light or pool_obj.is_a_light_show):
                is_group = pool_obj.subtype == "CIRCGRP"
                switches.append(
                    PoolCircuit(
                        coordinator,
                        pool_obj,
                        icon=(
                            "mdi:alpha-g-box-outline"
                            if is_group
                            else "mdi:alpha-f-box-outline"
                        ),
                        enabled_by_default=pool_obj.is_featured or is_group,
                    )
                )
            switches.append(
                PoolCircuit(
                    coordinator,
                    pool_obj,
                    attribute_key=DNTSTP_ATTR,
                    name="+ Don't Stop",
                    icon="mdi:timer-off-outline",
                    enabled_by_default=False,
                    entity_category=EntityCategory.CONFIG,
                )
            )
        elif (
            pool_obj.objtype == CIRCGRP_TYPE
            and not coordinator.controller.circuit_group_has_color_lights(
                pool_obj.objnam
            )
        ):
            switches.append(PoolCircuitGroup(coordinator, pool_obj))
        elif pool_obj.objtype == SCHED_TYPE:
            switches.append(PoolSchedule(coordinator, pool_obj))
        elif pool_obj.objtype == SYSTEM_TYPE:
            # Vacation mode uses convenience method
            switches.append(PoolVacation(coordinator, pool_obj))
    return switches


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load Pentair switch entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


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
        entity_category: EntityCategory | None = None,
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
        if entity_category is not None:
            self._attr_entity_category = entity_category

    @property
    def is_on(self) -> bool | None:
        """Return circuit state, or unknown for missing/malformed values."""
        value = self._pool_object[self._attribute_key]
        if value not in (STATUS_ON, STATUS_OFF):
            return None
        return bool(value == STATUS_ON)


class PoolSchedule(PoolCircuit):
    """Representation of a schedule's enabled state."""

    _attr_icon = "mdi:calendar-check"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a schedule enable switch."""
        super().__init__(coordinator, pool_object, enabled_by_default=False)

    @property
    def name(self) -> str:
        """Return the schedule display name."""
        return f"Schedule ({self._pool_object.sname or 'Unknown'})"

    @property
    def is_on(self) -> bool | None:
        """Return whether the schedule is enabled."""
        if self._pool_object[STATUS_ATTR] not in (STATUS_ON, STATUS_OFF):
            return None
        return bool(self._controller.is_schedule_enabled(self._pool_object.objnam))


class PoolCircuitGroup(PoolCircuit):
    """Representation of a true CIRCGRP without color lights."""

    _attr_icon = "mdi:alpha-g-box-outline"

    @property
    def is_on(self) -> bool | None:
        """Return group power state, or unknown for an invalid panel value."""
        if self._optimistic_state is not None:
            return self._optimistic_state
        status = self._pool_object[STATUS_ATTR]
        if not isinstance(status, str) or status not in (STATUS_ON, STATUS_OFF):
            return None
        return status == STATUS_ON

    def _member_objnams(self) -> list[str]:
        """Return current member circuit identifiers or raise if unavailable."""
        members = self._controller.get_circuits_in_group(self._pool_object.objnam)
        objnams = [member.objnam for member in members]
        if not objnams:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="circuit_group_members_missing",
            )
        return objnams

    async def _async_set_group_state(self, state: bool) -> None:
        """Atomically set every circuit referenced by the group."""
        member_objnams = self._member_objnams()
        self._optimistic_state = state
        self.async_write_ha_state()
        try:
            await self._async_execute_command(
                self._controller.set_multiple_circuit_states(member_objnams, state)
            )
        except HomeAssistantError:
            self._clear_optimistic_state()
            self.async_write_ha_state()
            raise

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on every member circuit."""
        await self._async_set_group_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off every member circuit."""
        await self._async_set_group_state(False)


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


class ManualHeatSwitch(PoolEntity, SwitchEntity):
    """Spa Manual Heat configuration switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:heat-wave"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize Spa Manual Heat."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=MANHT_ATTR,
            name="+ Manual Heat",
        )

    @property
    def is_on(self) -> bool | None:
        """Return the configured state, or unknown if it has not synchronized."""
        value = self._pool_object[self._attribute_key]
        if value not in (STATUS_ON, STATUS_OFF):
            return None
        return bool(value == STATUS_ON)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Spa Manual Heat."""
        await self._async_set_manual_heat(STATUS_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Spa Manual Heat."""
        await self._async_set_manual_heat(STATUS_OFF)

    async def _async_set_manual_heat(self, value: str) -> None:
        """Write MANHT and translate protocol failures."""
        try:
            await self._async_execute_command(
                self._controller.request_changes(
                    self._pool_object.objnam, {MANHT_ATTR: value}
                )
            )
        except HomeAssistantError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
            ) from err


class HeatBoostSwitch(PoolCircuit):
    """Disabled-by-default heat boost control for a body of water."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:heat-wave"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a body heat boost switch."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=BOOST_ATTR,
            name="+ Heat Boost",
            enabled_by_default=False,
        )

    @property
    def is_on(self) -> bool | None:
        """Map only canonical ON/OFF values and reject malformed states."""
        if self._optimistic_state is not None:
            return self._optimistic_state
        value = self._pool_object[self._attribute_key]
        if value == STATUS_ON:
            return True
        if value == STATUS_OFF:
            return False
        return None


class PoolVacation(PoolEntity, SwitchEntity):
    """Representation of vacation mode using convenience methods.

    Uses pyintellicenter set_vacation_mode() for control operations.
    This is a configuration entity that controls system-wide vacation behavior.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:palm-tree"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = True

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
        await self._async_set_vacation_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable vacation mode using convenience method."""
        await self._async_set_vacation_mode(False)

    async def _async_set_vacation_mode(self, state: bool) -> None:
        """Write vacation mode optimistically, reverting if the command fails."""
        self._optimistic_state = state
        self.async_write_ha_state()
        try:
            await self._async_execute_command(self._controller.set_vacation_mode(state))
        except HomeAssistantError:
            # The panel never received the change: drop the optimistic state so
            # the UI snaps back to reality, then surface the error to the call.
            self._clear_optimistic_state()
            self.async_write_ha_state()
            raise
