"""Evidence-bounded advanced setting descriptions and state validation.

The app's MANOVR owner is distinct from SYSTEM.MANHT. Resolve it from a
recognized panel value, never from a guessed object name or firmware boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pyintellicenter import SYSTEM_TYPE, SYSTIM_TYPE

MANOVR_ATTR = "MANOVR"


@dataclass(frozen=True, slots=True)
class ConfigurationSetting:
    """One read-only setting, with its wire values preserved in HA."""

    object_type: str
    key: str
    name: str
    values: frozenset[str] | None = None

    def state(self, raw: object) -> str | None:
        """Reject missing, echoed, or malformed state without inventing defaults."""
        if not isinstance(raw, str) or not raw or raw == self.key or raw.strip() != raw:
            return None
        if self.values is not None:
            return raw if raw in self.values else None
        if self.key == "TIMZON":
            try:
                offset = Decimal(raw)
            except InvalidOperation:
                return None
            return raw if offset.is_finite() else None
        # SOURCE is opaque; displaying it does not grant manual clock ownership.
        return raw if raw.isprintable() and len(raw) <= 255 else None


_ON_OFF = frozenset({"ON", "OFF"})
CONFIGURATION_SETTINGS = (
    ConfigurationSetting(SYSTEM_TYPE, "VALVE", "Pump valve delay setting", _ON_OFF),
    ConfigurationSetting(SYSTEM_TYPE, "HEATING", "Pump heater delay setting", _ON_OFF),
    ConfigurationSetting(SYSTEM_TYPE, "SASHP", "Body 1 solar relay setting", _ON_OFF),
    ConfigurationSetting(SYSTEM_TYPE, "SASHP2", "Body 2 solar relay setting", _ON_OFF),
    ConfigurationSetting(SYSTEM_TYPE, "TIMZON", "Panel time zone offset"),
    ConfigurationSetting(SYSTIM_TYPE, "SOURCE", "Clock source"),
    ConfigurationSetting(
        SYSTIM_TYPE, "CLK24A", "Clock format", frozenset({"AMPM", "HR24"})
    ),
    ConfigurationSetting(
        SYSTIM_TYPE, "DLSTIM", "Clock daylight saving setting", _ON_OFF
    ),
)


def manual_priority_supported(raw: object) -> bool:
    """Only canonical ON/OFF readback establishes a usable MANOVR field."""
    return isinstance(raw, str) and raw in _ON_OFF
