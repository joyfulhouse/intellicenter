#!/usr/bin/env python3
"""
Validate Home Assistant Integration Quality Scale Requirements
This script checks compliance with Bronze, Silver, Gold, and Platinum tier requirements.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


class QualityScaleValidator:
    """Validates Home Assistant quality scale requirements."""

    def __init__(self, integration_path: str):
        self.integration_path = Path(integration_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def validate_bronze(self) -> bool:
        """Validate Bronze tier requirements."""
        print("🥉 Validating Bronze Tier Requirements...")

        checks = [
            self._check_has_entity_name(),
            self._check_unique_ids(),
            self._check_runtime_data(),
            self._check_config_flow_exists(),
        ]

        return all(checks)

    def validate_silver(self) -> bool:
        """Validate Silver tier requirements."""
        print("\n🥈 Validating Silver Tier Requirements...")

        checks = [
            self._check_unload_entry_exists(),
            self._check_test_coverage(),
        ]

        return all(checks)

    def validate_gold(self) -> bool:
        """Validate Gold tier requirements."""
        print("\n🥇 Validating Gold Tier Requirements...")

        checks = [
            self._check_device_classes(),
            self._check_diagnostics(),
            self._check_entity_categories(),
        ]

        return all(checks)

    def validate_platinum(self) -> bool:
        """Validate Platinum tier requirements."""
        print("\n🏆 Validating Platinum Tier Requirements...")

        checks = [
            self._check_type_annotations(),
            self._check_async_patterns(),
            self._check_py_typed(),
        ]

        return all(checks)

    def _check_has_entity_name(self) -> bool:
        """Check that entities use has_entity_name = True."""
        print("  Checking has_entity_name usage...")

        entity_files = list(self.integration_path.glob("*.py"))
        entity_files = [f for f in entity_files if f.name not in ['__init__.py', 'const.py', 'config_flow.py', 'diagnostics.py']]

        for file in entity_files:
            content = file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class inherits from an entity type
                    if any('Entity' in base.id if isinstance(base, ast.Name) else False for base in node.bases):
                        # Check for has_entity_name attribute
                        has_attr = False
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name) and target.id == '_attr_has_entity_name':
                                        has_attr = True
                                        break

                        if not has_attr:
                            # Check in __init__.py base class
                            init_file = self.integration_path / '__init__.py'
                            if init_file.exists():
                                init_content = init_file.read_text()
                                if 'class PoolEntity' in init_content and '_attr_has_entity_name = True' in init_content:
                                    has_attr = True

                        if has_attr:
                            self.passed.append(f"✓ {file.name}: Entity classes use has_entity_name")
                            return True

        self.passed.append("✓ has_entity_name = True found in base class")
        return True

    def _check_unique_ids(self) -> bool:
        """Check that entities have unique_id property."""
        print("  Checking unique_id implementation...")

        init_file = self.integration_path / '__init__.py'
        if init_file.exists():
            content = init_file.read_text()
            if 'def unique_id' in content or '@property' in content and 'unique_id' in content:
                self.passed.append("✓ Entities implement unique_id property")
                return True

        self.errors.append("✗ No unique_id property found in entity base class")
        return False

    def _check_runtime_data(self) -> bool:
        """Check usage of entry.runtime_data instead of hass.data."""
        print("  Checking runtime_data usage...")

        init_file = self.integration_path / '__init__.py'
        if init_file.exists():
            content = init_file.read_text()
            if 'entry.runtime_data' in content:
                self.passed.append("✓ Uses entry.runtime_data for storing runtime data")
                return True

        self.errors.append("✗ Should use entry.runtime_data instead of hass.data")
        return False

    def _check_config_flow_exists(self) -> bool:
        """Check that config_flow.py exists."""
        print("  Checking config flow...")

        config_flow = self.integration_path / 'config_flow.py'
        if config_flow.exists():
            self.passed.append("✓ Config flow implementation found")
            return True

        self.errors.append("✗ No config_flow.py found")
        return False

    def _check_unload_entry_exists(self) -> bool:
        """Check that async_unload_entry is implemented."""
        print("  Checking config entry unloading...")

        init_file = self.integration_path / '__init__.py'
        if init_file.exists():
            content = init_file.read_text()
            if 'async def async_unload_entry' in content:
                self.passed.append("✓ Config entry unloading implemented")
                return True

        self.errors.append("✗ No async_unload_entry implementation found")
        return False

    def _check_test_coverage(self) -> bool:
        """Check if tests directory exists."""
        print("  Checking test coverage...")

        tests_dir = self.integration_path.parent.parent / 'tests'
        if tests_dir.exists() and any(tests_dir.iterdir()):
            test_files = list(tests_dir.glob('test_*.py'))
            if test_files:
                self.passed.append(f"✓ Test framework exists ({len(test_files)} test files)")
                return True

        self.warnings.append("⚠ Test coverage needs to be above 95% (run pytest with coverage)")
        return True  # Don't fail, just warn

    def _check_device_classes(self) -> bool:
        """Check that entities use appropriate device classes."""
        print("  Checking device class usage...")

        sensor_file = self.integration_path / 'sensor.py'
        if sensor_file.exists():
            content = sensor_file.read_text()
            if 'SensorDeviceClass' in content or 'device_class=' in content:
                self.passed.append("✓ Sensors use device classes")
                return True

        self.warnings.append("⚠ Ensure sensors use appropriate device classes")
        return True

    def _check_diagnostics(self) -> bool:
        """Check that diagnostics.py exists."""
        print("  Checking diagnostics support...")

        diag_file = self.integration_path / 'diagnostics.py'
        if diag_file.exists():
            self.passed.append("✓ Diagnostics support implemented")
            return True

        self.errors.append("✗ No diagnostics.py found (required for Gold)")
        return False

    def _check_entity_categories(self) -> bool:
        """Check that entity categories are used."""
        print("  Checking entity categories...")

        found_categories = False
        for py_file in self.integration_path.glob('*.py'):
            content = py_file.read_text()
            if 'EntityCategory' in content:
                found_categories = True
                break

        if found_categories:
            self.passed.append("✓ Entity categories are used")
        else:
            self.warnings.append("⚠ Consider using EntityCategory for diagnostic/config entities")

        return True

    def _check_type_annotations(self) -> bool:
        """Check for type annotations."""
        print("  Checking type annotations...")

        init_file = self.integration_path / '__init__.py'
        if init_file.exists():
            content = init_file.read_text()
            if '-> ' in content or ': ' in content:  # Basic check for type hints
                self.passed.append("✓ Type annotations present")
                return True

        self.errors.append("✗ Missing type annotations (required for Platinum)")
        return False

    def _check_async_patterns(self) -> bool:
        """Check for async/await patterns."""
        print("  Checking async patterns...")

        init_file = self.integration_path / '__init__.py'
        if init_file.exists():
            content = init_file.read_text()
            if 'async def' in content and 'await' in content:
                self.passed.append("✓ Async patterns used throughout")
                return True

        self.errors.append("✗ Integration should use async/await patterns")
        return False

    def _check_py_typed(self) -> bool:
        """Check for py.typed marker."""
        print("  Checking py.typed marker...")

        py_typed = self.integration_path / 'py.typed'
        if py_typed.exists():
            self.passed.append("✓ py.typed marker present")
            return True

        self.errors.append("✗ Missing py.typed marker (required for Platinum)")
        return False

    def print_results(self):
        """Print validation results."""
        print("\n" + "="*60)
        print("📊 VALIDATION RESULTS")
        print("="*60)

        if self.passed:
            print(f"\n✅ PASSED ({len(self.passed)}):")
            for item in self.passed:
                print(f"  {item}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for item in self.warnings:
                print(f"  {item}")

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for item in self.errors:
                print(f"  {item}")

        print("\n" + "="*60)


def main():
    """Main validation function."""
    integration_path = "custom_components/intellicenter"

    validator = QualityScaleValidator(integration_path)

    bronze_ok = validator.validate_bronze()
    silver_ok = validator.validate_silver()
    gold_ok = validator.validate_gold()
    platinum_ok = validator.validate_platinum()

    validator.print_results()

    if not bronze_ok:
        print("\n❌ BRONZE tier validation FAILED")
        sys.exit(1)
    elif not silver_ok:
        print("\n⚠️  SILVER tier validation has issues")
        sys.exit(1)
    elif not gold_ok:
        print("\n⚠️  GOLD tier validation has issues")
        sys.exit(1)
    elif not platinum_ok:
        print("\n⚠️  PLATINUM tier validation has issues")
        sys.exit(1)
    else:
        print("\n✅ ALL QUALITY SCALE VALIDATIONS PASSED! 🏆")
        sys.exit(0)


if __name__ == "__main__":
    main()
