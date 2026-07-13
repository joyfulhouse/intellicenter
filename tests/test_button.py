"""Test the Pentair IntelliCenter button platform."""

from unittest.mock import MagicMock, call

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pyintellicenter import (
    CIRCUIT_TYPE,
    DLY_ATTR,
    STATUS_OFF,
    STATUS_ON,
    SYSTEM_TYPE,
    ICConnectionError,
    PoolObject,
)
import pytest

from custom_components.intellicenter import PLATFORMS
from custom_components.intellicenter.button import CancelDelaysButton, _build_entities

pytestmark = pytest.mark.asyncio


@pytest.fixture
def system_object() -> PoolObject:
    """Return a SYSTEM object for the system-device button."""
    return PoolObject("SYS01", {"OBJTYP": SYSTEM_TYPE, "SNAME": "IntelliCenter System"})


async def test_button_platform_registered() -> None:
    """The integration forwards setup and unload to the button platform."""
    assert Platform.BUTTON in PLATFORMS


async def test_cancel_delays_button_created_unconditionally(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    system_object: PoolObject,
) -> None:
    """Every SYSTEM object creates exactly one enabled Cancel Delays button."""
    buttons = _build_entities(mock_coordinator, [system_object])

    assert len(buttons) == 1
    button = buttons[0]
    assert isinstance(button, CancelDelaysButton)
    assert button.name == "Cancel Delays"
    assert button.entity_registry_enabled_default is True


async def test_cancel_delays_writes_each_active_circuit(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    system_object: PoolObject,
) -> None:
    """Pressing cancels only circuits with a confirmed active delay."""
    active_one = PoolObject(
        "CIRC01", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Pool", "DLY": STATUS_ON}
    )
    inactive = PoolObject(
        "CIRC02", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Spa", "DLY": STATUS_OFF}
    )
    malformed = PoolObject(
        "CIRC03", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Aux", "DLY": "BROKEN"}
    )
    active_two = PoolObject(
        "CIRC04", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Cleaner", "DLY": STATUS_ON}
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.get_by_type.return_value = [
        active_one,
        inactive,
        malformed,
        active_two,
    ]
    button = CancelDelaysButton(mock_coordinator, system_object)

    await button.async_press()

    assert mock_coordinator.controller.request_changes.await_args_list == [
        call("CIRC01", {DLY_ATTR: STATUS_OFF}),
        call("CIRC04", {DLY_ATTR: STATUS_OFF}),
    ]


async def test_cancel_delays_refuses_without_active_delay(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    system_object: PoolObject,
) -> None:
    """A press with no confirmed active delay returns a translated error."""
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.get_by_type.return_value = [
        PoolObject(
            "CIRC01",
            {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Pool", "DLY": STATUS_OFF},
        ),
        PoolObject("CIRC02", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Spa"}),
    ]
    button = CancelDelaysButton(mock_coordinator, system_object)

    with pytest.raises(HomeAssistantError) as err:
        await button.async_press()

    assert err.value.translation_domain == "intellicenter"
    assert err.value.translation_key == "no_active_delays"
    mock_coordinator.controller.request_changes.assert_not_awaited()


async def test_cancel_delays_translates_write_failure(
    hass: HomeAssistant,
    mock_coordinator: MagicMock,
    system_object: PoolObject,
) -> None:
    """Protocol failures are surfaced as localized Home Assistant errors."""
    active = PoolObject(
        "CIRC01", {"OBJTYP": CIRCUIT_TYPE, "SNAME": "Pool", "DLY": STATUS_ON}
    )
    mock_coordinator.model = MagicMock()
    mock_coordinator.model.get_by_type.return_value = [active]
    mock_coordinator.controller.request_changes.side_effect = ICConnectionError(
        "Not connected"
    )
    button = CancelDelaysButton(mock_coordinator, system_object)

    with pytest.raises(HomeAssistantError) as err:
        await button.async_press()

    assert err.value.translation_domain == "intellicenter"
    assert err.value.translation_key == "cancel_delays_failed"
