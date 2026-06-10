"""Pentair Intellicenter water heaters.

This module provides water heater entities for pool and spa heating control.
A single :class:`PoolWaterHeater` models three kinds of body uniformly:

* **pure-standard** — only standard heaters (gas/solar/heat pump) are wired to
  the body. They are selected by assigning ``HEATER=<objnam>``; the panel derives
  the body ``MODE``.
* **pure-HCOMBO** — only a multi-mode combo heater (subtype HCOMBO, e.g. Pentair
  UltraTemp ETi Hybrid) is wired. IntelliCenter ignores ``HEATER`` assignments for
  HCOMBO heaters; instead the body ``MODE`` attribute must be written to a
  :class:`HeaterType` value. HCOMBO heaters expose all four sub-modes (Gas Only,
  Heat Pump Only, Hybrid, Dual) as distinct operation modes.
* **mixed** — the body's heater list contains BOTH an HCOMBO heater AND one or
  more standard heaters. Operations from both planes appear in the dropdown.

Every operation label resolves to a single atomic body write via
:meth:`PoolWaterHeater._operation_to_changes`, which sets the chosen control
plane and clears the opposite plane where safe. ``current_operation`` gives an
assigned standard heater precedence over the HCOMBO ``MODE`` so the reported
state stays correct even if one plane is momentarily stale after a switch. The
last non-off operation is remembered (and restored across restarts) so turn-on
returns the body to its previous mode.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from pyintellicenter import (
    HEATER_ATTR,
    HTMODE_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MODE_ATTR,
    NULL_OBJNAM,
    STATUS_ATTR,
    STATUS_OFF,
    HeaterType,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    PoolEntity,
    async_setup_pool_entities,
    bodies_affected_by,
    body_temperature_limits,
    heaters_for_body,
)
from .coordinator import IntelliCenterCoordinator

# IntelliCenter subtype for multi-mode combo heaters (e.g. UltraTemp ETi Hybrid)
_HCOMBO_SUBTYPE = "HCOMBO"

# Display labels for each HCOMBO mode shown in the operation dropdown
_HCOMBO_MODE_LABELS: dict[HeaterType, str] = {
    HeaterType.HYBRID_GAS: "Gas Only",
    HeaterType.HYBRID_ULTRA_TEMP: "Heat Pump Only",
    HeaterType.HYBRID_HYBRID: "Hybrid",
    HeaterType.HYBRID_DUAL: "Dual",
}
_HCOMBO_LABEL_TO_MODE: dict[str, HeaterType] = {
    label: mode for mode, label in _HCOMBO_MODE_LABELS.items()
}

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolWaterHeater]:
    """Build water heater entities for bodies affected by the candidate objects.

    A water heater belongs to a body of water but its existence depends on the
    heaters wired to that body. A body is therefore (re)considered when the body
    itself is a candidate OR when a candidate heater serves it, so that adding a
    heater to an existing body surfaces a water heater entity too. Duplicate
    entities for already-known bodies are filtered out by the caller via
    ``unique_id``; an existing entity keeps its (live) heater composition up to
    date itself (issue #57).
    """
    water_heaters: list[PoolWaterHeater] = []
    for body in bodies_affected_by(coordinator, candidates):
        heater_list = heaters_for_body(coordinator, body.objnam)
        if heater_list:
            water_heaters.append(PoolWaterHeater(coordinator, body, heater_list))

    return water_heaters


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool water heater entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


# -------------------------------------------------------------------------------------


class PoolWaterHeater(PoolEntity, WaterHeaterEntity, RestoreEntity):
    """Representation of a Pentair water heater."""

    LAST_OPERATION_ATTR = "LAST_OPERATION"
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
        # The heaters wired to this body are derived live from the model (see
        # `_heater_list`), so a heater added to an existing body is reflected on
        # the next coordinator update without rebuilding the entity (issue #57).
        # The list supplied at construction is retained only as a fallback for
        # the (rare) case where the live model cannot be enumerated.
        self._seed_heater_list = heater_list
        # Remember the last non-off operation so turn-on can restore it. None
        # means the body is currently off (nothing to restore yet).
        self._last_operation: str | None = self.current_operation
        if self._last_operation == STATE_OFF:
            self._last_operation = None

    @property
    def _heater_list(self) -> list[str]:
        """Return the heaters wired to this body, derived from the live model.

        Recomputed on each access so the entity reflects heaters added to (or
        removed from) its body at runtime (issue #57). Falls back to the list
        captured at construction if the live model yields nothing, which keeps
        behaviour stable when the model is not enumerable.
        """
        live = heaters_for_body(self.coordinator, self._pool_object.objnam)
        return live if live else self._seed_heater_list

    @property
    def _is_multimode(self) -> bool:
        """Return True if any heater wired to this body is a multi-mode (HCOMBO) heater.

        Derived from the live heater list so it tracks heaters added at runtime.
        """
        for heater_id in self._heater_list:
            heater_obj = self.coordinator.model[heater_id]
            if heater_obj is not None and heater_obj.subtype == _HCOMBO_SUBTYPE:
                return True
        return False

    def _current_hcombo_mode(self) -> HeaterType | None:
        """Return the active HCOMBO HeaterType, or None if off or not applicable."""
        if not self._is_multimode:
            return None
        mode = self._pool_object[MODE_ATTR]
        if mode:
            try:
                ht = HeaterType(int(mode))
            except ValueError:
                return None
            if ht in _HCOMBO_MODE_LABELS:
                return ht
        return None

    def _operation_to_changes(self, operation: str) -> dict[str, str] | None:
        """Resolve an operation label to the atomic body changes that select it.

        Returns None if the label is not a known operation for this body. HCOMBO
        sub-mode labels are only honoured on multimode bodies, so a standard heater
        whose name happens to match an HCOMBO label is never misrouted to the MODE
        plane on a non-multimode body. (On a multimode body an HCOMBO sub-mode label
        takes precedence over an identically-named standard heater — a pathological
        config; operation_list de-dupes so it is never shown twice.)
        """
        if operation == STATE_OFF:
            return {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)}
        if self._is_multimode:
            heater_type = _HCOMBO_LABEL_TO_MODE.get(operation)
            if heater_type is not None:
                # HCOMBO sub-mode: set the body MODE and clear any standard heater
                # assignment so the standard-heater-precedence in current_operation
                # reflects the HCOMBO mode. HEATER=NULL is safe (turn-off writes it too).
                return {MODE_ATTR: str(heater_type.value), HEATER_ATTR: NULL_OBJNAM}
        for heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if heater_obj is not None and operation == heater_obj.sname:
                # Standard heater: assign it. We intentionally do NOT write MODE here
                # (MODE=OFF would disable heating; the correct MODE depends on the
                # heater's type and the panel derives it). current_operation prefers an
                # assigned standard heater over a possibly-stale HCOMBO MODE.
                return {HEATER_ATTR: heater}
        return None

    def _default_on_operation(self) -> str:
        """Return a safe default operation label for turn-on with no last operation."""
        if self._is_multimode:
            # Economical default: heat pump only (NOT Dual, which runs gas + heat
            # pump together).
            return _HCOMBO_MODE_LABELS[HeaterType.HYBRID_ULTRA_TEMP]
        for heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if (
                heater_obj is not None
                and heater_obj.sname is not None
                and heater_obj.subtype != _HCOMBO_SUBTYPE
            ):
                return str(heater_obj.sname)
        # Fall back to the first heater's sname if no standard heater is found.
        first = self.coordinator.model[self._heater_list[0]]
        return str(first.sname) if first is not None else STATE_OFF

    @property
    def _is_heater_active(self) -> bool:
        """Return True if a heat mode/heater is selected and the body is on."""
        if self._pool_object[STATUS_ATTR] == STATUS_OFF:
            return False
        # str() pins the comparison operand to str so the result is a concrete
        # bool (HA's STATE_OFF is loosely typed and would otherwise widen to Any).
        return self.current_operation != str(STATE_OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the entity."""
        state_attributes = super().extra_state_attributes

        if self._last_operation is not None:
            state_attributes[self.LAST_OPERATION_ATTR] = self._last_operation

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
        return body_temperature_limits(self.coordinator)[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return body_temperature_limits(self.coordinator)[1]

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
            except (ValueError, TypeError) as err:
                raise HomeAssistantError(
                    f"Invalid temperature value '{target_temperature}'"
                ) from err
            # Library and connection failures surface as HomeAssistantError so
            # the service call reports a clean error instead of silently
            # logging while the UI snaps back.
            await self._async_execute_command(
                self._controller.set_setpoint(self._pool_object.objnam, temp_value)
            )

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
        # An assigned standard (non-HCOMBO) heater takes precedence. This also makes
        # the state correct when a stale HCOMBO MODE remains after switching to a
        # standard heater on a mixed body.
        heater = self._pool_object[HEATER_ATTR]
        if heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if (
                heater_obj is not None
                and heater_obj.sname is not None
                and heater_obj.subtype != _HCOMBO_SUBTYPE
            ):
                return str(heater_obj.sname)
        if self._is_multimode:
            mode = self._current_hcombo_mode()
            if mode is not None:
                return _HCOMBO_MODE_LABELS[mode]
        return str(STATE_OFF)

    @property
    def operation_list(self) -> list[str]:
        """Return the list of available operation modes."""
        operations: list[str] = [str(STATE_OFF)]
        if self._is_multimode:
            operations.extend(_HCOMBO_MODE_LABELS.values())
        # Always include standard (non-HCOMBO) heaters — handles pure standard and
        # mixed bodies. Skip a standard heater whose name collides with an HCOMBO
        # label already listed (so the dropdown never shows a duplicate entry).
        for heater in self._heater_list:
            heater_obj = self.coordinator.model[heater]
            if (
                heater_obj is not None
                and heater_obj.sname is not None
                and heater_obj.subtype != _HCOMBO_SUBTYPE
                and heater_obj.sname not in operations
            ):
                operations.append(heater_obj.sname)
        return operations

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        changes = self._operation_to_changes(operation_mode)
        if changes is None:
            _LOGGER.warning("Unknown operation mode: %s", operation_mode)
            return
        await self._async_execute_command(
            self._controller.request_changes(self._pool_object.objnam, changes)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on, restoring the last operation or a safe default."""
        operation = self._last_operation
        if operation is None or self._operation_to_changes(operation) is None:
            operation = self._default_on_operation()
        changes = self._operation_to_changes(operation)
        if changes is not None:
            await self._async_execute_command(
                self._controller.request_changes(self._pool_object.objnam, changes)
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off, clearing both control planes atomically."""
        await self._async_execute_command(
            self._controller.request_changes(
                self._pool_object.objnam,
                {HEATER_ATTR: NULL_OBJNAM, MODE_ATTR: str(HeaterType.OFF.value)},
            )
        )

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        updated = self._check_attributes_updated(
            updates,
            STATUS_ATTR,
            HEATER_ATTR,
            HTMODE_ATTR,
            LOTMP_ATTR,
            LSTTMP_ATTR,
            MODE_ATTR,
        )

        if updated and self.current_operation != STATE_OFF:
            self._last_operation = self.current_operation

        return updated

    async def async_added_to_hass(self) -> None:
        """Entity is added to Home Assistant."""
        await super().async_added_to_hass()

        if self._last_operation is not None:
            return

        last_state = await self.async_get_last_state()
        if last_state:
            saved = last_state.attributes.get(self.LAST_OPERATION_ATTR)
            # Only restore a label that is still a valid (non-off) operation for
            # this body's current configuration.
            if (
                saved is not None
                and saved != STATE_OFF
                and saved in self.operation_list
            ):
                self._last_operation = saved
