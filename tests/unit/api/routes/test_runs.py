"""Tests for runs router endpoints.

Tests the following endpoints:
- GET /runs - List all runs with optional status filter
- GET /runs/{id} - Get a specific run by ID
- GET /runs/current - Get the current active run
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.runs import router


class TestListRunsNoFilters:
    """Tests for GET /runs with no filters."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def runs_data(self) -> list[dict[str, Any]]:
        """Create mock run data with varying statuses."""
        now = datetime.now(tz=timezone.utc)
        return [
            {
                "id": "run-abc-123",
                "status": "completed",
                "spec_file": "spec_one.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 5,
            },
            {
                "id": "run-def-456",
                "status": "running",
                "spec_file": "spec_two.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 10,
            },
            {
                "id": "run-ghi-789",
                "status": "pending",
                "spec_file": "spec_three.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 3,
            },
            {
                "id": "run-jkl-012",
                "status": "failed",
                "spec_file": "spec_four.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 7,
            },
        ]

    def test_get_runs_returns_200_when_runs_exist(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs returns HTTP 200 when runs exist."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            assert response.status_code == 200

    def test_get_runs_returns_run_list_response(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs returns a RunListResponse with runs list."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert "runs" in json_body
            assert isinstance(json_body["runs"], list)
            assert len(json_body["runs"]) == 4

    def test_get_runs_returns_total_count(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs returns total count in RunListResponse."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert "total" in json_body
            assert json_body["total"] == 4

    def test_get_runs_response_items_have_id_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include id field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "id" in json_body["runs"][0]

    def test_get_runs_response_items_have_status_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include status field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "status" in json_body["runs"][0]

    def test_get_runs_response_items_have_spec_file_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include spec_file field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "spec_file" in json_body["runs"][0]

    def test_get_runs_response_items_have_created_at_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include created_at field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "created_at" in json_body["runs"][0]

    def test_get_runs_response_items_have_updated_at_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include updated_at field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "updated_at" in json_body["runs"][0]

    def test_get_runs_response_items_have_task_count_field(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs response items include task_count field."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": runs_data, "total": len(runs_data)},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert len(json_body["runs"]) >= 1
            assert "task_count" in json_body["runs"][0]

    def test_get_runs_ordered_by_creation_time_descending(
        self, client: TestClient, runs_data: list[dict[str, Any]]
    ) -> None:
        """GET /runs returns runs ordered by creation time descending."""
        # Create data with different timestamps
        now = datetime.now(tz=timezone.utc)
        ordered_data = [
            {
                "id": "run-newest",
                "status": "running",
                "spec_file": "spec.yaml",
                "created_at": "2024-01-15T12:00:00+00:00",
                "updated_at": "2024-01-15T12:00:00+00:00",
                "task_count": 1,
            },
            {
                "id": "run-oldest",
                "status": "completed",
                "spec_file": "spec.yaml",
                "created_at": "2024-01-14T12:00:00+00:00",
                "updated_at": "2024-01-14T12:00:00+00:00",
                "task_count": 1,
            },
        ]
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": ordered_data, "total": 2},
        ):
            response = client.get("/runs")
            json_body = response.json()
            runs = json_body["runs"]
            assert len(runs) == 2
            # Verify ordering - newest first
            assert runs[0]["id"] == "run-newest"
            assert runs[1]["id"] == "run-oldest"


class TestListRunsWithStatusFilter:
    """Tests for GET /runs with status filter."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def running_runs(self) -> list[dict[str, Any]]:
        """Create mock data for running runs only."""
        now = datetime.now(tz=timezone.utc)
        return [
            {
                "id": "run-running-1",
                "status": "running",
                "spec_file": "spec_running.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 5,
            },
        ]

    def test_get_runs_with_status_filter_returns_200(
        self, client: TestClient, running_runs: list[dict[str, Any]]
    ) -> None:
        """GET /runs?status=running returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": running_runs, "total": 1},
        ):
            response = client.get("/runs?status=running")
            assert response.status_code == 200

    def test_get_runs_with_status_filter_returns_matching_runs(
        self, client: TestClient, running_runs: list[dict[str, Any]]
    ) -> None:
        """GET /runs?status=running returns only runs with status='running'."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": running_runs, "total": 1},
        ):
            response = client.get("/runs?status=running")
            json_body = response.json()
            assert len(json_body["runs"]) == 1
            assert json_body["runs"][0]["status"] == "running"

    def test_get_runs_with_pending_status_returns_200(
        self, client: TestClient
    ) -> None:
        """GET /runs?status=pending returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs?status=pending")
            assert response.status_code == 200

    def test_get_runs_with_completed_status_returns_200(
        self, client: TestClient
    ) -> None:
        """GET /runs?status=completed returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs?status=completed")
            assert response.status_code == 200

    def test_get_runs_with_failed_status_returns_200(
        self, client: TestClient
    ) -> None:
        """GET /runs?status=failed returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs?status=failed")
            assert response.status_code == 200

    def test_get_runs_with_invalid_status_returns_422(
        self, client: TestClient
    ) -> None:
        """GET /runs?status=invalid_status returns HTTP 422 validation error."""
        response = client.get("/runs?status=invalid_status")
        assert response.status_code == 422

    def test_get_runs_with_invalid_status_returns_validation_error_detail(
        self, client: TestClient
    ) -> None:
        """GET /runs?status=invalid_status returns validation error with allowed values."""
        response = client.get("/runs?status=invalid_status")
        json_body = response.json()
        # FastAPI returns validation errors in 'detail' field
        assert "detail" in json_body


class TestGetRunById:
    """Tests for GET /runs/{id} endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def run_data(self) -> dict[str, Any]:
        """Create mock run data for a specific run."""
        now = datetime.now(tz=timezone.utc)
        return {
            "id": "run-abc-123",
            "status": "running",
            "spec_file": "spec.yaml",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "task_count": 10,
            "task_summary": {
                "pending": 3,
                "running": 2,
                "completed": 4,
                "failed": 1,
            },
        }

    def test_get_run_by_id_returns_200_when_run_exists(
        self, client: TestClient, run_data: dict[str, Any]
    ) -> None:
        """GET /runs/{id} returns HTTP 200 when run exists."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=run_data,
        ):
            response = client.get("/runs/run-abc-123")
            assert response.status_code == 200

    def test_get_run_by_id_returns_full_run_response(
        self, client: TestClient, run_data: dict[str, Any]
    ) -> None:
        """GET /runs/{id} returns full RunResponse with all fields."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=run_data,
        ):
            response = client.get("/runs/run-abc-123")
            json_body = response.json()
            assert json_body.get("id") == "run-abc-123"
            assert json_body.get("status") == "running"
            assert json_body.get("spec_file") == "spec.yaml"
            assert "created_at" in json_body
            assert "updated_at" in json_body
            assert json_body.get("task_count") == 10

    def test_get_run_by_id_returns_nested_task_summary(
        self, client: TestClient, run_data: dict[str, Any]
    ) -> None:
        """GET /runs/{id} returns nested task summary counts."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=run_data,
        ):
            response = client.get("/runs/run-abc-123")
            json_body = response.json()
            task_summary = json_body.get("task_summary", {})
            assert task_summary.get("pending") == 3
            assert task_summary.get("running") == 2
            assert task_summary.get("completed") == 4
            assert task_summary.get("failed") == 1

    def test_get_run_by_id_returns_404_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /runs/{id} returns HTTP 404 when run does not exist."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=None,
        ):
            response = client.get("/runs/run-nonexistent")
            assert response.status_code == 404

    def test_get_run_by_id_returns_detail_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /runs/{id} returns 'Run not found' detail when not found."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=None,
        ):
            response = client.get("/runs/run-nonexistent")
            json_body = response.json()
            assert json_body.get("detail") == "Run not found"

    def test_get_run_by_id_returns_error_code_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /runs/{id} returns error code ERR-RUN-404 when not found."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=None,
        ):
            response = client.get("/runs/run-nonexistent")
            json_body = response.json()
            # Error code may be in 'error_code' or as part of the response
            error_code = json_body.get("error_code", "")
            assert error_code == "ERR-RUN-404"


