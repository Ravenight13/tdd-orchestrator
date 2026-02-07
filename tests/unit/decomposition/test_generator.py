"""Tests for the Task Generator module.

This module tests the TaskGenerator class and utility functions
for task key generation, dependency calculation, and file path generation.
"""

from __future__ import annotations

import pytest

from tdd_orchestrator.decomposition.decomposer import DecomposedTask
from tdd_orchestrator.decomposition.generator import (
    TaskGenerator,
    camel_to_snake,
    generate_file_paths,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def generator() -> TaskGenerator:
    """Create a TaskGenerator with default prefix."""
    return TaskGenerator(prefix="SF")


@pytest.fixture
def sample_tasks() -> list[DecomposedTask]:
    """Create sample tasks across multiple phases."""
    return [
        DecomposedTask(
            task_key="",  # Will be assigned by generator
            title="Config Setup",
            goal="Set up configuration",
            estimated_tests=5,
            estimated_lines=50,
            test_file="",
            impl_file="",
            components=["Config"],
            phase=0,
            sequence=1,
        ),
        DecomposedTask(
            task_key="",
            title="Auth Handler",
            goal="Implement authentication",
            estimated_tests=8,
            estimated_lines=60,
            test_file="",
            impl_file="",
            components=["AuthHandler"],
            phase=0,
            sequence=2,
        ),
        DecomposedTask(
            task_key="",
            title="API Client",
            goal="Create API client",
            estimated_tests=10,
            estimated_lines=80,
            test_file="",
            impl_file="",
            components=["APIClient"],
            phase=1,
            sequence=1,
        ),
        DecomposedTask(
            task_key="",
            title="Data Processor",
            goal="Process data",
            estimated_tests=12,
            estimated_lines=90,
            test_file="",
            impl_file="",
            components=["DataProcessor"],
            phase=2,
            sequence=1,
        ),
    ]


# =============================================================================
# Test camel_to_snake
# =============================================================================


class TestCamelToSnake:
    """Tests for the camel_to_snake utility function."""

    def test_simple_pascal_case(self) -> None:
        """Test converting simple PascalCase."""
        assert camel_to_snake("SalesforceSettings") == "salesforce_settings"

    def test_acronym_at_start(self) -> None:
        """Test converting with acronym at start."""
        assert camel_to_snake("APIClient") == "api_client"

    def test_acronym_at_end(self) -> None:
        """Test converting with acronym at end."""
        assert camel_to_snake("JWTBearer") == "jwt_bearer"

    def test_mixed_case_with_numbers(self) -> None:
        """Test converting with numbers."""
        assert camel_to_snake("OAuth2Handler") == "oauth2_handler"

    def test_simple_lowercase(self) -> None:
        """Test that lowercase strings are unchanged."""
        assert camel_to_snake("simple") == "simple"

    def test_all_uppercase(self) -> None:
        """Test all uppercase acronym."""
        assert camel_to_snake("ABC") == "abc"

    def test_empty_string(self) -> None:
        """Test empty string handling."""
        assert camel_to_snake("") == ""

    def test_single_letter(self) -> None:
        """Test single letter handling."""
        assert camel_to_snake("A") == "a"
        assert camel_to_snake("a") == "a"

    def test_camel_case(self) -> None:
        """Test camelCase (starts with lowercase)."""
        assert camel_to_snake("myVariable") == "my_variable"

    def test_multiple_acronyms(self) -> None:
        """Test multiple acronyms in sequence."""
        assert camel_to_snake("HTTPAPIClient") == "httpapi_client"


# =============================================================================
# Test generate_file_paths
# =============================================================================


class TestGenerateFilePaths:
    """Tests for the generate_file_paths utility function."""

    def test_standard_component(self) -> None:
        """Test file path generation for standard component."""
        test_file, impl_file = generate_file_paths(
            "SalesforceSettings", "backend/src/integrations/salesforce"
        )

        assert test_file == "tests/unit/salesforce/test_salesforce_settings.py"
        assert impl_file == "backend/src/integrations/salesforce/salesforce_settings.py"

    def test_with_custom_test_base(self) -> None:
        """Test with custom test base path."""
        test_file, impl_file = generate_file_paths(
            "JWTBearer", "backend/src/auth", test_base="tests/unit"
        )

        assert test_file == "tests/unit/auth/test_jwt_bearer.py"
        assert impl_file == "backend/src/auth/jwt_bearer.py"

    def test_short_module_path(self) -> None:
        """Test with short module path."""
        test_file, impl_file = generate_file_paths("Config", "src/config")

        assert test_file == "tests/unit/config/test_config.py"
        assert impl_file == "src/config/config.py"

    def test_trailing_slash_in_module_base(self) -> None:
        """Test that trailing slashes are handled correctly."""
        test_file, impl_file = generate_file_paths("Handler", "backend/src/handlers/")

        assert test_file == "tests/unit/handlers/test_handler.py"
        assert impl_file == "backend/src/handlers/handler.py"


# =============================================================================
# Test TaskGenerator
# =============================================================================


class TestTaskGeneratorInit:
    """Tests for TaskGenerator initialization."""

    def test_default_prefix(self) -> None:
        """Test default prefix is TASK."""
        generator = TaskGenerator()
        assert generator.prefix == "TASK"

    def test_custom_prefix(self) -> None:
        """Test custom prefix."""
        generator = TaskGenerator(prefix="SF")
        assert generator.prefix == "SF"


class TestTaskKeyGeneration:
    """Tests for task key generation."""

    def test_task_key_format(self, generator: TaskGenerator) -> None:
        """Test task key format: {PREFIX}-TDD-{PHASE:02d}-{SEQ:02d}."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="Test",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=1,
                sequence=2,
            )
        ]

        result = generator.generate(tasks)

        assert result[0].task_key == "SF-TDD-01-02"

    def test_multiple_phases_and_sequences(
        self, generator: TaskGenerator, sample_tasks: list[DecomposedTask]
    ) -> None:
        """Test key generation across multiple phases."""
        result = generator.generate(sample_tasks)

        expected_keys = [
            "SF-TDD-00-01",  # Phase 0, Seq 1
            "SF-TDD-00-02",  # Phase 0, Seq 2
            "SF-TDD-01-01",  # Phase 1, Seq 1
            "SF-TDD-02-01",  # Phase 2, Seq 1
        ]

        actual_keys = [t.task_key for t in result]
        assert actual_keys == expected_keys

    def test_split_task_key_generation(self, generator: TaskGenerator) -> None:
        """Test split task key generation with -A, -B suffixes."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="Parent Task",
                goal="Original task",
                estimated_tests=20,
                estimated_lines=150,
                test_file="",
                impl_file="",
                phase=3,
                sequence=2,
            ),
            DecomposedTask(
                task_key="",
                title="Split Task A",
                goal="First subtask",
                estimated_tests=8,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=3,
                sequence=2,
                parent_task_key="SF-TDD-03-02",  # Indicates this is a split
                recursion_depth=1,
            ),
            DecomposedTask(
                task_key="",
                title="Split Task B",
                goal="Second subtask",
                estimated_tests=8,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=3,
                sequence=2,
                parent_task_key="SF-TDD-03-02",
                recursion_depth=1,
            ),
        ]

        result = generator.generate(tasks)

        # First task (parent) gets standard key
        assert result[0].task_key == "SF-TDD-03-02"
        # Split tasks get suffixes
        assert result[1].task_key == "SF-TDD-03-02-A"
        assert result[2].task_key == "SF-TDD-03-02-B"


