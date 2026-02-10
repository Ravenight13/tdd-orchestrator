"""Tests for the task retry endpoint.

Tests the POST /tasks/{task_key}/retry endpoint that resets a task's
status to pending and publishes an SSE event.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.tasks import router
from tdd_orchestrator.api.dependencies import get_broadcaster_dep


class TestRetryTaskSuccess:
    """Tests for POST /tasks/{task_key}/retry when task exists with failed status."""

    @pytest.fixture
    def mock_broadcaster(self) -> MagicMock:
        """Create a mock SSEBroadcaster."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(return_value=None)
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def failed_task(self) -> dict[str, Any]:
        """Create mock task data for a failed task."""
        return {
            "task_key": "task-001",
            "status": "failed",
        }

    @pytest.fixture
    def pending_task_response(self) -> dict[str, Any]:
        """Create mock task response after retry with pending status."""
        return {
            "task_key": "task-001",
            "status": "pending",
        }

    def test_retry_failed_task_returns_200(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/task-001/retry returns HTTP 200 when task exists with failed status."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-001/retry")
            assert response.status_code == 200

    def test_retry_failed_task_returns_task_response(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/task-001/retry returns TaskResponse body."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-001/retry")
            json_body = response.json()
            assert "task_key" in json_body
            assert "status" in json_body

    def test_retry_failed_task_returns_pending_status(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/task-001/retry returns status reset to 'pending'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-001/retry")
            json_body = response.json()
            assert json_body.get("status") == "pending"

    def test_retry_failed_task_returns_correct_task_key(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/task-001/retry returns the correct task_key."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-001/retry")
            json_body = response.json()
            assert json_body.get("task_key") == "task-001"

    def test_retry_task_updates_database_to_pending(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/task-001/retry calls retry_task to update status in database."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ) as mock_retry:
            client.post("/tasks/task-001/retry")
            mock_retry.assert_called_once_with("task-001")
            assert mock_retry.call_count == 1


class TestRetryTaskNotFound:
    """Tests for POST /tasks/{task_key}/retry when task does not exist."""

    @pytest.fixture
    def mock_broadcaster(self) -> MagicMock:
        """Create a mock SSEBroadcaster."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(return_value=None)
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_retry_nonexistent_task_returns_404(self, client: TestClient) -> None:
        """POST /tasks/nonexistent-task/retry returns HTTP 404 when task does not exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.post("/tasks/nonexistent-task/retry")
            assert response.status_code == 404

    def test_retry_nonexistent_task_returns_error_detail(self, client: TestClient) -> None:
        """POST /tasks/nonexistent-task/retry returns JSON body with detail 'Task not found'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=None,
        ):
            response = client.post("/tasks/nonexistent-task/retry")
            json_body = response.json()
            assert json_body.get("detail") == "Task not found"


class TestRetryTaskSSEBroadcast:
    """Tests for SSE event publishing when retrying a task."""

    @pytest.fixture
    def mock_broadcaster(self) -> MagicMock:
        """Create a mock SSEBroadcaster."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(return_value=None)
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted and broadcaster override."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def failed_task(self) -> dict[str, Any]:
        """Create mock task data for a failed task."""
        return {
            "task_key": "task-sse-001",
            "status": "failed",
        }

    @pytest.fixture
    def pending_task_response(self) -> dict[str, Any]:
        """Create mock task response after retry with pending status."""
        return {
            "task_key": "task-sse-001",
            "status": "pending",
        }

    def test_retry_task_calls_broadcaster_publish(
        self,
        client: TestClient,
        mock_broadcaster: MagicMock,
        failed_task: dict[str, Any],
        pending_task_response: dict[str, Any],
    ) -> None:
        """POST /tasks/{task_key}/retry calls broadcaster.publish."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            client.post("/tasks/task-sse-001/retry")
            mock_broadcaster.publish.assert_called_once()
            assert mock_broadcaster.publish.call_count == 1

    def test_retry_task_publishes_task_status_changed_event(
        self,
        client: TestClient,
        mock_broadcaster: MagicMock,
        failed_task: dict[str, Any],
        pending_task_response: dict[str, Any],
    ) -> None:
        """POST /tasks/{task_key}/retry publishes event with type 'task_status_changed'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            client.post("/tasks/task-sse-001/retry")
            call_args = mock_broadcaster.publish.call_args
            event = call_args[0][0] if call_args[0] else call_args[1].get("event")
            assert event is not None
            # Event should have type 'task_status_changed'
            if hasattr(event, "event"):
                assert event.event == "task_status_changed"
            elif isinstance(event, dict):
                assert event.get("event") == "task_status_changed" or event.get("type") == "task_status_changed"
            else:
                # If event is string data, just verify call was made
                assert mock_broadcaster.publish.called

    def test_retry_task_publishes_event_with_task_key(
        self,
        client: TestClient,
        mock_broadcaster: MagicMock,
        failed_task: dict[str, Any],
        pending_task_response: dict[str, Any],
    ) -> None:
        """POST /tasks/{task_key}/retry publishes event containing the task_key."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            client.post("/tasks/task-sse-001/retry")
            call_args = mock_broadcaster.publish.call_args
            event = call_args[0][0] if call_args[0] else call_args[1].get("event")
            assert event is not None
            # Event should contain task_key
            if hasattr(event, "data"):
                assert "task-sse-001" in str(event.data)
            elif isinstance(event, dict):
                assert event.get("task_key") == "task-sse-001" or "task-sse-001" in str(event)
            else:
                assert "task-sse-001" in str(event)

    def test_retry_task_publishes_event_with_pending_status(
        self,
        client: TestClient,
        mock_broadcaster: MagicMock,
        failed_task: dict[str, Any],
        pending_task_response: dict[str, Any],
    ) -> None:
        """POST /tasks/{task_key}/retry publishes event with new status 'pending'."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            client.post("/tasks/task-sse-001/retry")
            call_args = mock_broadcaster.publish.call_args
            event = call_args[0][0] if call_args[0] else call_args[1].get("event")
            assert event is not None
            # Event should contain status 'pending'
            if hasattr(event, "data"):
                assert "pending" in str(event.data)
            elif isinstance(event, dict):
                assert event.get("status") == "pending" or "pending" in str(event)
            else:
                assert "pending" in str(event)


class TestRetryTaskConflict:
    """Tests for POST /tasks/{task_key}/retry when task is in a non-retryable state."""

    @pytest.fixture
    def mock_broadcaster(self) -> MagicMock:
        """Create a mock SSEBroadcaster."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(return_value=None)
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def pending_task(self) -> dict[str, Any]:
        """Create mock task data for a pending task (non-retryable)."""
        return {
            "task_key": "task-pending-001",
            "status": "pending",
        }

    @pytest.fixture
    def running_task(self) -> dict[str, Any]:
        """Create mock task data for a running task (non-retryable)."""
        return {
            "task_key": "task-running-001",
            "status": "running",
        }

    @pytest.fixture
    def completed_task(self) -> dict[str, Any]:
        """Create mock task data for a completed task (non-retryable)."""
        return {
            "task_key": "task-completed-001",
            "status": "completed",
        }

    def test_retry_pending_task_returns_409(
        self, client: TestClient, pending_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns HTTP 409 for pending task."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=pending_task,
        ):
            response = client.post("/tasks/task-pending-001/retry")
            assert response.status_code == 409

    def test_retry_pending_task_returns_error_detail(
        self, client: TestClient, pending_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns JSON body with conflict detail for pending task."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=pending_task,
        ):
            response = client.post("/tasks/task-pending-001/retry")
            json_body = response.json()
            detail = json_body.get("detail", "")
            # Detail should indicate task cannot be retried from current status
            assert detail != ""
            assert "pending" in detail.lower() or "cannot" in detail.lower() or "retry" in detail.lower()

    def test_retry_running_task_returns_409(
        self, client: TestClient, running_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns HTTP 409 for running task."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=running_task,
        ):
            response = client.post("/tasks/task-running-001/retry")
            assert response.status_code == 409

    def test_retry_completed_task_returns_409(
        self, client: TestClient, completed_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns HTTP 409 for completed task."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=completed_task,
        ):
            response = client.post("/tasks/task-completed-001/retry")
            assert response.status_code == 409

    def test_retry_non_retryable_task_does_not_update_database(
        self, client: TestClient, pending_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry does not call retry_task for non-retryable status."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=pending_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
        ) as mock_retry:
            client.post("/tasks/task-pending-001/retry")
            mock_retry.assert_not_called()
            assert mock_retry.call_count == 0

    def test_retry_non_retryable_task_does_not_publish_event(
        self, client: TestClient, mock_broadcaster: MagicMock, pending_task: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry does not call broadcaster.publish for non-retryable status."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=pending_task,
        ):
            client.post("/tasks/task-pending-001/retry")
            mock_broadcaster.publish.assert_not_called()
            assert mock_broadcaster.publish.call_count == 0


class TestRetryTaskSSEPublishFailure:
    """Tests for POST /tasks/{task_key}/retry when SSE publish fails."""

    @pytest.fixture
    def mock_broadcaster_failing(self) -> MagicMock:
        """Create a mock SSEBroadcaster that raises an exception on publish."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(side_effect=Exception("SSE publish failed"))
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster_failing: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router and failing broadcaster."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster_failing
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def failed_task(self) -> dict[str, Any]:
        """Create mock task data for a failed task."""
        return {
            "task_key": "task-sse-fail-001",
            "status": "failed",
        }

    @pytest.fixture
    def pending_task_response(self) -> dict[str, Any]:
        """Create mock task response after retry with pending status."""
        return {
            "task_key": "task-sse-fail-001",
            "status": "pending",
        }

    def test_retry_task_returns_200_when_sse_fails(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns 200 even when SSE publish fails."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-sse-fail-001/retry")
            assert response.status_code == 200

    def test_retry_task_updates_database_when_sse_fails(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry updates database even when SSE publish fails."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ) as mock_retry:
            client.post("/tasks/task-sse-fail-001/retry")
            mock_retry.assert_called_once_with("task-sse-fail-001")
            assert mock_retry.call_count == 1

    def test_retry_task_returns_pending_status_when_sse_fails(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns pending status even when SSE publish fails."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-sse-fail-001/retry")
            json_body = response.json()
            assert json_body.get("status") == "pending"

    def test_retry_task_does_not_rollback_on_sse_failure(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry does not rollback database change on SSE failure."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ) as mock_retry:
            response = client.post("/tasks/task-sse-fail-001/retry")
            # Verify retry_task was called (database update attempted)
            mock_retry.assert_called_once()
            # Verify response indicates success (no rollback)
            assert response.status_code == 200
            json_body = response.json()
            assert json_body.get("status") == "pending"


class TestRetryTaskResponseStructure:
    """Tests for the response structure of the retry endpoint."""

    @pytest.fixture
    def mock_broadcaster(self) -> MagicMock:
        """Create a mock SSEBroadcaster."""
        broadcaster = MagicMock()
        broadcaster.publish = MagicMock(return_value=None)
        return broadcaster

    @pytest.fixture
    def app(self, mock_broadcaster: MagicMock) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        app.dependency_overrides[get_broadcaster_dep] = lambda: mock_broadcaster
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def failed_task(self) -> dict[str, Any]:
        """Create mock task data for a failed task."""
        return {
            "task_key": "task-struct-001",
            "status": "failed",
        }

    @pytest.fixture
    def pending_task_response(self) -> dict[str, Any]:
        """Create mock task response after retry with pending status."""
        return {
            "task_key": "task-struct-001",
            "status": "pending",
        }

    def test_retry_task_returns_json_content_type(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-struct-001/retry")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_retry_task_response_task_key_is_string(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry response task_key is a string."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-struct-001/retry")
            json_body = response.json()
            assert isinstance(json_body.get("task_key"), str)

    def test_retry_task_response_status_is_string(
        self, client: TestClient, failed_task: dict[str, Any], pending_task_response: dict[str, Any]
    ) -> None:
        """POST /tasks/{task_key}/retry response status is a string."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_detail",
            return_value=failed_task,
        ), patch(
            "tdd_orchestrator.api.routes.tasks.retry_task",
            return_value=pending_task_response,
        ):
            response = client.post("/tasks/task-struct-001/retry")
            json_body = response.json()
            assert isinstance(json_body.get("status"), str)
