"""Config flow for Pentair Intellicenter integration.

This module handles the configuration flow for setting up the IntelliCenter
integration, including:
- Manual user setup with IP address entry
- Library-based network discovery
- Zeroconf auto-discovery
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

from homeassistant.components import zeroconf
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow as HAConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pyintellicenter import ICBaseController, ICConnectionError, ICSystemInfo
import voluptuous as vol

# Import discovery - available in pyintellicenter 0.0.4+
try:
    from pyintellicenter import ICUnit, discover_intellicenter_units

    DISCOVERY_AVAILABLE = True
except ImportError:
    DISCOVERY_AVAILABLE = False

from .const import (
    CONF_KEEPALIVE_INTERVAL,
    CONF_RECONNECT_DELAY,
    CONF_TRANSPORT,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_TRANSPORT,
    DOMAIN,
    MAX_KEEPALIVE_INTERVAL,
    MAX_RECONNECT_DELAY,
    MIN_KEEPALIVE_INTERVAL,
    MIN_RECONNECT_DELAY,
    TRANSPORT_TCP,
    TRANSPORT_WEBSOCKET,
    TransportType,
)

_LOGGER = logging.getLogger(__name__)

# Discovery timeout in seconds
DISCOVERY_TIMEOUT = 10.0

# Setup method options
SETUP_DISCOVER = "discover"
SETUP_MANUAL = "manual"


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(HomeAssistantError):
    """Error to indicate the host is invalid."""


def _validate_host(host: str) -> str:
    """Validate and return the host address."""
    host = host.strip()
    if not host:
        raise InvalidHost("Host cannot be empty")

    try:
        ipaddress.ip_address(host)
    except ValueError as err:
        if " " in host or not host:
            raise InvalidHost(f"Invalid host: {host}") from err

    return host


class ConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Pentair Intellicenter config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize a new Intellicenter ConfigFlow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._discovered_units: list[ICUnit] = []
        self._reconfigure_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user.

        Presents options to discover devices or enter manually.
        """
        if user_input is None:
            return self._show_pick_method_form()

        # User selected a setup method
        if user_input.get("setup_method") == SETUP_DISCOVER:
            return await self.async_step_discover()
        return await self.async_step_manual()

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the discovery step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User selected a device from the list
            selected = user_input.get("device")
            if selected:
                # Find the selected unit
                for unit in self._discovered_units:
                    if unit.host == selected:
                        return await self._async_create_entry_from_unit(unit)

                # Try to connect with the selected host
                try:
                    host = _validate_host(selected)
                    system_info = await self._get_system_info(host)

                    await self.async_set_unique_id(system_info.unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=system_info.prop_name, data={CONF_HOST: host}
                    )
                except AbortFlow:
                    raise
                except InvalidHost:
                    errors["base"] = "invalid_host"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        # Perform discovery using HA's shared Zeroconf instance
        if DISCOVERY_AVAILABLE:
            try:
                zc = await zeroconf.async_get_instance(self.hass)
                self._discovered_units = await discover_intellicenter_units(
                    discovery_timeout=DISCOVERY_TIMEOUT,
                    zeroconf=zc,
                )
            except Exception:
                _LOGGER.exception("Discovery failed")
                self._discovered_units = []
        else:
            self._discovered_units = []

        if not self._discovered_units:
            # No devices found, show message and option to enter manually
            return self._show_no_devices_form(errors)

        # Filter out already configured devices
        available_units = []
        for unit in self._discovered_units:
            if not self._host_already_configured(unit.host):
                available_units.append(unit)

        if not available_units:
            return self.async_abort(reason="already_configured")

        self._discovered_units = available_units
        return self._show_device_picker_form(errors)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual IP entry step."""
        if user_input is None:
            return self._show_manual_form()

        errors: dict[str, str] = {}

        try:
            host = _validate_host(user_input[CONF_HOST])
            transport = user_input.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
            system_info = await self._get_system_info(host, transport)

            await self.async_set_unique_id(system_info.unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=system_info.prop_name,
                data={CONF_HOST: host, CONF_TRANSPORT: transport},
            )
        except AbortFlow:
            raise
        except InvalidHost:
            errors["base"] = "invalid_host"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        return self._show_manual_form(errors)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle device found via zeroconf."""
        _LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        host = str(discovery_info.host)

        if self._host_already_configured(host):
            return self.async_abort(reason="already_configured")

        try:
            system_info = await self._get_system_info(host)

            await self.async_set_unique_id(system_info.unique_id)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

            self._discovered_host = host
            self._discovered_name = system_info.prop_name

            self.context["title_placeholders"] = {"name": system_info.prop_name}

            return self._show_confirm_dialog()

        except AbortFlow:
            raise
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by zeroconf."""
        if user_input is None:
            return self._show_confirm_dialog()

        host = self._discovered_host
        if host is None:
            return self.async_abort(reason="unknown")

        try:
            system_info = await self._get_system_info(host)

            await self.async_set_unique_id(system_info.unique_id)
            self._abort_if_unique_id_configured()

        except AbortFlow:
            raise
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        return self.async_create_entry(
            title=system_info.prop_name, data={CONF_HOST: host}
        )

    def _show_pick_method_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the form to pick setup method."""
        options = [SETUP_MANUAL]

        if DISCOVERY_AVAILABLE:
            options.insert(0, SETUP_DISCOVER)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "setup_method",
                        default=SETUP_DISCOVER if DISCOVERY_AVAILABLE else SETUP_MANUAL,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                            translation_key="setup_method",
                        )
                    ),
                }
            ),
            errors=errors or {},
        )

    def _show_device_picker_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the form to pick a discovered device."""
        options = [
            SelectOptionDict(
                value=unit.host,
                label=f"{unit.name} ({unit.host})",
            )
            for unit in self._discovered_units
        ]

        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors or {},
            description_placeholders={"count": str(len(self._discovered_units))},
        )

    def _show_no_devices_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show form when no devices are found."""
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors or {},
            description_placeholders={"reason": "no_devices_found"},
        )

    def _show_manual_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the manual setup form."""
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_TRANSPORT, default=DEFAULT_TRANSPORT
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[TRANSPORT_TCP, TRANSPORT_WEBSOCKET],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="transport",
                        )
                    ),
                }
            ),
            errors=errors or {},
        )

    def _show_confirm_dialog(self) -> ConfigFlowResult:
        """Show the confirm dialog for zeroconf discovery."""
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "host": self._discovered_host or "",
                "name": self._discovered_name or "",
            },
        )

    async def _async_create_entry_from_unit(self, unit: ICUnit) -> ConfigFlowResult:
        """Create a config entry from a discovered unit."""
        try:
            system_info = await self._get_system_info(unit.host)

            await self.async_set_unique_id(system_info.unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=system_info.prop_name, data={CONF_HOST: unit.host}
            )
        except AbortFlow:
            raise
        except CannotConnect as err:
            raise CannotConnect from err

    async def _get_system_info(
        self, host: str, transport: TransportType = DEFAULT_TRANSPORT
    ) -> ICSystemInfo:
        """Attempt to connect and retrieve system information.

        Args:
            host: IP address or hostname of IntelliCenter
            transport: Transport type ("tcp" or "websocket")

        Returns:
            ICSystemInfo object with system details

        Raises:
            CannotConnect: If connection fails or system info unavailable
        """
        controller = ICBaseController(host, transport=transport)

        try:
            await controller.start()
            if controller.system_info is None:
                raise CannotConnect("System info not available")
            return controller.system_info
        except (
            ConnectionRefusedError,
            OSError,
            TimeoutError,
            ICConnectionError,
        ) as err:
            raise CannotConnect from err
        finally:
            await controller.stop()

    def _host_already_configured(self, host: str) -> bool:
        """Check if we already have a system with the same host address."""
        existing_hosts = {
            entry.data[CONF_HOST]
            for entry in self._async_current_entries()
            if CONF_HOST in entry.data
        }
        return host in existing_hosts

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration.

        Allows users to change the host address and transport type after initial setup.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                host = _validate_host(user_input[CONF_HOST])
                transport = user_input.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
                system_info = await self._get_system_info(host, transport)

                # Check if this host is different and not already configured
                if host != reconfigure_entry.data.get(CONF_HOST):
                    # Check if another entry uses this host
                    for entry in self._async_current_entries():
                        if (
                            entry.entry_id != reconfigure_entry.entry_id
                            and entry.data.get(CONF_HOST) == host
                        ):
                            return self.async_abort(reason="already_configured")

                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    title=system_info.prop_name,
                    data={CONF_HOST: host, CONF_TRANSPORT: transport},
                )
            except InvalidHost:
                errors["base"] = "invalid_host"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reconfigure")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=reconfigure_entry.data.get(CONF_HOST, ""),
                    ): str,
                    vol.Required(
                        CONF_TRANSPORT,
                        default=reconfigure_entry.data.get(
                            CONF_TRANSPORT, DEFAULT_TRANSPORT
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[TRANSPORT_TCP, TRANSPORT_WEBSOCKET],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="transport",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "name": reconfigure_entry.title,
            },
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle options flow for Pentair IntelliCenter integration.

    ``self.config_entry`` is provided by the base ``OptionsFlow`` class and is
    only available after the flow manager has initialised the flow. Do not
    assign it here, and do not read it from a custom ``__init__`` either: Home
    Assistant removed the ability to set the ``config_entry`` property in
    2025.12 (and the property raises if read before initialisation), so any
    ``__init__`` that touches ``self.config_entry`` breaks (issue #40).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options for IntelliCenter integration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_keepalive = self.config_entry.options.get(
            CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL
        )
        current_reconnect = self.config_entry.options.get(
            CONF_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_KEEPALIVE_INTERVAL,
                        default=current_keepalive,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_KEEPALIVE_INTERVAL,
                            max=MAX_KEEPALIVE_INTERVAL,
                        ),
                    ),
                    vol.Optional(
                        CONF_RECONNECT_DELAY,
                        default=current_reconnect,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_RECONNECT_DELAY,
                            max=MAX_RECONNECT_DELAY,
                        ),
                    ),
                }
            ),
            description_placeholders={
                "host": self.config_entry.data.get(CONF_HOST, "Unknown")
            },
        )
