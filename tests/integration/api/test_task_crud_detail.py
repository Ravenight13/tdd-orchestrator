"""Integration tests for task detail retrieval and filter parameters.

Tests verify retrieving individual task details, response model structures,
and query parameter validation against a DB-seeded test app.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_seeded_test_app


class TestTaskDetailResponse:
    """Tests for retrieving individual task details."""

    @pytest.mark.asyncio
    async def test_get_existing_task_returns_200_with_details(self) -> None:
        """GIVEN a seeded DB with TDD-T01 (pending)
        WHEN GET /tasks/TDD-T01 is called
        THEN the response is 200 with id and status fields.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/TDD-T01")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["id"] == "TDD-T01"
            assert json_body["status"] == "pending"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_task_detail_contains_required_fields(self) -> None:
        """GIVEN a seeded DB with TDD-T01
        WHEN GET /tasks/TDD-T01 is called
        THEN the response contains id, title, status, phase, sequence, complexity, attempts.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/TDD-T01")

            assert response.status_code == 200
            json_body = response.json()
            assert "id" in json_body
            assert "status" in json_body
            assert "title" in json_body
            assert "phase" in json_body
            assert "sequence" in json_body
            assert "complexity" in json_body
            assert "attempts" in json_body
        finally:
            await db.close()


class TestTaskFilterParams:
    """Tests for TaskFilterParams query parameter handling."""

    @pytest.mark.asyncio
    async def test_filter_params_accept_valid_status_values(self) -> None:
        """GIVEN a seeded DB
        WHEN GET /tasks?status={status} is called for each valid status
        THEN the request is accepted with 200 for all valid values.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                for status in ["pending", "running", "failed"]:
                    response = await client.get(f"/tasks?status={status}")
                    assert response.status_code == 200, f"Failed for status={status}"
                    json_body = response.json()
                    assert "tasks" in json_body
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_filter_params_reject_invalid_status(self) -> None:
        """GIVEN a seeded DB
        WHEN GET /tasks?status=invalid_status is called
        THEN the request returns 422.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?status=invalid_status")

            assert response.status_code == 422
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_filter_params_accept_limit_and_offset(self) -> None:
        """GIVEN a seeded DB
        WHEN GET /tasks?limit=10&offset=5 is called
        THEN the request is accepted with 200 and correct structure.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?limit=10&offset=5")

            assert response.status_code == 200
            json_body = response.json()
            assert "tasks" in json_body
            assert "total" in json_body
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_filter_params_reject_negative_limit(self) -> None:
        """GIVEN a seeded DB
        WHEN GET /tasks?limit=-1 is called
        THEN the request returns 422.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks?limit=-1")

            assert response.status_code == 422
        finally:
            await db.close()


class TestTaskResponseModel:
    """Tests for TaskResponse and related model structures."""

    @pytest.mark.asyncio
    async def test_task_list_response_structure(self) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN GET /tasks is called
        THEN the response matches TaskListResponse structure with tasks list and total int.
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
            assert isinstance(json_body["tasks"], list)
            total = json_body["total"]
            assert isinstance(total, int)
            assert total >= 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_task_response_in_list_has_required_fields(self) -> None:
        """GIVEN a seeded DB with 3 tasks
        WHEN GET /tasks is called
        THEN each task in the list has 'status' and 'id' fields.
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
            tasks = json_body["tasks"]
            assert len(tasks) > 0
            for task in tasks:
                assert "status" in task
                assert "id" in task
        finally:
            await db.close()
