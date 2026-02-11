"""Tests for the workers router endpoints.

Tests the GET /workers, GET /workers/{worker_id}, and GET /workers/stale endpoints
that return WorkerListResponse and WorkerResponse models.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.workers import router


class TestGetWorkersList:
    """Tests for GET /workers endpoint with workers in database."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def three_workers_data(self) -> list[dict[str, Any]]:
        """Create mock data for three workers."""
        now = datetime.now(timezone.utc)
        return [
            {
                "worker_id": "worker-001",
                "status": "idle",
                "last_heartbeat": now - timedelta(seconds=10),
                "current_task_id": None,
            },
            {
                "worker_id": "worker-002",
                "status": "busy",
                "last_heartbeat": now - timedelta(seconds=5),
                "current_task_id": "task-abc",
            },
            {
                "worker_id": "worker-003",
                "status": "idle",
                "last_heartbeat": now - timedelta(seconds=20),
                "current_task_id": None,
            },
        ]

    def test_get_workers_returns_200_when_workers_exist(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers returns HTTP 200 when workers exist in database."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            assert response.status_code == 200

    def test_get_workers_returns_correct_total(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers returns WorkerListResponse with total=3 for 3 workers."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            assert json_body.get("total") == 3

    def test_get_workers_returns_items_list(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers returns WorkerListResponse with items containing all workers."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", [])
            assert isinstance(items, list)
            assert len(items) == 3

    def test_get_workers_items_contain_worker_id(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers response items contain worker_id field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", [])
            for item in items:
                assert "worker_id" in item

    def test_get_workers_items_contain_status(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers response items contain status field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", [])
            for item in items:
                assert "status" in item

    def test_get_workers_items_contain_last_heartbeat(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers response items contain last_heartbeat field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", [])
            for item in items:
                assert "last_heartbeat" in item

    def test_get_workers_items_contain_current_task_id(
        self, client: TestClient, three_workers_data: list[dict[str, Any]]
    ) -> None:
        """GET /workers response items contain current_task_id field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": three_workers_data, "total": 3},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", [])
            for item in items:
                assert "current_task_id" in item


class TestGetWorkersListEmpty:
    """Tests for GET /workers endpoint when database is empty."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_workers_returns_200_when_no_workers(
        self, client: TestClient
    ) -> None:
        """GET /workers returns HTTP 200 when no workers exist."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers")
            assert response.status_code == 200

    def test_get_workers_returns_empty_items_when_no_workers(
        self, client: TestClient
    ) -> None:
        """GET /workers returns WorkerListResponse with empty items list."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers")
            json_body = response.json()
            items = json_body.get("items", None)
            assert items is not None
            assert isinstance(items, list)
            assert len(items) == 0

    def test_get_workers_returns_total_zero_when_no_workers(
        self, client: TestClient
    ) -> None:
        """GET /workers returns WorkerListResponse with total=0."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers")
            json_body = response.json()
            assert json_body.get("total") == 0


class TestGetWorkerById:
    """Tests for GET /workers/{worker_id} endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def worker_abc_data(self) -> dict[str, Any]:
        """Create mock data for worker-abc."""
        return {
            "worker_id": "worker-abc",
            "status": "busy",
            "last_heartbeat": datetime.now(timezone.utc) - timedelta(seconds=15),
            "current_task_id": "task-xyz",
        }

    def test_get_worker_by_id_returns_200_when_exists(
        self, client: TestClient, worker_abc_data: dict[str, Any]
    ) -> None:
        """GET /workers/worker-abc returns HTTP 200 when worker exists."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=worker_abc_data,
        ):
            response = client.get("/workers/worker-abc")
            assert response.status_code == 200

    def test_get_worker_by_id_returns_correct_worker_id(
        self, client: TestClient, worker_abc_data: dict[str, Any]
    ) -> None:
        """GET /workers/worker-abc returns WorkerResponse with worker_id='worker-abc'."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=worker_abc_data,
        ):
            response = client.get("/workers/worker-abc")
            json_body = response.json()
            assert json_body.get("worker_id") == "worker-abc"

    def test_get_worker_by_id_returns_status_field(
        self, client: TestClient, worker_abc_data: dict[str, Any]
    ) -> None:
        """GET /workers/worker-abc returns WorkerResponse with status field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=worker_abc_data,
        ):
            response = client.get("/workers/worker-abc")
            json_body = response.json()
            assert "status" in json_body
            assert json_body.get("status") == "busy"

    def test_get_worker_by_id_returns_last_heartbeat_field(
        self, client: TestClient, worker_abc_data: dict[str, Any]
    ) -> None:
        """GET /workers/worker-abc returns WorkerResponse with last_heartbeat field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=worker_abc_data,
        ):
            response = client.get("/workers/worker-abc")
            json_body = response.json()
            assert "last_heartbeat" in json_body

    def test_get_worker_by_id_returns_current_task_id_field(
        self, client: TestClient, worker_abc_data: dict[str, Any]
    ) -> None:
        """GET /workers/worker-abc returns WorkerResponse with current_task_id field."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=worker_abc_data,
        ):
            response = client.get("/workers/worker-abc")
            json_body = response.json()
            assert "current_task_id" in json_body
            assert json_body.get("current_task_id") == "task-xyz"

    def test_get_worker_by_id_returns_404_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /workers/nonexistent-id returns HTTP 404 when worker does not exist."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=None,
        ):
            response = client.get("/workers/nonexistent-id")
            assert response.status_code == 404

    def test_get_worker_by_id_returns_detail_message_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /workers/nonexistent-id returns JSON body with detail message."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value=None,
        ):
            response = client.get("/workers/nonexistent-id")
            json_body = response.json()
            detail = json_body.get("detail", "")
            # Accept error messages containing 'not found' or similar
            assert detail != "" and ("not found" in detail.lower() or "worker" in detail.lower())


class TestGetStaleWorkers:
    """Tests for GET /workers/stale endpoint with stale workers."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def workers_with_stale(self) -> dict[str, Any]:
        """Create mock data with 2 stale workers and 1 recent worker.

        Staleness threshold is >60 seconds since last heartbeat.
        """
        now = datetime.now(timezone.utc)
        stale_workers = [
            {
                "worker_id": "worker-stale-001",
                "status": "idle",
                "last_heartbeat": now - timedelta(seconds=120),  # 2 minutes ago - stale
                "current_task_id": None,
            },
            {
                "worker_id": "worker-stale-002",
                "status": "busy",
                "last_heartbeat": now - timedelta(seconds=90),  # 1.5 minutes ago - stale
                "current_task_id": "task-stuck",
            },
        ]
        return {"items": stale_workers, "total": 2}

    def test_get_stale_workers_returns_200(
        self, client: TestClient, workers_with_stale: dict[str, Any]
    ) -> None:
        """GET /workers/stale returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value=workers_with_stale,
        ):
            response = client.get("/workers/stale")
            assert response.status_code == 200

    def test_get_stale_workers_returns_correct_total(
        self, client: TestClient, workers_with_stale: dict[str, Any]
    ) -> None:
        """GET /workers/stale returns WorkerListResponse with total=2."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value=workers_with_stale,
        ):
            response = client.get("/workers/stale")
            json_body = response.json()
            assert json_body.get("total") == 2

    def test_get_stale_workers_returns_only_stale_workers(
        self, client: TestClient, workers_with_stale: dict[str, Any]
    ) -> None:
        """GET /workers/stale returns only workers with stale heartbeats."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value=workers_with_stale,
        ):
            response = client.get("/workers/stale")
            json_body = response.json()
            items = json_body.get("items", [])
            assert len(items) == 2
            worker_ids = [w.get("worker_id") for w in items]
            assert "worker-stale-001" in worker_ids
            assert "worker-stale-002" in worker_ids

    def test_get_stale_workers_items_contain_required_fields(
        self, client: TestClient, workers_with_stale: dict[str, Any]
    ) -> None:
        """GET /workers/stale items contain worker_id, status, last_heartbeat, current_task_id."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value=workers_with_stale,
        ):
            response = client.get("/workers/stale")
            json_body = response.json()
            items = json_body.get("items", [])
            for item in items:
                assert "worker_id" in item
                assert "status" in item
                assert "last_heartbeat" in item
                assert "current_task_id" in item


