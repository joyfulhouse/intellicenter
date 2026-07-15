"""Pentair Intellicenter lights.

This module provides light entities for pool lights and light shows.
Supports color effects for IntelliBrite, MagicStream, and GloBrite lights.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT, LightEntity
from homeassistant.components.light.const import ColorMode, LightEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    ACT_ATTR,
    CIRCUIT_ATTR,
    CIRCUIT_TYPE,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    USE_ATTR,
    ICError,
    ICLightGroupError,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    OnOffControlMixin,
    PoolEntity,
    async_setup_pool_entities,
)
from .const import DOMAIN, LIMIT_ATTR
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

_DIMMABLE_SUBTYPES = frozenset({"DIMMER"})
_SUPPORTED_DIMMER_LEVELS = (50, 75, 100)
_ENTITY_SERVICES = {
    "capture": "async_capture",
    "thumper": "async_thumper",
    "hold": "async_hold",
    "recall": "async_recall",
    "color_sync": "async_color_sync",
}


def _complete_light_group_children(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> tuple[PoolObject, ...] | None:
    """Resolve every distinct child of a real light-group parent."""
    if parent.objtype != CIRCUIT_TYPE or parent.subtype != "LITSHO":
        return None
    members = coordinator.controller.get_circuit_group_members(parent.objnam)
    children = coordinator.controller.get_circuits_in_group(parent.objnam)
    if (
        not members
        or len(children) != len(members)
        or len({child.objnam for child in children}) != len(children)
    ):
        return None
    return tuple(children)


def _is_complete_color_light_group(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> bool:
    """Return whether a complete light group supports existing color effects."""
    children = _complete_light_group_children(coordinator, parent)
    return children is not None and all(
        child.supports_color_effects for child in children
    )


def _is_color_sync_eligible(
    coordinator: IntelliCenterCoordinator, parent: PoolObject
) -> bool:
    """Return whether the group matches the evidence-scoped Color Sync gate."""
    children = _complete_light_group_children(coordinator, parent)
    system_info = coordinator.system_info
    return bool(
        system_info is not None
        and system_info.sw_version == "1.064"
        and children is not None
        and len(children) == 2
        and all(
            child.objtype == CIRCUIT_TYPE and child.subtype == "GLOW"
            for child in children
        )
    )


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolLight]:
    """Build light entities for the given candidate pool objects."""
    candidate_list = list(candidates)
    candidate_objnams = {obj.objnam for obj in candidate_list}
    entity_objects = {
        obj.objnam: obj
        for obj in candidate_list
        if obj.is_a_light or obj.is_a_light_show
    }

    # Re-evaluate an existing parent when a membership row or referenced child
    # arrives later. The shared setup helper de-duplicates the replacement by
    # unique_id and asks the original entity to refresh its model context.
    for parent in coordinator.model:
        if not parent.is_a_light_show:
            continue
        members = coordinator.controller.get_circuit_group_members(parent.objnam)
        if parent.objnam in candidate_objnams or any(
            member.objnam in candidate_objnams
            or member[CIRCUIT_ATTR] in candidate_objnams
            for member in members
        ):
            entity_objects.setdefault(parent.objnam, parent)

    lights: list[PoolLight] = []
    for obj in entity_objects.values():
        if obj.is_a_light:
            lights.append(
                PoolLight(
                    coordinator,
                    obj,
                    LIGHT_EFFECTS if obj.supports_color_effects else None,
                )
            )
        elif obj.is_a_light_show:
            lights.append(
                PoolLight(
                    coordinator,
                    obj,
                    LIGHT_EFFECTS
                    if _is_complete_color_light_group(coordinator, obj)
                    else None,
                )
            )
    return lights


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool lights based on a config entry."""
    platform = entity_platform.async_get_current_platform()
    for service_name, method_name in _ENTITY_SERVICES.items():
        platform.async_register_entity_service(service_name, None, method_name)
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


