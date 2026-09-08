"""DataUpdateCoordinator for Pentair IntelliCenter.

This module provides a coordinator that manages the connection to the IntelliCenter
system and distributes updates to all entities. Since IntelliCenter uses push-based
updates (local_push), this coordinator doesn't poll but instead receives real-time
notifications from the controller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyintellicenter import (
    # Attribute constants for tracking
    ACT_ATTR,
    ALK_ATTR,
    BODY_ATTR,
    BODY_TYPE,
    CALC_ATTR,
    CHEM_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_ATTR,
    CIRCUIT_TYPE,
    COOL_ATTR,
    CYACID_ATTR,
    DAY_ATTR,
    EXTINSTR_TYPE,
    FEATR_ATTR,
    FREEZE_ATTR,
    GPM_ATTR,
    HEATER_ATTR,
    HEATER_TYPE,
    HITMP_ATTR,
    HTMODE_ATTR,
    LISTORD_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MAX_ATTR,
    MAXF_ATTR,
    MIN_ATTR,
    MINF_ATTR,
    MODE_ATTR,
    MODULE_TYPE,
    NORMAL_ATTR,
    OBJTYP_ATTR,
    ORPHI_ATTR,
    ORPLO_ATTR,
    ORPSET_ATTR,
    ORPTNK_ATTR,
    ORPVAL_ATTR,
    ORPVOL_ATTR,
    PARENT_ATTR,
    PHHI_ATTR,
    PHLO_ATTR,
    PHSET_ATTR,
    PHTNK_ATTR,
    PHVAL_ATTR,
    PHVOL_ATTR,
    PMPCIRC_TYPE,
    POSIT_ATTR,
    PRIM_ATTR,
    PUMP_TYPE,
    PWR_ATTR,
    QUALTY_ATTR,
    RPM_ATTR,
    SALT_ATTR,
    SCHED_TYPE,
    SEC_ATTR,
    SELECT_ATTR,
    SENSE_TYPE,
    SERVICE_ATTR,
    SINDEX_ATTR,
    SNAME_ATTR,
    SOURCE_ATTR,
    SPEED_ATTR,
    STATUS_ATTR,
    SUBTYP_ATTR,
    SUPER_ATTR,
    SYSTEM_TYPE,
    TEMP_ATTR,
    TIME_ATTR,
    TIMOUT_ATTR,
    UPDATE_ATTR,
    USE_ATTR,
    VACFLO_ATTR,
    VER_ATTR,
    VOL_ATTR,
    ICBaseController,
    ICConnectionHandler,
    ICModelController,
    ICSystemInfo,
    PoolModel,
    PoolObject,
)

from .const import (
    CALIB_ATTR,
    DEFAULT_TRANSPORT,
    DNTSTP_ATTR,
    DOMAIN,
    LIMIT_ATTR,
    MANHT_ATTR,
    PORT_ATTR,
    PRIMFLO_ATTR,
    PRIMTIM_ATTR,
    PROBE_ATTR,
    SINGLE_ATTR,
    TransportType,
)

_LOGGER = logging.getLogger(__name__)

# Callback invoked when previously-unseen pool objects appear in the model at
# runtime. Each platform registers one of these so it can create entities for
# newly-added equipment without requiring a Home Assistant restart (issue #42).
NewObjectsListener = Callable[[list[PoolObject]], None]

# Callback invoked with the objnams of pool objects removed from the model.
# pyintellicenter 0.2.0 reconciles the model against the authoritative connect
# snapshot on every (re)connect: equipment deleted at the panel is pruned from
# the model and reported as a ``{objnam: None}`` entry through the update
# dispatch. Each platform registers one of these so it can remove the
# corresponding entities.
RemovedObjectsListener = Callable[[set[str]], None]


@dataclass(frozen=True, slots=True)
class ObjectUpdateContext:
    """Resolve the pool objects whose updates can affect one entity."""

    objnams: Callable[[], set[str]]
    invalidate: CALLBACK_TYPE


# These configuration attributes change the dependency graph itself. They are
# rare structural updates, so rebuild every entity edge and broadcast them.
_DEPENDENCY_EDGE_ATTRIBUTES = frozenset({BODY_ATTR, CIRCUIT_ATTR, PARENT_ATTR})

# PoolObject pops these attributes into dedicated slots, so they never appear
# in attribute_keys even when supplied by the panel.
_SLOTTED_ATTRS = frozenset({OBJTYP_ATTR, SUBTYP_ATTR})


# Default attribute tracking map - defines which attributes to monitor per object type
DEFAULT_ATTRIBUTES_MAP: dict[str, set[str]] = {
    BODY_TYPE: {
        SNAME_ATTR,
        HEATER_ATTR,
        HITMP_ATTR,  # Max temperature setpoint
        HTMODE_ATTR,
        LOTMP_ATTR,
        LSTTMP_ATTR,
        MODE_ATTR,  # Heat mode (used by multi-mode heaters like HCOMBO)
        STATUS_ATTR,
        TEMP_ATTR,
        VOL_ATTR,
    },
    CIRCUIT_TYPE: {
        SNAME_ATTR,
        STATUS_ATTR,
        USE_ATTR,
        SUBTYP_ATTR,
        FEATR_ATTR,
        LIMIT_ATTR,
        TIME_ATTR,  # Egg timer duration
        DNTSTP_ATTR,
        FREEZE_ATTR,  # Freeze protection status
    },
    CIRCGRP_TYPE: {
        PARENT_ATTR,
        CIRCUIT_ATTR,
        LISTORD_ATTR,
    },  # Circuit-group membership rows
    CHEM_TYPE: {
        SNAME_ATTR,
        BODY_ATTR,
        PRIM_ATTR,
        SEC_ATTR,
        SUPER_ATTR,
        SUBTYP_ATTR,
        # IntelliChem sensors (read-only)
        PHVAL_ATTR,
        ORPVAL_ATTR,
        PHTNK_ATTR,
        ORPTNK_ATTR,
        QUALTY_ATTR,
        # IntelliChem dosing volume sensors (cumulative, diagnostic)
        PHVOL_ATTR,
        ORPVOL_ATTR,
        # IntelliChem setpoints (controllable)
        PHSET_ATTR,
        ORPSET_ATTR,
        # IntelliChem water chemistry settings (read-only)
        ALK_ATTR,
        CALC_ATTR,
        CYACID_ATTR,
        SINDEX_ATTR,
        # IntelliChem alarm indicators (diagnostic)
        PHHI_ATTR,
        PHLO_ATTR,
        ORPHI_ATTR,
        ORPLO_ATTR,
        # IntelliChlor sensors
        SALT_ATTR,
        TIMOUT_ATTR,
    },
    # External instruments (pool covers). Without this entry PoolModel drops the
    # objects entirely and the cover platform never sees them (the model only
    # admits objtypes present in this map).
    EXTINSTR_TYPE: {
        SNAME_ATTR,
        STATUS_ATTR,
        POSIT_ATTR,
        NORMAL_ATTR,
        SUBTYP_ATTR,
    },
    # COOL is required by is_body_cooling(): without tracking it the heater
    # object's COOL attribute is never fetched and climate could never report
    # the COOLING action.
    HEATER_TYPE: {SNAME_ATTR, BODY_ATTR, COOL_ATTR, LISTORD_ATTR, SUBTYP_ATTR},
    PUMP_TYPE: {
        SNAME_ATTR,
        STATUS_ATTR,
        PWR_ATTR,
        RPM_ATTR,
        GPM_ATTR,
        PRIMFLO_ATTR,
        PRIMTIM_ATTR,
        # Pump operational limits (diagnostic)
        MAX_ATTR,
        MIN_ATTR,
        MAXF_ATTR,
        MINF_ATTR,
        SUBTYP_ATTR,  # Pump type: SPEED, FLOW, VSF
    },
    PMPCIRC_TYPE: {
        SNAME_ATTR,
        PARENT_ATTR,  # The pump this circuit setting belongs to
        CIRCUIT_ATTR,  # The circuit this setting is for
        SELECT_ATTR,  # "RPM" or "GPM" - determines which setpoint is active
        SPEED_ATTR,  # RPM setpoint when SELECT=RPM
        GPM_ATTR,  # GPM setpoint when SELECT=GPM
    },
    SENSE_TYPE: {SNAME_ATTR, SOURCE_ATTR, PROBE_ATTR, CALIB_ATTR},
    SCHED_TYPE: {
        SNAME_ATTR,
        STATUS_ATTR,
        ACT_ATTR,
        CIRCUIT_ATTR,
        DAY_ATTR,
        TIME_ATTR,
        TIMOUT_ATTR,
        HEATER_ATTR,
        LOTMP_ATTR,
        SINGLE_ATTR,
        DNTSTP_ATTR,
        VACFLO_ATTR,
    },
    # System unit/mode, vacation, firmware/update, manual-heat, plus SERVICE for
    # the system operating mode sensor
    SYSTEM_TYPE: {
        MANHT_ATTR,
        MODE_ATTR,
        SERVICE_ATTR,
        UPDATE_ATTR,
        VACFLO_ATTR,
        VER_ATTR,
    },
    MODULE_TYPE: {SNAME_ATTR, SUBTYP_ATTR, VER_ATTR, PORT_ATTR},
}


class IntelliCenterCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for IntelliCenter push-based updates.

    This coordinator manages the connection to an IntelliCenter system and
    coordinates updates across all entities. Unlike traditional polling
    coordinators, it receives real-time push updates from the controller.

    Attributes:
        controller: The ICModelController managing the connection
        model: The PoolModel containing all pool objects
        config_entry: The config entry for this integration instance
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        keepalive_interval: int = 90,
        reconnect_delay: int = 30,
        transport: TransportType = DEFAULT_TRANSPORT,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance
            entry: The config entry for this integration
            host: The IP address or hostname of the IntelliCenter
            keepalive_interval: How often to send keepalive queries (seconds)
            reconnect_delay: Initial delay before reconnection attempts (seconds)
            transport: Transport type ("tcp" or "websocket")
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            # No update_interval - we use push updates
        )

        self._object_update_listeners: dict[str, dict[CALLBACK_TYPE, None]] = {}
        # ponytail: CoordinatorEntity registers each bound entity callback once,
        # so callback identity is equivalent to HA's internal listener id here.
        self._object_update_contexts: dict[CALLBACK_TYPE, ObjectUpdateContext] = {}
        self._broadcast_update_listeners: dict[CALLBACK_TYPE, None] = {}
        self._failed_object_update_listeners: dict[CALLBACK_TYPE, None] = {}
        self._logged_object_update_failures: set[CALLBACK_TYPE] = set()
        self._structural_refresh = False

        self.config_entry = entry
        self._host = host
        self._keepalive_interval = keepalive_interval
        self._reconnect_delay = reconnect_delay
        self._transport = transport

        # Create the model with attribute tracking
        self._model = PoolModel(DEFAULT_ATTRIBUTES_MAP)

        # Create the controller
        self._controller = ICModelController(
            host,
            self._model,
            keepalive_interval=keepalive_interval,
            transport=transport,
        )

        # Create the connection handler
        self._handler = _CoordinatorConnectionHandler(
            self,
            self._controller,
            time_between_reconnects=reconnect_delay,
        )

        # Model updates arrive through a per-object subscription
        # (pyintellicenter 0.2.0) rather than the handler's single legacy
        # ``on_updated`` slot. Registering here - before any start() - means no
        # update (including the ``{objnam: None}`` removal entries emitted by
        # reconnect reconciliation) can be dispatched unobserved. The
        # subscription is deliberately never removed: its lifetime equals the
        # controller's (both die with this coordinator), and after astop() the
        # controller dispatches nothing - while an unsubscribe-on-stop would
        # silently starve a handler restarted after a stop.
        self._handler.subscribe(None, self._handle_model_updates)

        self._stop_listener: CALLBACK_TYPE | None = None

        # Dynamic-entity-addition state (issue #42).
        # `_known_objnams` is the set of object identifiers the platforms have
        # already created entities for. It is seeded once the initial connection
        # completes (so the objects present at setup are not treated as "new"),
        # then reconciled against the model whenever updates arrive or the
        # connection is (re)established. `_started` gates detection so the burst
        # of attribute updates emitted during the very first controller.start()
        # is ignored - the seed captures that full initial object set instead.
        self._known_objnams: set[str] = set()
        self._started = False
        self._new_objects_listeners: list[NewObjectsListener] = []
        self._removed_objects_listeners: list[RemovedObjectsListener] = []
        # Runtime-added objects may receive tracked attributes across multiple
        # updates. Remember seen keys so each later key growth can be dispatched,
        # and retain initially empty keys until a builder can use their value.
        self._pending_redispatch: dict[str, set[str]] = {}
        self._pending_truthy_redispatch: dict[str, set[str]] = {}

    @callback
    def async_add_listener(
        self, update_callback: CALLBACK_TYPE, context: Any = None
    ) -> Callable[[], None]:
        """Register a listener for its declared pool-object dependencies."""
        remove_listener = super().async_add_listener(update_callback, context)
        if isinstance(context, ObjectUpdateContext):
            self._object_update_contexts[update_callback] = context
            self._async_index_object_listener(update_callback, context)
        else:
            self._broadcast_update_listeners[update_callback] = None

        removed = False

        @callback
        def _remove_listener() -> None:
            nonlocal removed
            if removed:
                return
            removed = True
            self._object_update_contexts.pop(update_callback, None)
            self._broadcast_update_listeners.pop(update_callback, None)
            self._failed_object_update_listeners.pop(update_callback, None)
            self._logged_object_update_failures.discard(update_callback)
            for listeners in self._object_update_listeners.values():
                listeners.pop(update_callback, None)
            remove_listener()

        return _remove_listener

    @callback
    def _async_index_object_listener(
        self, update_callback: CALLBACK_TYPE, context: ObjectUpdateContext
    ) -> None:
        """Add one entity callback to each object it depends on."""
        self._broadcast_update_listeners.pop(update_callback, None)
        try:
            objnams = context.objnams()
        except Exception:
            if update_callback not in self._logged_object_update_failures:
                _LOGGER.exception(
                    "Error resolving object dependencies for listener %s",
                    id(update_callback),
                )
                self._logged_object_update_failures.add(update_callback)
            self._broadcast_update_listeners[update_callback] = None
            self._failed_object_update_listeners[update_callback] = None
            return
        self._failed_object_update_listeners.pop(update_callback, None)
        self._logged_object_update_failures.discard(update_callback)
        for objnam in objnams:
            self._object_update_listeners.setdefault(objnam, {})[update_callback] = None

    @callback
    def _async_refresh_object_listener_index(self) -> None:
        """Rebuild dependency edges after the pool-model structure changes."""
        self._object_update_listeners.clear()
        for update_callback, context in self._object_update_contexts.items():
            context.invalidate()
            self._async_index_object_listener(update_callback, context)

    @callback
    def _async_update_object_listeners(self, updated_objnams: set[str]) -> None:
        """Notify only listeners interested in the changed pool objects."""
        for update_callback in tuple(self._failed_object_update_listeners):
            context = self._object_update_contexts.get(update_callback)
            if context is not None:
                self._async_index_object_listener(update_callback, context)
        listeners = dict(self._broadcast_update_listeners)
        for objnam in updated_objnams:
            listeners.update(self._object_update_listeners.get(objnam, {}))
        for update_callback in listeners:
            try:
                update_callback()
            except Exception:
                _LOGGER.exception(
                    "Unexpected error updating listener %s for %s",
                    id(update_callback),
                    self.name,
                )

    @property
    def controller(self) -> ICModelController:
        """Return the ICModelController."""
        return self._controller

    @property
    def model(self) -> PoolModel:
        """Return the PoolModel."""
        return self._model

    @property
    def system_info(self) -> ICSystemInfo | None:
        """Return the system info from the controller."""
        return self._controller.system_info

    @property
    def structural_refresh(self) -> bool:
        """Return whether the current listener fan-out is structural."""
        return self._structural_refresh

    @property
    def connected(self) -> bool:
        """Return True if connected to the IntelliCenter.

        Delegates to the handler's ``connected`` property (pyintellicenter
        >= 0.2.2), which is ``not stopped and (handler flag or live
        transport)``. Crucially it reads ``True`` throughout a (re)connect's
        in-``start()`` object snapshot/backfill dispatch - the socket is up even
        though the handler's own flag is not set until ``start()`` returns - and
        ``False`` on a genuine outage or after stop. Gating entity availability
        on it is therefore correct: entities render available as the reconnect's
        fresh state fans out, with no spurious "unavailable" flicker.

        History: pyintellicenter 0.2.0/0.2.1 set the handler flag only *after*
        that in-``start()`` dispatch, so an earlier attempt to delegate here
        rendered every entity momentarily unavailable on each reconnect and was
        reverted. The library fixed it in 0.2.2 (#89) by or-ing the live
        transport into ``connected``; the manifest pin requires ``>= 0.2.2``.
        """
        return self._handler.connected

    async def async_start(self) -> None:
        """Start the connection to the IntelliCenter."""

        # Register stop listener
        async def _on_hass_stop(event: Any) -> None:
            """Stop the connection when Home Assistant stops.

            Runs the same async_stop as unload, so shutdown awaits the full
            controller teardown (astop) - the pre-0.2.0 fire-and-forget stop()
            could leave the socket half-closed when the event loop shut down
            underneath the untracked teardown task. The once-listener has
            already fired, so drop its reference first: a later unload's
            async_stop must not re-invoke the spent remover.
            """
            self._stop_listener = None
            await self.async_stop()

        self._stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, _on_hass_stop
        )

        # Start the connection
        await self._handler.start()

        # Snapshot the objects discovered during the initial connection. Anything
        # that appears in the model after this point is treated as newly-added
        # equipment and dispatched to the registered platform listeners.
        self._known_objnams = {obj.objnam for obj in self._model}
        self._started = True
        # Initial objects can also defer builders on missing or falsy attributes.
        for obj in self._model:
            self._seed_redispatch_bookkeeping(obj, only_if_deferred=True)

    async def async_stop(self) -> None:
        """Stop the connection to the IntelliCenter.

        Waits for the full controller teardown (``astop``), so
        ``async_unload_entry`` cannot complete - and a reload cannot reconnect
        - over a connection that is still closing.
        """
        # Cancel stop listener
        if self._stop_listener:
            self._stop_listener()
            self._stop_listener = None

        # Stop the handler and wait for the teardown. The model-update
        # subscription stays registered (see __init__): the stopped controller
        # dispatches nothing, and removing it would starve a restarted handler.
        # ``connected`` reads False immediately once the handler is stopped
        # (its ``_stopped`` guard), even before the teardown task closes the
        # socket.
        await self._handler.astop()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from the IntelliCenter.

        This method is not used for regular updates since IntelliCenter
        uses push-based updates. It's only called for the initial fetch
        or manual refresh requests.

        Returns:
            Empty dict since data is pushed, not pulled.
        """
        # Data is pushed via the connection handler, not pulled
        return {}

    @callback
    def async_add_new_objects_listener(
        self, listener: NewObjectsListener
    ) -> CALLBACK_TYPE:
        """Register a callback for newly-added pool objects.

        Each platform registers a listener during setup so it can create
        entities for equipment that appears after the integration has started
        (issue #42), e.g. a second IntelliChem controller coming online. The
        listener receives the list of new PoolObjects each time previously-unseen
        objects are detected in the model.

        Args:
            listener: Callback invoked with the list of new PoolObjects.

        Returns:
            A callable that unregisters the listener.
        """
        self._new_objects_listeners.append(listener)

        @callback
        def _remove_listener() -> None:
            self._new_objects_listeners.remove(listener)

        return _remove_listener

    @callback
    def async_add_removed_objects_listener(
        self, listener: RemovedObjectsListener
    ) -> CALLBACK_TYPE:
        """Register a callback for pool objects removed from the model.

        pyintellicenter reconciles the model against the authoritative connect
        snapshot on every (re)connect: equipment deleted at the panel is pruned
        and reported as ``{objnam: None}`` update entries. Each platform
        registers a listener so it can remove the corresponding entities at
        runtime instead of leaving ghosts behind until a restart.

        Args:
            listener: Callback invoked with the set of removed objnams.

        Returns:
            A callable that unregisters the listener.
        """
        self._removed_objects_listeners.append(listener)

        @callback
        def _remove_listener() -> None:
            self._removed_objects_listeners.remove(listener)

        return _remove_listener

    @callback
    def _seed_redispatch_bookkeeping(
        self, obj: PoolObject, *, only_if_deferred: bool = False
    ) -> None:
        """Remember tracked keys whose entity builders may need another pass."""
        tracked_keys = DEFAULT_ATTRIBUTES_MAP.get(obj.objtype, set())
        completeness_keys = tracked_keys - _SLOTTED_ATTRS
        seen_keys = set(obj.attribute_keys) & tracked_keys
        pending_truthy_keys = {key for key in seen_keys if not obj[key]}
        if only_if_deferred and not (
            completeness_keys - seen_keys or pending_truthy_keys
        ):
            return
        # Do not time-bound missing keys: #155 permits legitimately late tracked
        # values, while object-removal pruning bounds this bookkeeping's lifetime.
        self._pending_redispatch[obj.objnam] = seen_keys
        self._pending_truthy_redispatch[obj.objnam] = pending_truthy_keys

    @callback
    def _async_detect_new_objects(
        self, changed_objnams: set[str] | None = None
    ) -> set[str]:
        """Detect objects added to the model and notify platform listeners.

        Compares the current model against the set of objects the platforms
        already know about. Any new objects are recorded and dispatched to the
        registered listeners so the platforms can create entities for them at
        runtime. Does nothing until the initial connection has completed.
        Returns the objnams dispatched as new (empty when nothing changed).

        When changed_objnams is provided, only those direct model lookups are
        considered. A None value performs the full snapshot reconciliation used
        after initial connection and reconnect.

        Both independent and dependent new equipment are handled. Independent
        objects (e.g. a newly-installed IntelliChem) dispatch on their own.
        Some entities, however, can only be built once *another* object exists:
        a PMPCIRC's select/number entities need its parent pump, and a body's
        heater-dependent entities need the heater. To cover the case where the
        dependency arrives in a *separate, later* update than the child, any
        already-known object whose parent is among the just-arrived objects is
        re-dispatched alongside the new objects so a previously-skipped entity
        now gets built (issue #57). ``unique_id`` de-duplication in the platforms
        makes re-dispatching an already-built dependent harmless.
        """
        if not self._started:
            return set()

        if changed_objnams is None:
            candidates = list(self._model)
        else:
            candidates = [
                obj
                for objnam in changed_objnams
                if (obj := self._model[objnam]) is not None
            ]
        new_objects = [
            obj for obj in candidates if obj.objnam not in self._known_objnams
        ]
        if not new_objects:
            return set()

        # Re-evaluate already-known children whose parent is among the objects
        # that just arrived. Such a child was skipped earlier (its parent was
        # absent) and would otherwise never be reconsidered. Guard PARENT_ATTR
        # access: not every object carries it.
        new_objnams = {obj.objnam for obj in new_objects}
        dependents = [
            obj
            for obj in self._model
            if obj.objnam in self._known_objnams
            and obj.objnam not in new_objnams
            and (obj[PARENT_ATTR] or "") in new_objnams
        ]

        # Record before notifying so a listener cannot observe the objects as
        # "new" a second time (e.g. via a re-entrant refresh); duplicate entity
        # creation is additionally guarded by unique_id de-duplication in the
        # platforms. Dependents are already known, so they need no recording.
        self._known_objnams.update(new_objnams)
        # Track only objects whose later key growth can re-run entity builders.
        # Some builders require a truthy value, so a key that first arrives empty
        # remains pending until a later update makes it usable.
        for obj in new_objects:
            self._seed_redispatch_bookkeeping(obj, only_if_deferred=True)

        dependents_note = ""
        if dependents:
            dependents_note = (
                f"; re-evaluating {len(dependents)} dependent(s): "
                + ", ".join(obj.objnam for obj in dependents)
            )
        _LOGGER.debug(
            "Detected %d new pool object(s): %s%s",
            len(new_objects),
            ", ".join(obj.objnam for obj in new_objects),
            dependents_note,
        )
        # Dispatch the new objects together with any dependents whose parent just
        # arrived, so a child that was skipped before its parent existed is now
        # built. Dispatch to each platform independently: a failure in one
        # platform's builder must not skip the rest. Builders are deterministic,
        # so a logged error would recur rather than resolve on retry, which is
        # why the objects stay recorded as known above.
        dispatched = new_objects + dependents
        for listener in list(self._new_objects_listeners):
            try:
                listener(dispatched)
            except Exception:
                _LOGGER.exception(
                    "Error dispatching new pool objects to a platform listener"
                )
        return new_objnams

    @callback
    def _async_redispatch_backfilled(
        self, changes: Mapping[str, dict[str, Any]]
    ) -> bool:
        """Re-dispatch newly-added objects once their attribute backfill arrives.

        A runtime-added object reaches the platforms before the controller has
        fetched its full tracked-attribute set, so builders that gate on those
        attributes (pump PWR/RPM/GPM sensors, parent-pump limits) skip it.
        Initial-connect objects with unusable tracked values need the same retry.
        A subsequent update is relevant when its payload introduces a new tracked
        attribute key or makes a previously empty tracked value truthy. Ordinary
        value changes after a key has become usable must not rebuild entities.
        Dispatch the object (and any dependents whose parent it is) on each such
        transition. ``unique_id`` de-duplication in the platforms makes this
        harmless for entities that were already built. Returns whether a
        structural re-dispatch occurred.
        """
        if not self._pending_redispatch:
            return False
        ready_objnams: set[str] = set()
        for objnam, attributes in changes.items():
            seen_keys = self._pending_redispatch.get(objnam)
            pending_truthy_keys = self._pending_truthy_redispatch.get(objnam)
            obj = self._model[objnam]
            if seen_keys is None or pending_truthy_keys is None or obj is None:
                continue
            tracked_keys = DEFAULT_ATTRIBUTES_MAP.get(obj.objtype, set())
            arrived_keys = attributes.keys() & obj.attribute_keys & tracked_keys
            new_keys = arrived_keys - seen_keys
            became_truthy = {
                key for key in arrived_keys & pending_truthy_keys if obj[key]
            }
            if new_keys or became_truthy:
                seen_keys.update(arrived_keys)
                pending_truthy_keys.update(key for key in new_keys if not obj[key])
                pending_truthy_keys.difference_update(became_truthy)
                ready_objnams.add(objnam)
                completeness_keys = tracked_keys - _SLOTTED_ATTRS
                if completeness_keys <= seen_keys and not pending_truthy_keys:
                    self._pending_redispatch.pop(objnam, None)
                    self._pending_truthy_redispatch.pop(objnam, None)
        if not ready_objnams:
            return False

        ready = [
            obj for objnam in ready_objnams if (obj := self._model[objnam]) is not None
        ]
        # Children gated on a parent that was incomplete at first dispatch
        # (e.g. a PMPCIRC whose pump lacked MIN/MAX limits) get re-evaluated too.
        dependents = [
            obj
            for obj in self._model
            if obj.objnam not in ready_objnams
            and (obj[PARENT_ATTR] or "") in ready_objnams
        ]
        dispatched = ready + dependents
        if not dispatched:
            return False

        _LOGGER.debug(
            "Re-dispatching %d backfilled pool object(s): %s",
            len(dispatched),
            ", ".join(obj.objnam for obj in dispatched),
        )
        for listener in list(self._new_objects_listeners):
            try:
                listener(dispatched)
            except Exception:
                _LOGGER.exception(
                    "Error dispatching backfilled pool objects to a platform listener"
                )
        return True

    @callback
    def _handle_model_updates(
        self,
        controller: ICModelController,
        updates: Mapping[str, dict[str, Any] | None],
    ) -> None:
        """Receive model updates from the pyintellicenter subscription.

        Registered via ``handler.subscribe(None, ...)`` so it observes every
        update the library dispatches - the payload is shared and read-only by
        contract, which ``async_set_updated_data`` honors by building its own
        filtered dict.
        """
        _LOGGER.debug("Received update for %d pool objects", len(updates))
        self.async_set_updated_data(updates)

    @callback
    def async_set_updated_data(self, data: Mapping[str, dict[str, Any] | None]) -> None:
        """Handle push update from IntelliCenter.

        This is called from the model-update subscription when updates are
        received from the IntelliCenter system. An entry with value ``None``
        marks an object *removed* from the model (equipment deleted at the
        panel, pruned by reconnect reconciliation); those are split out and
        routed to the removal listeners so only real attribute diffs reach the
        entities - an entity's ``isUpdated`` would otherwise crash on the
        ``None``.

        Args:
            data: Mapping of object updates {objnam: {attr: value}}, where a
                ``None`` value marks the object's removal.
        """
        removed = {objnam for objnam, attrs in data.items() if attrs is None}
        changes: dict[str, dict[str, Any]] = {
            objnam: attrs for objnam, attrs in data.items() if attrs is not None
        }
        if removed:
            self._async_remove_objects(removed)

        self.data = changes
        changed_objnams = set(changes)
        # Ordinary notifications name every changed object, so additions can be
        # detected without traversing the full model. Reconnect completion below
        # retains the authoritative full-model reconciliation.
        just_added = self._async_detect_new_objects(changed_objnams)
        backfilled = self._async_redispatch_backfilled(changes)
        dependency_edges_changed = any(
            _DEPENDENCY_EDGE_ATTRIBUTES & attrs.keys() for attrs in changes.values()
        )
        # Structural changes can affect entities not named in the diff, so
        # rebuild the dependency index and force a full refresh. Keep the real
        # diff visible so entity-specific update side effects still run; only
        # ordinary attribute-only pushes use the targeted listener index.
        if (
            removed
            or just_added
            or backfilled
            or dependency_edges_changed
            or not changes
        ):
            self._async_refresh_object_listener_index()
            self._structural_refresh = True
            try:
                self.async_update_listeners()
            finally:
                self._structural_refresh = False
        else:
            self._async_update_object_listeners(changed_objnams)

    @callback
    def _async_remove_objects(self, removed: set[str]) -> None:
        """Handle objects pruned from the model by reconnect reconciliation.

        The library has already removed them from the model and stopped
        re-subscribing to them; here the coordinator's bookkeeping is pruned
        (so returning equipment is detected as new again) and the platforms
        are told to remove the corresponding entities. Dispatch to each
        platform independently: a failure in one platform's listener must not
        skip the rest.
        """
        self._known_objnams -= removed
        for objnam in removed:
            self._pending_redispatch.pop(objnam, None)
            self._pending_truthy_redispatch.pop(objnam, None)
        _LOGGER.info(
            "Pool object(s) removed from the panel: %s", ", ".join(sorted(removed))
        )
        for listener in list(self._removed_objects_listeners):
            try:
                listener(removed)
            except Exception:
                _LOGGER.exception(
                    "Error dispatching removed pool objects to a platform listener"
                )

    @callback
    def async_set_connection_state(self, connected: bool) -> None:
        """Update the connection state.

        Args:
            connected: True if connected, False if disconnected

        Entity availability is read live from ``self._handler.connected`` (see
        the ``connected`` property); this callback's job is the fan-out below -
        rendering the availability change - plus surfacing equipment added while
        the connection was down.
        """
        # A reconnect re-fetches the full object list into the model; surface any
        # equipment that was added while the connection was down.
        if connected:
            self._async_detect_new_objects()
            self._async_refresh_object_listener_index()
        # Clear the last push diff before fanning out. PoolEntity's update handler
        # writes state either when its attribute is in the diff or when the diff is
        # empty (= connection event); leaving the stale last-push diff in place would
        # make every entity NOT named in it skip the write, so availability changes
        # would never render (entities stuck "available" through an outage, or stuck
        # "unavailable" after a reconnect). Entities read their values from the live
        # model objects, not from this diff, so clearing it loses nothing.
        self.data = {}
        # Notify all listeners of the connection state change
        self.async_update_listeners()


class _CoordinatorConnectionHandler(ICConnectionHandler):
    """Connection handler that forwards events to the coordinator."""

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        controller: ICModelController,
        time_between_reconnects: int = 30,
    ) -> None:
        """Initialize the connection handler.

        Args:
            coordinator: The coordinator to notify of events
            controller: The ICModelController to manage
            time_between_reconnects: Initial delay between reconnection attempts
        """
        super().__init__(controller, time_between_reconnects=time_between_reconnects)
        self._coordinator = coordinator

    def on_started(self, controller: ICBaseController) -> None:
        """Handle initial connection to the Pentair system."""
        system_info = controller.system_info
        prop_name = system_info.prop_name if system_info else "Unknown"
        _LOGGER.info("Connected to IntelliCenter: '%s'", prop_name)

        # Log discovered objects
        if hasattr(controller, "model"):
            for pool_obj in controller.model:
                _LOGGER.debug("   Loaded %s", pool_obj)

    @callback
    def on_reconnected(self, controller: ICBaseController) -> None:
        """Handle reconnection to the Pentair system."""
        system_info = controller.system_info
        prop_name = system_info.prop_name if system_info else "Unknown"
        _LOGGER.info("Reconnected to IntelliCenter: '%s'", prop_name)
        self._coordinator.async_set_connection_state(True)

    @callback
    def on_disconnected(
        self, controller: ICBaseController, exc: Exception | None
    ) -> None:
        """Handle disconnection from the Pentair system."""
        system_info = controller.system_info
        prop_name = system_info.prop_name if system_info else "Unknown"
        _LOGGER.info("Disconnected from IntelliCenter: '%s'", prop_name)
        self._coordinator.async_set_connection_state(False)

    # Model updates deliberately do NOT go through an ``on_updated`` override:
    # the coordinator registers a subscription via ``handler.subscribe()``
    # (pyintellicenter 0.2.0), leaving this handler with lifecycle events only.
