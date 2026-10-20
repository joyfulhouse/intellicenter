"""Evidence-gated configuration numbers for physical temperature sensors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
import re
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import (
    EVENT_CORE_CONFIG_UPDATE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import Event, callback
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    CALIB_ATTR,
    MODE_ATTR,
    PROBE_ATTR,
    SENSE_TYPE,
    STATUS_ATTR,
    SYSTEM_TYPE,
    VER_ATTR,
    PoolObject,
)

from . import PoolEntity
from .const import DOMAIN
from .coordinator import IntelliCenterCoordinator


@dataclass(frozen=True)
class CalibrationLimits:
    """Device-verified integer CALIB limits in the keyed panel temperature unit."""

    minimum: int
    maximum: int
    step: int
    evidence: str

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int
                for value in (self.minimum, self.maximum, self.step)
            )
            or self.minimum >= self.maximum
            or self.step <= 0
            or (self.maximum - self.minimum) % self.step
            or not self.evidence.strip()
        ):
            raise ValueError("Invalid calibration limits or missing device evidence")

    def accepts(self, value: int) -> bool:
        """Return whether an integer offset is on the verified lattice."""
        return (
            self.minimum <= value <= self.maximum
            and (value - self.minimum) % self.step == 0
        )


# (exact firmware, SENSE subtype, panel MODE). Populate only with sanitized
# device evidence for bounds, precision, unit changes and persisted readback.
# App slider bounds describe a target temperature, not a CALIB offset range.
CALIBRATION_SUPPORT: dict[tuple[str, str, str], CalibrationLimits] = {}
PANEL_UNITS = {
    "ENGLISH": UnitOfTemperature.FAHRENHEIT,
    "METRIC": UnitOfTemperature.CELSIUS,
}


def parse_calibration_integer(value: Any) -> int | None:
    """Parse a protocol integer without truncation, booleans or zero defaults."""
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        return int(value)
    return None


def convert_offset(value: float, source: str, target: str) -> float:
    """Convert a temperature difference, preserving zero without adding 32."""
    if source not in PANEL_UNITS.values() or target not in PANEL_UNITS.values():
        raise ValueError("Calibration offsets require Celsius or Fahrenheit")
    if source == target:
        return value
    return value * 1.8 if target == UnitOfTemperature.FAHRENHEIT else value / 1.8


def _support_key(
    coordinator: IntelliCenterCoordinator, sensor: PoolObject
) -> tuple[str, str, str] | None:
    systems = coordinator.model.get_by_type(SYSTEM_TYPE)
    if len(systems) != 1 or sensor.subtype not in {"POOL", "SOLAR", "AIR"}:
        return None
    system = systems[0]
    mode, firmware = system[MODE_ATTR], system[VER_ATTR]
    if (
        not isinstance(mode, str)
        or mode not in PANEL_UNITS
        or not isinstance(firmware, str)
    ):
        return None
    return firmware, sensor.subtype, mode


def _connected_sensor(
    coordinator: IntelliCenterCoordinator, sensor: PoolObject
) -> bool:
    """Require explicit healthy status and a usable probe; missing is unknown."""
    probe = parse_calibration_integer(sensor[PROBE_ATTR])
    return (
        sensor[STATUS_ATTR] == "OK"
        and probe is not None
        and (
            probe == 0
            or coordinator.controller.get_sensor_probe_reading(sensor.objnam) == probe
        )
    )


def build_calibration_entities(
    coordinator: IntelliCenterCoordinator, candidates: Iterable[PoolObject]
) -> list[SensorCalibrationNumber]:
    """Discover distinct supported physical channels, independent of body order."""
    numbers: dict[str, SensorCalibrationNumber] = {}
    for sensor in candidates:
        if sensor.objtype != SENSE_TYPE or CALIB_ATTR not in sensor.attribute_keys:
            continue
        key = _support_key(coordinator, sensor)
        if (
            key is None
            or key not in CALIBRATION_SUPPORT
            or not _connected_sensor(coordinator, sensor)
        ):
            continue
        numbers[sensor.objnam] = SensorCalibrationNumber(coordinator, sensor, key)
    return list(numbers.values())


class SensorCalibrationNumber(PoolEntity, NumberEntity):
    """Calibration offset; an acknowledgement never supplies the entity state."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    # HA's TEMPERATURE device class performs absolute conversions. Offsets are
    # converted explicitly to HA's configured temperature unit instead.
    _attr_device_class = None

    def __init__(
        self,
        coordinator: IntelliCenterCoordinator,
        sensor: PoolObject,
        key: tuple[str, str, str],
    ) -> None:
        super().__init__(
            coordinator,
            sensor,
            attribute_key=CALIB_ATTR,
            name="+ Calibration",
            icon="mdi:thermometer-check",
            enabled_by_default=False,
        )
        self._initial_key = key
        self._initial_limits = CALIBRATION_SUPPORT[key]
        self._fresh_key: tuple[str, str, str] | None = key

    @property
    def _sensor(self) -> PoolObject | None:
        return self.coordinator.model[self._pool_object.objnam]

    @property
    def _key(self) -> tuple[str, str, str] | None:
        sensor = self._sensor
        return _support_key(self.coordinator, sensor) if sensor is not None else None

    @property
    def _limits(self) -> CalibrationLimits:
        key = self._key
        return (
            CALIBRATION_SUPPORT.get(key, self._initial_limits)
            if key
            else self._initial_limits
        )

    @property
    def _panel_unit(self) -> str:
        key = self._key
        return PANEL_UNITS[
            (key if key in CALIBRATION_SUPPORT else self._initial_key)[2]
        ]

    @property
    def native_unit_of_measurement(self) -> str:
        """Expose deltas in HA's configured unit without absolute conversion."""
        return str(self.coordinator.hass.config.units.temperature_unit)

    def _display_offset(self, value: float) -> float:
        return convert_offset(value, self._panel_unit, self.native_unit_of_measurement)

    @property
    def native_min_value(self) -> float:
        return self._display_offset(self._limits.minimum)

    @property
    def native_max_value(self) -> float:
        return self._display_offset(self._limits.maximum)

    @property
    def native_step(self) -> float:
        return self._display_offset(self._limits.step)

    @property
    def native_value(self) -> float | None:
        """Read only authoritative CALIB, including zero and negative offsets."""
        sensor = self._sensor
        key = self._key
        if (
            sensor is None
            or key is None
            or key not in CALIBRATION_SUPPORT
            or key != self._fresh_key
            or not _connected_sensor(self.coordinator, sensor)
        ):
            return None
        value = parse_calibration_integer(sensor[CALIB_ATTR])
        if value is None or not self._limits.accepts(value):
            return None
        # The generic library getter treats numeric 0 as absent; preserve an
        # explicitly parsed zero while using the normal accessor otherwise.
        if (
            value != 0
            and self._controller.get_sensor_calibration(sensor.objnam) != value
        ):
            return None
        return self._display_offset(value)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._key in CALIBRATION_SUPPORT
            and self.native_value is not None
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, self._units_updated)
        )

    @callback
    def _units_updated(self, event: Event) -> None:
        self.async_write_ha_state()

    def coordinator_update_dependencies(self) -> dict[str, set[str] | None]:
        return self._system_update_dependencies(MODE_ATTR, VER_ATTR)

    def isUpdated(self, updates: dict[str, dict[str, Any]]) -> bool:
        return self._check_attributes_updated(
            updates, CALIB_ATTR, PROBE_ATTR, STATUS_ATTR
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        updates = self.coordinator.data or {}
        if CALIB_ATTR in updates.get(self._pool_object.objnam, {}):
            self._fresh_key = self._key
        elif self._key != self._fresh_key:
            self._fresh_key = None
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Await the write, then independently read and verify the stored offset."""
        key, sensor = self._key, self._sensor
        if not self.available or key is None or sensor is None:
            raise self._error("calibration_unavailable")
        offset = convert_offset(
            value, self.native_unit_of_measurement, self._panel_unit
        )
        if not math.isfinite(offset) or not math.isclose(
            offset, round(offset), rel_tol=0, abs_tol=1e-9
        ):
            raise self._error("invalid_calibration")
        encoded = round(offset)
        if not self._limits.accepts(encoded):
            raise self._error("invalid_calibration")
        await self._async_execute_changes({CALIB_ATTR: str(encoded)})
        response = await self._async_execute_command(
            self._controller.send_cmd(
                "GetParamList",
                {"objectList": [{"objnam": sensor.objnam, "keys": [CALIB_ATTR]}]},
            ),
            translation_key="calibration_unconfirmed",
        )
        entries = response.get("objectList") if isinstance(response, dict) else None
        if (
            not self.coordinator.connected
            or self._key != key
            or self._sensor is not sensor
            or not isinstance(entries, list)
            or len(entries) != 1
            or not isinstance(entries[0], dict)
            or entries[0].get("objnam") != sensor.objnam
            or not isinstance(params := entries[0].get("params"), dict)
            or parse_calibration_integer(params.get(CALIB_ATTR)) != encoded
        ):
            raise self._error("calibration_unconfirmed")
        # Only a validated GetParamList response enters the shared model. NotifyList
        # remains authoritative too; SETPARAMLIST's acknowledgement never does.
        changed = sensor.update({CALIB_ATTR: str(encoded)})
        self._fresh_key = key
        if changed:
            self.coordinator.async_set_updated_data({sensor.objnam: changed})

    @staticmethod
    def _error(key: str) -> HomeAssistantError:
        return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)
