"""Tests for the Recursive Validation Loop module.

This module tests the AtomicityValidator and RecursiveValidator classes
for atomicity enforcement and automatic task re-decomposition.
"""

from __future__ import annotations

import json

import pytest

from tdd_orchestrator.decomposition.config import DecompositionConfig
from tdd_orchestrator.decomposition.task_model import DecomposedTask
from tdd_orchestrator.decomposition.llm_client import MockLLMClient
from tdd_orchestrator.decomposition.validators import (
    AtomicityValidator,
    RecursiveValidator,
    ValidationResult,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def config() -> DecompositionConfig:
    """Create a standard DecompositionConfig for testing."""
    return DecompositionConfig(
        max_recursion_depth=3,
        min_tests=5,
        max_tests=20,
        max_lines=100,
        min_criteria=2,
        max_criteria=5,
        max_components=3,
    )


@pytest.fixture
def atomicity_validator(config: DecompositionConfig) -> AtomicityValidator:
    """Create an AtomicityValidator instance."""
    return AtomicityValidator(config)


@pytest.fixture
def valid_task() -> DecomposedTask:
    """Create a task that passes all atomicity constraints."""
    return DecomposedTask(
        task_key="SF-TDD-01-01",
        title="Implement Config Loader",
        goal="Load YAML configuration files",
        estimated_tests=10,
        estimated_lines=50,
        test_file="tests/unit/config/test_loader.py",
        impl_file="src/config/loader.py",
        components=["ConfigLoader"],
        acceptance_criteria=[
            "Loading valid YAML returns config object",
            "Loading invalid YAML raises error",
            "Missing file raises ConfigNotFoundError",
        ],
        phase=1,
        sequence=1,
    )


@pytest.fixture
def oversized_task() -> DecomposedTask:
    """Create a task that violates multiple atomicity constraints."""
    return DecomposedTask(
        task_key="SF-TDD-02-01",
        title="Implement Full API Client",
        goal="Create complete API client with all features",
        estimated_tests=30,  # Too many tests
        estimated_lines=150,  # Too many lines
        test_file="tests/unit/api/test_client.py",
        impl_file="src/api/client.py",
        components=["APIClient", "AuthHandler", "RequestBuilder", "ResponseParser"],  # Too many
        acceptance_criteria=[
            "AC 1",
            "AC 2",
            "AC 3",
        ],
        phase=2,
        sequence=1,
    )


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """Create a mock LLM client with predefined split responses."""
    split_response = json.dumps(
        [
            {
                "title": "Implement API Request Builder",
                "goal": "Build HTTP requests",
                "estimated_tests": 8,
                "estimated_lines": 40,
                "components": ["RequestBuilder"],
                "test_file": "tests/unit/api/test_request.py",
                "impl_file": "src/api/request.py",
            },
            {
                "title": "Implement API Response Parser",
                "goal": "Parse API responses",
                "estimated_tests": 8,
                "estimated_lines": 40,
                "components": ["ResponseParser"],
                "test_file": "tests/unit/api/test_response.py",
                "impl_file": "src/api/response.py",
            },
        ]
    )
    return MockLLMClient(default_response=split_response)


# =============================================================================
# Test AtomicityValidator
# =============================================================================


class TestAtomicityValidatorPassingTasks:
    """Tests for AtomicityValidator with valid tasks."""

    def test_validates_passing_task(
        self, atomicity_validator: AtomicityValidator, valid_task: DecomposedTask
    ) -> None:
        """Test that a valid task passes validation."""
        result = atomicity_validator.validate(valid_task)

        assert result.is_valid is True
        assert result.violations == []
        assert result.task == valid_task

    def test_validates_task_at_min_bounds(self, atomicity_validator: AtomicityValidator) -> None:
        """Test task at minimum bounds passes."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Min Bounds Task",
            goal="Test",
            estimated_tests=5,  # At minimum
            estimated_lines=1,  # Well under max
            test_file="test.py",
            impl_file="impl.py",
            components=["One"],
            acceptance_criteria=["AC1", "AC2"],  # At minimum
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is True

    def test_validates_task_at_max_bounds(self, atomicity_validator: AtomicityValidator) -> None:
        """Test task at maximum bounds passes."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Max Bounds Task",
            goal="Test",
            estimated_tests=20,  # At maximum
            estimated_lines=100,  # At maximum
            test_file="test.py",
            impl_file="impl.py",
            components=["One", "Two", "Three"],  # At maximum
            acceptance_criteria=["AC1", "AC2", "AC3", "AC4", "AC5"],  # At maximum
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is True


class TestAtomicityValidatorDetectingViolations:
    """Tests for AtomicityValidator detecting constraint violations."""

    def test_detects_too_many_tests(self, atomicity_validator: AtomicityValidator) -> None:
        """Test detection of too many tests."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Too Many Tests",
            goal="Test",
            estimated_tests=25,  # Over 20 max
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is False
        assert len(result.violations) == 1
        assert "Too many tests: 25 > 20" in result.violations[0]

    def test_detects_too_few_tests(self, atomicity_validator: AtomicityValidator) -> None:
        """Test detection of too few tests."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Too Few Tests",
            goal="Test",
            estimated_tests=3,  # Under 5 min
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is False
        assert len(result.violations) == 1
        assert "Too few tests: 3 < 5" in result.violations[0]

    def test_detects_too_many_lines(self, atomicity_validator: AtomicityValidator) -> None:
        """Test detection of too many lines."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Too Many Lines",
            goal="Test",
            estimated_tests=10,
            estimated_lines=150,  # Over 100 max
            test_file="test.py",
            impl_file="impl.py",
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is False
        assert any("Too many lines" in v for v in result.violations)

    def test_detects_too_many_components(self, atomicity_validator: AtomicityValidator) -> None:
        """Test detection of too many components."""
        task = DecomposedTask(
            task_key="TEST-01",
            title="Too Many Components",
            goal="Test",
            estimated_tests=10,
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
            components=["A", "B", "C", "D", "E"],  # Over 3 max
        )

        result = atomicity_validator.validate(task)

        assert result.is_valid is False
        assert any("Too many components" in v for v in result.violations)

    def test_detects_multiple_violations(
        self, atomicity_validator: AtomicityValidator, oversized_task: DecomposedTask
    ) -> None:
        """Test detection of multiple simultaneous violations."""
        result = atomicity_validator.validate(oversized_task)

        assert result.is_valid is False
        assert len(result.violations) >= 3  # tests, lines, components


class TestAtomicityValidatorValidateAll:
    """Tests for AtomicityValidator.validate_all method."""

    def test_validate_all_returns_results_for_each_task(
        self, atomicity_validator: AtomicityValidator, valid_task: DecomposedTask
    ) -> None:
        """Test validate_all returns one result per task."""
        tasks = [valid_task, valid_task, valid_task]

        results = atomicity_validator.validate_all(tasks)

        assert len(results) == 3
        assert all(isinstance(r, ValidationResult) for r in results)


# =============================================================================
# Test RecursiveValidator
# =============================================================================


class TestRecursiveValidatorPassingTasks:
    """Tests for RecursiveValidator with valid tasks."""

    @pytest.mark.asyncio
    async def test_passes_valid_tasks_through(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
        valid_task: DecomposedTask,
    ) -> None:
        """Test that valid tasks pass through without modification."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        tasks, stats = await validator.validate_and_refine([valid_task])

        assert len(tasks) == 1
        assert tasks[0].task_key == valid_task.task_key
        assert stats.input_tasks == 1
        assert stats.output_tasks == 1
        assert stats.passed_validation == 1
        assert stats.split_count == 0


class TestRecursiveValidatorSplittingTasks:
    """Tests for RecursiveValidator task splitting."""

    @pytest.mark.asyncio
    async def test_splits_oversized_tasks(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
        oversized_task: DecomposedTask,
    ) -> None:
        """Test that oversized tasks are split into subtasks."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        tasks, stats = await validator.validate_and_refine([oversized_task])

        # Should have more tasks after splitting
        assert len(tasks) >= 2
        assert stats.split_count >= 1

    @pytest.mark.asyncio
    async def test_tracks_lineage_on_split(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
        oversized_task: DecomposedTask,
    ) -> None:
        """Test that split tasks have correct parent_task_key and recursion_depth."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        tasks, stats = await validator.validate_and_refine([oversized_task])

        # Find subtasks (those with parent_task_key set)
        subtasks = [t for t in tasks if t.parent_task_key is not None]

        for subtask in subtasks:
            assert subtask.parent_task_key == oversized_task.task_key
            assert subtask.recursion_depth == oversized_task.recursion_depth + 1


class TestRecursiveValidatorMaxDepth:
    """Tests for RecursiveValidator max depth handling."""

    @pytest.mark.asyncio
    async def test_respects_max_depth(
        self,
        atomicity_validator: AtomicityValidator,
        config: DecompositionConfig,
    ) -> None:
        """Test that tasks at max depth are flagged, not split."""
        # Create mock that always returns oversized tasks
        bad_response = json.dumps(
            [
                {
                    "title": "Still Oversized",
                    "goal": "Test",
                    "estimated_tests": 30,  # Still too many
                    "estimated_lines": 150,
                    "components": ["A", "B", "C", "D"],
                }
            ]
        )
        mock_client = MockLLMClient(default_response=bad_response)

        # Use config with max_depth=1
        shallow_config = DecompositionConfig(max_recursion_depth=1)
        shallow_validator = AtomicityValidator(shallow_config)

        validator = RecursiveValidator(shallow_validator, mock_client, shallow_config)

        oversized = DecomposedTask(
            task_key="BIG-01",
            title="Oversized",
            goal="Test",
            estimated_tests=30,
            estimated_lines=150,
            test_file="test.py",
            impl_file="impl.py",
            components=["A", "B", "C", "D"],
        )

        tasks, stats = await validator.validate_and_refine([oversized])

        # Should have flagged tasks since we can't fix them
        assert stats.flagged_for_review >= 1

    @pytest.mark.asyncio
    async def test_tracks_max_depth_in_stats(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
        oversized_task: DecomposedTask,
    ) -> None:
        """Test that max_depth_reached is tracked in stats."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        tasks, stats = await validator.validate_and_refine([oversized_task])

        # Should have reached at least depth 1 due to splits
        assert stats.max_depth_reached >= 1


class TestRecursiveValidationStats:
    """Tests for RecursiveValidationStats tracking."""

    @pytest.mark.asyncio
    async def test_stats_track_all_metrics(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
        valid_task: DecomposedTask,
        oversized_task: DecomposedTask,
    ) -> None:
        """Test that all stats are tracked correctly."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        # Mix of valid and oversized tasks
        tasks, stats = await validator.validate_and_refine([valid_task, oversized_task])

        assert stats.input_tasks == 2
        assert stats.output_tasks >= 2  # At least original valid + splits
        assert stats.passed_validation >= 1  # At least the valid task


class TestSplitStrategySelection:
    """Tests for split strategy selection."""

    def test_selects_by_component_strategy(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test by_component strategy selection."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        task = DecomposedTask(
            task_key="TEST-01",
            title="Test",
            goal="Test",
            estimated_tests=10,
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
            components=["A", "B", "C", "D", "E"],
        )

        violations = ["Too many components: 5 > 3 maximum"]
        strategy = validator._select_split_strategy(task, violations)

        assert strategy == "by_component"

    def test_selects_by_tests_strategy(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test by_tests strategy selection."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        task = DecomposedTask(
            task_key="TEST-01",
            title="Test",
            goal="Test",
            estimated_tests=30,
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
        )

        violations = ["Too many tests: 30 > 20 maximum"]
        strategy = validator._select_split_strategy(task, violations)

        assert strategy == "by_tests"

    def test_selects_by_size_strategy(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test by_size strategy selection."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        task = DecomposedTask(
            task_key="TEST-01",
            title="Test",
            goal="Test",
            estimated_tests=10,
            estimated_lines=150,
            test_file="test.py",
            impl_file="impl.py",
        )

        violations = ["Too many lines: 150 > 100 maximum"]
        strategy = validator._select_split_strategy(task, violations)

        assert strategy == "by_size"

    def test_selects_balanced_strategy_as_default(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test balanced strategy as default."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        task = DecomposedTask(
            task_key="TEST-01",
            title="Test",
            goal="Test",
            estimated_tests=10,
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
        )

        violations = ["Some other issue"]
        strategy = validator._select_split_strategy(task, violations)

        assert strategy == "balanced"


class TestSubtaskKeyGeneration:
    """Tests for subtask key suffix generation."""

    def test_generates_letter_suffixes(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test that subtask keys get A, B, C suffixes."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        parent_key = "SF-TDD-01-01"

        suffix_a = validator._get_subtask_suffix(parent_key)
        suffix_b = validator._get_subtask_suffix(parent_key)
        suffix_c = validator._get_subtask_suffix(parent_key)

        assert suffix_a == "A"
        assert suffix_b == "B"
        assert suffix_c == "C"

    def test_reset_counters_clears_state(
        self,
        atomicity_validator: AtomicityValidator,
        mock_llm_client: MockLLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Test that reset_counters clears suffix tracking."""
        validator = RecursiveValidator(atomicity_validator, mock_llm_client, config)

        parent_key = "SF-TDD-01-01"

        # Generate some suffixes
        validator._get_subtask_suffix(parent_key)
        validator._get_subtask_suffix(parent_key)

        # Reset
        validator.reset_counters()

        # Should start over at A
        suffix = validator._get_subtask_suffix(parent_key)
        assert suffix == "A"
