"""Tests for optional field extraction from LLM decomposition responses.

Tests that error_codes and blocking_assumption fields are correctly
extracted from LLM responses and included in DecomposedTask output.
"""

from __future__ import annotations

import json

import pytest

from tdd_orchestrator.decomposition import ParsedSpec
from tdd_orchestrator.decomposition.decomposer import (
    LLMDecomposer,
)
from tdd_orchestrator.decomposition.llm_client import (
    MockLLMClient,
)


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
