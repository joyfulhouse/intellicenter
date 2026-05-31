"""Guard against version/dependency drift between manifest.json and pyproject.toml.

These are two independent sources of truth that have silently drifted before
(manifest ``3.6.6`` vs pyproject ``3.6.0``; ``pyintellicenter>=0.1.15`` vs
``>=0.1.7``). HACS/Home Assistant read ``manifest.json``; packaging/tests read
``pyproject.toml``. This test fails loudly when they disagree so a release cannot
ship mismatched metadata.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _ROOT / "custom_components" / "intellicenter" / "manifest.json"
_PYPROJECT = _ROOT / "pyproject.toml"


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _pyintellicenter_spec(requirements: list[str]) -> str | None:
    """Return the pyintellicenter requirement string with whitespace removed."""
    for req in requirements:
        normalized = req.replace(" ", "")
        if normalized.replace("_", "-").lower().startswith("pyintellicenter"):
            return normalized
    return None


def test_version_matches() -> None:
    manifest_version = _manifest()["version"]
    pyproject_version = _pyproject()["project"]["version"]
    assert manifest_version == pyproject_version, (
        f"Version drift: manifest.json={manifest_version!r} != "
        f"pyproject.toml={pyproject_version!r}. Keep them in sync on every release."
    )


def test_pyintellicenter_pin_matches() -> None:
    manifest_spec = _pyintellicenter_spec(_manifest()["requirements"])
    pyproject_spec = _pyintellicenter_spec(_pyproject()["project"]["dependencies"])
    assert manifest_spec is not None, "manifest.json is missing a pyintellicenter requirement"
    assert pyproject_spec is not None, "pyproject.toml is missing a pyintellicenter dependency"
    assert manifest_spec == pyproject_spec, (
        f"pyintellicenter pin drift: manifest.json={manifest_spec!r} != "
        f"pyproject.toml={pyproject_spec!r}. Keep them in sync."
    )
