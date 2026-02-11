"""Tests for overlap detector.

Creates DecomposedTask objects directly (pure function, no mocks needed).
"""

from __future__ import annotations

import logging

from tdd_orchestrator.decomposition.task_model import DecomposedTask
from tdd_orchestrator.decomposition.overlap_detector import detect_overlaps


def _make_task(
    task_key: str = "T-01",
    impl_file: str = "src/foo.py",
    module_exports: list[str] | None = None,
    phase: int = 1,
    sequence: int = 1,
    task_type: str = "implement",
) -> DecomposedTask:
    """Create a minimal DecomposedTask for testing."""
    return DecomposedTask(
        task_key=task_key,
        title=f"Task {task_key}",
        goal="Test goal",
        estimated_tests=5,
        estimated_lines=50,
        test_file=f"tests/test_{task_key.lower()}.py",
        impl_file=impl_file,
        module_exports=module_exports or [],
        phase=phase,
        sequence=sequence,
        task_type=task_type,
    )


def test_no_overlap_different_impl_files() -> None:
    """Tasks targeting different impl files -> no changes."""
    tasks = [
        _make_task("T-01", impl_file="src/a.py", module_exports=["foo"]),
        _make_task("T-02", impl_file="src/b.py", module_exports=["foo"]),
    ]

    result = detect_overlaps(tasks)

    assert all(t.task_type == "implement" for t in result)


def test_no_overlap_same_file_different_exports() -> None:
    """Same impl_file but disjoint module_exports -> no changes."""
    tasks = [
        _make_task("T-01", impl_file="src/a.py", module_exports=["foo"], phase=1),
        _make_task("T-02", impl_file="src/a.py", module_exports=["bar"], phase=2),
    ]

    result = detect_overlaps(tasks)

    assert all(t.task_type == "implement" for t in result)


def test_overlap_marks_later_task_verify_only() -> None:
    """Same impl_file + overlapping exports + later phase -> verify-only."""
    tasks = [
        _make_task("T-01", impl_file="src/a.py", module_exports=["foo", "bar"], phase=1),
        _make_task("T-02", impl_file="src/a.py", module_exports=["foo", "baz"], phase=2),
    ]

    result = detect_overlaps(tasks)

    assert result[0].task_type == "implement"
    assert result[1].task_type == "verify-only"


def test_overlap_higher_sequence_within_phase() -> None:
    """Same phase but higher sequence -> later task becomes verify-only."""
    tasks = [
        _make_task(
            "T-01", impl_file="src/a.py", module_exports=["foo"],
            phase=1, sequence=1,
        ),
        _make_task(
            "T-02", impl_file="src/a.py", module_exports=["foo"],
            phase=1, sequence=2,
        ),
    ]

    result = detect_overlaps(tasks)

    assert result[0].task_type == "implement"
    assert result[1].task_type == "verify-only"


def test_parallel_conflict_same_phase_sequence(caplog: logging.LogRecord) -> None:
    """Same impl_file + same phase + same sequence -> warning, NO change."""
    tasks = [
        _make_task(
            "T-01", impl_file="src/a.py", module_exports=["foo"],
            phase=1, sequence=1,
        ),
        _make_task(
            "T-02", impl_file="src/a.py", module_exports=["foo"],
            phase=1, sequence=1,
        ),
    ]

    with caplog.at_level(logging.WARNING):
        result = detect_overlaps(tasks)

    # No task should be modified
    assert all(t.task_type == "implement" for t in result)
    assert "Parallel overlap conflict" in caplog.text


def test_no_module_exports_passes_through() -> None:
    """Tasks without module_exports -> no changes (backward compatible)."""
    tasks = [
        _make_task("T-01", impl_file="src/a.py", module_exports=[], phase=1),
        _make_task("T-02", impl_file="src/a.py", module_exports=[], phase=2),
    ]

    result = detect_overlaps(tasks)

    assert all(t.task_type == "implement" for t in result)


def test_already_verify_only_not_doubled() -> None:
    """Task already marked verify-only -> not modified again."""
    tasks = [
        _make_task(
            "T-01", impl_file="src/a.py", module_exports=["foo"], phase=1,
        ),
        _make_task(
            "T-02", impl_file="src/a.py", module_exports=["foo"], phase=2,
            task_type="verify-only",
        ),
    ]

    result = detect_overlaps(tasks)

    # Should remain verify-only, not be re-processed
    assert result[1].task_type == "verify-only"