class TestGetCurrentRun:
    """Tests for GET /runs/current endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def active_run_data(self) -> dict[str, Any]:
        """Create mock data for an active running run."""
        now = datetime.now(tz=timezone.utc)
        return {
            "id": "run-active-001",
            "status": "running",
            "spec_file": "active_spec.yaml",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "task_count": 15,
        }

    def test_get_current_run_returns_200_when_active_run_exists(
        self, client: TestClient, active_run_data: dict[str, Any]
    ) -> None:
        """GET /runs/current returns HTTP 200 when an active run exists."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=active_run_data,
        ):
            response = client.get("/runs/current")
            assert response.status_code == 200

    def test_get_current_run_returns_run_response(
        self, client: TestClient, active_run_data: dict[str, Any]
    ) -> None:
        """GET /runs/current returns RunResponse for the active run."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=active_run_data,
        ):
            response = client.get("/runs/current")
            json_body = response.json()
            assert json_body.get("id") == "run-active-001"
            assert json_body.get("status") == "running"
            assert json_body.get("spec_file") == "active_spec.yaml"
            assert json_body.get("task_count") == 15

    def test_get_current_run_returns_404_when_no_active_run(
        self, client: TestClient
    ) -> None:
        """GET /runs/current returns HTTP 404 when no active run exists."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=None,
        ):
            response = client.get("/runs/current")
            assert response.status_code == 404

    def test_get_current_run_returns_no_active_run_detail(
        self, client: TestClient
    ) -> None:
        """GET /runs/current returns 'No active run' detail when no active run."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=None,
        ):
            response = client.get("/runs/current")
            json_body = response.json()
            assert json_body.get("detail") == "No active run"

    def test_get_current_run_returns_error_code_when_no_active_run(
        self, client: TestClient
    ) -> None:
        """GET /runs/current returns error code ERR-RUN-404 when no active run."""
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=None,
        ):
            response = client.get("/runs/current")
            json_body = response.json()
            error_code = json_body.get("error_code", "")
            assert error_code == "ERR-RUN-404"


class TestListRunsEmptyState:
    """Tests for GET /runs when no runs exist."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_runs_returns_200_when_no_runs_exist(
        self, client: TestClient
    ) -> None:
        """GET /runs returns HTTP 200 when no runs exist."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs")
            assert response.status_code == 200

    def test_get_runs_returns_empty_list_when_no_runs_exist(
        self, client: TestClient
    ) -> None:
        """GET /runs returns empty runs list when no runs exist."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert json_body.get("runs") == []

    def test_get_runs_returns_total_zero_when_no_runs_exist(
        self, client: TestClient
    ) -> None:
        """GET /runs returns total=0 when no runs exist."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": [], "total": 0},
        ):
            response = client.get("/runs")
            json_body = response.json()
            assert json_body.get("total") == 0


class TestRunsResponseFormat:
    """Tests for response format validation."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def single_run(self) -> list[dict[str, Any]]:
        """Create single run data for response format tests."""
        now = datetime.now(tz=timezone.utc)
        return [
            {
                "id": "run-format-test",
                "status": "completed",
                "spec_file": "test_spec.yaml",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "task_count": 5,
            }
        ]

    def test_get_runs_returns_json_content_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """GET /runs returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": single_run, "total": 1},
        ):
            response = client.get("/runs")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_run_by_id_returns_json_content_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """GET /runs/{id} returns Content-Type application/json."""
        run_data = single_run[0]
        with patch(
            "tdd_orchestrator.api.routes.runs.get_run_by_id",
            return_value=run_data,
        ):
            response = client.get(f"/runs/{run_data['id']}")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_current_run_returns_json_content_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """GET /runs/current returns Content-Type application/json."""
        run_data = single_run[0].copy()
        run_data["status"] = "running"
        with patch(
            "tdd_orchestrator.api.routes.runs.get_current_run",
            return_value=run_data,
        ):
            response = client.get("/runs/current")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_run_id_is_string_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """Run id field is a string."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": single_run, "total": 1},
        ):
            response = client.get("/runs")
            json_body = response.json()
            runs = json_body.get("runs", [])
            assert len(runs) >= 1
            assert isinstance(runs[0].get("id"), str)

    def test_run_status_is_string_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """Run status field is a string."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": single_run, "total": 1},
        ):
            response = client.get("/runs")
            json_body = response.json()
            runs = json_body.get("runs", [])
            assert len(runs) >= 1
            assert isinstance(runs[0].get("status"), str)

    def test_run_task_count_is_integer_type(
        self, client: TestClient, single_run: list[dict[str, Any]]
    ) -> None:
        """Run task_count field is an integer."""
        with patch(
            "tdd_orchestrator.api.routes.runs.list_runs",
            return_value={"runs": single_run, "total": 1},
        ):
            response = client.get("/runs")
            json_body = response.json()
            runs = json_body.get("runs", [])
            assert len(runs) >= 1
            assert isinstance(runs[0].get("task_count"), int)


class TestRunsMethodNotAllowed:
    """Tests for non-allowed HTTP methods on runs endpoints."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the runs router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/runs")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_runs_list_returns_405(self, client: TestClient) -> None:
        """POST /runs returns HTTP 405 Method Not Allowed."""
        response = client.post("/runs")
        assert response.status_code == 405

    def test_put_runs_list_returns_405(self, client: TestClient) -> None:
        """PUT /runs returns HTTP 405 Method Not Allowed."""
        response = client.put("/runs")
        assert response.status_code == 405

    def test_delete_runs_list_returns_405(self, client: TestClient) -> None:
        """DELETE /runs returns HTTP 405 Method Not Allowed."""
        response = client.delete("/runs")
        assert response.status_code == 405

    def test_put_run_by_id_returns_405(self, client: TestClient) -> None:
        """PUT /runs/{id} returns HTTP 405 Method Not Allowed."""
        response = client.put("/runs/some-run-id")
        assert response.status_code == 405

    def test_delete_run_by_id_returns_405(self, client: TestClient) -> None:
        """DELETE /runs/{id} returns HTTP 405 Method Not Allowed."""
        response = client.delete("/runs/some-run-id")
        assert response.status_code == 405

    def test_post_runs_current_returns_405(self, client: TestClient) -> None:
        """POST /runs/current returns HTTP 405 Method Not Allowed."""
        response = client.post("/runs/current")
        assert response.status_code == 405
