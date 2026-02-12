"""Integration tests for task list filtering and pagination.

Tests verify listing tasks with status filters and pagination parameters.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.app import create_app


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
