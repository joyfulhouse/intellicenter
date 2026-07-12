"""Firmware version parsing and known-issue advisories.

The SYSTEM object's VER attribute carries the panel firmware in the form
``"IC: 1.064 , ICWEB:2021-10-19 1.007"``. This module parses the IC panel
version and compares it against a curated table of firmware releases with
documented problems. Matches raise Home Assistant Repairs issues so the user
sees a dismissible warning in Settings instead of hitting the problem blind.

Every advisory in ``KNOWN_FIRMWARE_ISSUES`` must cite a source via
``learn_more_url`` — no speculative entries. The table is deliberately
conservative: an advisory should describe a *documented* fault, not a hunch.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from pyintellicenter import SYSTEM_TYPE, VER_ATTR

from .const import DOMAIN

if TYPE_CHECKING:
    from . import IntelliCenterConfigEntry
    from .coordinator import IntelliCenterCoordinator

_LOGGER = logging.getLogger(__name__)

# Matches the IC panel version inside a raw VER string: "IC: 1.064 , ..." or a
# bare "1.064". The minor part is zero-padded on the wire ("064"), so both
# components are compared as integers.
_IC_VERSION_RE = re.compile(r"(?:IC:\s*)?(\d+)\.(\d+)")


def parse_ic_version(raw_value: Any) -> tuple[int, int] | None:
    """Extract the IC panel firmware version from a raw VER string.

    Returns a comparable ``(major, minor)`` tuple — e.g. ``"IC: 1.064"`` ->
    ``(1, 64)`` — or ``None`` when the value is missing or unparseable. An
    unparseable version must never break setup; the caller treats ``None``
    as "no advisories apply".
    """
    if raw_value is None:
        return None
    match = _IC_VERSION_RE.search(str(raw_value))
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


@dataclass(frozen=True)
class FirmwareAdvisory:
    """A documented problem affecting specific IntelliCenter firmware versions.

    Exactly one matcher should be set: ``max_version`` flags every version at
    or below the bound (inclusive); ``exact_versions`` flags only the listed
    versions. ``translation_key`` selects the issue text from strings.json
    (``issues.<translation_key>``); ``learn_more_url`` cites the source that
    documents the problem.
    """

    issue_id: str
    translation_key: str
    learn_more_url: str
    max_version: tuple[int, int] | None = None
    exact_versions: tuple[tuple[int, int], ...] | None = None

    def matches(self, version: tuple[int, int]) -> bool:
        """Return True if the given firmware version is affected."""
        if self.max_version is not None and version <= self.max_version:
            return True
        return bool(self.exact_versions and version in self.exact_versions)


# Curated advisories. Sources are mandatory (learn_more_url); entries are
# deliberately conservative — documented faults only. Notably ABSENT:
# - 1.064: the community-documented safe baseline and official revert point;
#   warning on it would be pure noise.
# - 3.004: mixed user reports (MicroBrite replay, freeze-protect toggle),
#   but it is Pentair's mandatory stepping stone to 3.008 — candidates for a
#   future entry if reports firm up (see issue #101).
# All IntelliCenter OCP models share one firmware path (research found no
# hardware generation stuck on 1.x), so the recommendations are universal:
# official path 1.047 -> 1.064 -> 3.004 -> 3.008, wireless remote updated
# together with the panel.
KNOWN_FIRMWARE_ISSUES: list[FirmwareAdvisory] = [
    # The 2.x line: 2.006 shipped with severe bugs (broken schedules incl.
    # Celsius setpoint corruption, pumps randomly commanded to 0 RPM,
    # spillway broken, RS-485 heater comm faults) and was pulled by Pentair;
    # 2.017 introduced new heater-control bugs; 2.026 was also pulled.
    # nodejs-poolController carried a hard "do not upgrade to 2.006" warning
    # for years. Pentair's official upgrade path skips 2.x entirely.
    FirmwareAdvisory(
        issue_id="firmware_2x",
        translation_key="firmware_2x",
        learn_more_url="https://www.troublefreepool.com/threads/intellicenter-2-006-firmware.267174/",
        exact_versions=((2, 6), (2, 17), (2, 26)),
    ),
    # Pre-1.064 firmware: superseded for years; only partial third-party
    # protocol support is documented (njsPC: dual-body gaps, missing
    # IntelliChem dose data), and Pentair's upgrade path requires stepping
    # through 1.064 anyway.
    FirmwareAdvisory(
        issue_id="firmware_outdated_1x",
        translation_key="firmware_outdated_1x",
        learn_more_url="https://www.pentair.com/en-us/pool-spa/education-support/homeowner-support/software-downloads/intellicenter-control-system.html",
        max_version=(1, 63),
    ),
]


def matching_advisories(
    version: tuple[int, int], advisories: list[FirmwareAdvisory]
) -> list[FirmwareAdvisory]:
    """Return the advisories affecting the given firmware version."""
    return [adv for adv in advisories if adv.matches(version)]


@callback
def async_check_firmware(
    hass: HomeAssistant,
    entry: IntelliCenterConfigEntry,
    coordinator: IntelliCenterCoordinator,
    advisories: list[FirmwareAdvisory] | None = None,
) -> None:
    """Raise Repairs issues for known-problem firmware; clear stale ones.

    Called at setup, after the model is populated. Issue ids are suffixed
    with the entry id so multi-panel installs get per-panel issues. Every
    known advisory that does NOT match is explicitly deleted, so an issue
    raised before a firmware upgrade clears on the next (re)load.
    """
    if advisories is None:
        advisories = KNOWN_FIRMWARE_ISSUES

    version: tuple[int, int] | None = None
    for obj in coordinator.model.get_by_type(SYSTEM_TYPE):
        version = parse_ic_version(obj[VER_ATTR])
        if version is not None:
            break

    matched: set[str] = set()
    if version is not None:
        for adv in matching_advisories(version, advisories):
            matched.add(adv.issue_id)
            _LOGGER.warning(
                "IntelliCenter firmware %d.%03d has a known issue (%s); see %s",
                version[0],
                version[1],
                adv.issue_id,
                adv.learn_more_url,
            )
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"{adv.issue_id}_{entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                learn_more_url=adv.learn_more_url,
                translation_key=adv.translation_key,
                translation_placeholders={
                    "firmware": f"{version[0]}.{version[1]:03d}",
                },
            )

    for adv in advisories:
        if adv.issue_id not in matched:
            ir.async_delete_issue(hass, DOMAIN, f"{adv.issue_id}_{entry.entry_id}")
