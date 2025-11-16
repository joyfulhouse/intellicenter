# CI/CD Workflows

This directory contains GitHub Actions workflows for validating the IntelliCenter integration against Home Assistant Quality Scale standards.

## Workflows

### `quality-validation.yml` (Primary)

**The main validation workflow** that implements a two-tier quality gate system:

#### Execution Flow

```
┌─────────────────────────────────────────────────┐
│          BRONZE TIER VALIDATION                 │
│  (All jobs run in parallel)                     │
├─────────────────────────────────────────────────┤
│  • UI Configuration                             │
│  • Code Quality Standards                       │
│  • Automated Testing                            │
│  • End-User Documentation                       │
│  • Home Assistant Validation (hassfest)         │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
          ✅ Bronze Summary
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│          SILVER TIER VALIDATION                 │
│  (Only runs if Bronze passes)                   │
├─────────────────────────────────────────────────┤
│  • Error Recovery Testing                       │
│  • Logging Best Practices                       │
│  • Enhanced Documentation                       │
│  • Active Code Ownership                        │
│  • Authentication Handling                      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
          ✅ Silver Summary
                  │
                  ▼
          🎉 Quality Gate
```

#### Bronze Tier Checks

1. **UI Configuration**
   - Verifies `config_flow.py` exists
   - Checks `strings.json` for UI text
   - Validates `config_flow: true` in manifest

2. **Code Quality Standards**
   - Ruff linting and formatting
   - Bandit security scanning
   - mypy type checking (advisory)

3. **Automated Testing**
   - Runs full pytest suite
   - Requires all tests to pass
   - Generates coverage reports

4. **End-User Documentation**
   - Validates README.md exists
   - Checks for required sections
   - Verifies documentation URL in manifest

5. **Home Assistant Validation**
   - Runs official hassfest validation
   - Ensures manifest compliance

#### Silver Tier Checks

1. **Error Recovery Testing**
   - Tests connection failure handling
   - Verifies ConnectionHandler exists
   - Validates exponential backoff implementation

2. **Logging Best Practices**
   - Scans for excessive logging in loops
   - Verifies appropriate log levels
   - Ensures no log flooding

3. **Enhanced Documentation**
   - Requires comprehensive troubleshooting section (50+ lines)
   - Verifies debug logging instructions
   - Checks documentation depth

4. **Active Code Ownership**
   - Validates codeowners in manifest
   - Checks for recent activity (90 days)

5. **Authentication Handling**
   - For auth-based integrations: validates re-auth flow
   - For local integrations: verifies no-auth is documented

#### Triggers

- Push to `main` or `develop` branches
- All pull requests
- Manual workflow dispatch

---

### `bronze-validation.yml` (Legacy)

**Deprecated** - Kept for backward compatibility.

This workflow still runs basic Bronze validation but displays a deprecation notice. New development should use `quality-validation.yml`.

---

### `hassfest.yaml` (Standalone)

Runs Home Assistant's official validation tool on a daily schedule.

**Triggers:**
- Push to any branch
- Pull requests
- Daily at midnight UTC

---

### `claude.yml`

Claude Code integration for AI-assisted code reviews on pull requests.

**Triggers:** Pull requests with `@claude` in title or body

---

## Local Validation

Before pushing, you can run validations locally:

### Bronze Tier (Local)

```bash
# Code quality
ruff check custom_components/
ruff format --check custom_components/
bandit -r custom_components/intellicenter/ -ll

# Type checking
mypy custom_components/intellicenter/ --ignore-missing-imports

# Tests
pytest tests/ -v --cov=custom_components/intellicenter
```

### Silver Tier (Local)

```bash
# Error recovery test
pytest tests/test_init.py::test_async_setup_entry_connection_failed -v

# Check for excessive logging
grep -rn "while.*:" custom_components/ | grep -A 5 "_LOGGER"

# Verify troubleshooting docs
sed -n '/## Troubleshooting/,/## /p' README.md | wc -l
```

---

## Status Badges

Add these to your README to show CI/CD status:

```markdown
![Quality Validation](https://github.com/joyfulhouse/intellicenter/actions/workflows/quality-validation.yml/badge.svg)
```

---

## Quality Scale Requirements

### Bronze Requirements
✅ UI Configuration
✅ Code Quality Standards
✅ Automated Testing
✅ End-User Documentation

### Silver Requirements
✅ Automatic Error Recovery
✅ Clean Logging Practices
✅ Enhanced Documentation
✅ Active Code Ownership
✅ Authentication Handling

See [QUALITY_SCALE_COMPLIANCE.md](../../QUALITY_SCALE_COMPLIANCE.md) for complete details.

---

## Troubleshooting CI/CD

### Bronze Tests Failing

1. **Ruff errors**: Run `ruff check --fix custom_components/`
2. **Format issues**: Run `ruff format custom_components/`
3. **Test failures**: Run `pytest tests/ -v` locally to debug
4. **hassfest errors**: Check manifest.json syntax

### Silver Validation Failing

1. **Error recovery**: Ensure ConnectionHandler is properly implemented
2. **Logging issues**: Review `_LOGGER` usage in loops
3. **Documentation**: Expand troubleshooting section in README
4. **Code ownership**: Add/update codeowners in manifest.json

### Workflow Not Running

1. Check workflow file syntax with `yamllint`
2. Verify triggers match your branch/PR
3. Check GitHub Actions are enabled for the repository

---

## Adding New Checks

To add a new validation step:

1. Add to appropriate tier in `quality-validation.yml`
2. Update the summary step to include the new check
3. Document in this README
4. Update `QUALITY_SCALE_COMPLIANCE.md`

Example:

```yaml
new-check:
  name: "Bronze: New Validation"
  runs-on: ubuntu-latest
  steps:
    - name: Checkout repository
      uses: actions/checkout@v4

    - name: Run validation
      run: |
        # Your validation logic
        echo "✅ Validation passed"
```

Then add to dependencies:

```yaml
bronze-summary:
  needs: [
    # ... existing jobs
    new-check,
  ]
```

---

## References

- [Home Assistant Quality Scale](https://www.home-assistant.io/docs/quality_scale/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [hassfest Action](https://github.com/home-assistant/actions/tree/master/hassfest)
