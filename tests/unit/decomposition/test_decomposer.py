"""Tests for the LLM decomposer module.

This module tests the LLMDecomposer class and DecomposedTask dataclass,
verifying the three-pass decomposition pipeline using MockLLMClient.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.decomposition import ParsedSpec
from tdd_orchestrator.decomposition.config import DecompositionConfig
from tdd_orchestrator.decomposition.decomposer import (
    DecomposedTask,
    LLMDecomposer,
)
from tdd_orchestrator.decomposition.llm_client import (
    LLMResponseParseError,
    MockLLMClient,
    parse_json_response,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Mock Response Fixtures
# =============================================================================


MOCK_PASS1_RESPONSE = json.dumps(
    [
        {
            "cycle_number": 1,
            "phase": "Foundation",
            "cycle_title": "Configuration Setup",
            "components": ["ConfigLoader", "Validator"],
            "expected_tests": "8-10",
            "module_hint": "src/config/",
        },
        {
            "cycle_number": 2,
            "phase": "Core",
            "cycle_title": "Data Processing",
            "components": ["DataProcessor"],
            "expected_tests": "10-12",
            "module_hint": "src/core/",
        },
    ]
)


MOCK_PASS2_RESPONSE = json.dumps(
    [
        {
            "title": "Implement config file loading",
            "goal": "Load YAML configuration files",
            "estimated_tests": 8,
            "estimated_lines": 45,
            "test_file": "tests/unit/config/test_loader.py",
            "impl_file": "src/config/loader.py",
            "components": ["ConfigLoader"],
        },
        {
            "title": "Add config validation",
            "goal": "Validate configuration schema",
            "estimated_tests": 6,
            "estimated_lines": 35,
            "test_file": "tests/unit/config/test_validator.py",
            "impl_file": "src/config/validator.py",
            "components": ["Validator"],
        },
    ]
)


MOCK_PASS3_RESPONSE = json.dumps(
    [
        "Loading a valid YAML file returns a config object",
        "Loading non-existent file raises ConfigNotFoundError",
        "Invalid YAML raises ConfigParseError with line number",
        "Config values accessible via dot notation",
    ]
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_client() -> MockLLMClient:
    """Create a mock LLM client with predefined responses."""
    return MockLLMClient(
        responses={
            # Pass 1: Matches "extract TDD cycles" in PHASE_EXTRACTION_PROMPT
            "extract TDD cycles": MOCK_PASS1_RESPONSE,
            # Pass 2: Matches "TDD task breakdown expert" in TASK_BREAKDOWN_PROMPT
            "TDD task breakdown expert": MOCK_PASS2_RESPONSE,
            # Pass 3: Matches "acceptance criteria" in AC_GENERATION_PROMPT
            "acceptance criteria": MOCK_PASS3_RESPONSE,
        }
    )


@pytest.fixture
def config() -> DecompositionConfig:
    """Create a test decomposition config."""
    return DecompositionConfig(
        max_cycles_per_spec=5,
        max_tasks_per_cycle=3,
        min_criteria=2,
        max_criteria=5,
    )


@pytest.fixture
def parsed_spec() -> ParsedSpec:
    """Create a minimal parsed spec for testing.

    The fixture includes 2 pre-extracted TDD cycles to verify the decomposer
    uses them directly instead of calling the LLM.
    """
    return ParsedSpec(
        functional_requirements=[
            {"id": "FR-1", "title": "User Authentication", "content": "..."},
            {"id": "FR-2", "title": "Data Processing", "content": "..."},
        ],
        acceptance_criteria=[
            {
                "id": "AC-1",
                "title": "Login Success",
                "gherkin": "GIVEN a valid user\nWHEN they login\nTHEN they see dashboard",
            }
        ],
        tdd_cycles=[
            {
                "cycle_number": 1,
                "cycle_title": "Configuration Setup",
                "title": "Configuration Setup",
                "phase": "Foundation",
                "components": ["ConfigLoader", "Validator"],
                "expected_tests": "8-10",
                "module_hint": "src/config/",
            },
            {
                "cycle_number": 2,
                "cycle_title": "Data Processing",
                "title": "Data Processing",
                "phase": "Core",
                "components": ["DataProcessor"],
                "expected_tests": "10-12",
                "module_hint": "src/core/",
            },
        ],
        raw_content="Sample PRD content for testing",
    )


@pytest.fixture
def decomposer(mock_client: MockLLMClient, config: DecompositionConfig) -> LLMDecomposer:
    """Create an LLMDecomposer with mock client."""
    return LLMDecomposer(client=mock_client, config=config)


# =============================================================================
# Test Classes
# =============================================================================


class TestDecomposedTask:
    """Tests for the DecomposedTask dataclass."""

    def test_create_decomposed_task_with_defaults(self) -> None:
        """Test creating a DecomposedTask with minimal fields."""
        task = DecomposedTask(
            task_key="TASK-001",
            title="Test Task",
            goal="Do something",
            estimated_tests=5,
            estimated_lines=50,
            test_file="test.py",
            impl_file="impl.py",
        )

        assert task.task_key == "TASK-001"
        assert task.title == "Test Task"
        assert task.components == []
        assert task.acceptance_criteria == []
        assert task.phase == 0
        assert task.sequence == 0
        assert task.parent_task_key is None
        assert task.recursion_depth == 0

    def test_decomposed_task_to_dict(self) -> None:
        """Test DecomposedTask.to_dict() conversion."""
        task = DecomposedTask(
            task_key="TASK-002",
            title="Convert Task",
            goal="Test dict conversion",
            estimated_tests=8,
            estimated_lines=60,
            test_file="tests/test_convert.py",
            impl_file="src/convert.py",
            components=["Converter"],
            acceptance_criteria=["Must convert", "Must validate"],
            phase=1,
            sequence=2,
        )

        result = task.to_dict()

        assert result["task_key"] == "TASK-002"
        assert result["title"] == "Convert Task"
        assert result["components"] == ["Converter"]
        assert result["acceptance_criteria"] == ["Must convert", "Must validate"]
        assert result["phase"] == 1
        assert result["sequence"] == 2


class TestMockLLMClient:
    """Tests for the MockLLMClient."""

    @pytest.mark.asyncio
    async def test_mock_client_returns_matched_response(self) -> None:
        """Test that mock client returns response matching prompt substring."""
        client = MockLLMClient(responses={"hello": "world", "test": "result"})

        response = await client.send_message("Say hello to me")
        assert response == "world"

        response = await client.send_message("This is a test")
        assert response == "result"

    @pytest.mark.asyncio
    async def test_mock_client_returns_default_response(self) -> None:
        """Test that mock client returns default for non-matching prompts."""
        client = MockLLMClient(
            responses={"specific": "match"}, default_response='{"default": true}'
        )

        response = await client.send_message("No matching substring here")
        assert response == '{"default": true}'

    @pytest.mark.asyncio
    async def test_mock_client_tracks_call_history(self) -> None:
        """Test that mock client tracks all calls made."""
        client = MockLLMClient()

        await client.send_message("First call")
        await client.send_message("Second call")
        await client.send_message("Third call")

        assert client.get_call_count() == 3
        assert "First call" in client.call_history
        assert "Second call" in client.call_history

    def test_mock_client_reset(self) -> None:
        """Test that reset clears call history."""
        client = MockLLMClient()
        client.call_history = ["a", "b", "c"]

        client.reset()

        assert client.get_call_count() == 0


class TestParseJsonResponse:
    """Tests for the parse_json_response utility function."""

    def test_parse_direct_json_array(self) -> None:
        """Test parsing a direct JSON array."""
        response = '[{"key": "value"}]'
        result = parse_json_response(response)
        assert result == [{"key": "value"}]

    def test_parse_json_in_code_block(self) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here is the JSON:
```json
[{"task": "test"}]
```
"""
        result = parse_json_response(response)
        assert result == [{"task": "test"}]

    def test_parse_json_in_code_block_no_language(self) -> None:
        """Test parsing JSON in code block without language specifier."""
        response = """```
{"name": "value"}
```"""
        result = parse_json_response(response)
        assert result == {"name": "value"}

    def test_parse_json_with_surrounding_text(self) -> None:
        """Test parsing JSON embedded in surrounding text."""
        response = """The cycles are: [{"cycle": 1}] and that's all."""
        result = parse_json_response(response)
        assert result == [{"cycle": 1}]

    def test_parse_json_raises_on_invalid(self) -> None:
        """Test that invalid JSON raises LLMResponseParseError."""
        response = "This is not JSON at all"
        with pytest.raises(LLMResponseParseError):
            parse_json_response(response)


