"""Tests for spec conformance validator."""

from __future__ import annotations

from dataclasses import dataclass, field

from tdd_orchestrator.decomposition.spec_validator import (
    SpecConformanceValidator,
    SpecViolation,
)


@dataclass
class FakeTask:
    """Minimal task-like object for testing."""

    task_key: str = "TEST-01"
    impl_file: str = ""
    test_file: str = ""
    module_exports: list[str] = field(default_factory=list)


class TestValidateImplPaths:
    """Tests for impl_file path validation."""

    def test_correct_paths_no_violations(self) -> None:
        """All paths match module_structure -> no violations."""
        tasks = [
            FakeTask(task_key="T-01", impl_file="src/api/routes.py"),
            FakeTask(task_key="T-02", impl_file="src/api/models.py"),
        ]
        module_structure = {"files": ["src/api/routes.py", "src/api/models.py"]}
        validator = SpecConformanceValidator()
        violations = validator.validate_impl_paths(tasks, module_structure)
        assert violations == []

    def test_wrong_prefix_violation(self) -> None:
        """src/htmx/ when spec says src/api/ -> violation."""
        tasks = [FakeTask(task_key="T-01", impl_file="src/htmx/routes.py")]
        module_structure = {"files": ["src/api/routes.py"]}
        validator = SpecConformanceValidator()
        violations = validator.validate_impl_paths(tasks, module_structure)
        assert len(violations) == 1
        assert violations[0].severity == "error"
        assert violations[0].field == "impl_file"
        assert "src/htmx/routes.py" in violations[0].actual

    def test_no_module_structure_no_violations(self) -> None:
        """Empty module_structure -> no violations (backward compat)."""
        tasks = [FakeTask(task_key="T-01", impl_file="src/anything/foo.py")]
        validator = SpecConformanceValidator()
        violations = validator.validate_impl_paths(tasks, None)
        assert violations == []

    def test_empty_files_no_violations(self) -> None:
        """module_structure with no files -> no violations."""
        tasks = [FakeTask(task_key="T-01", impl_file="src/foo/bar.py")]
        validator = SpecConformanceValidator()
        violations = validator.validate_impl_paths(tasks, {"files": []})
        assert violations == []

    def test_empty_impl_file_skipped(self) -> None:
        """Tasks with no impl_file are skipped."""
        tasks = [FakeTask(task_key="T-01", impl_file="")]
        module_structure = {"files": ["src/api/routes.py"]}
        validator = SpecConformanceValidator()
        violations = validator.validate_impl_paths(tasks, module_structure)
        assert violations == []


class TestValidateModuleExports:
    """Tests for module_exports validation."""

    def test_correct_exports_no_violations(self) -> None:
        """Exports match spec -> no violations."""
        tasks = [FakeTask(task_key="T-01", module_exports=["ConfigLoader", "load_config"])]
        module_api = {
            "src/config.py": {"exports": ["ConfigLoader", "load_config", "ConfigError"]}
        }
        validator = SpecConformanceValidator()
        violations = validator.validate_module_exports(tasks, module_api)
        assert violations == []

    def test_missing_export_warning(self) -> None:
        """Task has export not in spec -> warning."""
        tasks = [FakeTask(task_key="T-01", module_exports=["UnknownExport"])]
        module_api = {"src/config.py": {"exports": ["ConfigLoader"]}}
        validator = SpecConformanceValidator()
        violations = validator.validate_module_exports(tasks, module_api)
        assert len(violations) == 1
        assert violations[0].severity == "warning"
        assert violations[0].actual == "UnknownExport"

    def test_no_module_api_no_violations(self) -> None:
        """No module_api -> no violations."""
        tasks = [FakeTask(task_key="T-01", module_exports=["Something"])]
        validator = SpecConformanceValidator()
        violations = validator.validate_module_exports(tasks, None)
        assert violations == []


class TestValidateIntegrationTestPaths:
    """Tests for integration/e2e test path validation."""

    def test_bogus_integration_impl_error(self) -> None:
        """src/integration/foo.py for integration test -> error."""
        tasks = [
            FakeTask(
                task_key="T-01",
                test_file="tests/integration/test_api.py",
                impl_file="src/integration/app_lifecycle.py",
            )
        ]
        validator = SpecConformanceValidator()
        violations = validator.validate_integration_test_paths(tasks)
        assert len(violations) == 1
        assert violations[0].severity == "error"
        assert violations[0].field == "impl_file"

    def test_correct_integration_impl_no_violation(self) -> None:
        """Integration test with src/api/routes.py -> no violation."""
        tasks = [
            FakeTask(
                task_key="T-01",
                test_file="tests/integration/test_api.py",
                impl_file="src/api/routes.py",
            )
        ]
        validator = SpecConformanceValidator()
        violations = validator.validate_integration_test_paths(tasks)
        assert violations == []

    def test_e2e_bogus_impl_error(self) -> None:
        """src/e2e/flow.py for e2e test -> error."""
        tasks = [
            FakeTask(
                task_key="T-01",
                test_file="tests/e2e/test_full_flow.py",
                impl_file="src/e2e/flow.py",
            )
        ]
        validator = SpecConformanceValidator()
        violations = validator.validate_integration_test_paths(tasks)
        assert len(violations) == 1
        assert violations[0].severity == "error"

    def test_unit_test_not_checked(self) -> None:
        """Unit tests are not subject to integration test checks."""
        tasks = [
            FakeTask(
                task_key="T-01",
                test_file="tests/unit/test_config.py",
                impl_file="src/integration/something.py",
            )
        ]
        validator = SpecConformanceValidator()
        violations = validator.validate_integration_test_paths(tasks)
        assert violations == []


class TestValidateAll:
    """Tests for the combined validate() method."""

    def test_multiple_violation_types(self) -> None:
        """Validate catches violations from multiple checks."""
        tasks = [
            FakeTask(
                task_key="T-01",
                impl_file="src/htmx/routes.py",
                test_file="tests/integration/test_api.py",
            ),
        ]
        module_structure = {"files": ["src/api/routes.py"]}
        validator = SpecConformanceValidator()
        violations = validator.validate(tasks, module_structure)
        # Should get impl_path violation (wrong prefix) but NOT integration test
        # violation (src/htmx/ is not src/integration/)
        assert len(violations) >= 1
        assert any(v.field == "impl_file" for v in violations)
