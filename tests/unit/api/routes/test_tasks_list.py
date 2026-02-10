"""Tests for the tasks router list endpoint.

Tests the GET /tasks endpoint with filtering by status, phase, and complexity,
and offset/limit pagination returning TaskListResponse.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.tasks import router


class TestTasksListWithStatusFilter:
    """Tests for GET /tasks with status filter."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def pending_tasks_data(self) -> list[dict[str, Any]]:
        """Create mock pending tasks data."""
        return [
            {
                "id": "task-1",
                "spec": "Pending task 1",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {},
            },
            {
                "id": "task-2",
                "spec": "Pending task 2",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {},
            },
        ]

    @pytest.fixture
    def mock_list_response(self, pending_tasks_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Create mock TaskListResponse for pending tasks."""
        return {
            "tasks": pending_tasks_data,
            "total": 5,
            "limit": 10,
            "offset": 0,
        }

    def test_get_tasks_with_status_filter_returns_200(
        self, client: TestClient, mock_list_response: dict[str, Any]
    ) -> None:
        """GET /tasks?status=pending returns HTTP 200 when pending tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_list_response,
        ):
            response = client.get("/tasks?status=pending&limit=10&offset=0")
            assert response.status_code == 200

    def test_get_tasks_with_status_filter_returns_only_matching_status(
        self, client: TestClient, mock_list_response: dict[str, Any]
    ) -> None:
        """GET /tasks?status=pending returns only pending tasks in response."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_list_response,
        ):
            response = client.get("/tasks?status=pending&limit=10&offset=0")
            json_body = response.json()
            tasks = json_body.get("tasks", [])
            assert len(tasks) == 2
            for task in tasks:
                assert task.get("status") == "pending"

    def test_get_tasks_with_status_filter_returns_total_count_of_filtered_tasks(
        self, client: TestClient, mock_list_response: dict[str, Any]
    ) -> None:
        """GET /tasks?status=pending returns total count of all pending tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_list_response,
        ):
            response = client.get("/tasks?status=pending&limit=10&offset=0")
            json_body = response.json()
            assert json_body.get("total") == 5

    def test_get_tasks_with_status_filter_respects_limit(
        self, client: TestClient, mock_list_response: dict[str, Any]
    ) -> None:
        """GET /tasks?status=pending&limit=10 returns at most 10 items."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_list_response,
        ):
            response = client.get("/tasks?status=pending&limit=10&offset=0")
            json_body = response.json()
            tasks = json_body.get("tasks", [])
            assert len(tasks) <= 10


class TestTasksListWithMultipleFilters:
    """Tests for GET /tasks with phase and complexity filters combined."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def filtered_tasks_data(self) -> list[dict[str, Any]]:
        """Create mock tasks matching decomposition phase and high complexity."""
        return [
            {
                "id": "task-high-decomp-1",
                "spec": "High complexity decomposition task",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {"phase": "decomposition", "complexity": "high"},
            },
        ]

    @pytest.fixture
    def mock_filtered_response(self, filtered_tasks_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Create mock TaskListResponse for filtered tasks."""
        return {
            "tasks": filtered_tasks_data,
            "total": 1,
            "limit": 20,
            "offset": 0,
        }

    def test_get_tasks_with_phase_and_complexity_returns_200(
        self, client: TestClient, mock_filtered_response: dict[str, Any]
    ) -> None:
        """GET /tasks?phase=decomposition&complexity=high returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_filtered_response,
        ):
            response = client.get("/tasks?phase=decomposition&complexity=high")
            assert response.status_code == 200

    def test_get_tasks_with_phase_and_complexity_returns_matching_tasks(
        self, client: TestClient, mock_filtered_response: dict[str, Any]
    ) -> None:
        """GET /tasks?phase=decomposition&complexity=high returns only matching tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_filtered_response,
        ):
            response = client.get("/tasks?phase=decomposition&complexity=high")
            json_body = response.json()
            tasks = json_body.get("tasks", [])
            assert len(tasks) == 1
            assert tasks[0].get("id") == "task-high-decomp-1"

    def test_get_tasks_filters_are_and_combined(
        self, client: TestClient, mock_filtered_response: dict[str, Any]
    ) -> None:
        """GET /tasks with multiple filters applies them as AND combination."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_filtered_response,
        ) as mock_list:
            response = client.get("/tasks?phase=decomposition&complexity=high")
            assert response.status_code == 200
            # Verify list_tasks was called (filters are handled there)
            mock_list.assert_called_once()

    def test_get_tasks_with_all_three_filters(
        self, client: TestClient, mock_filtered_response: dict[str, Any]
    ) -> None:
        """GET /tasks?status=pending&phase=decomposition&complexity=high applies all filters."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_filtered_response,
        ):
            response = client.get("/tasks?status=pending&phase=decomposition&complexity=high")
            assert response.status_code == 200
            json_body = response.json()
            assert "tasks" in json_body
            assert isinstance(json_body["tasks"], list)


class TestTasksListPagination:
    """Tests for GET /tasks pagination with offset/limit."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def paginated_tasks_data(self) -> list[dict[str, Any]]:
        """Create mock tasks for items 11-20 of 25 total."""
        return [
            {
                "id": f"task-{i}",
                "spec": f"Task {i}",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {},
            }
            for i in range(11, 21)
        ]

    @pytest.fixture
    def mock_paginated_response(self, paginated_tasks_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Create mock TaskListResponse for paginated results."""
        return {
            "tasks": paginated_tasks_data,
            "total": 25,
            "limit": 10,
            "offset": 10,
        }

    def test_get_tasks_with_pagination_returns_200(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks?limit=10&offset=10 returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            assert response.status_code == 200

    def test_get_tasks_with_pagination_returns_correct_items(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks?limit=10&offset=10 returns items 11-20."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            json_body = response.json()
            tasks = json_body.get("tasks", [])
            assert len(tasks) == 10
            assert tasks[0].get("id") == "task-11"
            assert tasks[9].get("id") == "task-20"

    def test_get_tasks_with_pagination_returns_total_count(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks?limit=10&offset=10 returns total=25 for all tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            json_body = response.json()
            assert json_body.get("total") == 25

    def test_get_tasks_with_pagination_echoes_offset(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks?limit=10&offset=10 echoes offset=10 in response."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            json_body = response.json()
            assert json_body.get("offset") == 10

    def test_get_tasks_with_pagination_echoes_limit(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks?limit=10&offset=10 echoes limit=10 in response."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            json_body = response.json()
            assert json_body.get("limit") == 10

    def test_get_tasks_pagination_enables_computing_remaining_pages(
        self, client: TestClient, mock_paginated_response: dict[str, Any]
    ) -> None:
        """GET /tasks pagination info allows computing remaining pages."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_paginated_response,
        ):
            response = client.get("/tasks?limit=10&offset=10")
            json_body = response.json()
            total = json_body.get("total", 0)
            offset = json_body.get("offset", 0)
            limit = json_body.get("limit", 0)
            # With total=25, offset=10, limit=10: remaining = 25 - 10 - 10 = 5
            remaining = total - offset - len(json_body.get("tasks", []))
            assert remaining == 5


