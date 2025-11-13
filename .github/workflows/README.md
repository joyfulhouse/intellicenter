# CI/CD Workflows

This directory contains GitHub Actions workflows for quality assurance and validation.

## Workflows

### quality-scale.yaml (Primary)

**Purpose:** Validates compliance with Home Assistant Integration Quality Scale

**Triggers:**
- Push to `main` or `claude/**` branches
- Pull requests
- Manual workflow dispatch

**Jobs:**

1. **🥉 Bronze Tier Validation**
   - Validates Bronze tier requirements
   - Checks entity naming, unique IDs, runtime data usage
   - Must pass for pipeline to continue

2. **Code Quality Checks**
   - Black formatting check
   - isort import ordering
   - flake8 linting
   - Enforces code style consistency

3. **🥈 Silver Tier - Test Coverage**
   - Runs pytest test suite
   - Measures code coverage
   - Requires 75%+ coverage (goal: 95%)
   - Uploads coverage to Codecov

4. **🥇 Gold Tier Validation**
   - Checks diagnostics support
   - Validates device class usage
   - Verifies entity categories

5. **🏆 Platinum Tier - Type Checking**
   - Validates py.typed marker
   - Runs mypy type checker
   - Non-blocking (warnings allowed)

6. **Home Assistant Validation (hassfest)**
   - Validates manifest.json
   - Checks HA compatibility
   - Official HA validation tool

7. **📊 Quality Scale Report**
   - Generates comprehensive report
   - Shows tier compliance status
   - Fails if any critical check fails

### ci.yaml (Legacy/Simplified)

Simplified CI pipeline for basic checks. The quality-scale.yaml workflow is more comprehensive.

## Local Testing

Before pushing, run these checks locally:

```bash
# Quality scale validation
python scripts/validate_quality_scale.py

# Code formatting
black custom_components/intellicenter
isort custom_components/intellicenter

# Linting
flake8 custom_components/intellicenter --max-line-length=88 --extend-ignore=E203,W503,E501

# Type checking
mypy custom_components/intellicenter --ignore-missing-imports --explicit-package-bases

# Tests with coverage
pytest tests/ --cov=custom_components/intellicenter --cov-report=term -v
```

## Pipeline Status

All workflows must pass for:
- ✅ Merging pull requests
- ✅ Releasing new versions
- ✅ Maintaining quality scale certification

## Quality Scale Certification

Current status: **🏆 Platinum**

- ✅ Bronze: Config flow, entity naming, unique IDs
- ✅ Silver: Test coverage, entry unloading
- ✅ Gold: Diagnostics, device classes, categories
- ✅ Platinum: Type checking, async architecture

## References

- [Home Assistant Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Integration Checklist](https://developers.home-assistant.io/docs/development_checklist)
- [CI/CD Best Practices](https://docs.github.com/en/actions/learn-github-actions)
