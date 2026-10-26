"""Home Assistant entity regressions for authoritative telemetry readbacks."""

from __future__ import annotations

from datetime import timedelta
import logging
from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import EntityPlatform
from pyintellicenter import BODY_TYPE, CHEM_TYPE, SENSE_TYPE
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intellicenter import async_unload_entry
from custom_components.intellicenter.climate import PoolClimate
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator
from custom_components.intellicenter.sensor import (
    BodyLiveTemperatureSensor,
    PoolSensor,
    SensorProbeReading,
)
from custom_components.intellicenter.water_heater import PoolWaterHeater


@pytest.mark.asyncio
async def test_authoritative_readback_updates_ha_sensor_entities(
    hass: HomeAssistant,
) -> None:
    """Config-entry telemetry readback reaches sensors without another push."""
    entry = MockConfigEntry(
        domain="intellicenter",
        data={CONF_HOST: "192.0.2.212"},
        entry_id="issue_212",
    )
    entry.add_to_hass(hass)
    coordinator = IntelliCenterCoordinator(hass, entry, host="192.0.2.212")
    air = coordinator.model.add_object(
        "AIR", {"OBJTYP": SENSE_TYPE, "SNAME": "Air", "SOURCE": "70", "PROBE": "72"}
    )
    water = coordinator.model.add_object(
        "WATER", {"OBJTYP": SENSE_TYPE, "SNAME": "Water", "SOURCE": "80", "PROBE": "82"}
    )
    body = coordinator.model.add_object(
        "POOL1",
        {
            "OBJTYP": BODY_TYPE,
            "SUBTYP": "POOL",
            "SNAME": "Pool",
            "STATUS": "ON",
            "HEATER": "HTR01",
            "HTMODE": "1",
            "TEMP": "80",
            "LSTTMP": "79",
        },
    )
    chlorinator = coordinator.model.add_object(
        "ICHLOR1",
        {"OBJTYP": CHEM_TYPE, "SUBTYP": "ICHLOR", "SNAME": "Salt", "SALT": "3000"},
    )
    assert air and water and body and chlorinator
    climate = PoolClimate(coordinator, body, ["HTR01"])
    water_heater = PoolWaterHeater(coordinator, body, ["HTR01"])
    coordinator._started = True
    coordinator._known_objnams = {"AIR", "WATER", "POOL1", "ICHLOR1"}

    # These are the entities created by the sensor platform for the real model.
    entities = [
        PoolSensor(
            coordinator,
            air,
            device_class=SensorDeviceClass.TEMPERATURE,
            attribute_key="SOURCE",
        ),
        SensorProbeReading(coordinator, air),
        PoolSensor(
            coordinator,
            water,
            device_class=SensorDeviceClass.TEMPERATURE,
            attribute_key="SOURCE",
        ),
        SensorProbeReading(coordinator, water),
        BodyLiveTemperatureSensor(coordinator, body),
        PoolSensor(
            coordinator,
            body,
            device_class=SensorDeviceClass.TEMPERATURE,
            attribute_key="LSTTMP",
        ),
        PoolSensor(coordinator, chlorinator, device_class=None, attribute_key="SALT"),
    ]
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain="sensor",
        platform_name="intellicenter",
        platform=None,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = entry
    entities[1]._attr_entity_registry_enabled_default = True
    entities[3]._attr_entity_registry_enabled_default = True
    await platform.async_add_entities(entities)

    controller = coordinator.controller

    class FakeConnection:
        """Provide protocol responses while retaining the real controller path."""

        connected = False

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.notification_callback = None

        async def connect(self) -> None:
            self.connected = True

        async def disconnect(self) -> None:
            self.connected = False

        def set_notification_callback(self, callback) -> None:
            self.notification_callback = callback

        def set_disconnect_callback(self, callback) -> None:
            self.disconnect_callback = callback

        def add_notification_observer(self, _callback):
            return lambda: None

        async def send_request(self, command: str, **kwargs):
            if command == "GetParamList" and kwargs.get("condition") == "OBJTYP=SYSTEM":
                return {
                    "objectList": [
                        {
                            "objnam": "SYS",
                            "params": {
                                "OBJTYP": "SYSTEM",
                                "SNAME": "System",
                                "MODE": "ENGLISH",
                                "PROPNAME": "Synthetic pool",
                                "VER": "1.064",
                            },
                        }
                    ]
                }
            if command == "GetParamList" and "objectList" not in kwargs:
                return {"objectList": snapshot}
            if command == "RequestParamList":
                return {"objectList": []}
            assert command == "GetParamList"
            return {
                "objectList": [
                    {"objnam": "AIR", "params": {"SOURCE": "68", "PROBE": "69"}},
                    {"objnam": "WATER", "params": {"SOURCE": "77", "PROBE": "78"}},
                    {"objnam": "POOL1", "params": {"TEMP": "76", "LSTTMP": "75"}},
                    {"objnam": "ICHLOR1", "params": {"SALT": "3200"}},
                ]
            }

    snapshot = [
        {
            "objnam": "SYS",
            "params": {"OBJTYP": "SYSTEM", "SNAME": "System", "MODE": "ENGLISH"},
        },
        {
            "objnam": "AIR",
            "params": {
                "OBJTYP": SENSE_TYPE,
                "SNAME": "Air",
                "SOURCE": "70",
                "PROBE": "72",
            },
        },
        {
            "objnam": "WATER",
            "params": {
                "OBJTYP": SENSE_TYPE,
                "SNAME": "Water",
                "SOURCE": "80",
                "PROBE": "82",
            },
        },
        {
            "objnam": "POOL1",
            "params": {
                "OBJTYP": BODY_TYPE,
                "SUBTYP": "POOL",
                "SNAME": "Pool",
                "STATUS": "ON",
                "HEATER": "HTR01",
                "HTMODE": "1",
                "TEMP": "80",
                "LSTTMP": "79",
            },
        },
        {
            "objnam": "ICHLOR1",
            "params": {
                "OBJTYP": CHEM_TYPE,
                "SUBTYP": "ICHLOR",
                "SNAME": "Salt",
                "SALT": "3000",
            },
        },
    ]
    try:
        with patch("pyintellicenter.controller.ICConnection", FakeConnection):
            await coordinator.async_start()
            assert coordinator.connected
            controller._apply_updates([{"objnam": "AIR", "params": {"SOURCE": "68"}}])
            await controller._reconcile_telemetry()

        assert [entity.native_value for entity in entities] == [
            68,
            69,
            77,
            78,
            76,
            75,
            3200,
        ]
        assert coordinator.connected
        for entity in entities:
            entity.async_write_ha_state()
        await hass.async_block_till_done()
        assert [hass.states.get(entity.entity_id).state for entity in entities] == [
            "20.0",
            "20.5555555555556",
            "25.0",
            "25.5555555555556",
            "24.4444444444444",
            "23.8888888888889",
            "3200",
        ]
        assert air["SOURCE"] != air["PROBE"]
        assert water["SOURCE"] != water["PROBE"]
        assert climate.current_temperature == 75.0
        assert water_heater.current_temperature == 75.0
        worker = controller._telemetry_task
        assert worker is not None and not worker.done()
        entry.runtime_data = coordinator
        with patch.object(
            hass.config_entries, "async_unload_platforms", new_callable=AsyncMock
        ) as unload_platforms:
            unload_platforms.return_value = True
            assert await async_unload_entry(hass, entry)
        assert worker.done()
        assert controller._telemetry_task is None

        with patch("pyintellicenter.controller.ICConnection", FakeConnection):
            await coordinator.async_start()
        replacement_worker = controller._telemetry_task
        assert replacement_worker is not None and replacement_worker is not worker
        assert not replacement_worker.done()
    finally:
        await coordinator.async_stop()
        for entity in entities:
            await platform.async_remove_entity(entity.entity_id)
