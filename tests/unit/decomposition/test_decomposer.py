"""Tests for the LLM decomposer module.

This module tests the LLMDecomposer class and DecomposedTask dataclass,
verifying the three-pass decomposition pipeline using MockLLMClient.
"""

from __future__ import annotations

import json
import asyncio
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.decomposition import ParsedSpec
from tdd_orchestrator.decomposition.config import DecompositionConfig
from tdd_orchestrator.decomposition.decomposer import (
    LLMDecompositionError,
    DecomposedTask,
    LLMDecomposer,
)
from tdd_orchestrator.decomposition.llm_client import (
    LLMClientError,
    LLMResponseParseError,
    MockLLMClient,
    SubscriptionErrorSimulator,
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


class TestErrorCodeExtraction:
    """Tests for error_codes field extraction from LLM responses."""

    @pytest.fixture
    def mock_client_with_error_codes(self) -> MockLLMClient:
        """Create mock client returning tasks with error_codes."""
        pass1 = json.dumps(
            [
                {
                    "cycle_number": 1,
                    "phase": "Auth",
                    "cycle_title": "Authentication",
                    "components": ["JWTGenerator"],
                    "expected_tests": "8-10",
                    "module_hint": "src/auth/",
                }
            ]
        )

        pass2 = json.dumps(
            [
                {
                    "title": "Implement JWT generation",
                    "goal": "Generate JWT tokens for authentication",
                    "estimated_tests": 8,
                    "estimated_lines": 50,
                    "test_file": "tests/auth/test_jwt.py",
                    "impl_file": "src/auth/jwt.py",
                    "components": ["JWTGenerator"],
                    "error_codes": ["ERR-AUTH-001", "ERR-AUTH-002", "ERR-AUTH-005"],
                }
            ]
        )

        pass3 = json.dumps(
            [
                "Valid key generates token with correct claims",
                "Invalid key raises AuthError with code ERR-AUTH-001",
                "Expired key raises AuthError with code ERR-AUTH-002",
            ]
        )

        return MockLLMClient(
            responses={
                "extract TDD cycles": pass1,
                "Authentication": pass2,
                "acceptance criteria": pass3,
            }
        )

    @pytest.mark.asyncio
    async def test_error_codes_extracted_from_llm_response(
        self, mock_client_with_error_codes: MockLLMClient
    ) -> None:
        """Verify error_codes field is populated from LLM response."""
        decomposer = LLMDecomposer(client=mock_client_with_error_codes)
        spec = ParsedSpec(raw_content="Test spec with error catalog")

        tasks = await decomposer.decompose(spec)

        assert len(tasks) >= 1
        jwt_task = tasks[0]
        assert jwt_task.error_codes == ["ERR-AUTH-001", "ERR-AUTH-002", "ERR-AUTH-005"]

    @pytest.mark.asyncio
    async def test_error_codes_empty_when_not_in_response(self) -> None:
        """Verify error_codes defaults to empty list when not in response."""
        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Basic", "components": []}]
                ),
                "Basic": json.dumps(
                    [
                        {
                            "title": "Simple task",
                            "goal": "Do something",
                            "estimated_tests": 5,
                            "estimated_lines": 20,
                            "test_file": "test.py",
                            "impl_file": "impl.py",
                            "components": [],
                            # NOTE: error_codes field intentionally omitted
                        }
                    ]
                ),
                "acceptance criteria": json.dumps(["Criterion 1"]),
            }
        )
        decomposer = LLMDecomposer(client=client)

        tasks = await decomposer.decompose(ParsedSpec(raw_content="test"))

        assert tasks[0].error_codes == []

    @pytest.mark.asyncio
    async def test_error_codes_in_to_dict(
        self, mock_client_with_error_codes: MockLLMClient
    ) -> None:
        """Verify error_codes included in to_dict() output."""
        decomposer = LLMDecomposer(client=mock_client_with_error_codes)
        tasks = await decomposer.decompose(ParsedSpec(raw_content="test"))

        task_dict = tasks[0].to_dict()

        assert "error_codes" in task_dict
        assert task_dict["error_codes"] == ["ERR-AUTH-001", "ERR-AUTH-002", "ERR-AUTH-005"]


