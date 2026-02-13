"""Regression tests for integration-boundary detection in decomposition prompts.

Verifies that TASK_BREAKDOWN_PROMPT and AC_GENERATION_PROMPT contain
the boundary detection rules added to prevent mock-based tests from
being classified as unit tests for route handler / DB tasks.
"""

from tdd_orchestrator.decomposition.prompts import (
    AC_GENERATION_PROMPT,
    TASK_BREAKDOWN_PROMPT,
    format_task_breakdown_prompt,
)


class TestBoundaryDetectionInPrompts:
    """Verify prompt strings contain integration-boundary detection rules."""

    def test_task_breakdown_prompt_contains_boundary_detection_section(self) -> None:
        """The raw TASK_BREAKDOWN_PROMPT must include the boundary detection block."""
        assert "INTEGRATION-BOUNDARY DETECTION" in TASK_BREAKDOWN_PROMPT
        assert "Route handlers / API endpoints" in TASK_BREAKDOWN_PROMPT
        assert "Database query methods" in TASK_BREAKDOWN_PROMPT
        assert "External service clients" in TASK_BREAKDOWN_PROMPT
        assert "Message queue consumers/producers" in TASK_BREAKDOWN_PROMPT

    def test_task_breakdown_prompt_boundary_overrides_phase_classification(self) -> None:
        """The boundary detection section must explicitly state it overrides phase-based rules."""
        assert "overrides Phase-based classification" in TASK_BREAKDOWN_PROMPT
        # The TEST TYPE CLASSIFICATION block should note the override
        assert "unless overridden by" in TASK_BREAKDOWN_PROMPT

    def test_ac_prompt_contains_test_context_rules(self) -> None:
        """AC_GENERATION_PROMPT must include TEST CONTEXT RULES section."""
        assert "TEST CONTEXT RULES" in AC_GENERATION_PROMPT
        assert "seeded test database" in AC_GENERATION_PROMPT
        assert "GIVEN a test database seeded with" in AC_GENERATION_PROMPT
        assert "GIVEN a mocked" in AC_GENERATION_PROMPT

    def test_formatted_breakdown_includes_integration_boundary_block(self) -> None:
        """format_task_breakdown_prompt() output must contain the boundary block."""
        formatted = format_task_breakdown_prompt(
            cycle_number=1,
            cycle_title="API Route Handlers",
            phase="Foundation",
            components=["CircuitRouter"],
            expected_tests="8-10",
            module_hint="src/tdd_orchestrator/api/routes/",
            context="Build circuit breaker API routes.",
        )
        assert "INTEGRATION-BOUNDARY DETECTION" in formatted
        assert "Route handlers / API endpoints" in formatted
        assert "against real database with seeded data" in formatted
