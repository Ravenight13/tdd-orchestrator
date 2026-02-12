"""Integration tests for task retry functionality.

Tests verify retrying failed tasks, 404 handling for nonexistent tasks,
and 409 conflict handling for non-failed tasks against a DB-seeded test app.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.dependencies import get_broadcaster_dep

from .helpers import _create_seeded_test_app


class _StubBroadcaster:
    """Stub broadcaster that discards all published events."""

    async def publish(self, data: object) -> None:
        """No-op publish."""


def _override_broadcaster(app: object) -> None:
    """Override the broadcaster dependency with a stub on the given app."""
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_broadcaster_dep] = lambda: _StubBroadcaster()


class TestTaskRetry:
    """Tests for retrying failed tasks."""

    @pytest.mark.asyncio
    async def test_retry_failed_task_resets_status_to_pending(self) -> None:
        """GIVEN a task TDD-RETRY1 with status='blocked' (API: 'failed')
        WHEN POST /tasks/TDD-RETRY1/retry is called
        THEN the task status is reset to 'pending'.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            await db.create_task("TDD-RETRY1", "Retry Test", phase=0, sequence=10)
            await db.update_task_status("TDD-RETRY1", "blocked")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-RETRY1/retry", json={})

            assert response.status_code == 200
            json_body = response.json()
            assert json_body["task_key"] == "TDD-RETRY1"
            assert json_body["status"] == "pending"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_failed_task_returns_200_with_updated_details(self) -> None:
        """GIVEN a task TDD-RETRY2 with status='blocked' (API: 'failed')
        WHEN POST /tasks/TDD-RETRY2/retry is called
        THEN the response is 200 with task_key and status fields.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            await db.create_task("TDD-RETRY2", "Retry Test 2", phase=0, sequence=11)
            await db.update_task_status("TDD-RETRY2", "blocked")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-RETRY2/retry", json={})

            assert response.status_code == 200
            json_body = response.json()
            assert "task_key" in json_body
            assert "status" in json_body
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_resets_db_status_verified_via_get(self) -> None:
        """GIVEN a task TDD-RETRY3 with status='blocked' (API: 'failed')
        WHEN POST /tasks/TDD-RETRY3/retry is called
        THEN GET /tasks/TDD-RETRY3 returns status='pending'.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            await db.create_task("TDD-RETRY3", "Retry Test 3", phase=0, sequence=12)
            await db.update_task_status("TDD-RETRY3", "blocked")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                retry_resp = await client.post("/tasks/TDD-RETRY3/retry", json={})
                assert retry_resp.status_code == 200

                get_resp = await client.get("/tasks/TDD-RETRY3")
                assert get_resp.status_code == 200
                assert get_resp.json()["status"] == "pending"
        finally:
            await db.close()


class TestTaskNotFound:
    """Tests for 404 responses on nonexistent tasks."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_404(self) -> None:
        """GIVEN a seeded DB that does not contain task NONEXISTENT
        WHEN GET /tasks/NONEXISTENT is called
        THEN the response is 404 with 'detail' in the body.
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/NONEXISTENT")

            assert response.status_code == 404
            json_body = response.json()
            assert "detail" in json_body
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_nonexistent_task_returns_404(self) -> None:
        """GIVEN a seeded DB that does not contain task NONEXISTENT
        WHEN POST /tasks/NONEXISTENT/retry is called
        THEN the response is 404.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/tasks/NONEXISTENT/retry", json={}
                )

            assert response.status_code == 404
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_task_with_invalid_uuid_format_returns_error(self) -> None:
        """GIVEN a seeded DB
        WHEN GET /tasks/not-a-valid-uuid is called
        THEN the response is 404 (treated as task_key lookup, not found).
        """
        app, db = await _create_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/not-a-valid-uuid")

            assert response.status_code == 404
        finally:
            await db.close()


class TestTaskRetryConflict:
    """Tests for 409 Conflict when retrying non-failed tasks."""

    @pytest.mark.asyncio
    async def test_retry_running_task_returns_409_conflict(self) -> None:
        """GIVEN TDD-T02 has status='running' (DB: in_progress)
        WHEN POST /tasks/TDD-T02/retry is called
        THEN the response is 409 Conflict.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-T02/retry", json={})

            assert response.status_code == 409
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_running_task_does_not_change_status(self) -> None:
        """GIVEN TDD-T02 has status='running' (DB: in_progress)
        WHEN POST /tasks/TDD-T02/retry returns 409
        THEN GET /tasks/TDD-T02 still shows status='running'.
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                retry_resp = await client.post("/tasks/TDD-T02/retry", json={})
                assert retry_resp.status_code == 409

                get_resp = await client.get("/tasks/TDD-T02")
                assert get_resp.status_code == 200
                assert get_resp.json()["status"] == "running"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_pending_task_returns_conflict_or_error(self) -> None:
        """GIVEN TDD-T01 has status='pending'
        WHEN POST /tasks/TDD-T01/retry is called
        THEN the response is 409 (only failed tasks can be retried).
        """
        app, db = await _create_seeded_test_app()
        _override_broadcaster(app)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-T01/retry", json={})

            assert response.status_code == 409
        finally:
            await db.close()
