"""Tests for tasks listing, stats, and progress endpoints.

Tests the following endpoints:
- GET /tasks - List tasks with filtering and pagination
- GET /tasks/stats - Aggregate task statistics
- GET /tasks/progress - Task completion progress
"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.routes.tasks import router


class _MockRow(dict):  # type: ignore[type-arg]
    """Dict subclass that supports bracket-style access like aiosqlite rows."""

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


class _AsyncRowIterator:
    """Async iterator over a list of rows, for mocking ``async for row in cursor``."""

    def __init__(self, rows: list[_MockRow]) -> None:
        self._rows = rows
        self._index = 0

    def __aiter__(self) -> _AsyncRowIterator:
        return self

    async def __anext__(self) -> _MockRow:
        if self._index >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._index]
        self._index += 1
        return row


def _make_task_row(**overrides: Any) -> _MockRow:
    """Create a mock task row with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": 1,
        "task_key": "TDD-01-01",
        "title": "Test task",
        "status": "pending",
        "phase": 0,
        "sequence": 1,
        "complexity": "medium",
    }
    defaults.update(overrides)
    return _MockRow(defaults)


def _make_mock_db_with_conn() -> MagicMock:
    """Create a mock db object with a _conn attribute that supports execute."""
    mock_db = MagicMock()
    mock_db._conn = MagicMock()
    return mock_db


def _make_app(mock_db: Any) -> FastAPI:
    """Create a FastAPI app with the tasks router and overridden db dependency."""
    app = FastAPI()
    app.include_router(router, prefix="/tasks")

    async def override_get_db_dep() -> AsyncGenerator[Any, None]:
        yield mock_db

    app.dependency_overrides[get_db_dep] = override_get_db_dep
    return app


class TestGetTasksDefaultParams:
    """Tests for GET /tasks with default parameters (no filters)."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with two task rows and a count row."""
        db = _make_mock_db_with_conn()
        task_rows = [
            _make_task_row(task_key="TDD-01-01", title="Task one", status="pending"),
            _make_task_row(
                id=2, task_key="TDD-01-02", title="Task two", status="in_progress"
            ),
        ]
        count_row = _MockRow({"cnt": 2})

        # Two sequential execute calls: main query then count query
        main_cursor = AsyncMock()
        main_cursor.fetchall = AsyncMock(return_value=task_rows)
        main_cursor.__aenter__ = AsyncMock(return_value=main_cursor)
        main_cursor.__aexit__ = AsyncMock(return_value=False)

        count_cursor = AsyncMock()
        count_cursor.fetchone = AsyncMock(return_value=count_row)
        count_cursor.__aenter__ = AsyncMock(return_value=count_cursor)
        count_cursor.__aexit__ = AsyncMock(return_value=False)

        db._conn.execute = MagicMock(side_effect=[main_cursor, count_cursor])
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_returns_200(self, client: TestClient) -> None:
        """GET /tasks returns HTTP 200."""
        response = client.get("/tasks")
        assert response.status_code == 200

    def test_returns_tasks_list(self, client: TestClient) -> None:
        """GET /tasks returns a list of tasks."""
        body = client.get("/tasks").json()
        assert isinstance(body["tasks"], list)
        assert len(body["tasks"]) == 2

    def test_returns_total_count(self, client: TestClient) -> None:
        """GET /tasks returns total count matching query."""
        body = client.get("/tasks").json()
        assert body["total"] == 2

    def test_returns_limit_and_offset(self, client: TestClient) -> None:
        """GET /tasks returns default limit=20 and offset=0."""
        body = client.get("/tasks").json()
        assert body["limit"] == 20
        assert body["offset"] == 0

    def test_task_has_mapped_status(self, client: TestClient) -> None:
        """GET /tasks maps DB status 'in_progress' to API status 'running'."""
        body = client.get("/tasks").json()
        statuses = [t["status"] for t in body["tasks"]]
        assert "running" in statuses


class TestGetTasksStatusFilter:
    """Tests for GET /tasks with status filter."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db returning filtered results for status=failed."""
        db = _make_mock_db_with_conn()
        task_rows = [
            _make_task_row(task_key="TDD-02-01", status="blocked"),
        ]
        count_row = _MockRow({"cnt": 1})

        main_cursor = AsyncMock()
        main_cursor.fetchall = AsyncMock(return_value=task_rows)
        main_cursor.__aenter__ = AsyncMock(return_value=main_cursor)
        main_cursor.__aexit__ = AsyncMock(return_value=False)

        count_cursor = AsyncMock()
        count_cursor.fetchone = AsyncMock(return_value=count_row)
        count_cursor.__aenter__ = AsyncMock(return_value=count_cursor)
        count_cursor.__aexit__ = AsyncMock(return_value=False)

        db._conn.execute = MagicMock(side_effect=[main_cursor, count_cursor])
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_status_filter_returns_200(self, client: TestClient) -> None:
        """GET /tasks?status=failed returns HTTP 200."""
        response = client.get("/tasks?status=failed")
        assert response.status_code == 200

    def test_status_filter_maps_to_api_status(self, client: TestClient) -> None:
        """GET /tasks?status=failed maps DB 'blocked' to API 'failed'."""
        body = client.get("/tasks?status=failed").json()
        assert body["tasks"][0]["status"] == "failed"


