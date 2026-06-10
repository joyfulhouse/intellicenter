"""DataUpdateCoordinator for Pentair IntelliCenter.

This module provides a coordinator that manages the connection to the IntelliCenter
system and distributes updates to all entities. Since IntelliCenter uses push-based
updates (local_push), this coordinator doesn't poll but instead receives real-time
notifications from the controller.
"""

from __future__ import annotations

from collections.abc import Callable
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
    NORMAL_ATTR,
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
    SNAME_ATTR,
    SOURCE_ATTR,
    SPEED_ATTR,
    STATUS_ATTR,
    SUBTYP_ATTR,
    SUPER_ATTR,
    SYSTEM_TYPE,
    TIME_ATTR,
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

from .const import DEFAULT_TRANSPORT, DOMAIN, TransportType

_LOGGER = logging.getLogger(__name__)

# Callback invoked when previously-unseen pool objects appear in the model at
# runtime. Each platform registers one of these so it can create entities for
# newly-added equipment without requiring a Home Assistant restart (issue #42).
NewObjectsListener = Callable[[list[PoolObject]], None]

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
        VOL_ATTR,
    },
    CIRCUIT_TYPE: {
        SNAME_ATTR,
        STATUS_ATTR,
        USE_ATTR,
        SUBTYP_ATTR,
        FEATR_ATTR,
        TIME_ATTR,  # Egg timer duration
        FREEZE_ATTR,  # Freeze protection status
    },
    CIRCGRP_TYPE: {SNAME_ATTR, STATUS_ATTR, USE_ATTR, CIRCUIT_ATTR},  # Circuit groups
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
        # IntelliChem alarm indicators (diagnostic)
        PHHI_ATTR,
        PHLO_ATTR,
        ORPHI_ATTR,
        ORPLO_ATTR,
        # IntelliChlor sensors
        SALT_ATTR,
    },
    # External instruments (pool covers). Without this entry PoolModel drops the
    # objects entirely and the cover platform never sees them (the model only
    # admits objtypes present in this map).
    EXTINSTR_TYPE: {SNAME_ATTR, STATUS_ATTR, NORMAL_ATTR, SUBTYP_ATTR},
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
    SENSE_TYPE: {SNAME_ATTR, SOURCE_ATTR},
    SCHED_TYPE: {SNAME_ATTR, ACT_ATTR, VACFLO_ATTR},
    # MODE/VACFLO/VER plus SERVICE for the system operating mode sensor
    SYSTEM_TYPE: {MODE_ATTR, SERVICE_ATTR, VACFLO_ATTR, VER_ATTR},
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

        self._stop_listener: CALLBACK_TYPE | None = None
        self._connected = False

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
        # Objects dispatched to the platforms while potentially incomplete: a
        # runtime-added object is first seen with only the params its NotifyList
        # carried; the controller backfills the remaining tracked attributes via
        # RequestParamList in a LATER update. Each objnam here gets re-dispatched
        # once, when its next attribute update (the backfill) arrives, so
        # builders gated on attributes missing at first dispatch (e.g. pump
        # PWR/RPM/GPM sensors) get a second chance.
        self._pending_redispatch: set[str] = set()

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
    def connected(self) -> bool:
        """Return True if connected to the IntelliCenter."""
        return self._connected

    async def async_start(self) -> None:
        """Start the connection to the IntelliCenter."""

        # Register stop listener
        async def _on_hass_stop(event: Any) -> None:
            """Stop the connection when Home Assistant stops."""
            self._handler.stop()

        self._stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, _on_hass_stop
        )

        # Start the connection
        await self._handler.start()
        self._connected = True

        # Snapshot the objects discovered during the initial connection. Anything
        # that appears in the model after this point is treated as newly-added
        # equipment and dispatched to the registered platform listeners.
        self._known_objnams = {obj.objnam for obj in self._model}
        self._started = True

    async def async_stop(self) -> None:
        """Stop the connection to the IntelliCenter."""
        # Cancel stop listener
        if self._stop_listener:
            self._stop_listener()
            self._stop_listener = None

        # Stop the handler
        self._handler.stop()
        self._connected = False

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
    def _async_detect_new_objects(self) -> set[str]:
        """Detect objects added to the model and notify platform listeners.

        Compares the current model against the set of objects the platforms
        already know about. Any new objects are recorded and dispatched to the
        registered listeners so the platforms can create entities for them at
        runtime. Does nothing until the initial connection has completed.
        Returns the objnams dispatched as new (empty when nothing changed).

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

        new_objects = [
            obj for obj in self._model if obj.objnam not in self._known_objnams
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
        # Mark for a one-shot re-dispatch when the attribute backfill arrives.
        self._pending_redispatch.update(new_objnams)

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
    def _async_redispatch_backfilled(self, updated_objnams: set[str]) -> None:
        """Re-dispatch newly-added objects once their attribute backfill arrives.

        A runtime-added object reaches the platforms before the controller has
        fetched its full tracked-attribute set, so builders that gate on those
        attributes (pump PWR/RPM/GPM sensors, parent-pump limits) skip it. The
        first subsequent update for such an object is its backfill: dispatch it
        (and any dependents whose parent it is) one more time. ``unique_id``
        de-duplication in the platforms makes this harmless for entities that
        were already built.
        """
        if not self._pending_redispatch:
            return
        ready_objnams = self._pending_redispatch & updated_objnams
        if not ready_objnams:
            return
        self._pending_redispatch -= ready_objnams

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
            return

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

    @callback
    def async_set_updated_data(self, data: dict[str, dict[str, Any]]) -> None:
        """Handle push update from IntelliCenter.

        This is called by the connection handler when updates are received
        from the IntelliCenter system.

        Args:
            data: Dictionary of object updates {objnam: {attr: value}}
        """
        self.data = data
        # New equipment can enter the model on a reconnect (the controller
        # re-fetches every object on start), so reconcile before fanning out.
        just_added = self._async_detect_new_objects()
        # The update that introduced an object is not its backfill; only later
        # updates for that object complete it.
        self._async_redispatch_backfilled(set(data) - just_added)
        self.async_update_listeners()

    @callback
    def async_set_connection_state(self, connected: bool) -> None:
        """Update the connection state.

        Args:
            connected: True if connected, False if disconnected
        """
        self._connected = connected
        # A reconnect re-fetches the full object list into the model; surface any
        # equipment that was added while the connection was down.
        if connected:
            self._async_detect_new_objects()
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

    @callback
    def on_updated(
        self, controller: ICModelController, updates: dict[str, dict[str, Any]]
    ) -> None:
        """Handle updates from the Pentair system."""
        _LOGGER.debug("Received update for %d pool objects", len(updates))
        self._coordinator.async_set_updated_data(updates)
