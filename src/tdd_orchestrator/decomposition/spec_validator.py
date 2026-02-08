"""Spec conformance validator for decomposed tasks.

Validates that decomposed task fields (impl_file, test_file, module_exports)
are consistent with the spec's MODULE STRUCTURE and MODULE API SPECIFICATION.
Reports violations without auto-fixing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SpecViolation:
    """A single spec conformance violation.

    Attributes:
        task_key: The task that has the violation.
        field: Which field has the issue ("impl_file", "test_file", "module_exports").
        expected: What the spec says (or pattern).
        actual: What the task has.
        severity: "error" for definite problems, "warning" for possible issues.
    """

    task_key: str
    field: str
    expected: str
    actual: str
    severity: str  # "error" or "warning"


class SpecConformanceValidator:
    """Validates decomposed tasks against spec constraints.

    Checks impl_file paths against MODULE STRUCTURE, module_exports against
    MODULE API SPECIFICATION, and integration test paths for correctness.
    """

    def validate(
        self,
        tasks: list[Any],
        module_structure: dict[str, Any] | None = None,
        module_api: dict[str, dict[str, Any]] | None = None,
    ) -> list[SpecViolation]:
        """Run all validation checks against the spec.

        Args:
            tasks: List of DecomposedTask objects.
            module_structure: Dictionary with optional 'files' list.
            module_api: Dictionary mapping module paths to export specs.

        Returns:
            List of SpecViolation objects (empty if all valid).
        """
        violations: list[SpecViolation] = []
        violations.extend(self.validate_impl_paths(tasks, module_structure))
        violations.extend(self.validate_module_exports(tasks, module_api))
        violations.extend(self.validate_integration_test_paths(tasks))
        return violations

    def validate_impl_paths(
        self,
        tasks: list[Any],
        module_structure: dict[str, Any] | None = None,
    ) -> list[SpecViolation]:
        """Check impl_file starts with a path from MODULE STRUCTURE.

        Args:
            tasks: List of DecomposedTask objects.
            module_structure: Dictionary with optional 'files' list.

        Returns:
            List of violations for invalid impl_file paths.
        """
        if not module_structure or not module_structure.get("files"):
            return []

        # Extract valid directory prefixes from spec files
        valid_prefixes: set[str] = set()
        for file_path in module_structure["files"]:
            parts = str(file_path).rsplit("/", 1)
            if len(parts) == 2:
                valid_prefixes.add(parts[0] + "/")

        if not valid_prefixes:
            return []

        violations: list[SpecViolation] = []
        for task in tasks:
            impl_file = getattr(task, "impl_file", "") or ""
            task_key = getattr(task, "task_key", "unknown")

            if not impl_file:
                continue

            # Check if impl_file starts with any valid prefix
            matches_prefix = any(impl_file.startswith(prefix) for prefix in valid_prefixes)
            if not matches_prefix:
                violations.append(
                    SpecViolation(
                        task_key=task_key,
                        field="impl_file",
                        expected=f"one of: {', '.join(sorted(valid_prefixes))}",
                        actual=impl_file,
                        severity="error",
                    )
                )

        return violations

    def validate_module_exports(
        self,
        tasks: list[Any],
        module_api: dict[str, dict[str, Any]] | None = None,
    ) -> list[SpecViolation]:
        """Check module_exports match MODULE API SPECIFICATION.

        Args:
            tasks: List of DecomposedTask objects.
            module_api: Dictionary mapping module paths to export specs.

        Returns:
            List of violations for mismatched exports.
        """
        if not module_api:
            return []

        # Build a set of all valid exports from the spec
        valid_exports: set[str] = set()
        for spec in module_api.values():
            for export in spec.get("exports", []):
                valid_exports.add(str(export))

        if not valid_exports:
            return []

        violations: list[SpecViolation] = []
        for task in tasks:
            task_exports = getattr(task, "module_exports", []) or []
            task_key = getattr(task, "task_key", "unknown")

            for export in task_exports:
                if export not in valid_exports:
                    violations.append(
                        SpecViolation(
                            task_key=task_key,
                            field="module_exports",
                            expected=f"one of: {', '.join(sorted(valid_exports))}",
                            actual=str(export),
                            severity="warning",
                        )
                    )

        return violations

    def validate_integration_test_paths(
        self,
        tasks: list[Any],
    ) -> list[SpecViolation]:
        """Check integration/e2e tasks don't have bogus impl_file.

        Integration and e2e test tasks should have impl_file equal to test_file
        (the test IS the deliverable), not a fabricated src/integration/ path.

        Args:
            tasks: List of DecomposedTask objects.

        Returns:
            List of violations for incorrect integration test impl_files.
        """
        violations: list[SpecViolation] = []
        for task in tasks:
            test_file = getattr(task, "test_file", "") or ""
            impl_file = getattr(task, "impl_file", "") or ""
            task_key = getattr(task, "task_key", "unknown")

            # Check if this is an integration or e2e test task
            is_integration = test_file.startswith("tests/integration/")
            is_e2e = test_file.startswith("tests/e2e/")

            if not (is_integration or is_e2e):
                continue

            # Flag bogus impl_file paths for integration/e2e tasks
            if impl_file.startswith("src/integration/") or impl_file.startswith("src/e2e/"):
                violations.append(
                    SpecViolation(
                        task_key=task_key,
                        field="impl_file",
                        expected=f"test_file value ({test_file}) or existing src/ module",
                        actual=impl_file,
                        severity="error",
                    )
                )

        return violations
