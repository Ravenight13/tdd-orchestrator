"""Integration tests for task list filtering and pagination.

Tests verify listing tasks with status filters and pagination parameters
against a DB-seeded test app with known seed data.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_seeded_test_app


class TestTaskListFiltering:
    """Tests for listing tasks with status filters."""

    @pytest.mark.asyncio
    async def test_get_tasks_with_status_pending_returns_only_pending_tasks(
        self,
    ) -> None:
        """GIVEN a seeded DB with TDD-T01 (pending), TDD-T02 (running), TDD-T03 (passed)
        WHEN GET /tasks?status=pending is called
        THEN the response contains only the 1 pending task.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?status=pending")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["total"] == 1
            tasks = json_body["tasks"]
            assert len(tasks) == 1
            assert tasks[0]["status"] == "pending"
            assert tasks[0]["id"] == "TDD-T01"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_tasks_with_status_failed_returns_only_failed_tasks(
        self,
    ) -> None:
        """GIVEN a seeded DB with no blocked/failed tasks
        WHEN GET /tasks?status=failed is called
        THEN the response contains 0 tasks.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?status=failed")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["total"] == 0
            assert json_body["tasks"] == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_tasks_without_filter_returns_all_tasks(self) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN GET /tasks is called without status filter
        THEN the response contains all 3 tasks with total=3.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks")

            assert response.status_code == 200
            json_body = response.json()
            assert "tasks" in json_body
            assert "total" in json_body
            assert json_body["total"] == 3
            assert len(json_body["tasks"]) == 3
        finally:
            await db.close()


class TestTaskListPagination:
    """Tests for task list pagination via limit and offset."""

    @pytest.mark.asyncio
    async def test_pagination_with_limit_returns_correct_number_of_tasks(
        self,
    ) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN GET /tasks?limit=2&offset=0 is called
        THEN the response contains exactly 2 tasks with total=3.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?limit=2&offset=0")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["total"] == 3
            assert len(json_body["tasks"]) == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_pagination_with_offset_returns_next_page(self) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN first page (limit=2, offset=0) and second page (limit=2, offset=2) are fetched
        THEN both pages have total=3 but different task sets.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                first_page = await client.get("/tasks?limit=2&offset=0")
                second_page = await client.get("/tasks?limit=2&offset=2")

            assert first_page.status_code == 200
            assert second_page.status_code == 200

            first_json = first_page.json()
            second_json = second_page.json()

            # Total should be the same across pages
            assert first_json["total"] == 3
            assert second_json["total"] == 3

            # First page has 2 tasks, second page has 1 task
            assert len(first_json["tasks"]) == 2
            assert len(second_json["tasks"]) == 1

            # Pages have different tasks
            first_ids = {t["id"] for t in first_json["tasks"]}
            second_ids = {t["id"] for t in second_json["tasks"]}
            assert first_ids.isdisjoint(second_ids)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_pagination_offset_beyond_total_returns_empty_list(self) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN GET /tasks?limit=10&offset=1000 is called with offset beyond total
        THEN the response contains an empty tasks list but total=3.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?limit=10&offset=1000")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["tasks"] == []
            assert json_body["total"] == 3
        finally:
            await db.close()