class TestDependencyCalculation:
    """Tests for dependency calculation."""

    def test_phase_zero_no_dependencies(
        self, generator: TaskGenerator, sample_tasks: list[DecomposedTask]
    ) -> None:
        """Test that Phase 0 tasks have no dependencies."""
        result = generator.generate(sample_tasks)

        # Get Phase 0 tasks
        phase_0_tasks = [t for t in result if t.phase == 0]

        for task in phase_0_tasks:
            assert task.depends_on == []

    def test_phase_n_depends_on_phase_n_minus_1(
        self, generator: TaskGenerator, sample_tasks: list[DecomposedTask]
    ) -> None:
        """Test that Phase N tasks depend on ALL Phase N-1 tasks."""
        result = generator.generate(sample_tasks)

        # Phase 1 task should depend on both Phase 0 tasks
        phase_1_task = next(t for t in result if t.phase == 1)
        assert sorted(phase_1_task.depends_on) == ["SF-TDD-00-01", "SF-TDD-00-02"]

        # Phase 2 task should depend on Phase 1 task
        phase_2_task = next(t for t in result if t.phase == 2)
        assert phase_2_task.depends_on == ["SF-TDD-01-01"]

    def test_within_phase_no_cross_dependencies(self, generator: TaskGenerator) -> None:
        """Test that tasks within same phase have no cross-dependencies."""
        tasks = [
            DecomposedTask(
                task_key="",
                title=f"Task {i}",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=1,
                sequence=i,
            )
            for i in range(1, 4)
        ]

        result = generator.generate(tasks)

        # All tasks in same phase should have identical dependencies
        # (all depend on Phase 0, which is empty here)
        deps = [set(t.depends_on) for t in result]
        assert all(d == deps[0] for d in deps)


