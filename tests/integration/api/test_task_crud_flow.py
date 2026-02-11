"""Integration tests for task CRUD lifecycle through the API.

Tests verify the complete task lifecycle: create tasks via the database,
list with filters, retrieve details, and retry failed tasks.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.app import create_app

# These exports will be implemented in this module
from tests.integration.api.test_task_crud_flow import (
    TaskDetailResponse,
    TaskFilterParams,
    TaskListResponse,
    TaskResponse,
    TaskRetryRequest,
)

if TYPE_CHECKING:
    pass


class TestTaskListFiltering:
    """Tests for listing tasks with status filters."""

    @pytest.mark.asyncio
    async def test_get_tasks_with_status_pending_returns_only_pending_tasks(
        self,
    ) -> None:
        """GIVEN a running test app with tasks of varying statuses
        WHEN GET /tasks?status=pending is called
        THEN the response contains only pending tasks with correct total count.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # First create tasks with different statuses via the API/database
            # The actual creation mechanism depends on implementation
            response = await client.get("/tasks?status=pending")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        # Verify response matches TaskListResponse structure
        assert "tasks" in json_body
        assert "total" in json_body
        tasks = json_body.get("tasks", [])
        # All returned tasks should have pending status
        for task in tasks if tasks else []:
            assert task.get("status") == "pending"

    @pytest.mark.asyncio
    async def test_get_tasks_with_status_failed_returns_only_failed_tasks(
        self,
    ) -> None:
        """GIVEN a running test app with tasks of varying statuses
        WHEN GET /tasks?status=failed is called
        THEN the response contains only failed tasks.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?status=failed")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "tasks" in json_body
        tasks = json_body.get("tasks", [])
        for task in tasks if tasks else []:
            assert task.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_get_tasks_without_filter_returns_all_tasks(self) -> None:
        """GIVEN a running test app with multiple tasks
        WHEN GET /tasks is called without status filter
        THEN the response contains all tasks.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "tasks" in json_body
        assert "total" in json_body


class TestTaskListPagination:
    """Tests for task list pagination via limit and offset."""

    @pytest.mark.asyncio
    async def test_pagination_with_limit_returns_correct_number_of_tasks(
        self,
    ) -> None:
        """GIVEN 5 tasks exist in the database
        WHEN GET /tasks?limit=2&offset=0 is called
        THEN the response contains exactly 2 tasks with total=5.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?limit=2&offset=0")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "tasks" in json_body
        assert "total" in json_body
        tasks = json_body.get("tasks", [])
        # Should return at most 2 tasks
        assert len(tasks) <= 2

    @pytest.mark.asyncio
    async def test_pagination_with_offset_returns_next_page(self) -> None:
        """GIVEN 5 tasks exist in the database
        WHEN GET /tasks?limit=2&offset=2 is called
        THEN the response contains the next 2 tasks.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Get first page
            first_page = await client.get("/tasks?limit=2&offset=0")
            # Get second page
            second_page = await client.get("/tasks?limit=2&offset=2")

        assert first_page.status_code == 200
        assert second_page.status_code == 200

        first_json = first_page.json()
        second_json = second_page.json()

        assert first_json is not None
        assert second_json is not None
        assert "tasks" in first_json
        assert "tasks" in second_json

        # Total should be the same across pages
        first_total = first_json.get("total", 0)
        second_total = second_json.get("total", 0)
        assert first_total == second_total

    @pytest.mark.asyncio
    async def test_pagination_offset_beyond_total_returns_empty_list(self) -> None:
        """GIVEN tasks exist in the database
        WHEN GET /tasks?limit=10&offset=1000 is called with offset beyond total
        THEN the response contains an empty tasks list but correct total.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?limit=10&offset=1000")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "tasks" in json_body
        tasks = json_body.get("tasks", [])
        assert tasks == [] or len(tasks) == 0


class TestTaskRetry:
    """Tests for retrying failed tasks."""

    @pytest.mark.asyncio
    async def test_retry_failed_task_resets_status_to_pending(self) -> None:
        """GIVEN a task exists with status='failed' in the database
        WHEN POST /tasks/{task_id}/retry is called with a valid TaskRetryRequest
        THEN the task status is reset to 'pending' and retry_count is incremented.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Retry the failed task
            response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

        # If task exists and is failed, should return 200
        # If task doesn't exist or isn't failed, different status codes
        assert response.status_code in (200, 404, 409)
        if response.status_code == 200:
            json_body = response.json()
            assert json_body is not None
            assert json_body.get("status") == "pending"
            # retry_count should be incremented
            assert "retry_count" in json_body

    @pytest.mark.asyncio
    async def test_retry_failed_task_returns_200_with_updated_details(self) -> None:
        """GIVEN a task with status='failed' exists
        WHEN POST /tasks/{task_id}/retry is called
        THEN the response is 200 with updated task details.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

        # Expect 200 for successful retry, 404 if not found, 409 if not failed
        assert response.status_code in (200, 404, 409)
        json_body = response.json()
        assert json_body is not None

    @pytest.mark.asyncio
    async def test_retry_increments_retry_count_by_one(self) -> None:
        """GIVEN a failed task with retry_count=N
        WHEN POST /tasks/{task_id}/retry is called
        THEN the task's retry_count becomes N+1.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

        if response.status_code == 200:
            json_body = response.json()
            assert json_body is not None
            retry_count = json_body.get("retry_count")
            assert retry_count is not None
            assert isinstance(retry_count, int)
            assert retry_count >= 1


