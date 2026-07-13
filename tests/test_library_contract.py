"""Contract tests against the REAL pyintellicenter library.

The rest of the suite mocks ``ICModelController``, so a ``MagicMock`` answers to
*any* attribute access. That means a rename or removal of a controller method the
integration actually calls would pass the mocked tests and only break in
production. These tests import the actually-installed library and assert that the
API surface the integration depends on still exists, catching library/integration
drift across ``pyintellicenter`` version bumps (the kind of drift that let
manifest ``>=0.1.15`` ship while tests ran against 0.1.8).

To regenerate ``CONTROLLER_METHODS`` after the integration changes::

    grep -rhoE "(controller|_controller)\\.[a-zA-Z_]+\\(" \\
        custom_components/intellicenter/ \\
        | sed -E 's/.*\\.([a-zA-Z_]+)\\(/\\1/' | sort -u
"""

from __future__ import annotations

import pyintellicenter

from custom_components.intellicenter.const import (
    CALIB_ATTR,
    MANHT_ATTR,
    PORT_ATTR,
    PRIMFLO_ATTR,
    PRIMTIM_ATTR,
    PROBE_ATTR,
)
from custom_components.intellicenter.coordinator import DEFAULT_ATTRIBUTES_MAP

# Methods the integration invokes on the controller (ICModelController, which
# inherits ICBaseController). Existence + callability is asserted, not the exact
# signature: that catches the real drift risk (rename/removal) without coupling
# the test to internal parameter changes.
#
# NOTE: ``number.py`` dispatches several controller setters dynamically via a
# ``getattr(controller, method_name)`` table keyed on string literals (the
# IntelliChem setpoint methods below). The regenerate-grep in the module
# docstring matches ``controller.<name>(`` call syntax, so it structurally
# cannot find those string-literal method names -- they must be listed here
# manually:
#   set_alkalinity, set_calcium_hardness, set_cyanuric_acid,
#   set_orp_setpoint, set_ph_setpoint
CONTROLLER_METHODS = (
    "body_supports_cooling",
    "get_chem_alerts",
    "get_chlorinator_output",
    "get_pump_circuit_speed",
    "get_saturation_index",
    "get_schedule_circuit",
    "get_schedule_days",
    "get_schedule_start_time",
    "get_schedule_stop_time",
    "get_sensor_calibration",
    "get_sensor_probe_reading",
    "has_chem_alert",
    "is_body_cooling",
    "is_body_heating",
    "is_schedule_enabled",
    "is_vacation_mode",
    "refresh_pump_circuit_speed",
    "request_changes",
    "set_alkalinity",
    "set_calcium_hardness",
    "set_chlorinator_output",
    "set_cooling_setpoint",
    "set_cyanuric_acid",
    "set_heat_mode",
    "set_heating_setpoint",
    "set_light_effect",
    "set_orp_setpoint",
    "set_ph_setpoint",
    "set_setpoint",
    "set_vacation_mode",
    "start",
    "stop",
)

# Top-level symbols (classes/functions) the integration imports from the library.
REQUIRED_SYMBOLS = (
    "ICBaseController",
    "ICModelController",
    "ICConnectionHandler",
    "ICConnectionError",
    "ICTimeoutError",
    "ICSystemInfo",
    "PoolModel",
    "PoolObject",
    "SERVICE_ATTR",
    "discover_intellicenter_units",
    "ICUnit",
)


def test_required_symbols_exist() -> None:
    """Every top-level symbol the integration imports must still be exported."""
    missing = [name for name in REQUIRED_SYMBOLS if not hasattr(pyintellicenter, name)]
    assert not missing, (
        f"pyintellicenter no longer exports {missing}; the integration imports these. "
        "Update the integration or pin a compatible library version."
    )


def test_controller_methods_exist_and_callable() -> None:
    """Every controller method the integration calls must still exist."""
    controller = pyintellicenter.ICModelController
    missing = [
        name
        for name in CONTROLLER_METHODS
        if not callable(getattr(controller, name, None))
    ]
    assert not missing, (
        f"ICModelController is missing methods the integration calls: {missing}. "
        "This is library/integration contract drift that mocked tests cannot catch."
    )


def test_light_effects_includes_sam_show() -> None:
    """The installed library must map the SAm light show (issue #47).

    IntelliCenter reports the SAm show via USE=SAMMOD; ``light.py`` maps that
    code through ``LIGHT_EFFECTS``. Asserting against the *installed* library
    catches a manifest pin shipping a version without the fix -- the drift the
    mocked light tests cannot see.
    """
    effects = pyintellicenter.LIGHT_EFFECTS
    assert effects.get("SAMMOD") == "SAm", (
        "Installed pyintellicenter is missing the SAMMOD->'SAm' light show. "
        "Bump the manifest pin to a version that includes it."
    )


def test_chemistry_and_manual_heat_attributes_are_tracked() -> None:
    """Every attribute consumed by the new entities is requested into PoolModel."""
    assert {
        pyintellicenter.SINDEX_ATTR,
        pyintellicenter.TIMOUT_ATTR,
    } <= DEFAULT_ATTRIBUTES_MAP[pyintellicenter.CHEM_TYPE]
    assert "CHLOR" not in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.CHEM_TYPE]
    assert MANHT_ATTR not in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.BODY_TYPE]
    assert MANHT_ATTR in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.SYSTEM_TYPE]


def test_roadmap_attributes_are_tracked() -> None:
    """PoolModel must retain every object and attribute used by track 4."""
    assert (
        pyintellicenter.DLY_ATTR
        not in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.CIRCUIT_TYPE]
    )
    assert (
        pyintellicenter.TEMP_ATTR in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.BODY_TYPE]
    )
    assert (
        pyintellicenter.BOOST_ATTR
        not in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.BODY_TYPE]
    )
    assert {PRIMFLO_ATTR, PRIMTIM_ATTR} <= DEFAULT_ATTRIBUTES_MAP[
        pyintellicenter.PUMP_TYPE
    ]
    assert {PROBE_ATTR, CALIB_ATTR} <= DEFAULT_ATTRIBUTES_MAP[
        pyintellicenter.SENSE_TYPE
    ]
    assert (
        pyintellicenter.UPDATE_ATTR
        in DEFAULT_ATTRIBUTES_MAP[pyintellicenter.SYSTEM_TYPE]
    )
    assert {
        pyintellicenter.SNAME_ATTR,
        pyintellicenter.SUBTYP_ATTR,
        pyintellicenter.VER_ATTR,
        PORT_ATTR,
    } <= DEFAULT_ATTRIBUTES_MAP[pyintellicenter.MODULE_TYPE]


def test_sensor_diagnostic_helpers_are_available() -> None:
    """The installed library supplies the typed sensor diagnostic helpers."""
    assert callable(pyintellicenter.ICModelController.get_sensor_probe_reading)
    assert callable(pyintellicenter.ICModelController.get_sensor_calibration)
