"""Tests for the PRD submission and status endpoints.

Tests the POST /prd/submit and GET /prd/status/{run_id} endpoints that
manage PRD pipeline runs using in-memory state.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import tdd_orchestrator.api.routes.prd as prd_module
from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.routes.prd import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_prd_state() -> Any:
    """Reset in-memory PRD state before and after each test."""
    prd_module._active_runs.clear()
    prd_module._rate_counter.clear()
    yield
    prd_module._active_runs.clear()
    prd_module._rate_counter.clear()


@pytest.fixture()
def mock_create_task(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock asyncio.create_task to prevent background coroutines."""
    mock = MagicMock()
    monkeypatch.setattr("tdd_orchestrator.api.routes.prd.asyncio.create_task", mock)
    return mock


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/prd")
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    app.dependency_overrides[get_db_dep] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    """Build a valid PRD submit payload with optional overrides."""
    defaults: dict[str, Any] = {
        "name": "Test PRD",
        "content": "Some PRD content",
        "workers": 2,
        "dry_run": False,
        "create_pr": False,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# TestPrdSubmitSuccess
# ---------------------------------------------------------------------------


class TestPrdSubmitSuccess:
    """Tests for POST /prd/submit with valid input."""

    def test_returns_200(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """POST /prd/submit returns 200 with valid payload."""
        response = client.post("/prd/submit", json=_valid_payload())
        assert response.status_code == 200

    def test_response_has_run_id(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Response body has a run_id string."""
        body = client.post("/prd/submit", json=_valid_payload()).json()
        assert "run_id" in body
        assert isinstance(body["run_id"], str)
        assert len(body["run_id"]) > 0

    def test_response_has_status_pending(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Response status is 'pending'."""
        body = client.post("/prd/submit", json=_valid_payload()).json()
        assert body["status"] == "pending"

    def test_response_has_message(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Response has a message field."""
        body = client.post("/prd/submit", json=_valid_payload()).json()
        assert "message" in body
        assert isinstance(body["message"], str)

    def test_spawns_background_task(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Submit spawns a background task via asyncio.create_task."""
        client.post("/prd/submit", json=_valid_payload())
        mock_create_task.assert_called_once()

    def test_name_gets_sanitized(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Name with special chars is sanitized in the message."""
        body = client.post(
            "/prd/submit", json=_valid_payload(name="My Great PRD!")
        ).json()
        assert "my-great-prd" in body["message"]


# ---------------------------------------------------------------------------
# TestPrdSubmitValidation
# ---------------------------------------------------------------------------


class TestPrdSubmitValidation:
    """Tests for POST /prd/submit input validation."""

    def test_empty_name_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Empty name returns 422."""
        response = client.post("/prd/submit", json=_valid_payload(name=""))
        assert response.status_code == 422

    def test_missing_name_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Missing name field returns 422."""
        payload = _valid_payload()
        del payload["name"]
        response = client.post("/prd/submit", json=payload)
        assert response.status_code == 422

    def test_empty_content_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Empty content returns 422."""
        response = client.post("/prd/submit", json=_valid_payload(content=""))
        assert response.status_code == 422

    def test_missing_content_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Missing content field returns 422."""
        payload = _valid_payload()
        del payload["content"]
        response = client.post("/prd/submit", json=payload)
        assert response.status_code == 422

    def test_oversized_content_returns_400(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Content exceeding 1MB returns 400."""
        big_content = "x" * (1_048_577)
        response = client.post("/prd/submit", json=_valid_payload(content=big_content))
        assert response.status_code == 400

    def test_name_sanitizes_to_empty_returns_400(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Name that sanitizes to empty returns 400."""
        response = client.post("/prd/submit", json=_valid_payload(name="!!!"))
        assert response.status_code == 400

    def test_workers_below_minimum_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Workers below 1 returns 422."""
        response = client.post("/prd/submit", json=_valid_payload(workers=0))
        assert response.status_code == 422

    def test_workers_above_maximum_returns_422(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Workers above 8 returns 422."""
        response = client.post("/prd/submit", json=_valid_payload(workers=9))
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestPrdSubmitConcurrentRejection
# ---------------------------------------------------------------------------


class TestPrdSubmitConcurrentRejection:
    """Tests for POST /prd/submit concurrent run prevention."""

    def test_returns_409_when_run_active(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Returns 409 when another run has status 'running'."""
        prd_module._active_runs["existing-run"] = {
            "run_id": "existing-run",
            "stage": "decompose",
            "status": "running",
            "task_count": None,
            "error_message": None,
            "name": "existing",
        }
        response = client.post("/prd/submit", json=_valid_payload())
        assert response.status_code == 409

    def test_allows_submit_after_previous_completes(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Allows new submit when previous run has status 'completed'."""
        prd_module._active_runs["old-run"] = {
            "run_id": "old-run",
            "stage": "done",
            "status": "completed",
            "task_count": 5,
            "error_message": None,
            "name": "old",
        }
        response = client.post("/prd/submit", json=_valid_payload())
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestPrdSubmitRateLimit
# ---------------------------------------------------------------------------


class TestPrdSubmitRateLimit:
    """Tests for POST /prd/submit rate limiting."""

    def test_returns_429_when_rate_limit_exceeded(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Returns 429 when 5 recent submissions exist."""
        now = time.time()
        prd_module._rate_counter.extend([now - i for i in range(5)])
        response = client.post("/prd/submit", json=_valid_payload())
        assert response.status_code == 429

    def test_allows_submit_when_old_entries_expired(
        self, client: TestClient, mock_create_task: MagicMock
    ) -> None:
        """Allows submit when 5 timestamps are all older than 1 hour."""
        old_time = time.time() - 3700  # >3600s ago
        prd_module._rate_counter.extend([old_time] * 5)
        response = client.post("/prd/submit", json=_valid_payload())
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestPrdStatusSuccess
# ---------------------------------------------------------------------------


class TestPrdStatusSuccess:
    """Tests for GET /prd/status/{run_id} with valid run."""

    def test_returns_200(self, client: TestClient) -> None:
        """GET /prd/status/{run_id} returns 200 for known run."""
        prd_module._active_runs["test-run"] = {
            "run_id": "test-run",
            "stage": "decompose",
            "status": "running",
            "task_count": 3,
            "error_message": None,
            "name": "test",
        }
        assert client.get("/prd/status/test-run").status_code == 200

    def test_response_fields(self, client: TestClient) -> None:
        """Response has run_id, stage, status, task_count, error_message."""
        prd_module._active_runs["test-run"] = {
            "run_id": "test-run",
            "stage": "execute",
            "status": "running",
            "task_count": 5,
            "error_message": None,
            "name": "test",
        }
        body = client.get("/prd/status/test-run").json()
        assert body["run_id"] == "test-run"
        assert body["stage"] == "execute"
        assert body["status"] == "running"
        assert body["task_count"] == 5
        assert body["error_message"] is None

    def test_returns_current_stage(self, client: TestClient) -> None:
        """Response reflects the current stage of the run."""
        prd_module._active_runs["test-run"] = {
            "run_id": "test-run",
            "stage": "pr",
            "status": "running",
            "task_count": None,
            "error_message": None,
            "name": "test",
        }
        body = client.get("/prd/status/test-run").json()
        assert body["stage"] == "pr"

    def test_null_fields_allowed(self, client: TestClient) -> None:
        """task_count and error_message can be None."""
        prd_module._active_runs["test-run"] = {
            "run_id": "test-run",
            "stage": "pending",
            "status": "pending",
            "task_count": None,
            "error_message": None,
            "name": "test",
        }
        body = client.get("/prd/status/test-run").json()
        assert body["task_count"] is None
        assert body["error_message"] is None


# ---------------------------------------------------------------------------
# TestPrdStatusNotFound
# ---------------------------------------------------------------------------


class TestPrdStatusNotFound:
    """Tests for GET /prd/status/{run_id} when run not found."""

    def test_returns_404_for_unknown_run_id(self, client: TestClient) -> None:
        """GET /prd/status/unknown returns 404."""
        assert client.get("/prd/status/unknown-id").status_code == 404

    def test_404_detail_contains_run_id(self, client: TestClient) -> None:
        """404 detail contains the requested run_id."""
        body = client.get("/prd/status/missing-run").json()
        assert "missing-run" in body["detail"]
