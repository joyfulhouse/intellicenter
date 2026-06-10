"""Pentair Intellicenter lights.

This module provides light entities for pool lights and light shows.
Supports color effects for IntelliBrite, MagicStream, and GloBrite lights.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.light import ATTR_EFFECT, LightEntity
from homeassistant.components.light.const import ColorMode, LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    CIRCUIT_ATTR,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    USE_ATTR,
    PoolObject,
)

from . import (
    IntelliCenterConfigEntry,
    OnOffControlMixin,
    PoolEntity,
    async_setup_pool_entities,
)
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolLight]:
    """Build light entities for the given candidate pool objects."""
    lights: list[PoolLight] = []
    for obj in candidates:
        if obj.is_a_light:
            lights.append(
                PoolLight(
                    coordinator,
                    obj,
                    LIGHT_EFFECTS if obj.supports_color_effects else None,
                )
            )
        elif obj.is_a_light_show:
            # Check if all child lights support color effects
            children = coordinator.model.get_children(obj)
            supports_color = all(
                circuit_obj.supports_color_effects
                for child in children
                if (circuit_obj := coordinator.model[child[CIRCUIT_ATTR]]) is not None
            )
            lights.append(
                PoolLight(
                    coordinator,
                    obj,
                    LIGHT_EFFECTS if supports_color else None,
                )
            )
    return lights


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool lights based on a config entry."""
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

        self._light_effects = color_effects
        self._reversed_light_effects: dict[str, str] | None = (
            {v: k for k, v in color_effects.items()} if color_effects else None
        )

        if self._light_effects:
            self._attr_supported_features |= LightEntityFeature.EFFECT

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
        if ATTR_EFFECT in kwargs and self._reversed_light_effects:
            effect = kwargs[ATTR_EFFECT]
            new_use = self._reversed_light_effects.get(effect)
            if new_use is None:
                raise HomeAssistantError(f"Unknown light effect: {effect}")
            await self._async_execute_command(
                self._controller.set_light_effect(self._pool_object.objnam, new_use)
            )

        # On/off (with optimistic UI feedback) comes from OnOffControlMixin.
        await super().async_turn_on(**kwargs)

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        return self._check_attributes_updated(updates, STATUS_ATTR, USE_ATTR)