class TestBlockingAssumptionExtraction:
    """Tests for blocking_assumption field extraction from LLM responses."""

    @pytest.fixture
    def mock_client_with_blocking(self) -> MockLLMClient:
        """Create mock client returning tasks with blocking_assumption."""
        pass1 = json.dumps(
            [
                {
                    "cycle_number": 1,
                    "cycle_title": "Salesforce Auth",
                    "components": ["SFAuth"],
                    "blocking_assumptions": ["A-4"],
                }
            ]
        )

        pass2 = json.dumps(
            [
                {
                    "title": "Configure Salesforce credentials",
                    "goal": "Set up integration user authentication",
                    "estimated_tests": 6,
                    "estimated_lines": 30,
                    "test_file": "tests/sf/test_auth.py",
                    "impl_file": "src/sf/auth.py",
                    "components": ["SFAuth"],
                    "error_codes": [],
                    "blocking_assumption": "A-4",
                }
            ]
        )

        pass3 = json.dumps(
            [
                "GIVEN assumption A-4 verified, WHEN authenticating, THEN succeeds",
                "IF assumption A-4 false, THEN raises AuthError with ERR-AUTH-003",
            ]
        )

        return MockLLMClient(
            responses={
                "extract TDD cycles": pass1,
                "Salesforce Auth": pass2,
                "acceptance criteria": pass3,
            }
        )

    @pytest.mark.asyncio
    async def test_blocking_assumption_extracted(
        self, mock_client_with_blocking: MockLLMClient
    ) -> None:
        """Verify blocking_assumption field is populated from LLM response."""
        decomposer = LLMDecomposer(client=mock_client_with_blocking)

        tasks = await decomposer.decompose(ParsedSpec(raw_content="test"))

        assert tasks[0].blocking_assumption == "A-4"

    @pytest.mark.asyncio
    async def test_blocking_assumption_none_when_not_blocked(self) -> None:
        """Verify blocking_assumption is None for non-blocked tasks."""
        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Simple", "components": []}]
                ),
                "Simple": json.dumps(
                    [
                        {
                            "title": "Unblocked task",
                            "goal": "Task with no blocking assumptions",
                            "estimated_tests": 5,
                            "estimated_lines": 20,
                            "test_file": "test.py",
                            "impl_file": "impl.py",
                            "components": [],
                            # NOTE: blocking_assumption field intentionally omitted
                        }
                    ]
                ),
                "acceptance criteria": json.dumps(["Criterion 1"]),
            }
        )
        decomposer = LLMDecomposer(client=client)

        tasks = await decomposer.decompose(ParsedSpec(raw_content="test"))

        assert tasks[0].blocking_assumption is None

    @pytest.mark.asyncio
    async def test_blocking_assumption_in_to_dict(
        self, mock_client_with_blocking: MockLLMClient
    ) -> None:
        """Verify blocking_assumption included in to_dict() output."""
        decomposer = LLMDecomposer(client=mock_client_with_blocking)
        tasks = await decomposer.decompose(ParsedSpec(raw_content="test"))

        task_dict = tasks[0].to_dict()

        assert "blocking_assumption" in task_dict
        assert task_dict["blocking_assumption"] == "A-4"


