"""Pentair Intellicenter lights.

This module provides light entities for pool lights and light shows.
Supports color effects for IntelliBrite, MagicStream, and GloBrite lights.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from homeassistant.components.light import (
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    CIRCUIT_ATTR,
    LIGHT_EFFECTS,
    STATUS_ATTR,
    STATUS_OFF,
    USE_ATTR,
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
    """Load pool lights based on a config entry."""
    coordinator = entry.runtime_data

    lights: list[PoolLight] = []

    obj: PoolObject
    for obj in coordinator.model:
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

    async_add_entities(lights)


class PoolLight(PoolEntity, LightEntity):
    """Representation of a Pentair light.

    Supports basic on/off control and color effects for compatible lights
    (IntelliBrite, MagicStream, GloBrite).
    """

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.ONOFF}
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

    _optimistic_state: bool | None = None  # None = use real state

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        # Use optimistic state if set, otherwise use real state
        if self._optimistic_state is not None:
            return self._optimistic_state
        return bool(self._pool_object.status == self._pool_object.on_status)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        # Optimistic update for immediate UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()
        self.request_changes({STATUS_ATTR: STATUS_OFF})

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        # Optimistic update for immediate UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()

        # Handle light effect using convenience method if specified
        if ATTR_EFFECT in kwargs and self._reversed_light_effects:
            effect = kwargs[ATTR_EFFECT]
            new_use = self._reversed_light_effects.get(effect)
            if new_use:
                try:
                    # Use convenience method with validation
                    await self._controller.set_light_effect(
                        self._pool_object.objnam, new_use
                    )
                except ValueError:
                    _LOGGER.warning("Invalid light effect: %s", effect)

        # Turn on the light
        self.request_changes({STATUS_ATTR: self._pool_object.on_status})

    def _clear_optimistic_state(self) -> None:
        """Clear optimistic state when real update is received."""
        self._optimistic_state = None

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        return self._check_attributes_updated(updates, STATUS_ATTR, USE_ATTR)
