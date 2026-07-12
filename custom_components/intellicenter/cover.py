"""Pentair Intellicenter covers.

This module provides cover entities for pool covers and other motorized covers.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyintellicenter import (
    EXTINSTR_TYPE,
    NORMAL_ATTR,
    POSIT_ATTR,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    PoolObject,
)

from . import IntelliCenterConfigEntry, PoolEntity, async_setup_pool_entities
from .const import DOMAIN
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Coordinator handles updates via push, so no parallel update limit needed
PARALLEL_UPDATES = 0

# -------------------------------------------------------------------------------------


def _build_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolCover]:
    """Build cover entities for the given candidate pool objects.

    STATUS on an EXTINSTR/COVER object is the "Cover Enabled" toggle in the
    panel's Settings > Covers page, not its position (confirmed by capturing
    the panel's own SETPARAMLIST traffic: enabling a cover writes STATUS and
    never touches POSIT). A cover disabled there still exists as a static
    object and would otherwise get a permanent, non-functional entity. Skip
    it only on a confirmed STATUS_OFF - an unset/unknown STATUS (e.g. before
    the model's initial backfill completes) still gets an entity rather than
    being silently hidden.
    """
    covers: list[PoolCover] = []
    for pool_obj in candidates:
        if pool_obj.objtype == EXTINSTR_TYPE and pool_obj.subtype == "COVER":
            if pool_obj[STATUS_ATTR] == STATUS_OFF:
                continue
            covers.append(PoolCover(coordinator, pool_obj))
    return covers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Load pool cover entities based on a config entry."""
    async_setup_pool_entities(entry, async_add_entities, _build_entities)
    _sync_disabled_covers(hass, entry)

    # async_setup_pool_entities's dynamic listener only fires for genuinely new
    # pool objects (issue #42), never for an attribute change on one it already
    # knows about - so toggling a cover's "Cover Enabled" setting after setup
    # would otherwise sit until the integration is reloaded. React on every push
    # update instead (cheap: a handful of covers, one registry lookup each) to
    # both build a newly-enabled cover's entity on its first enable and to
    # disable/re-enable an already-registered one on every later toggle.
    coordinator = entry.runtime_data
    created_unique_ids = {
        f"{entry.entry_id}_{cover.objnam}"
        for cover in coordinator.controller.get_covers()
        if cover[STATUS_ATTR] == STATUS_ON
    }

    @callback
    def _async_handle_cover_update() -> None:
        new_covers = [
            cover
            for cover in _build_entities(
                coordinator, coordinator.controller.get_covers()
            )
            if cover.unique_id not in created_unique_ids
        ]
        if new_covers:
            created_unique_ids.update(cover.unique_id for cover in new_covers)
            async_add_entities(new_covers)
        _sync_disabled_covers(hass, entry)

    entry.async_on_unload(coordinator.async_add_listener(_async_handle_cover_update))


@callback
def _sync_disabled_covers(hass: HomeAssistant, entry: IntelliCenterConfigEntry) -> None:
    """Disable (or re-enable) registry entries for covers the panel disables.

    ``_build_entities`` only creates an entity for a cover reporting
    STATUS=ON, so a cover disabled in the panel's Settings > Covers page
    never gets an entity on a fresh setup. But an entity created before this
    filter existed - or before the cover was disabled in the panel - stays
    registered until something acts on it. Disabling it (rather than
    removing it) matches Home Assistant's convention for integration-driven
    unavailability: the entity_id, history, and any automations referencing
    it survive, and the user can still manually re-enable it if they
    disagree. A registry entry disabled for any other reason (e.g. the user
    disabled it themselves) is left untouched - this only ever acts on
    disabled_by values of None or our own INTEGRATION.

    Known, accepted limitation: the registry only stores the current
    disabled_by value, not who last changed it. If a user manually
    re-enables (clears disabled_by on) a cover we disabled while the panel
    still reports it disabled, that clear is indistinguishable here from a
    fresh entity, and the next push re-disables it. Not worth working around
    - a panel-disabled cover has no real POSIT data flowing anyway.
    """
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    for cover in coordinator.controller.get_covers():
        unique_id = f"{entry.entry_id}_{cover.objnam}"
        entity_id = registry.async_get_entity_id(Platform.COVER, DOMAIN, unique_id)
        if entity_id is None:
            continue
        reg_entry = registry.entities[entity_id]
        panel_enabled = cover[STATUS_ATTR] == STATUS_ON
        if not panel_enabled and reg_entry.disabled_by is None:
            registry.async_update_entity(
                entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
            )
        elif (
            panel_enabled
            and reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        ):
            registry.async_update_entity(entity_id, disabled_by=None)


# -------------------------------------------------------------------------------------


class PoolCover(PoolEntity, CoverEntity):
    """Representation of a Pentair pool cover."""

    _attr_device_class = CoverDeviceClass.SHADE

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
    ) -> None:
        """Initialize a pool cover entity.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this cover represents
        """
        super().__init__(
            coordinator,
            pool_object,
            extra_state_attributes=[NORMAL_ATTR, STATUS_ATTR],
            icon="mdi:arrow-expand-horizontal",
        )
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        )

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, or None if the state is unknown."""
        # Without both attributes the position cannot be derived; report unknown
        # rather than fabricating "closed" (safety automations may key off this).
        raw_posit = self._pool_object[POSIT_ATTR]
        raw_normal = self._pool_object[NORMAL_ATTR]
        if raw_posit is None or raw_normal is None:
            return None
        # The cover is closed if:
        # - POSIT is ON and NORMAL is ON (cover is normally closed)
        # - POSIT is OFF and NORMAL is OFF (cover is normally open)
        return bool((raw_posit == STATUS_ON) == (raw_normal == STATUS_ON))

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # To open the cover, we need to set POSIT opposite of NORMAL
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        self.request_changes({POSIT_ATTR: STATUS_OFF if normal else STATUS_ON})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # To close the cover, we need to set POSIT same as NORMAL
        normal = self._pool_object[NORMAL_ATTR] == STATUS_ON
        self.request_changes({POSIT_ATTR: STATUS_ON if normal else STATUS_OFF})

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""
        return self._check_attributes_updated(
            updates, POSIT_ATTR, NORMAL_ATTR, STATUS_ATTR
        )
