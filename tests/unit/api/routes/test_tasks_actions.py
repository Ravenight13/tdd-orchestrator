"""Tests for task detail and retry endpoints.

Tests the following endpoints:
- GET /tasks/{task_key} - Get task detail with attempt history
- POST /tasks/{task_key}/retry - Retry a failed task
"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.dependencies import get_broadcaster_dep, get_db_dep
from tdd_orchestrator.api.routes.tasks import router


class _MockRow(dict):  # type: ignore[type-arg]
    """Dict subclass that supports bracket-style access like aiosqlite rows."""

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Override get to match dict behaviour."""
        return super().get(key, default)


def _make_task_dict(**overrides: Any) -> dict[str, Any]:
    """Create a mock task dict with sensible defaults."""
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
    return defaults


def _make_attempt_dict(**overrides: Any) -> dict[str, Any]:
    """Create a mock attempt dict with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": 1,
        "stage": "RED",
        "attempt_number": 1,
        "success": False,
        "error_message": None,
        "started_at": "2024-01-15T10:00:00Z",
    }
    defaults.update(overrides)
    return defaults


def _make_mock_db_with_conn() -> MagicMock:
    """Create a mock db object with a _conn attribute."""
    mock_db = MagicMock()
    mock_db._conn = MagicMock()
    return mock_db


def _make_app(
    mock_db: Any, mock_broadcaster: Any | None = None
) -> FastAPI:
    """Create a FastAPI app with the tasks router and overridden dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/tasks")

    async def override_get_db_dep() -> AsyncGenerator[Any, None]:
        yield mock_db

    app.dependency_overrides[get_db_dep] = override_get_db_dep

    if mock_broadcaster is not None:
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster

    return app


