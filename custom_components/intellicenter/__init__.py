"""Pentair IntelliCenter Integration.

This integration connects to a Pentair IntelliCenter pool control system
via local network (not cloud) using a custom TCP protocol on port 6681.
It supports Zeroconf discovery and local push updates for real-time responsiveness.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
import contextlib
import errno
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyintellicenter import (
    BODY_ATTR,
    BODY_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    LISTORD_ATTR,
    STATUS_ATTR,
    STATUS_OFF,
    STATUS_ON,
    ICConnectionError,
    ICError,
    ICModelController,
    ICTimeoutError,
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
from .firmware import async_check_firmware

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Platforms supported by this integration
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
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


# OSError errnos that indicate a transient network condition (the panel / bridge is
# briefly unreachable or still booting) rather than a permanent local fault.
# ConnectionError and TimeoutError subclasses are always transient and handled
# separately in _is_transient_connection_error().
_TRANSIENT_OS_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, _name, None)
        for _name in (
            "EHOSTUNREACH",
            "ENETUNREACH",
            "ETIMEDOUT",
            "EHOSTDOWN",
            "ENETDOWN",
            "ENETRESET",
        )
    )
    if code is not None
)


def _is_transient_connection_error(err: Exception) -> bool:
    """Return True if ``err`` is a transient connection failure worth retrying.

    pyintellicenter raises ICConnectionError / ICTimeoutError for transport problems
    (refused, reset, timeout, EHOSTUNREACH — issue #41). ICConnectionHandler.start()
    can also re-raise a raw OSError / TimeoutError surfaced via the request future on
    the first connection attempt, so builtin connection/timeout errors and
    network-errno OSErrors are treated as transient too.

    Everything else is treated as permanent so setup fails visibly instead of retrying
    forever: ICCommandError (the panel actively rejected a command — a protocol or
    firmware incompatibility, which per HA guidance is a permanent fault rather than an
    outage) and non-network OSErrors such as PermissionError or ENOSPC.
    """
    if isinstance(err, (ICConnectionError, ICTimeoutError)):
        return True
    if isinstance(err, (ConnectionError, TimeoutError)):
        return True
    return isinstance(err, OSError) and err.errno in _TRANSIENT_OS_ERRNOS


@callback
def _async_migrate_legacy_unique_ids(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> None:
    """Adopt entities created by the pre-fork integrations.

    The jlvaillant/dwradcliffe integrations built their unique_id by
    concatenating the entry id and the objnam with no separator
    (``f"{entry_id}{objnam}"``); this integration joins them with an underscore.
    Both ship the same ``intellicenter`` domain and the same config-flow
    ``VERSION = 1``, so a user replacing those integrations with this one keeps
    their config entry, HA never calls ``async_migrate_entry``, and every
    entity's unique_id silently fails to match. The old registry entries are
    left behind as unavailable and the entities come back as ``.._2``
    duplicates, breaking every automation, dashboard card and history graph
    that referenced them.

    Rewriting the unique_id in place keeps the original entity_id, name,
    area and settings. Entries already carrying the separator are skipped, as
    are rewrites that would collide with an existing entry (which would mean
    both formats are somehow present - the newer one wins and the stale entry
    is left for the user to remove).
    """
    registry = er.async_get(hass)
    prefix = entry.entry_id
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = registry_entry.unique_id
        if not unique_id.startswith(prefix) or unique_id.startswith(f"{prefix}_"):
            continue
        new_unique_id = f"{prefix}_{unique_id[len(prefix) :]}"
        if registry.async_get_entity_id(
            registry_entry.domain, registry_entry.platform, new_unique_id
        ):
            _LOGGER.debug(
                "Not migrating %s: %s already exists",
                registry_entry.entity_id,
                new_unique_id,
            )
            continue
        _LOGGER.info(
            "Migrating %s to the current unique_id format", registry_entry.entity_id
        )
        registry.async_update_entity(
            registry_entry.entity_id, new_unique_id=new_unique_id
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> bool:
    """Set up IntelliCenter integration from a config entry."""
    # Adopt any entities left by the pre-fork integrations before the platforms
    # build theirs, so they are matched by unique_id instead of duplicated.
    _async_migrate_legacy_unique_ids(hass, entry)

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

    # Bring the connection up, then wire up platforms + the options listener. The whole
    # sequence shares one cleanup contract via `setup_complete`: on ANY non-success exit
    # the finally stops the coordinator, because async_start() starts a reconnect task +
    # EVENT_HOMEASSISTANT_STOP listener and HA does not unload an entry whose setup
    # raised — so this is the only place those can be torn down. The `connected` flag
    # scopes transient/permanent classification to the connection attempt only; a
    # post-connect failure (e.g. a platform setup error) propagates unchanged.
    connected = False
    setup_complete = False
    try:
        await coordinator.async_start()
        connected = True
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
        # Warn (via Repairs) if the panel runs firmware with documented issues;
        # also clears stale advisories after a firmware upgrade + reload.
        async_check_firmware(hass, entry, coordinator)
        setup_complete = True
    except Exception as err:
        if not connected and _is_transient_connection_error(err):
            # Transient connection failure → HA's built-in exponential-backoff retry
            # instead of a permanent setup_error needing a manual reload (issue #41).
            # The message (host + cause) is shown to the user while HA retries.
            raise ConfigEntryNotReady(
                f"Could not connect to IntelliCenter at {entry.data[CONF_HOST]}: {err}"
            ) from err
        # Permanent / unexpected fault (rejected command, non-network OSError, a
        # post-connect platform error, a programming error, ...): fail loudly as
        # setup_error rather than retry forever or mask it as transient.
        raise
    finally:
        # Runs on failure OR cancellation (CancelledError is a BaseException that
        # bypasses `except Exception`). async_stop() is null-safe on a partial start;
        # suppress so cleanup never masks the original exception. A coordinator left in
        # runtime_data by a post-connect failure is now stopped (inert) and is replaced
        # on the next setup attempt.
        if not setup_complete:
            with contextlib.suppress(Exception):
                await coordinator.async_stop()

    return True


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
# Dynamic entity setup helper
# -------------------------------------------------------------------------------------


def async_setup_pool_entities(
    entry: IntelliCenterConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[
        [IntelliCenterCoordinator, Iterable[PoolObject]], list[Any]
    ],
) -> None:
    """Create entities now and whenever new pool objects appear at runtime.

    Every platform builds its entities by inspecting the objects in the pool
    model. This helper runs that builder once for the objects present at setup,
    then registers a coordinator listener so the same builder runs for any
    equipment that is added later (issue #42) - for example a second IntelliChem
    controller coming online - without requiring a Home Assistant restart.

    Entities are de-duplicated by ``unique_id`` so an object can never produce a
    duplicate entity, even though the coordinator already reports each new object
    only once. A duplicate builder result refreshes the original entity's shared
    model context, allowing cross-object capabilities to change in place.

    The reverse direction is handled too: equipment deleted at the panel is
    pruned from the model by pyintellicenter's reconnect reconciliation and
    reported through the coordinator's removed-objects listeners; the removed
    object's entities are deleted from the entity registry (and the dedup map),
    so re-added equipment gets fresh entities instead of being swallowed.

    Args:
        entry: The config entry whose ``runtime_data`` is the coordinator.
        async_add_entities: The platform's add-entities callback.
        build_entities: Builds the entity objects for a set of candidate pool
            objects. Receives the coordinator (for cross-object lookups) and the
            objects to consider; returns the list of entities to add.
    """
    coordinator = entry.runtime_data
    created_entities: dict[str, Any] = {}

    @callback
    def _add(candidates: Iterable[PoolObject]) -> None:
        entities: list[Any] = []
        for entity in build_entities(coordinator, candidates):
            uid = entity.unique_id
            existing = created_entities.get(uid)
            if existing is not None:
                existing.async_refresh_model_context()
                continue
            created_entities[uid] = entity
            entities.append(entity)
        if entities:
            async_add_entities(entities)

    @callback
    def _remove(removed_objnams: set[str]) -> None:
        # Scope: removes the entities OF the removed objects. Entities that
        # merely *depend* on them (a body's water_heater/climate whose last
        # heater was deleted) are not retired - they keep rendering from their
        # construction-time seed until the integration is reloaded. Removals
        # only dispatch during reconnect reconciliation, so an entity add
        # in flight at that moment (built but not yet registered) is a
        # theoretical gap accepted here: such an entity is dropped from the
        # dedup map but cannot be deleted from a registry it isn't in yet, and
        # the same equipment returning before the platform finishes the
        # pending teardown could have its replacement rejected as a duplicate.
        # Both require a second reconnect cycle inside the removal's own event
        # loop turn, which cannot happen in practice.
        registry = er.async_get(coordinator.hass)
        for uid, entity in list(created_entities.items()):
            if entity._pool_object.objnam not in removed_objnams:
                continue
            # Drop the dedup record first so the equipment coming back later
            # is built fresh rather than swallowed by the unique_id filter.
            del created_entities[uid]
            entity_id = getattr(entity, "entity_id", None)
            if entity_id and registry.async_get(entity_id) is not None:
                # Registry removal also removes the entity from the state
                # machine; it must not linger as a restorable ghost.
                registry.async_remove(entity_id)
            elif entity.hass is not None:
                # Added to HA but (unexpectedly) not registered: remove the
                # live entity directly.
                entity.hass.async_create_task(
                    entity.async_remove(force_remove=True),
                    f"intellicenter_remove_{uid}",
                )

    # Initial population from the objects discovered at setup.
    _add(list(coordinator.model))

    # Dynamic population for objects added after startup, and removal of
    # entities whose equipment was deleted at the panel (ghost equipment).
    entry.async_on_unload(coordinator.async_add_new_objects_listener(_add))
    entry.async_on_unload(coordinator.async_add_removed_objects_listener(_remove))


def bodies_affected_by(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[PoolObject]:
    """Return bodies of water touched by the candidate objects.

    Heater-dependent platforms (water_heater, climate) create one entity per
    body, but whether that entity exists depends on the heaters wired to the
    body. A body is included when it is itself a candidate OR when a candidate
    heater serves it, so adding a heater to a body re-evaluates that body
    (issue #42). When the body already has an entity, the duplicate is filtered
    by ``async_setup_pool_entities`` via ``unique_id`` and the existing entity
    instead picks up the new heater from its live heater list (issue #57).

    Args:
        coordinator: The coordinator providing the pool model.
        candidates: The newly-considered pool objects.

    Returns:
        The list of body PoolObjects to (re)evaluate.
    """
    body_objnams: set[str] = set()
    for obj in candidates:
        if obj.objtype == BODY_TYPE:
            body_objnams.add(obj.objnam)
        elif obj.objtype == HEATER_TYPE:
            served = obj[BODY_ATTR]
            if served:
                body_objnams.update(served.split(" "))

    bodies: list[PoolObject] = []
    for objnam in body_objnams:
        body = coordinator.model[objnam]
        if body is not None and body.objtype == BODY_TYPE:
            bodies.append(body)
    return bodies


def safe_int(value: Any) -> int | None:
    """Convert a device-supplied value to int, or None if it isn't numeric.

    Attribute values arrive from the panel as strings and are not guaranteed to
    parse; an unguarded int() inside an entity builder or state property can
    take down a whole platform on one malformed value.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def protocol_on_off(value: Any) -> bool | None:
    """Map the protocol's canonical ON/OFF values to a nullable boolean."""
    if value == STATUS_ON:
        return True
    if value == STATUS_OFF:
        return False
    return None


def is_user_circuit(pool_object: PoolObject) -> bool:
    """Return whether an object is a user-controllable circuit.

    Freeze-protection pseudo-circuits are diagnostic state objects rather than
    user circuits. All other CIRCUIT objects are represented by either the
    switch or light platform and share circuit configuration controls.
    """
    return pool_object.objtype == CIRCUIT_TYPE and pool_object.subtype != "FRZ"


def _heater_sort_key(heater: PoolObject) -> int:
    """Sort heaters by LISTORD; unparsable or missing values sort last."""
    order = safe_int(heater[LISTORD_ATTR])
    return order if order is not None else 100


def heaters_for_body(
    coordinator: IntelliCenterCoordinator, body_objnam: str
) -> list[str]:
    """Return the objnams of the heaters wired to a body, in UI order.

    A heater serves a body when the body's objnam appears in the heater's
    (space-separated) ``BODY`` attribute. Heaters are ordered by ``LISTORD``;
    those without one sort last.

    Heater-dependent entities (water_heater, climate) call this against the
    *live* model so their heater composition tracks heaters added to an existing
    body at runtime, rather than being frozen when the entity was built (issue
    #57).

    Args:
        coordinator: The coordinator providing the pool model.
        body_objnam: The body whose heaters should be returned.

    Returns:
        The heater objnams serving the body, ordered by ``LISTORD``.
    """
    heaters = sorted(
        coordinator.model.get_by_type(HEATER_TYPE),
        key=_heater_sort_key,
    )
    return [
        heater.objnam
        for heater in heaters
        if body_objnam in (heater[BODY_ATTR] or "").split(" ")
    ]


def body_temperature_limits(
    coordinator: IntelliCenterCoordinator,
) -> tuple[float, float]:
    """Return the valid body temperature setpoint range in the panel's unit.

    IntelliCenter accepts body setpoints of 40-104 °F; on METRIC systems the
    equivalent 5-40 °C. This is the single source for every platform exposing
    body temperature setpoints (water_heater, climate, number/HITMP) - the
    limits were previously hard-coded per platform and had drifted (a 4 °F
    floor typo in water_heater).

    Args:
        coordinator: The coordinator providing the system info.

    Returns:
        (min, max) in the panel's native temperature unit.
    """
    system_info = coordinator.system_info
    if system_info is not None and system_info.uses_metric:
        return (5.0, 40.0)
    return (40.0, 104.0)


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

    # Optimistic on/off state rendered ahead of the device echo; None means
    # "render the real model state". Owned here (not on the mixin) so the
    # clear-on-update/-failure hooks below work for every subclass regardless
    # of MRO ordering.
    _optimistic_state: bool | None = None

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
        """Async helper to request changes with error handling.

        Runs as a fire-and-forget task, so a failure cannot be raised back to
        the service call. Instead, any optimistic state is reverted and the
        entity re-rendered from the model - otherwise a failed command (e.g.
        issued while the connection drops) would leave the UI showing a state
        the device never reached, with no push update ever clearing it.
        """
        try:
            await self._controller.request_changes(self._pool_object.objnam, changes)
        except Exception:
            _LOGGER.exception(
                "Failed to request changes for %s: %s",
                self._pool_object.objnam,
                changes,
            )
            self._clear_optimistic_state()
            self.async_write_ha_state()

    async def _async_execute_command(
        self,
        command: Awaitable[Any],
        translation_key: str | None = None,
    ) -> Any:
        """Await a controller command, surfacing failures as HomeAssistantError.

        pyintellicenter raises ICError subclasses (connection lost, command
        rejected, request timeout) and ValueError (setpoint validation); none
        of them subclass HomeAssistantError, so without this conversion a
        failed service call surfaces as a raw 'Unknown error' traceback.
        """
        try:
            return await command
        except (ICError, ValueError) as err:
            if translation_key is not None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key=translation_key,
                ) from err
            raise HomeAssistantError(
                f"IntelliCenter command for '{self.name}' failed: {err}"
            ) from err

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
    def async_refresh_model_context(self) -> None:
        """Refresh state derived from other objects in the shared model."""

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
            self._clear_optimistic_state()
            self.async_write_ha_state()
        elif not updates:
            if self.coordinator.model[self._pool_object.objnam] is None:
                # The object is gone from the model (equipment deleted at the
                # panel): this entity is concurrently being removed by the
                # platform's removed-objects listener. Skip the re-render so a
                # doomed entity can't write one last ghost state in the same
                # fan-out that announced its removal.
                return
            # Connection event (the coordinator cleared its diff): re-render every
            # entity so availability changes take effect, and drop any optimistic
            # state - after a reconnect the model is the fresh source of truth, and
            # a command issued around a disconnect may never produce the echo update
            # that would otherwise clear it.
            self._clear_optimistic_state()
            self.async_write_ha_state()

    @callback
    def _clear_optimistic_state(self) -> None:
        """Clear any optimistic state once authoritative data arrives.

        Harmless for entities that never render optimistically (the attribute
        stays None for them).
        """
        self._optimistic_state = None

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


# -------------------------------------------------------------------------------------
# On/Off Control Mixin
# -------------------------------------------------------------------------------------


# Under static type checking the mixin is treated as an ``Entity`` subclass so
# mypy can resolve the ``Entity`` members it uses (``hass``,
# ``async_write_ha_state``) without redeclaring them - redeclaring
# ``async_write_ha_state`` would clash with its ``@final`` marker on ``Entity``.
# At runtime the mixin stays a plain ``object`` subclass, so the method
# resolution order of the concrete entity classes is unchanged.
if TYPE_CHECKING:
    _MixinBase = Entity
else:
    _MixinBase = object


class OnOffControlMixin(_MixinBase):
    """Mixin for entities with simple on/off control.

    Classes using this mixin must also inherit from PoolEntity, which owns the
    optimistic-state attribute and its clearing hooks (on real updates,
    connection events, and failed fire-and-forget commands).
    """

    _pool_object: PoolObject
    _attribute_key: str
    _optimistic_state: bool | None

    if TYPE_CHECKING:

        def request_changes(self, changes: dict[str, Any]) -> None:
            """Request changes - provided by PoolEntity."""
            ...

        def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
            """Check if entity was updated - provided by PoolEntity."""
            ...

    @property
    def is_on(self) -> bool | None:
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