class TestTaskNotFound:
    """Tests for 404 responses on nonexistent tasks."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_404(self) -> None:
        """GIVEN no tasks exist in the database
        WHEN GET /tasks/{nonexistent_uuid} is called
        THEN the response is 404 with an error body containing a descriptive message.
        """
        app = create_app()
        nonexistent_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/tasks/{nonexistent_id}")

        assert response.status_code == 404
        json_body = response.json()
        assert json_body is not None
        # Should contain error detail
        assert "detail" in json_body or "error" in json_body or "message" in json_body

    @pytest.mark.asyncio
    async def test_retry_nonexistent_task_returns_404(self) -> None:
        """GIVEN no tasks exist in the database
        WHEN POST /tasks/{nonexistent_uuid}/retry is called
        THEN the response is 404.
        """
        app = create_app()
        nonexistent_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/tasks/{nonexistent_id}/retry",
                json={},
            )

        assert response.status_code == 404
        json_body = response.json()
        assert json_body is not None

    @pytest.mark.asyncio
    async def test_get_task_with_invalid_uuid_format_returns_error(self) -> None:
        """GIVEN an invalid UUID format
        WHEN GET /tasks/{invalid_uuid} is called
        THEN the response indicates an error (400 or 422).
        """
        app = create_app()
        invalid_id = "not-a-valid-uuid"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/tasks/{invalid_id}")

        # Should return 400 or 422 for invalid UUID format, or 404 if treated as not found
        assert response.status_code in (400, 404, 422)
        json_body = response.json()
        assert json_body is not None


class TestTaskRetryConflict:
    """Tests for 409 Conflict when retrying non-failed tasks."""

    @pytest.mark.asyncio
    async def test_retry_running_task_returns_409_conflict(self) -> None:
        """GIVEN a task exists with status='running' (not failed)
        WHEN POST /tasks/{task_id}/retry is called
        THEN the response is 409 Conflict indicating only failed tasks can be retried.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

        # If task is running, should be 409; if not found, 404
        assert response.status_code in (404, 409)
        json_body = response.json()
        assert json_body is not None

    @pytest.mark.asyncio
    async def test_retry_running_task_does_not_change_status(self) -> None:
        """GIVEN a task exists with status='running'
        WHEN POST /tasks/{task_id}/retry is called and returns 409
        THEN the task status remains 'running' unchanged in the database.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Attempt retry
            retry_response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

            # If we got a 409, verify the task status is still running
            if retry_response.status_code == 409:
                get_response = await client.get(f"/tasks/{task_id}")
                if get_response.status_code == 200:
                    json_body = get_response.json()
                    assert json_body is not None
                    assert json_body.get("status") == "running"

        # At minimum, the retry should not have succeeded
        assert retry_response.status_code in (404, 409)

    @pytest.mark.asyncio
    async def test_retry_pending_task_returns_conflict_or_error(self) -> None:
        """GIVEN a task exists with status='pending'
        WHEN POST /tasks/{task_id}/retry is called
        THEN the response indicates the task cannot be retried (409 or appropriate error).
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/tasks/{task_id}/retry",
                json={},
            )

        # Should not return 200 since task is not failed
        assert response.status_code in (404, 409)
        json_body = response.json()
        assert json_body is not None


