# Development

How to set up a development environment for Pentair IntelliCenter.

This integration is built on the
[pyintellicenter](https://github.com/joyfulhouse/pyintellicenter) protocol
library. See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, and
[TESTING.md](TESTING.md) for the test suite layout.

## Prerequisites

- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

## Setup

```bash
git clone https://github.com/joyfulhouse/intellicenter.git
git clone https://github.com/joyfulhouse/pyintellicenter.git

cd intellicenter
uv sync

# Optional: develop against a local checkout of the protocol library
uv pip install -e ../pyintellicenter
```

For normal test/CI runs the published release is used (per `manifest.json`:
`pyintellicenter>=0.1.19`). Keep `pyproject.toml`'s pin and `uv.lock` in sync
with `manifest.json`.

## Quality Checks

```bash
uv run pytest                                   # tests
uv run ruff check --fix && uv run ruff format   # lint + format
uv run mypy custom_components/intellicenter/    # type check (strict, see mypy.ini)
```

Run all of these before opening a pull request. See
[CONTRIBUTING](https://github.com/joyfulhouse/.github/blob/main/CONTRIBUTING.md)
for the contribution workflow.

## Releasing

1. Bump `version` in `custom_components/intellicenter/manifest.json` (and
   `pyproject.toml`).
2. Update [../CHANGELOG.md](../CHANGELOG.md): move the `## [Unreleased]` entries
   into a new dated version section and refresh the compare links.
3. Open a pull request and merge to `main`.
4. Create the matching GitHub release/tag to publish the HACS zip asset.
