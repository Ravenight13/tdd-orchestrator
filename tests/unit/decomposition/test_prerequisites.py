"""Tests for prerequisite task generation from spec metadata.

Tests the deterministic Phase 0 task generation for dependency changes
and package scaffolding detected in parsed specs.
"""

from __future__ import annotations

from tdd_orchestrator.decomposition import ParsedSpec, generate_prerequisite_tasks


def _make_key_generator() -> object:
    """Create a simple task key generator for testing.

    Returns a callable that generates sequential task keys for phase 0.
    """
    counter: dict[int, int] = {}

    def gen(phase: int) -> str:
        counter[phase] = counter.get(phase, 0) + 1
        return f"TEST-TDD-{phase:02d}-{counter[phase]:02d}"

    return gen


class TestPrerequisiteTaskGeneration:
    """Test generate_prerequisite_tasks function."""

    def test_generates_dependency_task_from_dependency_changes(self) -> None:
        """Test that dependency changes produce a Phase 0 dependency task."""
        spec = ParsedSpec(
            dependency_changes={
                "extra_name": "api",
                "packages": ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0"],
                "raw": "...",
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        assert len(tasks) == 1
        task = tasks[0]
        assert task.phase == 0
        assert task.sequence == 1
        assert "[api]" in task.title
        assert task.impl_file == "pyproject.toml"
        assert task.depends_on == []
        assert task.complexity == "low"
        assert len(task.acceptance_criteria) == 3
        assert "fastapi" in task.acceptance_criteria[2]

    def test_generates_scaffold_task_from_module_structure(self) -> None:
        """Test that module_structure with base_path produces a scaffold task."""
        spec = ParsedSpec(
            module_structure={
                "base_path": "backend/src/api",
                "files": ["router.py", "models.py", "schemas.py"],
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        assert len(tasks) == 1
        task = tasks[0]
        assert task.phase == 0
        assert task.sequence == 2
        assert "backend/src/api" in task.title
        assert task.impl_file == "backend/src/api/__init__.py"
        assert task.depends_on == []
        assert task.complexity == "low"
        assert any("backend.src.api" in ac for ac in task.acceptance_criteria)
        # Should mention file count
        assert any("3 module files" in ac for ac in task.acceptance_criteria)

    def test_generates_both_tasks_when_both_present(self) -> None:
        """Test that both dependency and scaffold tasks are generated together."""
        spec = ParsedSpec(
            dependency_changes={
                "extra_name": "web",
                "packages": ["flask>=3.0.0"],
                "raw": "...",
            },
            module_structure={
                "base_path": "src/web",
                "files": ["app.py"],
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        assert len(tasks) == 2
        assert tasks[0].sequence == 1  # Dependency task first
        assert tasks[1].sequence == 2  # Scaffold task second
        assert tasks[0].impl_file == "pyproject.toml"
        assert tasks[1].impl_file == "src/web/__init__.py"

    def test_no_tasks_when_no_metadata(self) -> None:
        """Test that empty spec produces no prerequisite tasks."""
        spec = ParsedSpec()
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())
        assert tasks == []

    def test_no_tasks_when_dependency_changes_has_no_packages(self) -> None:
        """Test that dependency_changes without packages produces no task."""
        spec = ParsedSpec(
            dependency_changes={"raw": "No changes needed."},
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())
        assert tasks == []

    def test_no_scaffold_task_when_module_structure_has_no_base_path(self) -> None:
        """Test that module_structure without base_path produces no scaffold task."""
        spec = ParsedSpec(
            module_structure={"base_path": "", "files": ["app.py"]},
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())
        assert tasks == []

    def test_task_keys_are_unique(self) -> None:
        """Test that generated task keys are unique across tasks."""
        spec = ParsedSpec(
            dependency_changes={
                "extra_name": "api",
                "packages": ["pkg1"],
                "raw": "...",
            },
            module_structure={
                "base_path": "src/api",
                "files": [],
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        keys = [t.task_key for t in tasks]
        assert len(keys) == len(set(keys)), f"Duplicate task keys: {keys}"

    def test_scaffold_task_without_files_omits_file_count_criterion(self) -> None:
        """Test that scaffold task without files doesn't mention file count."""
        spec = ParsedSpec(
            module_structure={
                "base_path": "src/api",
                "files": [],
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        assert len(tasks) == 1
        # Should not mention file count when files list is empty
        assert not any("module files" in ac for ac in tasks[0].acceptance_criteria)

    def test_dependency_task_truncates_long_package_list(self) -> None:
        """Test that goal truncates when more than 5 packages."""
        spec = ParsedSpec(
            dependency_changes={
                "extra_name": "all",
                "packages": [f"pkg{i}>=1.0" for i in range(8)],
                "raw": "...",
            },
        )
        tasks = generate_prerequisite_tasks(spec, _make_key_generator())

        assert len(tasks) == 1
        assert "(+3 more)" in tasks[0].goal