class TestGetStaleWorkersEmpty:
    """Tests for GET /workers/stale endpoint when no workers are stale."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_stale_workers_returns_200_when_no_stale(
        self, client: TestClient
    ) -> None:
        """GET /workers/stale returns HTTP 200 when no workers are stale."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers/stale")
            assert response.status_code == 200

    def test_get_stale_workers_returns_empty_items_when_no_stale(
        self, client: TestClient
    ) -> None:
        """GET /workers/stale returns WorkerListResponse with empty items list."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers/stale")
            json_body = response.json()
            items = json_body.get("items", None)
            assert items is not None
            assert isinstance(items, list)
            assert len(items) == 0

    def test_get_stale_workers_returns_total_zero_when_no_stale(
        self, client: TestClient
    ) -> None:
        """GET /workers/stale returns WorkerListResponse with total=0."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers/stale")
            json_body = response.json()
            assert json_body.get("total") == 0


class TestWorkersResponseStructure:
    """Tests for worker endpoints response structure."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_workers_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """GET /workers returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_workers_stale_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """GET /workers/stale returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.workers.list_stale_workers",
            return_value={"items": [], "total": 0},
        ):
            response = client.get("/workers/stale")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_worker_by_id_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """GET /workers/{worker_id} returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.workers.get_worker_by_id",
            return_value={
                "worker_id": "worker-test",
                "status": "idle",
                "last_heartbeat": datetime.now(timezone.utc),
                "current_task_id": None,
            },
        ):
            response = client.get("/workers/worker-test")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type


