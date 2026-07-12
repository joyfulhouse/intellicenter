"""Test firmware version parsing and known-issue advisories."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.intellicenter.const import DOMAIN
from custom_components.intellicenter.firmware import (
    KNOWN_FIRMWARE_ISSUES,
    FirmwareAdvisory,
    async_check_firmware,
    matching_advisories,
    parse_ic_version,
)

pytestmark = pytest.mark.asyncio


# -------------------------------------------------------------------------------------
# parse_ic_version


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Hardware-observed format (IC 1.064 unit)
        ("IC: 1.064 , ICWEB:2021-10-19 1.007", (1, 64)),
        ("IC: 2.006", (2, 6)),
        ("IC:1.047", (1, 47)),
        ("IC: 3.004 , ICWEB:2024-11-02 2.010", (3, 4)),
        # Version without the IC: prefix (defensive)
        ("1.064", (1, 64)),
        # Unparseable values
        ("", None),
        ("garbage", None),
        (None, None),
    ],
)
async def test_parse_ic_version(
    raw: str | None, expected: tuple[int, int] | None
) -> None:
    """The IC panel version is extracted from the raw VER string."""
    assert parse_ic_version(raw) == expected


# -------------------------------------------------------------------------------------
# matching_advisories


def _advisory(**overrides) -> FirmwareAdvisory:
    """Return a test advisory with sensible defaults."""
    defaults = {
        "issue_id": "test_advisory",
        "translation_key": "firmware_test",
        "max_version": None,
        "exact_versions": None,
        "learn_more_url": "https://example.com",
    }
    defaults.update(overrides)
    return FirmwareAdvisory(**defaults)


async def test_matching_advisories_max_version() -> None:
    """A max_version advisory matches all versions at or below the bound."""
    adv = _advisory(max_version=(1, 47))
    assert adv in matching_advisories((1, 40), [adv])
    assert adv in matching_advisories((1, 47), [adv])
    assert adv not in matching_advisories((1, 64), [adv])
    assert adv not in matching_advisories((2, 6), [adv])


async def test_matching_advisories_exact_versions() -> None:
    """An exact_versions advisory matches only the listed versions."""
    adv = _advisory(exact_versions=((1, 64),))
    assert adv in matching_advisories((1, 64), [adv])
    assert adv not in matching_advisories((1, 63), [adv])
    assert adv not in matching_advisories((2, 6), [adv])


async def test_known_firmware_issues_are_well_formed() -> None:
    """Every curated advisory has an id, translation key, source, and a matcher."""
    for adv in KNOWN_FIRMWARE_ISSUES:
        assert adv.issue_id
        assert adv.translation_key
        assert adv.learn_more_url and adv.learn_more_url.startswith("https://")
        assert adv.max_version is not None or adv.exact_versions is not None


# -------------------------------------------------------------------------------------
# async_check_firmware


def _mock_coordinator_with_ver(pool_model, raw_ver: str | None) -> MagicMock:
    """Build a minimal coordinator mock exposing a SYSTEM object with VER."""
    coordinator = MagicMock()
    system_obj = MagicMock()
    system_obj.__getitem__ = MagicMock(return_value=raw_ver)
    coordinator.model.get_by_type.return_value = [system_obj]
    return coordinator


async def test_async_check_firmware_creates_issue(hass: HomeAssistant) -> None:
    """A firmware version matching an advisory raises a Repairs issue."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = _mock_coordinator_with_ver(None, "IC: 1.040")

    advisories = [_advisory(issue_id="outdated", max_version=(1, 47))]
    async_check_firmware(hass, entry, coordinator, advisories=advisories)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "outdated_test_entry") is not None


async def test_async_check_firmware_clears_stale_issue(hass: HomeAssistant) -> None:
    """An issue raised for an old firmware is deleted once the version no longer matches."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    advisories = [_advisory(issue_id="outdated", max_version=(1, 47))]

    coordinator = _mock_coordinator_with_ver(None, "IC: 1.040")
    async_check_firmware(hass, entry, coordinator, advisories=advisories)
    await hass.async_block_till_done()

    # Firmware upgraded -> advisory no longer applies
    coordinator = _mock_coordinator_with_ver(None, "IC: 2.006")
    async_check_firmware(hass, entry, coordinator, advisories=advisories)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "outdated_test_entry") is None


async def test_async_check_firmware_unparseable_is_noop(hass: HomeAssistant) -> None:
    """An unparseable VER value raises no issue and does not crash setup."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = _mock_coordinator_with_ver(None, "garbage")

    advisories = [_advisory(issue_id="outdated", max_version=(1, 47))]
    async_check_firmware(hass, entry, coordinator, advisories=advisories)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "outdated_test_entry") is None