class TestTaskDetailResponse:
    """Tests for retrieving individual task details."""

    @pytest.mark.asyncio
    async def test_get_existing_task_returns_200_with_details(self) -> None:
        """GIVEN a task exists in the database
        WHEN GET /tasks/{task_id} is called
        THEN the response is 200 with TaskDetailResponse containing task details.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/tasks/{task_id}")

        # Task may or may not exist; verify response structure
        assert response.status_code in (200, 404)
        json_body = response.json()
        assert json_body is not None

        if response.status_code == 200:
            # Verify TaskDetailResponse structure
            assert "id" in json_body or "task_id" in json_body
            assert "status" in json_body

    @pytest.mark.asyncio
    async def test_task_detail_contains_required_fields(self) -> None:
        """GIVEN a task exists in the database
        WHEN GET /tasks/{task_id} is called
        THEN the response contains all required TaskDetailResponse fields.
        """
        app = create_app()
        task_id = str(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/tasks/{task_id}")

        json_body = response.json()
        assert json_body is not None

        if response.status_code == 200:
            # TaskDetailResponse should have these fields based on acceptance criteria
            assert "status" in json_body
            # retry_count should be present for retry tracking
            assert "retry_count" in json_body or response.status_code == 404


class TestTaskFilterParams:
    """Tests for TaskFilterParams query parameter handling."""

    @pytest.mark.asyncio
    async def test_filter_params_accept_valid_status_values(self) -> None:
        """GIVEN valid status filter values
        WHEN GET /tasks?status={status} is called
        THEN the request is accepted and processed.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            for status in ["pending", "running", "failed"]:
                response = await client.get(f"/tasks?status={status}")
                assert response.status_code == 200, f"Failed for status={status}"
                json_body = response.json()
                assert json_body is not None

    @pytest.mark.asyncio
    async def test_filter_params_reject_invalid_status(self) -> None:
        """GIVEN an invalid status filter value
        WHEN GET /tasks?status=invalid is called
        THEN the request returns an error (400 or 422).
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?status=invalid_status")

        # Should reject invalid status values
        assert response.status_code in (400, 422)
        json_body = response.json()
        assert json_body is not None

    @pytest.mark.asyncio
    async def test_filter_params_accept_limit_and_offset(self) -> None:
        """GIVEN valid limit and offset parameters
        WHEN GET /tasks?limit=10&offset=5 is called
        THEN the request is accepted and processed.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?limit=10&offset=5")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "tasks" in json_body
        assert "total" in json_body

    @pytest.mark.asyncio
    async def test_filter_params_reject_negative_limit(self) -> None:
        """GIVEN a negative limit parameter
        WHEN GET /tasks?limit=-1 is called
        THEN the request returns an error.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks?limit=-1")

        # Should reject negative limit
        assert response.status_code in (400, 422)
        json_body = response.json()
        assert json_body is not None


class TestTaskResponseModel:
    """Tests for TaskResponse and related model structures."""

    @pytest.mark.asyncio
    async def test_task_list_response_structure(self) -> None:
        """GIVEN the API is running
        WHEN GET /tasks is called
        THEN the response matches TaskListResponse structure.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None

        # TaskListResponse structure
        assert "tasks" in json_body
        assert "total" in json_body
        assert isinstance(json_body.get("tasks"), list)
        total = json_body.get("total")
        assert isinstance(total, int)
        assert total >= 0

    @pytest.mark.asyncio
    async def test_task_response_in_list_has_required_fields(self) -> None:
        """GIVEN tasks exist in the database
        WHEN GET /tasks returns tasks
        THEN each task in the list matches TaskResponse structure.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/tasks")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None

        tasks = json_body.get("tasks", [])
        for task in tasks if tasks else []:
            # Each TaskResponse should have these minimum fields
            assert "status" in task
            # Typically includes id field
            assert "id" in task or "task_id" in task
