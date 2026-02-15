"""Tests for the analytics router endpoints.

Tests the GET /analytics/attempts-by-stage, GET /analytics/task-completion-timeline,
and GET /analytics/invocation-stats endpoints that return aggregate statistics
from the attempts and invocations tables.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.routes.analytics import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockRow(dict[str, Any]):
    """Dict subclass that supports bracket access for aiosqlite row compat."""

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


class _DualMock:
    """Object that works as both an async context manager and an awaitable.

    ``async with db._conn.execute(...)`` needs ``__aenter__``/``__aexit__``.
    ``await db._conn.execute(...)`` needs the object to be awaitable.
    This wrapper satisfies both protocols by delegating to the inner cursor.
    """

    def __init__(self, cursor: AsyncMock) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> AsyncMock:
        return self._cursor

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def __await__(self) -> Any:
        async def _resolve() -> AsyncMock:
            return self._cursor

        return _resolve().__await__()


def _mock_cursor(rows: list[_MockRow]) -> _DualMock:
    """Return a dual-protocol mock whose cursor yields *rows*."""
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    cursor.fetchone = AsyncMock(return_value=rows[0] if rows else None)
    return _DualMock(cursor)


def _make_mock_db() -> MagicMock:
    """Create a mock db object with a mock _conn attribute."""
    db = MagicMock()
    db._conn = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Row factories
# ---------------------------------------------------------------------------


def _make_attempts_row(
    stage: str = "green",
    total: int = 10,
    successes: int = 8,
    avg_duration_ms: float | None = 1500.0,
) -> _MockRow:
    """Build a mock row for attempts-by-stage query."""
    return _MockRow(
        {
            "stage": stage,
            "total": total,
            "successes": successes,
            "avg_duration_ms": avg_duration_ms,
        }
    )


def _make_timeline_row(
    date: str = "2026-02-14",
    completed: int = 5,
) -> _MockRow:
    """Build a mock row for task-completion-timeline query."""
    return _MockRow({"date": date, "completed": completed})


def _make_invocation_row(
    stage: str = "red",
    count: int = 20,
    total_tokens: int = 5000,
    avg_duration_ms: float | None = 2300.0,
) -> _MockRow:
    """Build a mock row for invocation-stats query."""
    return _MockRow(
        {
            "stage": stage,
            "count": count,
            "total_tokens": total_tokens,
            "avg_duration_ms": avg_duration_ms,
        }
    )


# ---------------------------------------------------------------------------
# TestAttemptsByStageSuccess
# ---------------------------------------------------------------------------


class TestAttemptsByStageSuccess:
    """Tests for GET /analytics/attempts-by-stage with valid data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /analytics/attempts-by-stage returns 200 with stage rows."""
        rows = [
            _make_attempts_row(stage="red", total=5, successes=3),
            _make_attempts_row(stage="green", total=10, successes=8),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        assert client.get("/analytics/attempts-by-stage").status_code == 200

    def test_response_has_stages_key(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Response body has a 'stages' list."""
        rows = [_make_attempts_row()]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/attempts-by-stage").json()
        assert "stages" in body
        assert isinstance(body["stages"], list)

    def test_stage_fields_present(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Each stage item has stage, total, successes, avg_duration_ms."""
        rows = [_make_attempts_row(stage="green", total=10, successes=8, avg_duration_ms=1500.0)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/attempts-by-stage").json()
        item = body["stages"][0]
        assert item["stage"] == "green"
        assert item["total"] == 10
        assert item["successes"] == 8
        assert item["avg_duration_ms"] == 1500.0

    def test_avg_duration_ms_null_handling(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Row with avg_duration_ms=None returns None in response."""
        rows = [_make_attempts_row(avg_duration_ms=None)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/attempts-by-stage").json()
        assert body["stages"][0]["avg_duration_ms"] is None


# ---------------------------------------------------------------------------
# TestAttemptsByStageEmpty
# ---------------------------------------------------------------------------


class TestAttemptsByStageEmpty:
    """Tests for GET /analytics/attempts-by-stage with no data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_with_empty_stages(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Empty result returns 200 with empty stages list."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/analytics/attempts-by-stage").json()
        assert body == {"stages": []}


# ---------------------------------------------------------------------------
# TestTaskCompletionTimelineSuccess
# ---------------------------------------------------------------------------


class TestTaskCompletionTimelineSuccess:
    """Tests for GET /analytics/task-completion-timeline with valid data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /analytics/task-completion-timeline returns 200."""
        rows = [
            _make_timeline_row(date="2026-02-12", completed=3),
            _make_timeline_row(date="2026-02-13", completed=7),
            _make_timeline_row(date="2026-02-14", completed=5),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        assert client.get("/analytics/task-completion-timeline").status_code == 200

    def test_response_has_timeline_key(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Response body has a 'timeline' key."""
        rows = [_make_timeline_row()]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/task-completion-timeline").json()
        assert "timeline" in body
        assert isinstance(body["timeline"], list)

    def test_timeline_point_fields(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Each timeline item has date (str) and completed (int)."""
        rows = [_make_timeline_row(date="2026-02-14", completed=5)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/task-completion-timeline").json()
        item = body["timeline"][0]
        assert item["date"] == "2026-02-14"
        assert item["completed"] == 5


# ---------------------------------------------------------------------------
# TestTaskCompletionTimelineEmpty
# ---------------------------------------------------------------------------


class TestTaskCompletionTimelineEmpty:
    """Tests for GET /analytics/task-completion-timeline with no data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_with_empty_timeline(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Empty result returns 200 with empty timeline list."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/analytics/task-completion-timeline").json()
        assert body == {"timeline": []}


# ---------------------------------------------------------------------------
# TestInvocationStatsSuccess
# ---------------------------------------------------------------------------


class TestInvocationStatsSuccess:
    """Tests for GET /analytics/invocation-stats with valid data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /analytics/invocation-stats returns 200 with stage rows."""
        rows = [
            _make_invocation_row(stage="red", count=20),
            _make_invocation_row(stage="green", count=15),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        assert client.get("/analytics/invocation-stats").status_code == 200

    def test_response_has_invocations_key(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Response body has an 'invocations' key."""
        rows = [_make_invocation_row()]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/invocation-stats").json()
        assert "invocations" in body
        assert isinstance(body["invocations"], list)

    def test_total_tokens_is_int(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """total_tokens should be int (COALESCE prevents NULL)."""
        rows = [_make_invocation_row(total_tokens=5000)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/invocation-stats").json()
        assert isinstance(body["invocations"][0]["total_tokens"], int)
        assert body["invocations"][0]["total_tokens"] == 5000

    def test_avg_duration_ms_null_handling(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Row with avg_duration_ms=None returns None in response."""
        rows = [_make_invocation_row(avg_duration_ms=None)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/analytics/invocation-stats").json()
        assert body["invocations"][0]["avg_duration_ms"] is None


# ---------------------------------------------------------------------------
# TestInvocationStatsEmpty
# ---------------------------------------------------------------------------


class TestInvocationStatsEmpty:
    """Tests for GET /analytics/invocation-stats with no data."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_with_empty_invocations(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Empty result returns 200 with empty invocations list."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/analytics/invocation-stats").json()
        assert body == {"invocations": []}


# ---------------------------------------------------------------------------
# TestAnalyticsDbUnavailable
# ---------------------------------------------------------------------------


class TestAnalyticsDbUnavailable:
    """Tests that all analytics endpoints return 503 when db is None."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/analytics")
        return app

    @pytest.fixture()
    def client(self, app: FastAPI) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    def test_attempts_by_stage_returns_503(self, client: TestClient) -> None:
        """GET /analytics/attempts-by-stage returns 503 when db is None."""
        assert client.get("/analytics/attempts-by-stage").status_code == 503

    def test_task_completion_timeline_returns_503(self, client: TestClient) -> None:
        """GET /analytics/task-completion-timeline returns 503 when db is None."""
        assert client.get("/analytics/task-completion-timeline").status_code == 503

    def test_invocation_stats_returns_503(self, client: TestClient) -> None:
        """GET /analytics/invocation-stats returns 503 when db is None."""
        assert client.get("/analytics/invocation-stats").status_code == 503
