"""Tests for circular dependency detector.

Creates DecomposedTask objects directly (pure function, no mocks needed).
"""

from __future__ import annotations

from tdd_orchestrator.decomposition.dependency_validator import validate_no_cycles
from tdd_orchestrator.decomposition.task_model import DecomposedTask


def _make_task(
    task_key: str = "T-01",
    depends_on: list[str] | None = None,
) -> DecomposedTask:
    """Create a minimal DecomposedTask for testing."""
    return DecomposedTask(
        task_key=task_key,
        title=f"Task {task_key}",
        goal="Test goal",
        estimated_tests=5,
        estimated_lines=50,
        test_file=f"tests/test_{task_key.lower()}.py",
        impl_file=f"src/{task_key.lower()}.py",
        depends_on=depends_on or [],
    )


def test_linear_chain_no_cycles() -> None:
    """A -> B -> C linear chain has no cycles."""
    tasks = [
        _make_task("A"),
        _make_task("B", depends_on=["A"]),
        _make_task("C", depends_on=["B"]),
    ]

    errors = validate_no_cycles(tasks)

    assert errors == []


def test_self_reference_detected() -> None:
    """A task depending on itself is a cycle."""
    tasks = [_make_task("A", depends_on=["A"])]

    errors = validate_no_cycles(tasks)

    assert len(errors) == 1
    assert "A" in errors[0]


def test_simple_two_node_cycle() -> None:
    """A -> B -> A is a cycle."""
    tasks = [
        _make_task("A", depends_on=["B"]),
        _make_task("B", depends_on=["A"]),
    ]

    errors = validate_no_cycles(tasks)

    assert len(errors) == 1
    assert "A" in errors[0]
    assert "B" in errors[0]


def test_three_node_cycle() -> None:
    """A -> B -> C -> A is a cycle."""
    tasks = [
        _make_task("A", depends_on=["C"]),
        _make_task("B", depends_on=["A"]),
        _make_task("C", depends_on=["B"]),
    ]

    errors = validate_no_cycles(tasks)

    assert len(errors) == 1
    assert "->" in errors[0]


def test_diamond_no_cycles() -> None:
    """Diamond shape A->B, A->C, B->D, C->D has no cycles."""
    tasks = [
        _make_task("A"),
        _make_task("B", depends_on=["A"]),
        _make_task("C", depends_on=["A"]),
        _make_task("D", depends_on=["B", "C"]),
    ]

    errors = validate_no_cycles(tasks)

    assert errors == []


def test_cycle_in_subgraph() -> None:
    """Clean A->B chain + separate C->D->C cycle; only cycle nodes reported."""
    tasks = [
        _make_task("A"),
        _make_task("B", depends_on=["A"]),
        _make_task("C", depends_on=["D"]),
        _make_task("D", depends_on=["C"]),
    ]

    errors = validate_no_cycles(tasks)

    assert len(errors) == 1
    # Only C and D should be in the error, not A or B
    assert "A" not in errors[0]
    assert "B" not in errors[0]
    assert "C" in errors[0]
    assert "D" in errors[0]


def test_no_dependencies() -> None:
    """All tasks with empty depends_on -> no cycles."""
    tasks = [
        _make_task("A"),
        _make_task("B"),
        _make_task("C"),
    ]

    errors = validate_no_cycles(tasks)

    assert errors == []


def test_single_task() -> None:
    """Single task with no dependencies -> no cycles."""
    tasks = [_make_task("A")]

    errors = validate_no_cycles(tasks)

    assert errors == []


def test_missing_dependency_target() -> None:
    """A depends on Z (not in task list) -> graceful, no false cycle."""
    tasks = [
        _make_task("A", depends_on=["Z"]),
        _make_task("B", depends_on=["A"]),
    ]

    errors = validate_no_cycles(tasks)

    assert errors == []


def test_empty_task_list() -> None:
    """Empty input returns empty errors."""
    errors = validate_no_cycles([])

    assert errors == []


def test_large_graph_performance() -> None:
    """50+ tasks in linear chain completes without issue."""
    tasks = [_make_task(f"T-{i:03d}") for i in range(60)]
    # Each task depends on the previous one
    for i in range(1, len(tasks)):
        tasks[i] = _make_task(
            f"T-{i:03d}",
            depends_on=[f"T-{i - 1:03d}"],
        )

    errors = validate_no_cycles(tasks)

    assert errors == []
