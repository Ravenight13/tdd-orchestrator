"""Unit tests for dep_graph module — runtime dependency checker."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from tdd_orchestrator.dep_graph import (
    are_dependencies_met,
    get_dependency_graph,
    validate_dependencies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockRow:
    """Lightweight mock for an aiosqlite Row supporting index access."""

    def __init__(self, values: tuple[Any, ...]) -> None:
        self._values = values

    def __getitem__(self, index: int) -> Any:  # noqa: ANN401
        return self._values[index]


def _make_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
    """Return a MagicMock that behaves as an async context-manager cursor.

    The cursor supports ``fetchall`` (returns all *rows*) and ``fetchone``
    (returns the first row or ``None``).
    """
    mock_rows = [_MockRow(r) for r in rows]
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=mock_rows)
    cursor.fetchone = AsyncMock(return_value=mock_rows[0] if mock_rows else None)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=cursor)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _build_mock_db(calls: dict[str, list[tuple[Any, ...]]]) -> AsyncMock:
    """Build a mock ``OrchestratorDB`` whose ``_conn.execute`` dispatches
    based on SQL content.

    *calls* maps a SQL substring to the rows that query should return.
    If a query matches multiple substrings the first match wins.
    """
    db = AsyncMock()
    db._conn = MagicMock()

    def _execute(sql: str, params: tuple[Any, ...] = ()) -> MagicMock:  # noqa: ARG001
        for fragment, rows in calls.items():
            if fragment in sql:
                return _make_cursor(rows)
        # Fallback — empty result
        return _make_cursor([])

    db._conn.execute = _execute
    return db


# ---------------------------------------------------------------------------
# validate_dependencies
# ---------------------------------------------------------------------------


class TestValidateDependencies:
    """Tests for validate_dependencies()."""

    async def test_dangling_ref_detected(self) -> None:
        """A depends_on value with no matching task_key is flagged."""
        db = _build_mock_db(
            {
                "SELECT task_key FROM tasks": [
                    ("TASK-01",),
                    ("TASK-02",),
                ],
                "SELECT task_key, depends_on FROM tasks": [
                    ("TASK-01", '["TASK-02"]'),
                    ("TASK-02", '["TASK-99"]'),
                ],
            }
        )

        issues = await validate_dependencies(db)
        assert len(issues) == 1
        assert issues[0]["task_key"] == "TASK-02"
        assert issues[0]["dangling_refs"] == ["TASK-99"]

    async def test_no_dangling_refs(self) -> None:
        """When all deps exist, the result should be an empty list."""
        db = _build_mock_db(
            {
                "SELECT task_key FROM tasks": [
                    ("TASK-01",),
                    ("TASK-02",),
                ],
                "SELECT task_key, depends_on FROM tasks": [
                    ("TASK-01", "[]"),
                    ("TASK-02", '["TASK-01"]'),
                ],
            }
        )

        issues = await validate_dependencies(db)
        assert issues == []

    async def test_empty_depends_on_variants(self) -> None:
        """NULL, '[]', and 'null' should all be treated as no deps."""
        db = _build_mock_db(
            {
                "SELECT task_key FROM tasks": [
                    ("A",),
                    ("B",),
                    ("C",),
                ],
                "SELECT task_key, depends_on FROM tasks": [
                    ("A", None),
                    ("B", "[]"),
                    ("C", "null"),
                ],
            }
        )

        issues = await validate_dependencies(db)
        assert issues == []


# ---------------------------------------------------------------------------
# get_dependency_graph
# ---------------------------------------------------------------------------


class TestGetDependencyGraph:
    """Tests for get_dependency_graph()."""

    async def test_multiple_tasks(self) -> None:
        """Graph should map every task to its dependency list."""
        db = _build_mock_db(
            {
                "SELECT task_key, depends_on FROM tasks": [
                    ("TASK-01", "[]"),
                    ("TASK-02", '["TASK-01"]'),
                    ("TASK-03", '["TASK-01", "TASK-02"]'),
                ],
            }
        )

        graph = await get_dependency_graph(db)
        assert graph == {
            "TASK-01": [],
            "TASK-02": ["TASK-01"],
            "TASK-03": ["TASK-01", "TASK-02"],
        }

    async def test_empty_table(self) -> None:
        """An empty tasks table returns an empty graph."""
        db = _build_mock_db({"SELECT task_key, depends_on FROM tasks": []})

        graph = await get_dependency_graph(db)
        assert graph == {}


# ---------------------------------------------------------------------------
# are_dependencies_met
# ---------------------------------------------------------------------------


class TestAreDependenciesMet:
    """Tests for are_dependencies_met()."""

    async def test_all_deps_met(self) -> None:
        """Returns True when every dependency is complete or passing."""
        call_index = {"idx": 0}
        rows_sequence: list[list[tuple[Any, ...]]] = [
            # First call: SELECT depends_on … WHERE task_key = ?
            [('["DEP-A", "DEP-B"]',)],
            # Second call: SELECT status … WHERE task_key = ? (DEP-A)
            [("complete",)],
            # Third call: SELECT status … WHERE task_key = ? (DEP-B)
            [("passing",)],
        ]

        db = AsyncMock()
        db._conn = MagicMock()

        def _execute(sql: str, params: tuple[Any, ...] = ()) -> MagicMock:  # noqa: ARG001
            idx = call_index["idx"]
            call_index["idx"] += 1
            return _make_cursor(rows_sequence[idx])

        db._conn.execute = _execute

        result = await are_dependencies_met(db, "TASK-X")
        assert result is True

    async def test_unmet_deps(self) -> None:
        """Returns False when at least one dependency is not terminal."""
        call_index = {"idx": 0}
        rows_sequence: list[list[tuple[Any, ...]]] = [
            [('["DEP-A"]',)],
            [("in_progress",)],
        ]

        db = AsyncMock()
        db._conn = MagicMock()

        def _execute(sql: str, params: tuple[Any, ...] = ()) -> MagicMock:  # noqa: ARG001
            idx = call_index["idx"]
            call_index["idx"] += 1
            return _make_cursor(rows_sequence[idx])

        db._conn.execute = _execute

        result = await are_dependencies_met(db, "TASK-X")
        assert result is False

    async def test_no_dependencies(self) -> None:
        """A task with no depends_on is considered met."""
        db = _build_mock_db(
            {"SELECT depends_on FROM tasks WHERE task_key": [("[]",)]}
        )

        result = await are_dependencies_met(db, "TASK-X")
        assert result is True

    async def test_null_depends_on(self) -> None:
        """A task with NULL depends_on is considered met."""
        db = _build_mock_db(
            {"SELECT depends_on FROM tasks WHERE task_key": [(None,)]}
        )

        result = await are_dependencies_met(db, "TASK-X")
        assert result is True

    async def test_task_not_found(self) -> None:
        """A non-existent task_key returns True (no deps to block)."""
        db = _build_mock_db(
            {"SELECT depends_on FROM tasks WHERE task_key": []}
        )

        result = await are_dependencies_met(db, "MISSING")
        assert result is True

    async def test_dependency_not_found(self) -> None:
        """Returns False when a dependency task_key does not exist."""
        call_index = {"idx": 0}
        rows_sequence: list[list[tuple[Any, ...]]] = [
            [('["GHOST"]',)],
            [],  # No row for GHOST
        ]

        db = AsyncMock()
        db._conn = MagicMock()

        def _execute(sql: str, params: tuple[Any, ...] = ()) -> MagicMock:  # noqa: ARG001
            idx = call_index["idx"]
            call_index["idx"] += 1
            return _make_cursor(rows_sequence[idx])

        db._conn.execute = _execute

        result = await are_dependencies_met(db, "TASK-X")
        assert result is False