class TestWorkersMethodNotAllowed:
    """Tests for non-GET methods on worker endpoints returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the workers router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/workers")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_workers_returns_405(self, client: TestClient) -> None:
        """POST /workers returns HTTP 405 Method Not Allowed."""
        response = client.post("/workers")
        assert response.status_code == 405

    def test_put_workers_returns_405(self, client: TestClient) -> None:
        """PUT /workers returns HTTP 405 Method Not Allowed."""
        response = client.put("/workers")
        assert response.status_code == 405

    def test_delete_workers_returns_405(self, client: TestClient) -> None:
        """DELETE /workers returns HTTP 405 Method Not Allowed."""
        response = client.delete("/workers")
        assert response.status_code == 405

    def test_patch_workers_returns_405(self, client: TestClient) -> None:
        """PATCH /workers returns HTTP 405 Method Not Allowed."""
        response = client.patch("/workers")
        assert response.status_code == 405

    def test_post_workers_stale_returns_405(self, client: TestClient) -> None:
        """POST /workers/stale returns HTTP 405 Method Not Allowed."""
        response = client.post("/workers/stale")
        assert response.status_code == 405

    def test_put_workers_stale_returns_405(self, client: TestClient) -> None:
        """PUT /workers/stale returns HTTP 405 Method Not Allowed."""
        response = client.put("/workers/stale")
        assert response.status_code == 405

    def test_delete_workers_stale_returns_405(self, client: TestClient) -> None:
        """DELETE /workers/stale returns HTTP 405 Method Not Allowed."""
        response = client.delete("/workers/stale")
        assert response.status_code == 405

    def test_patch_workers_stale_returns_405(self, client: TestClient) -> None:
        """PATCH /workers/stale returns HTTP 405 Method Not Allowed."""
        response = client.patch("/workers/stale")
        assert response.status_code == 405
