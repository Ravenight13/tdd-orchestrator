"""DB-seeded integration tests for task API endpoints.

Tests exercise the /tasks/stats, /tasks/progress, /tasks/{task_key},
and /tasks/{task_key}/retry endpoints against a pre-seeded in-memory
database with known task states.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_seeded_test_app


class _StubBroadcaster:
    """No-op broadcaster for tests that hit the retry endpoint."""

    async def publish(self, event: dict[str, Any]) -> None:  # noqa: ARG002
        pass


class TestTaskStats:
    """Tests for the GET /tasks/stats endpoint with seeded data."""

    @pytest.mark.asyncio
    async def test_stats_returns_correct_counts_from_seeded_data(self) -> None:
        """GIVEN a database seeded with three tasks (pending, in_progress, complete)
        WHEN GET /tasks/stats is called
        THEN the response contains pending=1, running=1, passed=1, failed=0, total=3.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/stats")

            assert response.status_code == 200
            body = response.json()
            assert body["pending"] == 1
            assert body["running"] == 1
            assert body["passed"] == 1
            assert body["failed"] == 0
            assert body["total"] == 3
        finally:
            await db.close()


class TestTaskProgress:
    """Tests for the GET /tasks/progress endpoint with seeded data."""

    @pytest.mark.asyncio
    async def test_progress_returns_total_completed_and_percentage(self) -> None:
        """GIVEN a database seeded with three tasks where one is complete
        WHEN GET /tasks/progress is called
        THEN the response contains total=3, completed=1, and percentage near 33.33.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/progress")

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 3
            assert body["completed"] == 1
            assert body["percentage"] == pytest.approx(33.33, abs=0.1)
        finally:
            await db.close()


class TestTaskDetail:
    """Tests for the GET /tasks/{task_key} endpoint with seeded data."""

    @pytest.mark.asyncio
    async def test_get_existing_task_returns_detail_with_attempts(self) -> None:
        """GIVEN a seeded pending task TDD-T01 exists in the database
        WHEN GET /tasks/TDD-T01 is called
        THEN the response is 200 with id, title, status='pending', and empty attempts.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/TDD-T01")

            assert response.status_code == 200
            body = response.json()
            assert body["id"] == "TDD-T01"
            assert body["title"] == "Test Task 1"
            assert body["status"] == "pending"
            assert body["phase"] == 0
            assert body["sequence"] == 0
            assert body["attempts"] == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_task_detail_includes_attempts_after_recording(self) -> None:
        """GIVEN a seeded task TDD-T01 with one recorded stage attempt
        WHEN GET /tasks/TDD-T01 is called
        THEN the response includes an attempts array with one entry.
        """
        app, db = await _create_seeded_test_app()

        try:
            task = await db.get_task_by_key("TDD-T01")
            assert task is not None
            task_id = int(task["id"])
            await db.record_stage_attempt(task_id, "red", 1, True)

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/tasks/TDD-T01")

            assert response.status_code == 200
            body = response.json()
            attempts = body["attempts"]
            assert len(attempts) == 1
            assert attempts[0]["stage"] == "red"
            assert attempts[0]["attempt_number"] == 1
            assert attempts[0]["success"] is True
        finally:
            await db.close()


class TestTaskRetry:
    """Tests for the POST /tasks/{task_key}/retry endpoint with seeded data."""

    @pytest.mark.asyncio
    async def test_retry_blocked_task_transitions_to_pending(self) -> None:
        """GIVEN a task TDD-T04 with DB status 'blocked' (API status 'failed')
        WHEN POST /tasks/TDD-T04/retry is called
        THEN the response is 200 with status='pending'.
        """
        from tdd_orchestrator.api.dependencies import get_broadcaster_dep

        app, db = await _create_seeded_test_app()
        app.dependency_overrides[get_broadcaster_dep] = _StubBroadcaster

        try:
            await db.create_task("TDD-T04", "Test Task 4", phase=0, sequence=3)
            await db.update_task_status("TDD-T04", "blocked")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-T04/retry")

            assert response.status_code == 200
            body = response.json()
            assert body["task_key"] == "TDD-T04"
            assert body["status"] == "pending"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_retry_pending_task_returns_409_conflict(self) -> None:
        """GIVEN a seeded task TDD-T01 with status 'pending'
        WHEN POST /tasks/TDD-T01/retry is called
        THEN the response is 409 Conflict because only failed tasks can be retried.
        """
        from tdd_orchestrator.api.dependencies import get_broadcaster_dep

        app, db = await _create_seeded_test_app()
        app.dependency_overrides[get_broadcaster_dep] = _StubBroadcaster

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/tasks/TDD-T01/retry")

            assert response.status_code == 409
            body = response.json()
            assert "detail" in body
        finally:
            await db.close()