class TestLLMDecomposer:
    """Tests for the LLMDecomposer class."""

    @pytest.mark.asyncio
    async def test_full_decomposition_flow(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test the complete three-pass decomposition flow."""
        tasks = await decomposer.decompose(parsed_spec)

        # Should have generated tasks from 2 cycles * 2 tasks each
        assert len(tasks) >= 2
        assert all(isinstance(t, DecomposedTask) for t in tasks)

        # Each task should have a unique key
        task_keys = [t.task_key for t in tasks]
        assert len(task_keys) == len(set(task_keys))

    @pytest.mark.asyncio
    async def test_pass1_cycle_extraction(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test Pass 1: cycle extraction from spec."""
        cycles = await decomposer._extract_cycles(parsed_spec)

        assert len(cycles) == 2
        assert cycles[0]["cycle_number"] == 1
        assert cycles[0]["cycle_title"] == "Configuration Setup"
        assert cycles[1]["cycle_number"] == 2

    @pytest.mark.asyncio
    async def test_pass2_task_breakdown(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test Pass 2: breaking a cycle into tasks."""
        cycle = {
            "cycle_number": 1,
            "cycle_title": "Test Cycle",
            "phase": "Foundation",
            "components": ["Component1"],
            "expected_tests": "8-10",
            "module_hint": "src/",
        }

        tasks = await decomposer._break_cycle(cycle, parsed_spec)

        assert len(tasks) == 2
        assert tasks[0]["title"] == "Implement config file loading"
        assert tasks[0]["phase"] == 1
        assert tasks[0]["sequence"] == 1

    @pytest.mark.asyncio
    async def test_pass3_ac_generation(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test Pass 3: generating acceptance criteria for a task."""
        task = {
            "title": "Generate AC Task",
            "goal": "Test AC generation",
            "estimated_tests": 8,
            "test_file": "test.py",
            "impl_file": "impl.py",
            "components": ["TestComponent"],
            "phase": 1,
            "sequence": 1,
        }

        decomposed = await decomposer._generate_ac(task, parsed_spec)

        assert isinstance(decomposed, DecomposedTask)
        assert len(decomposed.acceptance_criteria) >= 2
        assert "Loading a valid YAML file" in decomposed.acceptance_criteria[0]

    @pytest.mark.asyncio
    async def test_metrics_tracking(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test that decomposition metrics are tracked correctly."""
        await decomposer.decompose(parsed_spec)

        metrics = decomposer.get_metrics()

        assert metrics.pass1_cycles_extracted == 2
        assert metrics.pass2_tasks_generated >= 2
        assert metrics.total_llm_calls >= 3  # At least 1 + 2 + N calls
        assert metrics.total_duration_seconds > 0

    @pytest.mark.asyncio
    async def test_parallel_execution(self, parsed_spec: ParsedSpec) -> None:
        """Test that parallel execution makes multiple concurrent calls."""
        client = MockLLMClient(
            responses={
                "extract TDD cycles": MOCK_PASS1_RESPONSE,
                "TDD task breakdown expert": MOCK_PASS2_RESPONSE,
                "acceptance criteria": MOCK_PASS3_RESPONSE,
            }
        )
        config = DecompositionConfig(enable_parallel_calls=True)
        decomposer = LLMDecomposer(client=client, config=config)

        await decomposer.decompose(parsed_spec)

        # Should have made calls for Pass 1, Pass 2 (per cycle), Pass 3 (per task)
        assert client.get_call_count() >= 5

    @pytest.mark.asyncio
    async def test_error_handling_invalid_pass1_response(self, parsed_spec: ParsedSpec) -> None:
        """Test that decomposer uses pre-extracted cycles instead of LLM.

        When the spec has pre-extracted TDD cycles, the decomposer skips
        the LLM call entirely and uses the existing cycles.
        """
        client = MockLLMClient(default_response="not valid json at all")
        decomposer = LLMDecomposer(client=client)

        # Uses pre-extracted cycles from spec (no LLM call)
        cycles = await decomposer._extract_cycles(parsed_spec)

        # Returns the spec's existing TDD cycles
        assert len(cycles) == 2
        assert cycles[0]["cycle_title"] == "Configuration Setup"
        assert cycles[1]["cycle_title"] == "Data Processing"

    @pytest.mark.asyncio
    async def test_task_key_generation(
        self, decomposer: LLMDecomposer, parsed_spec: ParsedSpec
    ) -> None:
        """Test that task keys follow the PREFIX-TDD-PHASE-SEQ format."""
        tasks = await decomposer.decompose(parsed_spec)

        # Task keys should follow {PREFIX}-TDD-{PHASE:02d}-{SEQ:02d} format
        keys = sorted([t.task_key for t in tasks])
        # 2 cycles * 2 tasks each = 4 tasks
        # Cycle 1: TASK-TDD-01-01, TASK-TDD-01-02
        # Cycle 2: TASK-TDD-02-01, TASK-TDD-02-02
        expected = [
            "TASK-TDD-01-01",
            "TASK-TDD-01-02",
            "TASK-TDD-02-01",
            "TASK-TDD-02-02",
        ]
        assert keys == expected


class TestDecomposerEdgeCases:
    """Test edge cases for the LLMDecomposer."""

    @pytest.mark.asyncio
    async def test_empty_spec_decomposition(self) -> None:
        """Test decomposition with an empty spec."""
        client = MockLLMClient(default_response="[]")
        decomposer = LLMDecomposer(client=client)
        empty_spec = ParsedSpec()

        tasks = await decomposer.decompose(empty_spec)

        assert tasks == []

    @pytest.mark.asyncio
    async def test_config_limits_respected(self) -> None:
        """Test that config limits are respected."""
        # Response with many cycles
        many_cycles = json.dumps(
            [{"cycle_number": i, "cycle_title": f"Cycle {i}"} for i in range(10)]
        )
        client = MockLLMClient(
            responses={
                "extract TDD cycles": many_cycles,
                "Decompose this TDD cycle": MOCK_PASS2_RESPONSE,
                "acceptance criteria": MOCK_PASS3_RESPONSE,
            }
        )
        config = DecompositionConfig(max_cycles_per_spec=3, max_tasks_per_cycle=2)
        decomposer = LLMDecomposer(client=client, config=config)

        cycles = await decomposer._extract_cycles(ParsedSpec(raw_content="test"))

        assert len(cycles) == 3  # Limited by config

    @pytest.mark.asyncio
    async def test_sequential_execution_mode(self, parsed_spec: ParsedSpec) -> None:
        """Test sequential (non-parallel) execution mode."""
        client = MockLLMClient(
            responses={
                "extract TDD cycles": MOCK_PASS1_RESPONSE,
                "TDD task breakdown expert": MOCK_PASS2_RESPONSE,
                "acceptance criteria": MOCK_PASS3_RESPONSE,
            }
        )
        config = DecompositionConfig(enable_parallel_calls=False)
        decomposer = LLMDecomposer(client=client, config=config)

        tasks = await decomposer.decompose(parsed_spec)

        assert len(tasks) >= 2
        assert client.get_call_count() >= 5