class PoolLight(PoolEntity, OnOffControlMixin, LightEntity):
    """Representation of a Pentair light.

    Supports basic on/off control (via OnOffControlMixin's optimistic
    scaffolding) and color effects for compatible lights (IntelliBrite,
    MagicStream, GloBrite).
    """

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.ONOFF}
    _attr_supported_features = LightEntityFeature(0)

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        color_effects: dict[str, str] | None = None,
    ) -> None:
        """Initialize a pool light.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this light represents
            color_effects: Optional mapping of IntelliCenter codes to effect names
        """
        super().__init__(coordinator, pool_object, extra_state_attributes=[USE_ATTR])

        self._attr_supported_features = LightEntityFeature(0)
        self._light_effects: dict[str, str] | None = None
        self._reversed_light_effects: dict[str, str] | None = None
        self._dimmable = pool_object.subtype in _DIMMABLE_SUBTYPES

        if self._dimmable:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        self._set_light_effects(color_effects)

    def _set_light_effects(self, color_effects: dict[str, str] | None) -> bool:
        """Replace the effect mapping and report whether capability changed."""
        if self._light_effects == color_effects:
            return False
        self._light_effects = color_effects
        self._reversed_light_effects = (
            {value: key for key, value in color_effects.items()}
            if color_effects
            else None
        )
        if color_effects:
            self._attr_supported_features |= LightEntityFeature.EFFECT
        else:
            self._attr_supported_features &= ~LightEntityFeature.EFFECT
        return True

    def _refresh_light_group_effects(self) -> bool:
        """Refresh group effects from the current complete membership model."""
        if not self._pool_object.is_a_light_show:
            return False
        color_effects = (
            LIGHT_EFFECTS
            if _is_complete_color_light_group(self.coordinator, self._pool_object)
            else None
        )
        return self._set_light_effects(color_effects)

    @callback
    def async_refresh_model_context(self) -> None:
        """Refresh cross-object group capability without replacing the entity."""
        current = self.coordinator.model[self._pool_object.objnam]
        if current is not None:
            self._pool_object = current
        if self._refresh_light_group_effects() and self.hass is not None:
            self.async_write_ha_state()

    @property
    def brightness(self) -> int | None:
        """Return DIMMER LIMIT as Home Assistant brightness."""
        if not self._dimmable:
            return None
        raw_limit = self._pool_object[LIMIT_ATTR]
        if isinstance(raw_limit, bool):
            return None
        try:
            limit = float(raw_limit)
        except (TypeError, ValueError):
            return None
        if not 0 <= limit <= 100:
            return None
        return round(limit * 255 / 100)

    @property
    def effect_list(self) -> list[str] | None:
        """Return the list of supported effects."""
        if self._reversed_light_effects is None:
            return None
        return list(self._reversed_light_effects.keys())

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        if self._light_effects is None:
            return None
        use_value = self._pool_object[USE_ATTR]
        return self._light_effects.get(use_value) if use_value else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light, applying the requested effect first.

        The effect write is awaited (and any failure raised) BEFORE the
        optimistic on-state is rendered, so a light that cannot accept the
        command never shows as on.
        """
        await self._async_apply_effect(kwargs)

        if ATTR_BRIGHTNESS in kwargs and self._dimmable:
            requested = int(kwargs[ATTR_BRIGHTNESS])
            percentage = requested * 100 / 255
            limit = min(
                _SUPPORTED_DIMMER_LEVELS,
                key=lambda level: abs(level - percentage),
            )
            self._optimistic_state = True
            self.async_write_ha_state()
            self.request_changes(
                {
                    LIMIT_ATTR: str(limit),
                    STATUS_ATTR: self._pool_object.on_status,
                }
            )
            return

        # On/off (with optimistic UI feedback) comes from OnOffControlMixin.
        await super().async_turn_on(**kwargs)

    async def _async_apply_effect(self, kwargs: dict[str, Any]) -> None:
        """Apply a requested light effect before changing power state."""
        if ATTR_EFFECT not in kwargs:
            return
        effect = kwargs[ATTR_EFFECT]
        new_use = (
            self._reversed_light_effects.get(effect)
            if self._reversed_light_effects
            else None
        )
        if new_use is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_light_effect",
            )
        await self._async_set_effect(new_use)

    async def _async_set_effect(self, effect: str) -> None:
        """Set a standard color or show through pyintellicenter."""
        await self._async_execute_command(
            self._controller.set_light_effect(self._pool_object.objnam, effect),
            translation_key="command_failed",
        )

    async def _async_magicstream_command(self, command: str) -> None:
        """Run a MagicStream-only momentary ACT command."""
        if self._pool_object.subtype != "MAGIC2":
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="magicstream_command_unsupported",
            )
        await self._async_execute_command(
            self._controller.request_changes(
                self._pool_object.objnam, {ACT_ATTR: command}
            ),
            translation_key="command_failed",
        )

    async def async_capture(self) -> None:
        """Capture the current MagicStream color."""
        await self._async_magicstream_command("CAPTURE")

    async def async_thumper(self) -> None:
        """Toggle the MagicStream thumper."""
        await self._async_magicstream_command("THUMPER")

    async def async_hold(self) -> None:
        """Hold the current MagicStream color."""
        await self._async_magicstream_command("HOLD")

    async def async_recall(self) -> None:
        """Recall the saved MagicStream color."""
        await self._async_magicstream_command("RECALL")

    async def async_color_sync(self) -> None:
        """Synchronize the supported two-light IntelliCenter group."""
        if not _is_color_sync_eligible(self.coordinator, self._pool_object):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="light_group_command_unsupported",
            )
        try:
            await self._controller.run_light_group_sync(self._pool_object.objnam)
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="light_group_command_unsupported",
            ) from err
        except ICLightGroupError as err:
            if err.acknowledged or err.onset_seen:
                translation_key = "light_group_command_incomplete"
            elif err.dispatch_started and not err.response_received:
                translation_key = "light_group_command_uncertain"
            else:
                translation_key = "light_group_command_failed"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=translation_key,
            ) from err
        except ICError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="light_group_command_failed",
            ) from err

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        return self._refresh_light_group_effects() or self._check_attributes_updated(
            updates,
            STATUS_ATTR,
            USE_ATTR,
            LIMIT_ATTR,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh group capability across reconnects and ordinary updates."""
        if not (self.coordinator.data or {}):
            self._refresh_light_group_effects()
        super()._handle_coordinator_update()