class TestGetTasksPhaseAndComplexityFilters:
    """Tests for GET /tasks with phase and complexity filters."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db returning filtered results."""
        db = _make_mock_db_with_conn()
        task_rows = [_make_task_row(complexity="high", phase=1)]
        count_row = _MockRow({"cnt": 1})

        main_cursor = AsyncMock()
        main_cursor.fetchall = AsyncMock(return_value=task_rows)
        main_cursor.__aenter__ = AsyncMock(return_value=main_cursor)
        main_cursor.__aexit__ = AsyncMock(return_value=False)

        count_cursor = AsyncMock()
        count_cursor.fetchone = AsyncMock(return_value=count_row)
        count_cursor.__aenter__ = AsyncMock(return_value=count_cursor)
        count_cursor.__aexit__ = AsyncMock(return_value=False)

        db._conn.execute = MagicMock(side_effect=[main_cursor, count_cursor])
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_phase_filter_returns_200(self, client: TestClient) -> None:
        """GET /tasks?phase=red returns HTTP 200."""
        response = client.get("/tasks?phase=red")
        assert response.status_code == 200

    def test_complexity_filter_returns_200(self, client: TestClient) -> None:
        """GET /tasks?complexity=high returns HTTP 200."""
        response = client.get("/tasks?complexity=high")
        assert response.status_code == 200


class TestGetTasksPagination:
    """Tests for GET /tasks with custom limit and offset."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db returning one task with total=5."""
        db = _make_mock_db_with_conn()
        task_rows = [_make_task_row()]
        count_row = _MockRow({"cnt": 5})

        main_cursor = AsyncMock()
        main_cursor.fetchall = AsyncMock(return_value=task_rows)
        main_cursor.__aenter__ = AsyncMock(return_value=main_cursor)
        main_cursor.__aexit__ = AsyncMock(return_value=False)

        count_cursor = AsyncMock()
        count_cursor.fetchone = AsyncMock(return_value=count_row)
        count_cursor.__aenter__ = AsyncMock(return_value=count_cursor)
        count_cursor.__aexit__ = AsyncMock(return_value=False)

        db._conn.execute = MagicMock(side_effect=[main_cursor, count_cursor])
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_custom_limit_returned(self, client: TestClient) -> None:
        """GET /tasks?limit=5&offset=2 returns limit=5 in response."""
        body = client.get("/tasks?limit=5&offset=2").json()
        assert body["limit"] == 5

    def test_custom_offset_returned(self, client: TestClient) -> None:
        """GET /tasks?limit=5&offset=2 returns offset=2 in response."""
        body = client.get("/tasks?limit=5&offset=2").json()
        assert body["offset"] == 2

    def test_total_reflects_full_count(self, client: TestClient) -> None:
        """GET /tasks with pagination returns total from count query."""
        body = client.get("/tasks?limit=1&offset=0").json()
        assert body["total"] == 5


class TestGetTasksEmptyResult:
    """Tests for GET /tasks when no tasks match."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db returning empty results."""
        db = _make_mock_db_with_conn()
        count_row = _MockRow({"cnt": 0})

        main_cursor = AsyncMock()
        main_cursor.fetchall = AsyncMock(return_value=[])
        main_cursor.__aenter__ = AsyncMock(return_value=main_cursor)
        main_cursor.__aexit__ = AsyncMock(return_value=False)

        count_cursor = AsyncMock()
        count_cursor.fetchone = AsyncMock(return_value=count_row)
        count_cursor.__aenter__ = AsyncMock(return_value=count_cursor)
        count_cursor.__aexit__ = AsyncMock(return_value=False)

        db._conn.execute = MagicMock(side_effect=[main_cursor, count_cursor])
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_empty_returns_200(self, client: TestClient) -> None:
        """GET /tasks returns 200 even with no matching tasks."""
        assert client.get("/tasks").status_code == 200

    def test_empty_returns_empty_list(self, client: TestClient) -> None:
        """GET /tasks returns empty tasks list."""
        body = client.get("/tasks").json()
        assert body["tasks"] == []

    def test_empty_returns_total_zero(self, client: TestClient) -> None:
        """GET /tasks returns total=0 for empty result set."""
        body = client.get("/tasks").json()
        assert body["total"] == 0