class TestGetTaskDetailFound:
    """Tests for GET /tasks/{task_key} when task exists."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db that returns a task and its attempts."""
        db = _make_mock_db_with_conn()
        db.get_task_by_key = AsyncMock(
            return_value=_make_task_dict(
                task_key="TDD-03-01", title="Auth login", status="in_progress"
            )
        )
        db.get_stage_attempts = AsyncMock(
            return_value=[
                _make_attempt_dict(id=1, stage="RED", attempt_number=1, success=False),
                _make_attempt_dict(
                    id=2,
                    stage="RED",
                    attempt_number=2,
                    success=True,
                    error_message="compile error",
                ),
            ]
        )
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db))

    def test_returns_200(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 returns HTTP 200."""
        assert client.get("/tasks/TDD-03-01").status_code == 200

    def test_returns_task_id(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 returns id matching task_key."""
        body = client.get("/tasks/TDD-03-01").json()
        assert body["id"] == "TDD-03-01"

    def test_returns_mapped_status(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 maps DB 'in_progress' to API 'running'."""
        body = client.get("/tasks/TDD-03-01").json()
        assert body["status"] == "running"

    def test_returns_title(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 returns task title."""
        body = client.get("/tasks/TDD-03-01").json()
        assert body["title"] == "Auth login"

    def test_returns_attempts_list(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 returns attempts array."""
        body = client.get("/tasks/TDD-03-01").json()
        assert isinstance(body["attempts"], list)
        assert len(body["attempts"]) == 2

    def test_attempt_has_stage(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 attempt entries include stage field."""
        body = client.get("/tasks/TDD-03-01").json()
        assert body["attempts"][0]["stage"] == "RED"

    def test_attempt_has_success_field(self, client: TestClient) -> None:
        """GET /tasks/TDD-03-01 attempt entries include success boolean."""
        body = client.get("/tasks/TDD-03-01").json()
        assert body["attempts"][0]["success"] is False


class TestGetTaskDetailNotFound:
    """Tests for GET /tasks/{task_key} when task does not exist."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db that returns None for get_task_by_key."""
        db = _make_mock_db_with_conn()
        db.get_task_by_key = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def client(self, mock_db: MagicMock) -> TestClient:
        """Create a test client with mocked db."""
        return TestClient(_make_app(mock_db), raise_server_exceptions=False)

    def test_returns_404(self, client: TestClient) -> None:
        """GET /tasks/NONEXISTENT returns HTTP 404."""
        assert client.get("/tasks/NONEXISTENT").status_code == 404

    def test_returns_detail_message(self, client: TestClient) -> None:
        """GET /tasks/NONEXISTENT returns 'Task not found' detail."""
        body = client.get("/tasks/NONEXISTENT").json()
        assert body["detail"] == "Task not found"


class TestRetryTaskSuccess:
    """Tests for POST /tasks/{task_key}/retry on a failed (blocked) task."""

    @pytest.fixture
    def mock_broadcaster(self) -> AsyncMock:
        """Create a mock broadcaster."""
        broadcaster = AsyncMock()
        broadcaster.publish = AsyncMock()
        return broadcaster

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with a blocked task."""
        db = _make_mock_db_with_conn()
        db.get_task_by_key = AsyncMock(
            return_value=_make_task_dict(
                task_key="TDD-05-01", status="blocked"
            )
        )
        db.update_task_status = AsyncMock()
        return db

    @pytest.fixture
    def client(
        self, mock_db: MagicMock, mock_broadcaster: AsyncMock
    ) -> TestClient:
        """Create a test client with mocked db and broadcaster."""
        return TestClient(_make_app(mock_db, mock_broadcaster))

    def test_returns_200(self, client: TestClient) -> None:
        """POST /tasks/TDD-05-01/retry returns HTTP 200."""
        assert client.post("/tasks/TDD-05-01/retry").status_code == 200

    def test_returns_pending_status(self, client: TestClient) -> None:
        """POST /tasks/TDD-05-01/retry returns status='pending'."""
        body = client.post("/tasks/TDD-05-01/retry").json()
        assert body["status"] == "pending"

    def test_returns_task_key(self, client: TestClient) -> None:
        """POST /tasks/TDD-05-01/retry returns task_key in response."""
        body = client.post("/tasks/TDD-05-01/retry").json()
        assert body["task_key"] == "TDD-05-01"

    def test_calls_update_task_status(
        self, mock_db: MagicMock, mock_broadcaster: AsyncMock
    ) -> None:
        """POST /tasks/TDD-05-01/retry calls db.update_task_status."""
        client = TestClient(_make_app(mock_db, mock_broadcaster))
        client.post("/tasks/TDD-05-01/retry")
        mock_db.update_task_status.assert_awaited_once_with("TDD-05-01", "pending")

    def test_publishes_sse_event(
        self, mock_db: MagicMock, mock_broadcaster: AsyncMock
    ) -> None:
        """POST /tasks/TDD-05-01/retry publishes SSE event."""
        import json

        from tdd_orchestrator.api.sse import SSEEvent

        client = TestClient(_make_app(mock_db, mock_broadcaster))
        client.post("/tasks/TDD-05-01/retry")
        mock_broadcaster.publish.assert_awaited_once()
        call_args = mock_broadcaster.publish.call_args[0][0]
        assert isinstance(call_args, SSEEvent)
        assert call_args.event == "task_status_changed"
        data = json.loads(call_args.data)
        assert data["task_key"] == "TDD-05-01"
        assert data["status"] == "pending"


class TestRetryTaskNotFound:
    """Tests for POST /tasks/{task_key}/retry when task does not exist."""

    @pytest.fixture
    def mock_broadcaster(self) -> AsyncMock:
        """Create a mock broadcaster."""
        return AsyncMock()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db that returns None for get_task_by_key."""
        db = _make_mock_db_with_conn()
        db.get_task_by_key = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def client(
        self, mock_db: MagicMock, mock_broadcaster: AsyncMock
    ) -> TestClient:
        """Create a test client with mocked db and broadcaster."""
        return TestClient(
            _make_app(mock_db, mock_broadcaster), raise_server_exceptions=False
        )

    def test_returns_404(self, client: TestClient) -> None:
        """POST /tasks/MISSING/retry returns HTTP 404."""
        assert client.post("/tasks/MISSING/retry").status_code == 404

    def test_returns_detail_message(self, client: TestClient) -> None:
        """POST /tasks/MISSING/retry returns 'Task not found' detail."""
        body = client.post("/tasks/MISSING/retry").json()
        assert body["detail"] == "Task not found"


class TestRetryTaskConflict:
    """Tests for POST /tasks/{task_key}/retry when task is not in failed status."""

    @pytest.fixture
    def mock_broadcaster(self) -> AsyncMock:
        """Create a mock broadcaster."""
        return AsyncMock()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock db with a pending (non-failed) task."""
        db = _make_mock_db_with_conn()
        db.get_task_by_key = AsyncMock(
            return_value=_make_task_dict(
                task_key="TDD-06-01", status="pending"
            )
        )
        return db

    @pytest.fixture
    def client(
        self, mock_db: MagicMock, mock_broadcaster: AsyncMock
    ) -> TestClient:
        """Create a test client with mocked db and broadcaster."""
        return TestClient(
            _make_app(mock_db, mock_broadcaster), raise_server_exceptions=False
        )

    def test_returns_409(self, client: TestClient) -> None:
        """POST /tasks/TDD-06-01/retry returns HTTP 409 for non-failed task."""
        assert client.post("/tasks/TDD-06-01/retry").status_code == 409

    def test_returns_conflict_detail(self, client: TestClient) -> None:
        """POST /tasks/TDD-06-01/retry returns detail about non-retryable status."""
        body = client.post("/tasks/TDD-06-01/retry").json()
        assert "Cannot retry" in body["detail"]
        assert "pending" in body["detail"]


class TestActionEndpoints503:
    """Tests for 503 when DB is unavailable on detail/retry endpoints."""

    @pytest.fixture
    def mock_broadcaster(self) -> AsyncMock:
        """Create a mock broadcaster."""
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_broadcaster: AsyncMock) -> TestClient:
        """Create a test client with None db (unavailable)."""
        return TestClient(
            _make_app(None, mock_broadcaster), raise_server_exceptions=False
        )

    def test_get_task_detail_returns_503(self, client: TestClient) -> None:
        """GET /tasks/TDD-01 returns 503 when DB is unavailable."""
        assert client.get("/tasks/TDD-01").status_code == 503

    def test_retry_task_returns_503(self, client: TestClient) -> None:
        """POST /tasks/TDD-01/retry returns 503 when DB is unavailable."""
        assert client.post("/tasks/TDD-01/retry").status_code == 503
