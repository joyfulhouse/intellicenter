"""Pentair IntelliCenter Integration.

This integration connects to a Pentair IntelliCenter pool control system
via local network (not cloud) using a custom TCP protocol on port 6681.
It supports Zeroconf discovery and local push updates for real-time responsiveness.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyintellicenter import (
    STATUS_ATTR,
    ICModelController,
    PoolObject,
)

from .const import (
    CONF_KEEPALIVE_INTERVAL,
    CONF_RECONNECT_DELAY,
    CONF_TRANSPORT,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_TRANSPORT,
    DOMAIN,
)
from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Platforms supported by this integration
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

type IntelliCenterConfigEntry = ConfigEntry[IntelliCenterCoordinator]


# -------------------------------------------------------------------------------------
# Setup Functions
# -------------------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pentair IntelliCenter Integration."""
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> bool:
    """Set up IntelliCenter integration from a config entry."""
    # Get configuration options with defaults
    keepalive_interval = entry.options.get(
        CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL
    )
    reconnect_delay = entry.options.get(CONF_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY)

    # Get transport type from entry data (defaults to TCP for backwards compatibility)
    transport = entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)

    # Create the coordinator
    coordinator = IntelliCenterCoordinator(
        hass,
        entry,
        host=entry.data[CONF_HOST],
        keepalive_interval=keepalive_interval,
        reconnect_delay=reconnect_delay,
        transport=transport,
    )

    try:
        # Start the connection
        await coordinator.async_start()

        # Store the coordinator in the entry's runtime_data
        entry.runtime_data = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register update listener for options changes
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        return True

    except ConnectionRefusedError as err:
        raise ConfigEntryNotReady from err


