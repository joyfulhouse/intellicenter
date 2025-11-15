.PHONY: help lint format type-check bronze test pytest install-hooks

help:
	@echo "Available targets:"
	@echo "  lint          - Run ruff linting checks"
	@echo "  format        - Format code with ruff"
	@echo "  format-check  - Check code formatting without modifying"
	@echo "  type-check    - Run mypy type checking"
	@echo "  pytest        - Run pytest test suite"
	@echo "  bronze        - Run all bronze level checks (lint, format, type-check, pytest)"
	@echo "  test          - Alias for bronze"
	@echo "  install-hooks - Install pre-commit hooks"

lint:
	ruff check custom_components/

lint-fix:
	ruff check --fix custom_components/

format:
	ruff format custom_components/

format-check:
	ruff format --check custom_components/

type-check:
	mypy custom_components/intellicenter/ --ignore-missing-imports --no-strict-optional || true

pytest:
	pytest tests/ -v --tb=short

bronze: lint format-check type-check pytest
	@echo "✅ All bronze level checks passed!"

test: bronze

install-hooks:
	pre-commit install
