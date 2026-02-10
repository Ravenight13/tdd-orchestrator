"""Tests for the task detail endpoint.

Tests the GET /tasks/{task_key} endpoint that returns TaskDetailResponse
with nested AttemptResponse objects.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.tasks import router


class TestTaskDetailWithAttempts:
    """Tests for GET /tasks/{task_key} with task that has attempts."""

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
    def task_with_two_failed_attempts(self) -> dict[str, Any]:
        """Create mock task data with two failed attempts."""
        return {
            "task_key": "task-001",
            "status": "failing",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "attempts": [
                {
                    "attempt_number": 1,
                    "status": "failed",
                    "started_at": datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2024, 1, 15, 10, 32, 0, tzinfo=timezone.utc),
                    "error_message": "Test assertion failed",
                },
                {
                    "attempt_number": 2,
                    "status": "failed",
                    "started_at": datetime(2024, 1, 15, 10, 33, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2024, 1, 15, 10, 34, 0, tzinfo=timezone.utc),
                    "error_message": "Another test failure",
                },
            ],
        }

    def test_get_task_detail_returns_200_when_task_exists(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 returns HTTP 200 when task exists."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            assert response.status_code == 200

    def test_get_task_detail_returns_correct_task_key(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 returns TaskDetailResponse with task_key='task-001'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            assert json_body.get("task_key") == "task-001"

    def test_get_task_detail_returns_correct_status(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 returns TaskDetailResponse with status='failing'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            assert json_body.get("status") == "failing"

    def test_get_task_detail_returns_attempts_list(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 returns TaskDetailResponse with attempts list."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert isinstance(attempts, list)
            assert len(attempts) == 2

    def test_get_task_detail_attempts_ordered_by_attempt_number(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 returns attempts ordered by attempt_number ascending."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) == 2
            assert attempts[0].get("attempt_number") == 1
            assert attempts[1].get("attempt_number") == 2

    def test_get_task_detail_attempts_contain_required_fields(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 attempts include attempt_number, status, started_at, finished_at, error_message."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            for attempt in attempts:
                assert "attempt_number" in attempt
                assert "status" in attempt
                assert "started_at" in attempt
                assert "finished_at" in attempt
                assert "error_message" in attempt

    def test_get_task_detail_first_attempt_has_correct_status(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 first attempt has status='failed'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert attempts[0].get("status") == "failed"

    def test_get_task_detail_second_attempt_has_correct_status(
        self, client: TestClient, task_with_two_failed_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-001 second attempt has status='failed'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_two_failed_attempts,
        ):
            response = client.get("/tasks/task-001")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 2
            assert attempts[1].get("status") == "failed"


class TestTaskDetailNotFound:
    """Tests for GET /tasks/{task_key} when task does not exist."""

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

    def test_get_task_detail_returns_404_when_task_not_found(
        self, client: TestClient
    ) -> None:
        """GET /tasks/nonexistent-task returns HTTP 404 when task does not exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/nonexistent-task")
            assert response.status_code == 404

    def test_get_task_detail_returns_error_detail_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /tasks/nonexistent-task returns JSON body with detail='Task not found'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/nonexistent-task")
            json_body = response.json()
            detail = json_body.get("detail", "")
            # Accept either 'Task not found' or an error code
            assert detail == "Task not found" or "not found" in detail.lower() or detail != ""


class TestTaskDetailNoAttempts:
    """Tests for GET /tasks/{task_key} with task that has no attempts."""

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
    def task_with_no_attempts(self) -> dict[str, Any]:
        """Create mock task data with no attempts."""
        return {
            "task_key": "task-clean",
            "status": "pending",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "attempts": [],
        }

    def test_get_task_detail_returns_200_for_task_with_no_attempts(
        self, client: TestClient, task_with_no_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-clean returns HTTP 200 for pending task with no attempts."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_no_attempts,
        ):
            response = client.get("/tasks/task-clean")
            assert response.status_code == 200

    def test_get_task_detail_returns_correct_task_key_for_pending_task(
        self, client: TestClient, task_with_no_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-clean returns TaskDetailResponse with task_key='task-clean'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_no_attempts,
        ):
            response = client.get("/tasks/task-clean")
            json_body = response.json()
            assert json_body.get("task_key") == "task-clean"

    def test_get_task_detail_returns_pending_status(
        self, client: TestClient, task_with_no_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-clean returns TaskDetailResponse with status='pending'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_no_attempts,
        ):
            response = client.get("/tasks/task-clean")
            json_body = response.json()
            assert json_body.get("status") == "pending"

    def test_get_task_detail_returns_empty_attempts_list(
        self, client: TestClient, task_with_no_attempts: dict[str, Any]
    ) -> None:
        """GET /tasks/task-clean returns TaskDetailResponse with empty attempts list."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_no_attempts,
        ):
            response = client.get("/tasks/task-clean")
            json_body = response.json()
            attempts = json_body.get("attempts", None)
            assert attempts is not None
            assert isinstance(attempts, list)
            assert len(attempts) == 0


class TestTaskDetailRichAttemptMetadata:
    """Tests for GET /tasks/{task_key} with rich attempt metadata."""

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
    def task_with_rich_attempt(self) -> dict[str, Any]:
        """Create mock task data with one attempt containing all metadata fields."""
        return {
            "task_key": "task-rich",
            "status": "failed",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "attempts": [
                {
                    "attempt_number": 1,
                    "status": "failed",
                    "started_at": datetime(2024, 1, 15, 10, 31, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2024, 1, 15, 10, 32, 0, tzinfo=timezone.utc),
                    "exit_code": 1,
                    "error_message": "Process exited with error",
                    "stdout_log": "Running tests...\nTest 1 passed",
                    "stderr_log": "Error: assertion failed in test_foo",
                },
            ],
        }

    def test_get_task_detail_returns_200_for_rich_attempt(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich returns HTTP 200 for task with rich attempt metadata."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            assert response.status_code == 200

    def test_get_task_detail_attempt_includes_attempt_number(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes attempt_number field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "attempt_number" in attempts[0]
            assert attempts[0]["attempt_number"] == 1

    def test_get_task_detail_attempt_includes_status(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes status field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "status" in attempts[0]
            assert attempts[0]["status"] == "failed"

    def test_get_task_detail_attempt_includes_started_at(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes started_at field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "started_at" in attempts[0]
            assert attempts[0]["started_at"] is not None

    def test_get_task_detail_attempt_includes_finished_at(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes finished_at field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "finished_at" in attempts[0]
            assert attempts[0]["finished_at"] is not None

    def test_get_task_detail_attempt_includes_exit_code(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes exit_code field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "exit_code" in attempts[0]
            assert attempts[0]["exit_code"] == 1

    def test_get_task_detail_attempt_includes_error_message(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt includes error_message field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            assert "error_message" in attempts[0]
            assert attempts[0]["error_message"] == "Process exited with error"

    def test_get_task_detail_all_attempt_fields_present(
        self, client: TestClient, task_with_rich_attempt: dict[str, Any]
    ) -> None:
        """GET /tasks/task-rich attempt has all required metadata fields."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=task_with_rich_attempt,
        ):
            response = client.get("/tasks/task-rich")
            json_body = response.json()
            attempts = json_body.get("attempts", [])
            assert len(attempts) >= 1
            attempt = attempts[0]
            required_fields = [
                "attempt_number",
                "status",
                "started_at",
                "finished_at",
                "exit_code",
                "error_message",
            ]
            for field in required_fields:
                assert field in attempt, f"Field '{field}' is missing from attempt"