class TestGetStats:
    """Tests for GET /tasks/stats endpoint."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with stats rows."""
        db = _make_mock_db_with_conn()
        stats_rows = [
            _MockRow({"status": "pending", "cnt": 5}),
            _MockRow({"status": "in_progress", "cnt": 2}),
            _MockRow({"status": "passing", "cnt": 3}),
            _MockRow({"status": "blocked", "cnt": 1}),
        ]
        cursor = MagicMock()
        cursor.__aenter__ = AsyncMock(return_value=_AsyncRowIterator(stats_rows))
        cursor.__aexit__ = AsyncMock(return_value=False)
        db._conn.execute = MagicMock(return_value=cursor)
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_stats_returns_200(self, client: TestClient) -> None:
        """GET /tasks/stats returns HTTP 200."""
        assert client.get("/tasks/stats").status_code == 200

    def test_stats_returns_pending_count(self, client: TestClient) -> None:
        """GET /tasks/stats returns pending=5."""
        body = client.get("/tasks/stats").json()
        assert body["pending"] == 5

    def test_stats_returns_running_count(self, client: TestClient) -> None:
        """GET /tasks/stats maps in_progress to running=2."""
        body = client.get("/tasks/stats").json()
        assert body["running"] == 2

    def test_stats_returns_passed_count(self, client: TestClient) -> None:
        """GET /tasks/stats maps passing to passed=3."""
        body = client.get("/tasks/stats").json()
        assert body["passed"] == 3

    def test_stats_returns_failed_count(self, client: TestClient) -> None:
        """GET /tasks/stats maps blocked to failed=1."""
        body = client.get("/tasks/stats").json()
        assert body["failed"] == 1

    def test_stats_returns_total(self, client: TestClient) -> None:
        """GET /tasks/stats returns total=11 (sum of all counts)."""
        body = client.get("/tasks/stats").json()
        assert body["total"] == 11


class TestGetStatsEmpty:
    """Tests for GET /tasks/stats when no tasks exist."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with no stats rows."""
        db = _make_mock_db_with_conn()
        cursor = MagicMock()
        cursor.__aenter__ = AsyncMock(return_value=_AsyncRowIterator([]))
        cursor.__aexit__ = AsyncMock(return_value=False)
        db._conn.execute = MagicMock(return_value=cursor)
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_empty_stats_returns_all_zeros(self, client: TestClient) -> None:
        """GET /tasks/stats returns all zeros when DB is empty."""
        body = client.get("/tasks/stats").json()
        assert body == {"pending": 0, "running": 0, "passed": 0, "failed": 0, "total": 0}


class TestGetProgress:
    """Tests for GET /tasks/progress endpoint."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with progress data."""
        db = _make_mock_db_with_conn()
        db.get_progress = AsyncMock(
            return_value={
                "total": 10,
                "completed": 5,
                "percentage": 50.0,
                "by_status": {"pending": 3, "passing": 5, "blocked": 2},
            }
        )
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_progress_returns_200(self, client: TestClient) -> None:
        """GET /tasks/progress returns HTTP 200."""
        assert client.get("/tasks/progress").status_code == 200

    def test_progress_returns_total(self, client: TestClient) -> None:
        """GET /tasks/progress returns total task count."""
        body = client.get("/tasks/progress").json()
        assert body["total"] == 10

    def test_progress_returns_percentage(self, client: TestClient) -> None:
        """GET /tasks/progress returns completion percentage."""
        body = client.get("/tasks/progress").json()
        assert body["percentage"] == 50.0


class TestListEndpoints503:
    """Tests for 503 when DB is unavailable on list/stats/progress endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client with None db (unavailable)."""
        return TestClient(_make_app(None), raise_server_exceptions=False)

    def test_get_tasks_returns_503(self, client: TestClient) -> None:
        """GET /tasks returns 503 when DB is unavailable."""
        assert client.get("/tasks").status_code == 503

    def test_get_stats_returns_503(self, client: TestClient) -> None:
        """GET /tasks/stats returns 503 when DB is unavailable."""
        assert client.get("/tasks/stats").status_code == 503

    def test_get_progress_returns_503(self, client: TestClient) -> None:
        """GET /tasks/progress returns 503 when DB is unavailable."""
        assert client.get("/tasks/progress").status_code == 503
