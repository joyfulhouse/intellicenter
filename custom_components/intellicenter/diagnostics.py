"""Diagnostics support for Intellicenter.

This module provides diagnostic information for troubleshooting the integration.
Sensitive data like IP addresses are automatically redacted.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import IntelliCenterConfigEntry
from .coordinator import IntelliCenterCoordinator

# Keys to redact from diagnostics output for privacy
TO_REDACT = {
    CONF_HOST,  # IP address
    "host",
    "ip",
    "IP",
    "HOST",
    "PROPNAME",  # Pool system name (could identify the owner)
    "propName",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IntelliCenterConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to get diagnostics for.

    Returns:
        Dictionary containing redacted diagnostic information.
    """
    # Start with basic entry info that's always available
    diagnostics_data: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
    }

    try:
        # ``runtime_data`` is typed as the coordinator, but Home Assistant deletes
        # it when the entry unloads (and it is unset before the entry loads), so
        # read it defensively: ``getattr`` yields ``None`` instead of raising if
        # it is absent.
        coordinator: IntelliCenterCoordinator | None = getattr(
            entry, "runtime_data", None
        )
        if coordinator is None:
            diagnostics_data["error"] = "Coordinator not found"
            return dict(async_redact_data(diagnostics_data, TO_REDACT))

        controller = coordinator.controller

        # Collect pool object information
        objects = [
            {
                "objnam": obj.objnam,
                "objtype": obj.objtype,
                "subtype": obj.subtype,
                "properties": obj.properties,
            }
            for obj in coordinator.model
        ]

        # Include system info if available
        system_info: dict[str, Any] = {}
        if coordinator.system_info:
            system_info = {
                "sw_version": coordinator.system_info.sw_version,
                "uses_metric": coordinator.system_info.uses_metric,
            }

        # Include connection state
        connection_state: dict[str, Any] = {
            "connected": coordinator.connected,
        }

        # Include connection metrics for observability if available
        if hasattr(controller, "metrics") and controller.metrics:
            connection_state["metrics"] = controller.metrics.to_dict()

        # Count objects by type for summary
        object_types: dict[str, int] = {}
        for obj in coordinator.model:
            obj_type = obj.objtype
            object_types[obj_type] = object_types.get(obj_type, 0) + 1

        diagnostics_data["system_info"] = system_info
        diagnostics_data["connection_state"] = connection_state
        diagnostics_data["object_count"] = len(objects)
        diagnostics_data["object_types"] = object_types
        diagnostics_data["objects"] = objects

    except Exception as err:
        diagnostics_data["error"] = f"Error collecting diagnostics: {err}"

    # Redact sensitive information before returning
    result: dict[str, Any] = async_redact_data(diagnostics_data, TO_REDACT)
    return result