class TestGeneratorEdgeCases:
    """Tests for edge cases in TaskGenerator."""

    def test_empty_task_list(self, generator: TaskGenerator) -> None:
        """Test handling of empty task list."""
        result = generator.generate([])
        assert result == []

    def test_single_task(self, generator: TaskGenerator) -> None:
        """Test handling of single task."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="Only Task",
                goal="Single task",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=0,
                sequence=1,
            )
        ]

        result = generator.generate(tasks)

        assert len(result) == 1
        assert result[0].task_key == "SF-TDD-00-01"
        assert result[0].depends_on == []

    def test_single_phase_multiple_tasks(self, generator: TaskGenerator) -> None:
        """Test multiple tasks in single phase."""
        tasks = [
            DecomposedTask(
                task_key="",
                title=f"Task {i}",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=0,
                sequence=i,
            )
            for i in range(1, 5)
        ]

        result = generator.generate(tasks)

        # All tasks should have Phase 0, no dependencies
        assert len(result) == 4
        assert all(t.depends_on == [] for t in result)
        assert [t.task_key for t in result] == [
            "SF-TDD-00-01",
            "SF-TDD-00-02",
            "SF-TDD-00-03",
            "SF-TDD-00-04",
        ]

    def test_unsorted_input_is_sorted(self, generator: TaskGenerator) -> None:
        """Test that unsorted input is properly sorted."""
        # Tasks in reverse order
        tasks = [
            DecomposedTask(
                task_key="",
                title="Phase 2",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=2,
                sequence=1,
            ),
            DecomposedTask(
                task_key="",
                title="Phase 0",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=0,
                sequence=1,
            ),
            DecomposedTask(
                task_key="",
                title="Phase 1",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                phase=1,
                sequence=1,
            ),
        ]

        result = generator.generate(tasks)

        # Should be sorted by phase
        phases = [t.phase for t in result]
        assert phases == [0, 1, 2]

    def test_original_tasks_not_modified(
        self, generator: TaskGenerator, sample_tasks: list[DecomposedTask]
    ) -> None:
        """Test that original tasks are not modified (immutability)."""
        original_keys = [t.task_key for t in sample_tasks]
        original_deps = [t.depends_on.copy() for t in sample_tasks]

        generator.generate(sample_tasks)

        # Original tasks should be unchanged
        assert [t.task_key for t in sample_tasks] == original_keys
        assert [t.depends_on for t in sample_tasks] == original_deps


class TestGenerateWithFilePaths:
    """Tests for generate_with_file_paths method."""

    def test_fills_missing_file_paths(self, generator: TaskGenerator) -> None:
        """Test that missing file paths are filled."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="SalesforceClient",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                components=["SalesforceClient"],
                phase=0,
                sequence=1,
            )
        ]

        result = generator.generate_with_file_paths(tasks, "backend/src/integrations/salesforce")

        assert result[0].test_file == "tests/unit/salesforce/test_salesforce_client.py"
        assert result[0].impl_file == "backend/src/integrations/salesforce/salesforce_client.py"

    def test_preserves_existing_file_paths(self, generator: TaskGenerator) -> None:
        """Test that existing file paths are preserved."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="Test",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="custom/test.py",
                impl_file="custom/impl.py",
                phase=0,
                sequence=1,
            )
        ]

        result = generator.generate_with_file_paths(tasks, "backend/src/module")

        assert result[0].test_file == "custom/test.py"
        assert result[0].impl_file == "custom/impl.py"

    def test_uses_title_when_no_components(self, generator: TaskGenerator) -> None:
        """Test fallback to title when no components."""
        tasks = [
            DecomposedTask(
                task_key="",
                title="DataHandler",
                goal="Test",
                estimated_tests=5,
                estimated_lines=50,
                test_file="",
                impl_file="",
                components=[],  # No components
                phase=0,
                sequence=1,
            )
        ]

        result = generator.generate_with_file_paths(tasks, "backend/src/handlers")

        assert "data_handler" in result[0].test_file
        assert "data_handler" in result[0].impl_file
