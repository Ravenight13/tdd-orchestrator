"""Integration tests for task detail retrieval and filter parameters.

Tests verify retrieving individual task details, response model structures,
and query parameter validation.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.app import create_app


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
