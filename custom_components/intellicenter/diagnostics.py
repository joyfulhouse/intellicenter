"""Diagnostics support for Intellicenter."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .pyintellicenter import ModelController


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    controller: ModelController = entry.runtime_data.controller

    objects = [
        {
            "objnam": obj.objnam,
            "objtype": obj.objtype,
            "subtype": obj.subtype,
            "properties": obj.properties,
        }
        for obj in controller.model.objectList
    ]

    return {"objects": objects}