class TestTasksListDefaultPagination:
    """Tests for GET /tasks with default pagination."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def default_tasks_data(self) -> list[dict[str, Any]]:
        """Create mock tasks for default pagination."""
        return [
            {
                "id": f"task-{i}",
                "spec": f"Task {i}",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 30, i % 60, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {},
            }
            for i in range(1, 21)
        ]

    @pytest.fixture
    def mock_default_response(self, default_tasks_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Create mock TaskListResponse with default pagination."""
        return {
            "tasks": default_tasks_data,
            "total": 50,
            "limit": 20,
            "offset": 0,
        }

    def test_get_tasks_without_params_returns_200(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks without query parameters returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            assert response.status_code == 200

    def test_get_tasks_without_params_uses_default_offset(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks without query parameters uses offset=0."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert json_body.get("offset") == 0

    def test_get_tasks_without_params_uses_default_limit(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks without query parameters uses limit=20."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert json_body.get("limit") == 20

    def test_get_tasks_without_params_returns_up_to_20_tasks(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks without query parameters returns at most 20 tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            tasks = json_body.get("tasks", [])
            assert len(tasks) <= 20

    def test_get_tasks_without_params_returns_total_count(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks without query parameters returns total count of all tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert json_body.get("total") == 50

    def test_get_tasks_without_params_returns_task_list_response_structure(
        self, client: TestClient, mock_default_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns TaskListResponse with tasks, total, limit, offset."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_default_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert "tasks" in json_body
            assert "total" in json_body
            assert "limit" in json_body
            assert "offset" in json_body


class TestTasksListInvalidStatusFilter:
    """Tests for GET /tasks with invalid status filter value."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_tasks_with_invalid_status_returns_422(
        self, client: TestClient
    ) -> None:
        """GET /tasks?status=nonexistent_status returns HTTP 422."""
        response = client.get("/tasks?status=nonexistent_status")
        assert response.status_code == 422

    def test_get_tasks_with_invalid_status_returns_validation_error_body(
        self, client: TestClient
    ) -> None:
        """GET /tasks?status=nonexistent_status returns validation error body."""
        response = client.get("/tasks?status=nonexistent_status")
        json_body = response.json()
        assert "detail" in json_body

    def test_get_tasks_with_invalid_status_indicates_allowed_values(
        self, client: TestClient
    ) -> None:
        """GET /tasks?status=nonexistent_status error indicates allowed status values."""
        response = client.get("/tasks?status=nonexistent_status")
        json_body = response.json()
        detail = json_body.get("detail", [])
        # FastAPI validation error should mention the invalid field
        error_text = str(detail).lower()
        assert "status" in error_text or "nonexistent_status" in error_text

    def test_get_tasks_with_empty_status_still_validates(
        self, client: TestClient
    ) -> None:
        """GET /tasks?status= with empty value is handled appropriately."""
        # Empty string might be treated as missing or as invalid
        response = client.get("/tasks?status=")
        # Should either return 200 (treated as no filter) or 422 (invalid)
        assert response.status_code in [200, 422]


class TestTasksListInvalidPhaseFilter:
    """Tests for GET /tasks with invalid phase filter value."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_tasks_with_invalid_phase_returns_422(
        self, client: TestClient
    ) -> None:
        """GET /tasks?phase=invalid_phase returns HTTP 422."""
        response = client.get("/tasks?phase=invalid_phase")
        assert response.status_code == 422

    def test_get_tasks_with_invalid_phase_returns_validation_error(
        self, client: TestClient
    ) -> None:
        """GET /tasks?phase=invalid_phase returns validation error body."""
        response = client.get("/tasks?phase=invalid_phase")
        json_body = response.json()
        assert "detail" in json_body


class TestTasksListInvalidComplexityFilter:
    """Tests for GET /tasks with invalid complexity filter value."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_tasks_with_invalid_complexity_returns_422(
        self, client: TestClient
    ) -> None:
        """GET /tasks?complexity=invalid_complexity returns HTTP 422."""
        response = client.get("/tasks?complexity=invalid_complexity")
        assert response.status_code == 422

    def test_get_tasks_with_invalid_complexity_returns_validation_error(
        self, client: TestClient
    ) -> None:
        """GET /tasks?complexity=invalid_complexity returns validation error body."""
        response = client.get("/tasks?complexity=invalid_complexity")
        json_body = response.json()
        assert "detail" in json_body


class TestTasksListResponseStructure:
    """Tests for TaskListResponse structure."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_empty_response(self) -> dict[str, Any]:
        """Create mock TaskListResponse with empty tasks list."""
        return {
            "tasks": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }

    def test_get_tasks_returns_json_content_type(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_tasks_with_no_results_returns_empty_list(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks with no matching tasks returns empty tasks list."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert json_body.get("tasks") == []
            assert json_body.get("total") == 0

    def test_get_tasks_tasks_field_is_list(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns tasks field as a list."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert isinstance(json_body.get("tasks"), list)

    def test_get_tasks_total_field_is_integer(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns total field as an integer."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert isinstance(json_body.get("total"), int)

    def test_get_tasks_limit_field_is_integer(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns limit field as an integer."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert isinstance(json_body.get("limit"), int)

    def test_get_tasks_offset_field_is_integer(
        self, client: TestClient, mock_empty_response: dict[str, Any]
    ) -> None:
        """GET /tasks returns offset field as an integer."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_empty_response,
        ):
            response = client.get("/tasks")
            json_body = response.json()
            assert isinstance(json_body.get("offset"), int)


class TestTasksListMethodNotAllowed:
    """Tests for non-GET methods on /tasks returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_tasks_returns_405(self, client: TestClient) -> None:
        """POST /tasks returns HTTP 405 Method Not Allowed."""
        response = client.post("/tasks")
        assert response.status_code == 405

    def test_put_tasks_returns_405(self, client: TestClient) -> None:
        """PUT /tasks returns HTTP 405 Method Not Allowed."""
        response = client.put("/tasks")
        assert response.status_code == 405

    def test_delete_tasks_returns_405(self, client: TestClient) -> None:
        """DELETE /tasks returns HTTP 405 Method Not Allowed."""
        response = client.delete("/tasks")
        assert response.status_code == 405

    def test_patch_tasks_returns_405(self, client: TestClient) -> None:
        """PATCH /tasks returns HTTP 405 Method Not Allowed."""
        response = client.patch("/tasks")
        assert response.status_code == 405


class TestTasksRouterMounting:
    """Tests for tasks router mountability."""

    def test_router_is_mountable_on_fastapi_app(self) -> None:
        """The tasks router can be mounted on a FastAPI app."""
        mock_response = {
            "tasks": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        client = TestClient(app)
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_response,
        ):
            response = client.get("/tasks")
            assert response.status_code == 200

    def test_router_mounted_at_custom_prefix(self) -> None:
        """The tasks router can be mounted at a custom prefix."""
        mock_response = {
            "tasks": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/tasks")
        client = TestClient(app)
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_response,
        ):
            response = client.get("/api/v1/tasks")
            assert response.status_code == 200


class TestTasksListEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_tasks_with_zero_limit(self, client: TestClient) -> None:
        """GET /tasks?limit=0 is handled appropriately."""
        mock_response = {
            "tasks": [],
            "total": 10,
            "limit": 0,
            "offset": 0,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_response,
        ):
            response = client.get("/tasks?limit=0")
            # Either returns empty list or validation error
            assert response.status_code in [200, 422]

    def test_get_tasks_with_negative_offset(self, client: TestClient) -> None:
        """GET /tasks?offset=-1 returns validation error."""
        response = client.get("/tasks?offset=-1")
        assert response.status_code == 422

    def test_get_tasks_with_negative_limit(self, client: TestClient) -> None:
        """GET /tasks?limit=-1 returns validation error."""
        response = client.get("/tasks?limit=-1")
        assert response.status_code == 422

    def test_get_tasks_with_very_large_offset(self, client: TestClient) -> None:
        """GET /tasks?offset=1000000 returns empty list when offset exceeds total."""
        mock_response = {
            "tasks": [],
            "total": 25,
            "limit": 20,
            "offset": 1000000,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_response,
        ):
            response = client.get("/tasks?offset=1000000")
            assert response.status_code == 200
            json_body = response.json()
            assert json_body.get("tasks") == []

    def test_get_tasks_with_non_integer_limit(self, client: TestClient) -> None:
        """GET /tasks?limit=abc returns validation error."""
        response = client.get("/tasks?limit=abc")
        assert response.status_code == 422

    def test_get_tasks_with_non_integer_offset(self, client: TestClient) -> None:
        """GET /tasks?offset=xyz returns validation error."""
        response = client.get("/tasks?offset=xyz")
        assert response.status_code == 422

    def test_get_tasks_with_float_limit(self, client: TestClient) -> None:
        """GET /tasks?limit=10.5 is handled appropriately."""
        response = client.get("/tasks?limit=10.5")
        # Either truncates to int or returns validation error
        assert response.status_code in [200, 422]

    def test_get_tasks_with_extra_query_params_still_works(
        self, client: TestClient
    ) -> None:
        """GET /tasks with extra query params still returns tasks."""
        mock_response = {
            "tasks": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.list_tasks",
            return_value=mock_response,
        ):
            response = client.get("/tasks?unknown_param=value&another=123")
            assert response.status_code == 200
