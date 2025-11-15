# Validation Pipeline

This project uses a bronze level validation pipeline to ensure code quality and consistency.

## Bronze Level Compliance

Bronze level compliance includes:

- **Linting**: Code quality checks using `ruff`
- **Formatting**: Code formatting using `ruff format`
- **Type Checking**: Static type analysis using `mypy`

## Running Checks Locally

### Setup

First, install testing dependencies:

```bash
# Option 1: Using a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-test.txt

# Option 2: Using the system (if allowed)
pip install -r requirements-test.txt
```

### Using Make (Recommended)

```bash
# Run all bronze level checks (lint, format, type-check, pytest)
make bronze

# Run individual checks
make lint          # Run linting only
make format-check  # Check formatting only
make type-check    # Run type checking only
make pytest        # Run tests only

# Auto-fix issues
make lint-fix      # Fix linting issues
make format        # Format code
```

### Using Commands Directly

```bash
# Linting
ruff check custom_components/
ruff check --fix custom_components/  # Auto-fix

# Formatting
ruff format --check custom_components/  # Check only
ruff format custom_components/          # Format

# Type checking
mypy custom_components/intellicenter/ --ignore-missing-imports --no-strict-optional

# Testing
pytest tests/ -v
pytest tests/ -v --tb=short  # Short traceback
pytest tests/test_config_flow.py  # Run specific test file
```

## CI/CD Pipeline

The validation pipeline runs automatically in GitHub Actions:

1. **Bronze Validation** (`.github/workflows/bronze-validation.yml`)
   - Runs on all pushes to `main` and pull requests
   - Executes: ruff check, ruff format, mypy
   - Must pass before hassfest validation

2. **Hassfest Validation**
   - Runs after bronze validation passes
   - Validates Home Assistant component structure

3. **Claude Code Review** (`.github/workflows/claude.yml`)
   - Only runs after bronze validation and hassfest pass
   - Triggered by `@claude` mentions in PR comments/reviews
   - Provides AI-powered code review

## Pre-commit Hooks

Install pre-commit hooks to run checks automatically before commits:

```bash
make install-hooks
```

Or manually:

```bash
pre-commit install
```

## Configuration Files

- `pyproject.toml`: Ruff and mypy configuration
- `.pre-commit-config.yaml`: Pre-commit hook configuration
- `setup.cfg`: Legacy configuration (deprecated, kept for backwards compatibility)
- `Makefile`: Convenient commands for running checks

## Tool Versions

- **Ruff**: v0.8.4 (replaces black, isort, flake8, pyupgrade)
- **Mypy**: v1.13.0
- **Python**: 3.12+

## Ignoring Specific Rules

If you need to ignore a specific rule for a line of code, use:

```python
# ruff: noqa: E501
```

Or add to `pyproject.toml` for project-wide ignores.

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Mypy Documentation](https://mypy.readthedocs.io/)
- [Pre-commit Documentation](https://pre-commit.com/)