async def async_unload_entry(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> bool:
    """Unload IntelliCenter config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Stop the coordinator
    if entry.runtime_data:
        await entry.runtime_data.async_stop()

    _LOGGER.info("Unloaded IntelliCenter integration: %s", entry.entry_id)

    return bool(unload_ok)


async def async_reload_entry(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> bool:
    """Migrate old entry data to current version."""
    _LOGGER.debug("Migrating from version %s.%s", entry.version, entry.minor_version)
    # Currently at version 1.1, no migration needed yet
    return True


# -------------------------------------------------------------------------------------
# Base Entity Class
# -------------------------------------------------------------------------------------


class PoolEntity(CoordinatorEntity[IntelliCenterCoordinator], Entity):
    """Base representation of a Pool entity linked to a pool object.

    This class provides common functionality for all pool-related entities
    including device info, state attributes, and update callbacks.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        pool_object: PoolObject,
        attribute_key: str = STATUS_ATTR,
        name: str | None = None,
        enabled_by_default: bool = True,
        extra_state_attributes: Iterable[str] | None = None,
        icon: str | None = None,
        unit_of_measurement: str | None = None,
    ) -> None:
        """Initialize a Pool entity.

        Args:
            coordinator: The coordinator for this integration
            pool_object: The PoolObject this entity represents
            attribute_key: The primary attribute to monitor (default: STATUS_ATTR)
            name: Custom name or suffix (prefixed with '+') for the entity
            enabled_by_default: Whether the entity is enabled by default
            extra_state_attributes: Additional attributes to include in state
            icon: Custom icon for the entity
            unit_of_measurement: Unit of measurement for sensors
        """
        super().__init__(coordinator)

        self._pool_object = pool_object
        self._attribute_key = attribute_key
        self._custom_name = name
        self._extra_state_attrs: set[str] = (
            set(extra_state_attributes) if extra_state_attributes else set()
        )

        self._attr_entity_registry_enabled_default = enabled_by_default
        self._attr_native_unit_of_measurement = unit_of_measurement
        if icon:
            self._attr_icon = icon

        _LOGGER.debug("Mapping %s", pool_object)

    @property
    def _entry_id(self) -> str:
        """Return the config entry ID."""
        return str(self.coordinator.config_entry.entry_id)

    @property
    def _controller(self) -> ICModelController:
        """Return the controller."""
        return self.coordinator.controller

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self.coordinator.connected)

    @property
    def name(self) -> str | None:
        """Return the name of the entity.

        Strips trailing " 1" from the name when it's the only instance
        of that device type (e.g., "IntelliChem 1" becomes "IntelliChem").
        """
        sname: str | None = self._pool_object.sname
        if sname:
            sname = self._simplify_name(sname)

        if self._custom_name is None:
            return sname
        elif self._custom_name.startswith("+"):
            base_name = sname or ""
            return base_name + self._custom_name[1:]
        return self._custom_name

    def _simplify_name(self, name: str) -> str:
        """Remove trailing number when it's the only instance of this type.

        IntelliCenter names devices like "IntelliChem 1" even when there's
        only one. This method strips the trailing " 1" in such cases.
        """
        # Check if name ends with " 1"
        match = re.match(r"^(.+) 1$", name)
        if not match:
            return name

        base_name = match.group(1)
        obj_type = self._pool_object.objtype
        obj_subtype = self._pool_object.subtype

        # Count how many objects of the same type/subtype exist
        count = sum(
            1
            for obj in self.coordinator.model
            if obj.objtype == obj_type and obj.subtype == obj_subtype
        )

        # Only strip " 1" if there's exactly one instance
        if count == 1:
            return base_name

        return name

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        my_id = f"{self._entry_id}_{self._pool_object.objnam}"
        if self._attribute_key != STATUS_ATTR:
            my_id = my_id + self._attribute_key
        return my_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        system_info = self.coordinator.system_info

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            manufacturer="Pentair",
            model="IntelliCenter",
            name=system_info.prop_name if system_info else "IntelliCenter",
            sw_version=system_info.sw_version if system_info else None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the entity."""
        pool_obj = self._pool_object

        obj_type = pool_obj.objtype
        if pool_obj.subtype:
            obj_type += f"/{pool_obj.subtype}"

        attributes: dict[str, Any] = {
            "OBJNAM": pool_obj.objnam,
            "OBJTYPE": obj_type,
        }

        if pool_obj.status:
            attributes["Status"] = pool_obj.status

        for attribute in self._extra_state_attrs:
            value = pool_obj[attribute]
            if value is not None:
                attributes[attribute] = value

        return attributes

    def request_changes(self, changes: dict[str, Any]) -> None:
        """Request changes to the associated Pool object.

        Args:
            changes: Dictionary of attribute changes to apply

        Note:
            This method fires and forgets the request. Changes will be
            reflected as an update notification if successful.
        """
        self.hass.async_create_task(
            self._async_request_changes(changes),
            f"intellicenter_request_changes_{self._pool_object.objnam}",
        )

    async def _async_request_changes(self, changes: dict[str, Any]) -> None:
        """Async helper to request changes with error handling."""
        try:
            await self._controller.request_changes(self._pool_object.objnam, changes)
        except Exception:
            _LOGGER.exception(
                "Failed to request changes for %s: %s",
                self._pool_object.objnam,
                changes,
            )

    def _check_attributes_updated(
        self, updates: dict[str, dict[str, Any]], *attributes: str
    ) -> bool:
        """Check if any of the specified attributes were updated."""
        my_updates = updates.get(self._pool_object.objnam, {})
        if not my_updates:
            return False
        return bool(set(attributes) & my_updates.keys())

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        """Return true if the entity is updated by the updates from IntelliCenter."""
        return self._attribute_key in updates.get(self._pool_object.objnam, {})

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        updates = self.coordinator.data or {}

        # Check if this entity needs to update
        if updates and self.isUpdated(updates):
            # Update the pool object reference if it changed
            updated_obj = self.coordinator.model[self._pool_object.objnam]
            if updated_obj:
                self._pool_object = updated_obj
            # Clear optimistic state if this entity uses OnOffControlMixin
            if hasattr(self, "_clear_optimistic_state"):
                self._clear_optimistic_state()
            self.async_write_ha_state()
        elif not updates:
            # Connection state change - update availability
            self.async_write_ha_state()

    def pentairTemperatureSettings(self) -> str:
        """Return the native temperature unit from the Pentair system.

        This returns the unit that raw temperature values from IntelliCenter
        are expressed in. Home Assistant will automatically convert the display
        to match the user's unit system preference (Settings > System > General).
        """
        system_info = self.coordinator.system_info
        if system_info is None:
            return str(UnitOfTemperature.FAHRENHEIT)

        if system_info.uses_metric:
            return str(UnitOfTemperature.CELSIUS)
        return str(UnitOfTemperature.FAHRENHEIT)

    def _safe_float_conversion(self, value: Any) -> float | None:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int_conversion(self, value: Any) -> int | None:
        """Safely convert a value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None


# -------------------------------------------------------------------------------------
# On/Off Control Mixin
# -------------------------------------------------------------------------------------


class OnOffControlMixin:
    """Mixin for entities with simple on/off control.

    Classes using this mixin must also inherit from PoolEntity.
    Implements optimistic updates for immediate UI feedback.
    """

    _pool_object: PoolObject
    _attribute_key: str
    _optimistic_state: bool | None = None  # None = use real state

    if TYPE_CHECKING:
        hass: HomeAssistant

        def request_changes(self, changes: dict[str, Any]) -> None:
            """Request changes - provided by PoolEntity."""
            ...

        def async_write_ha_state(self) -> None:
            """Write entity state to Home Assistant - provided by Entity."""
            ...

        def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
            """Check if entity was updated - provided by PoolEntity."""
            ...

    @property
    def is_on(self) -> bool:
        """Return true if the entity is on."""
        # Use optimistic state if set, otherwise use real state
        if self._optimistic_state is not None:
            return self._optimistic_state
        return bool(
            self._pool_object[self._attribute_key] == self._pool_object.on_status
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        # Optimistic update for immediate UI feedback
        self._optimistic_state = True
        self.async_write_ha_state()
        self.request_changes({self._attribute_key: self._pool_object.on_status})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        # Optimistic update for immediate UI feedback
        self._optimistic_state = False
        self.async_write_ha_state()
        self.request_changes({self._attribute_key: self._pool_object.off_status})

    @callback
    def _clear_optimistic_state(self) -> None:
        """Clear optimistic state when real update is received."""
        self._optimistic_state = None
