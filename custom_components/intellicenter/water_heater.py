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
last non-off operation and setpoint are remembered (and restored across
restarts) so turn-on returns the body to its previous mode and target
temperature (some firmwares reset ``LOTMP`` while the heat source is Off —
issue #118).
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
from .const import DOMAIN
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
_SOLAR_MODE_LABELS: dict[HeaterType, str] = {
    HeaterType.SOLAR_ONLY: "Solar Only",
    HeaterType.SOLAR_PREFERRED: "Solar Preferred",
}
_SOLAR_LABEL_TO_MODE: dict[str, HeaterType] = {
    label: mode for mode, label in _SOLAR_MODE_LABELS.items()
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
    # retire_dependents: every builder predicate (body existence, the heater's
    # BODY wiring) is stable configuration, so a body's water heater is retired
    # when its last heater is deleted at the panel (issue #124). Known caveat:
    # a heater deleted AND replaced within one reconnect retires + recreates
    # the entity (losing registry customizations) because the replacement's
    # BODY attribute only backfills after the removal dispatch - rare, and
    # strictly better than a permanent ghost.
    async_setup_pool_entities(
        entry, async_add_entities, _build_entities, retire_dependents=True
    )


# -------------------------------------------------------------------------------------


class PoolWaterHeater(PoolEntity, WaterHeaterEntity, RestoreEntity):
    """Representation of a Pentair water heater."""

    LAST_OPERATION_ATTR = "LAST_OPERATION"
    LAST_SETPOINT_ATTR = "LAST_SETPOINT"
    LAST_SETPOINT_METRIC_ATTR = "LAST_SETPOINT_METRIC"
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
        # Remember the last active setpoint so turn-on can write it back: some
        # firmwares reset a body's LOTMP while its heat source is Off (issue
        # #118). Seed from the model only when a heat mode is active; otherwise
        # leave None so RestoreEntity may supply it in async_added_to_hass.
        # The unit mode in effect at capture time rides along as provenance
        # (see _remember_setpoint) - the pair is always set/cleared together.
        self._last_setpoint: float | None = None
        self._last_setpoint_metric: bool | None = None
        if self._last_operation is not None:
            seed_setpoint = self.target_temperature
            if seed_setpoint is not None:
                self._remember_setpoint(seed_setpoint)

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

    @property
    def _has_solar(self) -> bool:
        """Return whether a solar heater is configured for this body."""
        for heater_id in self._heater_list:
            heater_obj = self.coordinator.model[heater_id]
            if heater_obj is not None and heater_obj.subtype == "SOLAR":
                return True
        return False

    def _current_solar_mode(self) -> HeaterType | None:
        """Return the active solar mode when supported and valid."""
        if not self._has_solar:
            return None
        mode = self._pool_object[MODE_ATTR]
        try:
            heater_type = HeaterType(int(mode))
        except (ValueError, TypeError):
            return None
        return heater_type if heater_type in _SOLAR_MODE_LABELS else None

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
                # Standard heater: assign it. On solar-capable bodies also write
                # MODE=HEATER so a previously selected solar mode does not linger
                # (current_operation gives a valid solar MODE precedence). On
                # non-solar bodies MODE is left alone: the panel derives it, and
                # current_operation prefers the assigned standard heater over a
                # possibly-stale HCOMBO MODE.
                if self._has_solar:
                    return {
                        HEATER_ATTR: heater,
                        MODE_ATTR: str(HeaterType.HEATER.value),
                    }
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

        # Exposed in the panel's native unit so a restart restores it verbatim
        # (never the HA-converted `temperature` attribute, which would break on
        # unit-preference mismatches). The unit mode saved alongside is the one
        # captured WITH the value, never the panel's current mode - a mid-session
        # unit flip must not relabel a 40 F memory as 40 C (= 104 F), which
        # would let a restart adopt it and silently drive the heater to max.
        if self._last_setpoint is not None and self._last_setpoint_metric is not None:
            state_attributes[self.LAST_SETPOINT_ATTR] = self._last_setpoint
            state_attributes[self.LAST_SETPOINT_METRIC_ATTR] = (
                self._last_setpoint_metric
            )

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
            # Only a setpoint the panel accepted becomes the turn-on restore
            # value; a failed command raised above and leaves the memory alone.
            self._remember_setpoint(float(temp_value))

    @property
    def current_operation(self) -> str:
        """Return current operation.

        This reflects the configured heater mode, independent of whether the
        body is currently running (STATUS). A user can preselect a heater for
        a body even when it's off (e.g., setting the Spa heater while in Pool
        mode). The real-time heating activity is exposed via the heating_status
        extra state attribute.

        For multi-mode (HCOMBO) heaters, operation is controlled via MODE_ATTR
        on the body rather than HEATER_ATTR assignment.
        """
        # A valid solar MODE takes precedence: selecting Solar Only/Preferred
        # writes MODE and leaves HEATER pointing at the previous heater, so the
        # heater assignment alone cannot be trusted on solar-capable bodies.
        # (Hardware: MODE is the panel's authoritative heat-mode plane; a body
        # heating with a standard heater reports MODE=2/HEATER.)
        solar_mode = self._current_solar_mode()
        if solar_mode is not None:
            return _SOLAR_MODE_LABELS[solar_mode]
        # Otherwise an assigned standard (non-HCOMBO) heater is the operation.
        # This also keeps the state correct when a stale HCOMBO MODE remains
        # after switching to a standard heater on a mixed body.
        heater = self._pool_object[HEATER_ATTR]
        heater_obj = (
            self.coordinator.model[heater] if heater in self._heater_list else None
        )
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
        if self._has_solar:
            operations.extend(_SOLAR_MODE_LABELS.values())
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
        if operation_mode not in self.operation_list:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_heat_mode",
            )
        await self._async_apply_operation(operation_mode)

    @property
    def _panel_uses_metric(self) -> bool:
        """Return whether the panel currently expresses setpoints in Celsius."""
        system_info = self.coordinator.system_info
        return bool(system_info is not None and system_info.uses_metric)

    def _setpoint_in_limits(self, value: float) -> bool:
        """Return whether a value is within the panel's current setpoint limits."""
        low, high = body_temperature_limits(self.coordinator)
        return low <= value <= high

    def _remember_setpoint(self, value: float) -> None:
        """Remember a setpoint together with the unit mode it was captured under.

        The provenance flag is fixed at capture time - it must NOT be derived
        from the panel's current mode later (e.g. when rendering state), or a
        mid-session unit flip would relabel the value into the new mode.
        """
        self._last_setpoint = value
        self._last_setpoint_metric = self._panel_uses_metric

    def _forget_setpoint(self) -> None:
        """Drop the setpoint memory and its unit provenance together."""
        self._last_setpoint = None
        self._last_setpoint_metric = None

    def _setpoint_restore_change(self) -> dict[str, str] | None:
        """Return the LOTMP write restoring the remembered setpoint, if needed.

        Some firmwares reset a body's LOTMP while its heat source is Off (the
        panel hides its setpoint UI in that state), so re-selecting a heat
        source without restoring the setpoint leaves the body heating toward
        the panel's reset value, e.g. 47 °F (issue #118). Returns None when
        there is no memory, when the memory falls outside the current setpoint
        limits (a unit-mode flip - discarded rather than clamped, since
        clamping would pick a wrong extreme), or when the model already holds
        the remembered value.
        """
        last = self._last_setpoint
        if last is None:
            return None
        if self._last_setpoint_metric != self._panel_uses_metric:
            # The panel's unit mode flipped since capture: the memory is
            # meaningless in the new mode (even if numerically in range, e.g.
            # a 40 F memory on a now-METRIC panel). Forget it so it also stops
            # being persisted, and skip the restore.
            self._forget_setpoint()
            return None
        if not self._setpoint_in_limits(last):
            # Discard means discard: forget the value too, so it stops being
            # persisted via LAST_SETPOINT and cannot resurrect after a second
            # unit flip. Kept as the final guard behind the provenance check.
            self._forget_setpoint()
            return None
        if self.target_temperature == last:
            return None
        # int() matches the async_set_temperature convention for LOTMP writes.
        return {LOTMP_ATTR: str(int(last))}

    async def _async_apply_operation(self, operation: str) -> None:
        """Apply a validated operation through its matching control plane."""
        # Restore the remembered setpoint only on an HA-initiated off->on
        # transition (this method backs both async_turn_on and
        # async_set_operation_mode); switching between two active modes keeps
        # whatever setpoint the body already has.
        restore: dict[str, str] | None = None
        if operation != STATE_OFF and self.current_operation == str(STATE_OFF):
            restore = self._setpoint_restore_change()
        solar_mode = _SOLAR_LABEL_TO_MODE.get(operation)
        if self._has_solar and solar_mode is not None:
            await self._async_execute_command(
                self._controller.set_heat_mode(self._pool_object.objnam, solar_mode),
                translation_key="command_failed",
            )
            # Solar goes through the typed heat-mode helper, so the setpoint
            # restore cannot ride along atomically and follows as its own write.
            if restore is not None:
                await self._async_execute_command(
                    self._controller.request_changes(self._pool_object.objnam, restore),
                    translation_key="command_failed",
                )
            return
        changes = self._operation_to_changes(operation)
        if changes is not None:
            if restore is not None:
                # Merge so heat source and setpoint land in ONE atomic write.
                changes |= restore
            await self._async_execute_command(
                self._controller.request_changes(self._pool_object.objnam, changes),
                translation_key="command_failed",
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on, restoring the last operation or a safe default."""
        operation = self._last_operation
        if operation is None or operation not in self.operation_list:
            operation = self._default_on_operation()
        await self._async_apply_operation(operation)

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
            # Capture the setpoint only from pushes that explicitly carry LOTMP
            # while a heat mode is active. The LOTMP gate keeps an unrelated
            # STATUS/HTMODE/... push from overwriting a just-issued
            # set_temperature with the stale model value before its echo
            # arrives; the non-off gate ignores the off-state LOTMP resets this
            # memory guards against (issue #118). Deliberate tradeoffs: a
            # genuine setpoint edit made at the panel while the heat source is
            # Off is not remembered, and a firmware that split a
            # panel-initiated turn-off into two notifications with the LOTMP
            # reset arriving FIRST (heat source still non-off in the model)
            # would still be captured - no clean client-side fix exists for
            # that ordering.
            if LOTMP_ATTR in updates.get(self._pool_object.objnam, {}):
                setpoint = self.target_temperature
                if setpoint is not None:
                    self._remember_setpoint(setpoint)

        return updated

    async def async_added_to_hass(self) -> None:
        """Entity is added to Home Assistant."""
        await super().async_added_to_hass()

        if self._last_operation is not None and self._last_setpoint is not None:
            return

        last_state = await self.async_get_last_state()
        if not last_state:
            return

        if self._last_operation is None:
            saved = last_state.attributes.get(self.LAST_OPERATION_ATTR)
            # Only restore a label that is still a valid (non-off) operation for
            # this body's current configuration.
            if (
                saved is not None
                and saved != STATE_OFF
                and saved in self.operation_list
            ):
                self._last_operation = saved

        if self._last_setpoint is None:
            saved_setpoint = last_state.attributes.get(self.LAST_SETPOINT_ATTR)
            if saved_setpoint is None:
                return
            try:
                setpoint = float(saved_setpoint)
            except (TypeError, ValueError):
                return
            # Stored in the panel's native unit; the unit mode it was saved
            # under must match the current one - a value saved on an ENGLISH
            # system is meaningless after a METRIC flip. A corrupt (non-bool)
            # marker is rejected too. A legacy state without unit metadata is
            # accepted only when the value is unambiguous: the ENGLISH
            # (40-104 °F) and METRIC (5-40 °C) ranges meet at exactly 40, and
            # restoring 40 °F as 40 °C (= 104 °F) would silently drive the
            # heater to max. The range check below remains as a second line of
            # defense.
            saved_metric = last_state.attributes.get(self.LAST_SETPOINT_METRIC_ATTR)
            if saved_metric is None:
                if setpoint == 40.0:
                    return
            elif (
                not isinstance(saved_metric, bool)
                or saved_metric != self._panel_uses_metric
            ):
                return
            if self._setpoint_in_limits(setpoint):
                # _remember_setpoint stamps the current mode as provenance,
                # which the checks above just proved is the saved value's mode.
                self._remember_setpoint(setpoint)
