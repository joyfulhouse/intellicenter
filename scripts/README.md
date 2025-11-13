# Quality Scale Validation Scripts

This directory contains scripts to validate Home Assistant Integration Quality Scale compliance.

## validate_quality_scale.py

Validates compliance with Bronze, Silver, Gold, and Platinum quality scale tiers.

### Usage

```bash
# Run from repository root
python scripts/validate_quality_scale.py
```

### What it checks

#### 🥉 Bronze Tier
- ✅ Entities use `has_entity_name = True`
- ✅ Entities have `unique_id` property
- ✅ Uses `entry.runtime_data` for runtime data
- ✅ Config flow implementation exists

#### 🥈 Silver Tier
- ✅ Config entry unloading (`async_unload_entry`)
- ✅ Test framework exists
- ⚠️ Test coverage > 95% (measured separately)

#### 🥇 Gold Tier
- ✅ Device classes used
- ✅ Diagnostics support (`diagnostics.py`)
- ✅ Entity categories used

#### 🏆 Platinum Tier
- ✅ Type annotations present
- ✅ Async/await patterns used
- ✅ `py.typed` marker exists

### Exit Codes

- `0`: All validations passed
- `1`: Validation failed

### Example Output

```
🥉 Validating Bronze Tier Requirements...
  Checking has_entity_name usage...
  Checking unique_id implementation...
  Checking runtime_data usage...
  Checking config flow...

✅ ALL QUALITY SCALE VALIDATIONS PASSED! 🏆
```

## CI/CD Integration

This script is automatically run in GitHub Actions via `.github/workflows/quality-scale.yaml`.

## Local Testing

Before committing, run:

```bash
# Validate quality scale
python scripts/validate_quality_scale.py

# Run linting
black custom_components/intellicenter
isort custom_components/intellicenter
flake8 custom_components/intellicenter --max-line-length=88

# Run type checking
mypy custom_components/intellicenter --ignore-missing-imports

# Run tests with coverage
pytest tests/ --cov=custom_components/intellicenter --cov-report=term
```

## References

- [Home Assistant Quality Scale Rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)
- [Integration Development Checklist](https://developers.home-assistant.io/docs/development_checklist)
