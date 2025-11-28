"""DataUpdateCoordinator for Pentair IntelliCenter.

This module provides a coordinator that manages the connection to the IntelliCenter
system and distributes updates to all entities. Since IntelliCenter uses push-based
updates (local_push), this coordinator doesn't poll but instead receives real-time
notifications from the controller.
"""

from __future__ import annotations

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
    CYACID_ATTR,
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
    ORPHI_ATTR,
    ORPLO_ATTR,
    ORPSET_ATTR,
    ORPTNK_ATTR,
    ORPVAL_ATTR,
    PHHI_ATTR,
    PHLO_ATTR,
    PHSET_ATTR,
    PHTNK_ATTR,
    PHVAL_ATTR,
    PRIM_ATTR,
    PUMP_TYPE,
    PWR_ATTR,
    QUALTY_ATTR,
    RPM_ATTR,
    SALT_ATTR,
    SCHED_TYPE,
    SEC_ATTR,
    SENSE_TYPE,
    SNAME_ATTR,
    SOURCE_ATTR,
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
)

from .const import DEFAULT_TRANSPORT, DOMAIN, TransportType

_LOGGER = logging.getLogger(__name__)

# Default attribute tracking map - defines which attributes to monitor per object type
DEFAULT_ATTRIBUTES_MAP: dict[str, set[str]] = {
    BODY_TYPE: {
        SNAME_ATTR,
        HEATER_ATTR,
        HITMP_ATTR,  # Max temperature setpoint
        HTMODE_ATTR,
        LOTMP_ATTR,
        LSTTMP_ATTR,
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
    HEATER_TYPE: {SNAME_ATTR, BODY_ATTR, LISTORD_ATTR},
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
    },
    SENSE_TYPE: {SNAME_ATTR, SOURCE_ATTR},
    SCHED_TYPE: {SNAME_ATTR, ACT_ATTR, VACFLO_ATTR},
    SYSTEM_TYPE: {MODE_ATTR, VACFLO_ATTR, VER_ATTR},  # VER_ATTR for firmware version
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
    def async_set_updated_data(self, data: dict[str, dict[str, Any]]) -> None:
        """Handle push update from IntelliCenter.

        This is called by the connection handler when updates are received
        from the IntelliCenter system.

        Args:
            data: Dictionary of object updates {objnam: {attr: value}}
        """
        self.data = data
        self.async_update_listeners()

    @callback
    def async_set_connection_state(self, connected: bool) -> None:
        """Update the connection state.

        Args:
            connected: True if connected, False if disconnected
        """
        self._connected = connected
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
