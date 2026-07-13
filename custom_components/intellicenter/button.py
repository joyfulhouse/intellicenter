"""Pentair IntelliCenter button entities."""

from __future__ import annotations

from collections.abc import Iterable
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    CIRCUIT_TYPE,
    DLY_ATTR,
    STATUS_OFF,
    STATUS_ON,
    SYSTEM_TYPE,
    ICError,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity, async_setup_pool_entities
from .const import DOMAIN
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[CancelDelaysButton]:
    """Build the system-level Cancel Delays button."""
    return [
        CancelDelaysButton(coordinator, pool_object)
        for pool_object in candidates
        if pool_object.objtype == SYSTEM_TYPE
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load IntelliCenter button entities."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)


class CancelDelaysButton(PoolEntity, ButtonEntity):
    """Cancel every circuit delay currently reported as active."""

    _attr_icon = "mdi:timer-off-outline"

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize the Cancel Delays button on the system device."""
        super().__init__(
            coordinator,
            pool_object,
            attribute_key=DLY_ATTR,
            name="Cancel Delays",
        )

    async def async_press(self) -> None:
        """Clear DLY on each circuit with a confirmed active delay."""
        delayed = [
            circuit
            for circuit in self.coordinator.model.get_by_type(CIRCUIT_TYPE)
            if circuit[DLY_ATTR] == STATUS_ON
        ]
        if not delayed:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="no_active_delays",
            )

        try:
            for circuit in delayed:
                await self._controller.request_changes(
                    circuit.objnam, {DLY_ATTR: STATUS_OFF}
                )
        except (ICError, ValueError) as err:
            _LOGGER.warning("Failed to cancel IntelliCenter delays: %s", err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cancel_delays_failed",
            ) from err