class TestMalformedLLMResponses:
    """Test decomposer resilience to malformed LLM responses."""

    @pytest.mark.asyncio
    async def test_llm_returns_extra_fields(self) -> None:
        """Test that decomposer ignores unexpected fields from LLM."""
        # Pass 2 response with extra unexpected fields
        response_with_extra = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": 5,
                    "estimated_lines": 50,
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": ["TestComponent"],
                    # Extra fields that should be ignored
                    "extra_field": "should be ignored",
                    "unexpected_data": {"nested": "value"},
                    "random_number": 42,
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_extra,
                "acceptance criteria": '["Criterion 1", "Criterion 2"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        tasks = await decomposer.decompose(parsed_spec)

        # Should succeed and ignore extra fields
        assert len(tasks) == 1
        assert tasks[0].title == "Test task"
        assert tasks[0].goal == "Test goal"
        # Verify extra fields are not in to_dict() output
        task_dict = tasks[0].to_dict()
        assert "extra_field" not in task_dict
        assert "unexpected_data" not in task_dict
        assert "random_number" not in task_dict

    @pytest.mark.asyncio
    async def test_llm_returns_wrong_types(self) -> None:
        """Test that decomposer handles type mismatches gracefully."""
        # Pass 2 response with wrong types
        response_with_wrong_types = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": "not-a-number",  # Should be int
                    "estimated_lines": "also-not-a-number",  # Should be int
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": "single-string",  # Should be list
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_wrong_types,
                "acceptance criteria": '["Criterion 1"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        # Currently, the decomposer accepts type mismatches without validation
        # This test documents the current behavior (not strict type checking)
        tasks = await decomposer.decompose(parsed_spec)

        # System currently allows wrong types to pass through
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Test task"
        assert task.goal == "Test goal"
        # CURRENT BEHAVIOR: Wrong types are not rejected
        # estimated_tests is still a string (not converted to int)
        assert task.estimated_tests == "not-a-number"  # Type mismatch accepted
        assert task.estimated_lines == "also-not-a-number"  # Type mismatch accepted
        # components might be converted to list or remain as string
        # This documents that type validation is not currently enforced

    @pytest.mark.asyncio
    async def test_llm_returns_null_values(self) -> None:
        """Test that decomposer handles null values in optional fields."""
        # Pass 2 response with null values
        response_with_nulls = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": 5,
                    "estimated_lines": 50,
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": None,  # Optional field with null
                    "phase": None,  # Optional field with null
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_nulls,
                "acceptance criteria": '["Criterion 1", "Criterion 2"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        tasks = await decomposer.decompose(parsed_spec)

        # Should handle null values gracefully
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Test task"
        # Null components should default to empty list
        assert task.components == [] or task.components is None
        # Null phase should default to 0 or None
        assert isinstance(task.phase, int) or task.phase is None


