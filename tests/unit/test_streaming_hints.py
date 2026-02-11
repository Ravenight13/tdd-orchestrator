"""Unit tests for streaming hint detection and enrichment."""

from __future__ import annotations

from tdd_orchestrator.decomposition.decomposer import DecomposedTask
from tdd_orchestrator.decomposition.streaming_hints import (
    STREAMING_TEST_HINTS,
    detect_streaming_task,
    enrich_streaming_hints,
)


def _make_task(
    *,
    title: str = "Normal task",
    goal: str = "Do something",
    acceptance_criteria: list[str] | None = None,
    components: list[str] | None = None,
    implementation_hints: str = "",
    complexity: str = "medium",
) -> DecomposedTask:
    """Helper to build a DecomposedTask with minimal required fields."""
    return DecomposedTask(
        task_key="TASK-001",
        title=title,
        goal=goal,
        estimated_tests=5,
        estimated_lines=50,
        test_file="tests/test_example.py",
        impl_file="src/example.py",
        acceptance_criteria=acceptance_criteria or [],
        components=components or [],
        implementation_hints=implementation_hints,
        complexity=complexity,
    )


def test_detect_streaming_task_sse_in_title() -> None:
    """'SSE' in title triggers streaming detection."""
    task = _make_task(title="Implement SSE Events Endpoint")
    assert detect_streaming_task(task) is True


def test_detect_streaming_task_websocket_in_goal() -> None:
    """'websocket' in goal triggers streaming detection."""
    task = _make_task(goal="Create a websocket handler for real-time updates")
    assert detect_streaming_task(task) is True


def test_detect_streaming_task_event_stream_in_criteria() -> None:
    """'event stream' in acceptance criteria triggers streaming detection."""
    task = _make_task(
        acceptance_criteria=["Endpoint returns event stream with proper headers"]
    )
    assert detect_streaming_task(task) is True


def test_detect_streaming_task_normal_task_returns_false() -> None:
    """Normal task without streaming keywords returns False."""
    task = _make_task(title="Add user login", goal="Implement authentication")
    assert detect_streaming_task(task) is False


def test_enrich_streaming_hints_injects_hints() -> None:
    """Streaming task gets STREAMING_TEST_HINTS in implementation_hints."""
    task = _make_task(title="SSE endpoint")
    [enriched] = enrich_streaming_hints([task])
    assert STREAMING_TEST_HINTS in enriched.implementation_hints


def test_enrich_streaming_hints_preserves_existing_hints() -> None:
    """Existing hints are preserved (appended after streaming hints)."""
    existing = "Use httpx for testing."
    task = _make_task(title="SSE endpoint", implementation_hints=existing)
    [enriched] = enrich_streaming_hints([task])
    assert STREAMING_TEST_HINTS in enriched.implementation_hints
    assert existing in enriched.implementation_hints


def test_enrich_streaming_hints_forces_high_complexity() -> None:
    """Streaming task complexity is forced to 'high'."""
    task = _make_task(title="SSE endpoint", complexity="low")
    [enriched] = enrich_streaming_hints([task])
    assert enriched.complexity == "high"


def test_enrich_streaming_hints_leaves_non_streaming_unchanged() -> None:
    """Non-streaming tasks pass through with no modifications."""
    task = _make_task(title="Add login page", complexity="low")
    [unchanged] = enrich_streaming_hints([task])
    assert unchanged.implementation_hints == ""
    assert unchanged.complexity == "low"