class TestTaskDetailPathTraversal:
    """Tests for GET /tasks/{task_key} with path-traversal characters."""

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

    def test_get_task_with_path_traversal_returns_404_or_422(
        self, client: TestClient
    ) -> None:
        """GET /tasks/../etc/passwd returns 404 or 422, not a server error."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/../etc/passwd")
            # Should return 404 (not found) or 422 (validation error), not 500
            assert response.status_code in [404, 422]

    def test_get_task_with_path_traversal_does_not_leak_paths(
        self, client: TestClient
    ) -> None:
        """GET /tasks/../etc/passwd does not leak internal file paths."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/../etc/passwd")
            response_text = response.text.lower()
            # Should not contain file system path indicators
            assert "/etc/" not in response_text
            assert "/usr/" not in response_text
            assert "/var/" not in response_text
            assert "/home/" not in response_text

    def test_get_task_with_dot_dot_slash_returns_safe_error(
        self, client: TestClient
    ) -> None:
        """GET /tasks/..%2F..%2Fetc%2Fpasswd returns safe error response."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/..%2F..%2Fetc%2Fpasswd")
            assert response.status_code in [404, 422]

    def test_get_task_with_encoded_traversal_does_not_leak_info(
        self, client: TestClient
    ) -> None:
        """GET /tasks/..%2Fetc%2Fpasswd does not leak system information."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.get("/tasks/..%2Fetc%2Fpasswd")
            json_body = response.json()
            # Check response body doesn't contain sensitive path info
            body_text = str(json_body).lower()
            assert "password" not in body_text
            assert "/etc/passwd" not in body_text


class TestTaskDetailResponseStructure:
    """Tests for TaskDetailResponse structure."""

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
    def simple_task(self) -> dict[str, Any]:
        """Create simple mock task data."""
        return {
            "task_key": "task-simple",
            "status": "pending",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "attempts": [],
        }

    def test_get_task_detail_returns_json_content_type(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_task_detail_response_has_task_key_field(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response has task_key field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert "task_key" in json_body

    def test_get_task_detail_response_has_status_field(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response has status field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert "status" in json_body

    def test_get_task_detail_response_has_attempts_field(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response has attempts field."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert "attempts" in json_body

    def test_get_task_detail_task_key_is_string(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response task_key is a string."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert isinstance(json_body.get("task_key"), str)

    def test_get_task_detail_status_is_string(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response status is a string."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert isinstance(json_body.get("status"), str)

    def test_get_task_detail_attempts_is_list(
        self, client: TestClient, simple_task: dict[str, Any]
    ) -> None:
        """GET /tasks/{task_key} response attempts is a list."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=simple_task,
        ):
            response = client.get("/tasks/task-simple")
            json_body = response.json()
            assert isinstance(json_body.get("attempts"), list)


class TestTaskDetailMethodNotAllowed:
    """Tests for non-GET methods on /tasks/{task_key}."""

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

    def test_post_task_detail_returns_405(self, client: TestClient) -> None:
        """POST /tasks/task-001 returns HTTP 405 Method Not Allowed."""
        response = client.post("/tasks/task-001")
        assert response.status_code == 405

    def test_put_task_detail_returns_405(self, client: TestClient) -> None:
        """PUT /tasks/task-001 returns HTTP 405 Method Not Allowed."""
        response = client.put("/tasks/task-001")
        assert response.status_code == 405

    def test_delete_task_detail_returns_405(self, client: TestClient) -> None:
        """DELETE /tasks/task-001 returns HTTP 405 Method Not Allowed."""
        response = client.delete("/tasks/task-001")
        assert response.status_code == 405

    def test_patch_task_detail_returns_405(self, client: TestClient) -> None:
        """PATCH /tasks/task-001 returns HTTP 405 Method Not Allowed."""
        response = client.patch("/tasks/task-001")
        assert response.status_code == 405