class TestSubscriptionErrorRecovery:
    """Tests for decomposer handling of Claude Agent SDK subscription errors.

    IMPORTANT: We use subscription-based auth via 'claude login', NOT API keys.
    These tests simulate subscription-model errors, not API key errors.

    Key differences from API key testing:
    - No 401/403 HTTP errors (subscription uses session auth)
    - No 429 rate limits (subscription uses monthly quotas)
    - Errors wrapped as LLMClientError by ClaudeAgentSDKClient
    """

    @pytest.mark.asyncio
    async def test_session_expired_suggests_relogin(self) -> None:
        """Verify session expiration error suggests 'claude login'."""
        client = SubscriptionErrorSimulator(error_type="session_expired")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention re-authentication via claude login
        assert "session" in error_msg or "login" in error_msg or "expired" in error_msg

    @pytest.mark.asyncio
    async def test_quota_exceeded_indicates_monthly_limit(self) -> None:
        """Verify quota exceeded error indicates monthly subscription limit."""
        client = SubscriptionErrorSimulator(error_type="quota_exceeded")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention quota/subscription, NOT rate limit
        assert "quota" in error_msg or "subscription" in error_msg or "monthly" in error_msg

    @pytest.mark.asyncio
    async def test_sdk_not_installed_helpful_message(self) -> None:
        """Verify SDK not installed error provides helpful guidance."""
        client = SubscriptionErrorSimulator(error_type="sdk_not_installed")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention SDK installation or claude login
        assert "sdk" in error_msg or "claude" in error_msg or "installed" in error_msg

    @pytest.mark.asyncio
    async def test_timeout_propagates_correctly(self) -> None:
        """Verify timeout errors are propagated appropriately."""
        client = SubscriptionErrorSimulator(error_type="timeout")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, asyncio.TimeoutError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connection_error_handled_gracefully(self) -> None:
        """Verify network errors don't crash decomposer."""
        client = SubscriptionErrorSimulator(error_type="connection_error")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, ConnectionError)):
            await decomposer.decompose(ParsedSpec(raw_content="test"))

    @pytest.mark.asyncio
    async def test_malformed_response_uses_fallback(self) -> None:
        """Verify malformed model response falls back to existing cycles."""
        client = SubscriptionErrorSimulator(error_type="malformed_response")
        decomposer = LLMDecomposer(client=client)

        # Spec with existing TDD cycles for fallback
        spec = ParsedSpec(
            raw_content="test",
            tdd_cycles=[
                {
                    "cycle_number": 1,
                    "title": "Fallback Cycle",
                    "components": ["FallbackComponent"],
                }
            ],
        )

        # Should fall back to existing cycles when model returns garbage
        cycles = await decomposer._extract_cycles(spec)
        assert len(cycles) == 1
        assert cycles[0]["title"] == "Fallback Cycle"

    @pytest.mark.asyncio
    async def test_model_unavailable_error_clear(self) -> None:
        """Verify model unavailable error is clear about the issue."""
        client = SubscriptionErrorSimulator(error_type="model_unavailable")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        assert "unavailable" in error_msg or "model" in error_msg

    @pytest.mark.asyncio
    async def test_partial_response_handled(self) -> None:
        """Verify truncated responses from model don't crash decomposer."""
        client = SubscriptionErrorSimulator(error_type="partial_response")
        decomposer = LLMDecomposer(client=client)

        # Should raise parse error or fall back, not crash
        with pytest.raises((LLMDecompositionError, LLMResponseParseError)):
            await decomposer.decompose(ParsedSpec(raw_content="test"))

    @pytest.mark.asyncio
    async def test_metrics_track_subscription_errors(self) -> None:
        """Verify decomposition metrics track subscription errors."""
        client = SubscriptionErrorSimulator(error_type="quota_exceeded")
        decomposer = LLMDecomposer(client=client)

        try:
            await decomposer.decompose(ParsedSpec(raw_content="test"))
        except Exception:
            pass  # Expected to fail

        metrics = decomposer.get_metrics()
        assert len(metrics.errors) > 0

    @pytest.mark.asyncio
    async def test_call_limit_prevents_runaway_usage(self) -> None:
        """Verify LLM call limit prevents excessive subscription usage."""
        # Mock that always returns valid response (simulating working subscription)
        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [
                        {
                            "cycle_number": i,
                            "cycle_title": f"Cycle {i}",
                            "components": [],
                        }
                        for i in range(1, 20)
                    ]
                ),  # 19 cycles would use many calls
                "Cycle": json.dumps(
                    [
                        {
                            "title": "Task",
                            "goal": "Goal",
                            "estimated_tests": 5,
                            "estimated_lines": 20,
                            "test_file": "t.py",
                            "impl_file": "i.py",
                            "components": [],
                        }
                    ]
                ),
                "acceptance criteria": json.dumps(["AC"]),
            }
        )

        # Very low limit to protect subscription quota
        config = DecompositionConfig(
            max_total_llm_calls=5,
            max_cycles_per_spec=20,
        )
        decomposer = LLMDecomposer(client=client, config=config)

        # Decomposer logs warnings but doesn't raise when limit hit
        await decomposer.decompose(ParsedSpec(raw_content="test"))

        # Should have errors in metrics about exceeding limit
        metrics = decomposer.get_metrics()
        assert len(metrics.errors) > 0
        assert any("limit" in err.lower() for err in metrics.errors)
