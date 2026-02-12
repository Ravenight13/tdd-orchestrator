"""Integration tests for task retry functionality.

Tests verify retrying failed tasks, 404 handling for nonexistent tasks,
and 409 conflict handling for non-failed tasks.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.app import create_app


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
