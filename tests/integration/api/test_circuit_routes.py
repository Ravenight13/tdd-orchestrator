"""Integration tests for circuit breaker routes (DB-backed, no mocks).

Tests exercise GET /circuits, GET /circuits/health, GET /circuits/{id},
and POST /circuits/{id}/reset against a seeded in-memory database.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_circuits_seeded_test_app, _create_test_app


class TestListCircuits:
    """Tests for GET /circuits endpoint."""

    @pytest.mark.asyncio
    async def test_list_circuits_returns_seeded_data(self) -> None:
        """GIVEN a DB seeded with 6 circuit breakers
        WHEN GET /circuits is called
        THEN response is 200 with all 6 circuits.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits")

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 6
            assert len(body["circuits"]) == 6
            # Each circuit has required fields
            for circuit in body["circuits"]:
                assert "id" in circuit
                assert "level" in circuit
                assert "identifier" in circuit
                assert "state" in circuit
                assert "failure_count" in circuit
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_list_circuits_filters_by_level(self) -> None:
        """GIVEN a DB with circuits at stage, worker, and system levels
        WHEN GET /circuits?level=stage is called
        THEN only stage-level circuits are returned.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits", params={"level": "stage"})

            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 3
            for circuit in body["circuits"]:
                assert circuit["level"] == "stage"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_list_circuits_filters_by_state(self) -> None:
        """GIVEN a DB with circuits in closed, open, and half_open states
        WHEN GET /circuits?state=open is called
        THEN only open circuits are returned.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits", params={"state": "open"})

            assert response.status_code == 200
            body = response.json()
            # We seeded 2 open circuits: TDD-T02:green (stage) and worker_2 (worker)
            assert body["total"] == 2
            for circuit in body["circuits"]:
                assert circuit["state"] == "open"
        finally:
            await db.close()


class TestGetCircuitById:
    """Tests for GET /circuits/{circuit_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_circuit_by_id(self) -> None:
        """GIVEN a DB with seeded circuits
        WHEN GET /circuits/1 is called
        THEN the circuit with id=1 is returned.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits/1")

            assert response.status_code == 200
            body = response.json()
            assert body["id"] == "1"
            assert body["level"] == "stage"
            assert body["identifier"] == "TDD-T01:red"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_circuit_not_found_returns_404(self) -> None:
        """GIVEN a DB with seeded circuits
        WHEN GET /circuits/999 is called (nonexistent)
        THEN response is 404.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits/999")

            assert response.status_code == 404
        finally:
            await db.close()


class TestResetCircuit:
    """Tests for POST /circuits/{circuit_id}/reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_circuit_changes_state(self) -> None:
        """GIVEN an open circuit (id=2, state='open')
        WHEN POST /circuits/2/reset is called
        THEN the circuit state is reset to 'closed' with zeroed counters.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/circuits/2/reset")

            assert response.status_code == 200
            body = response.json()
            assert body["id"] == "2"
            assert body["state"] == "closed"
            assert body["failure_count"] == 0
            assert body["success_count"] == 0

            # Verify audit event was created
            async with db._conn.execute(
                "SELECT * FROM circuit_breaker_events WHERE circuit_id = ? "
                "AND event_type = 'manual_reset'",
                (2,),
            ) as cursor:
                event = await cursor.fetchone()
            assert event is not None
            assert str(event["from_state"]) == "open"
            assert str(event["to_state"]) == "closed"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_reset_nonexistent_circuit_returns_404(self) -> None:
        """GIVEN a DB with seeded circuits
        WHEN POST /circuits/999/reset is called (nonexistent)
        THEN response is 404.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/circuits/999/reset")

            assert response.status_code == 404
        finally:
            await db.close()


class TestCircuitHealth:
    """Tests for GET /circuits/health endpoint."""

    @pytest.mark.asyncio
    async def test_circuit_health_returns_per_level_summary(self) -> None:
        """GIVEN a DB with circuits across 3 levels
        WHEN GET /circuits/health is called
        THEN per-level summaries are returned.
        """
        app, db = await _create_circuits_seeded_test_app()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits/health")

            assert response.status_code == 200
            body = response.json()
            assert isinstance(body, list)
            # 3 levels seeded: stage, worker, system
            assert len(body) == 3

            levels = {item["level"]: item for item in body}

            assert levels["stage"]["total_circuits"] == 3
            assert levels["stage"]["closed_count"] == 1
            assert levels["stage"]["open_count"] == 1
            assert levels["stage"]["half_open_count"] == 1

            assert levels["worker"]["total_circuits"] == 2
            assert levels["worker"]["closed_count"] == 1
            assert levels["worker"]["open_count"] == 1

            assert levels["system"]["total_circuits"] == 1
            assert levels["system"]["closed_count"] == 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_circuit_health_empty_db_returns_empty_list(self) -> None:
        """GIVEN a DB with no circuit breakers
        WHEN GET /circuits/health is called
        THEN an empty list is returned.
        """
        from tdd_orchestrator.api.dependencies import get_db_dep
        from tdd_orchestrator.database.core import OrchestratorDB

        db = OrchestratorDB(":memory:")
        await db.connect()

        try:
            app = _create_test_app()

            async def override_get_db() -> AsyncGenerator[Any, None]:
                yield db

            app.dependency_overrides[get_db_dep] = override_get_db

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/circuits/health")

            assert response.status_code == 200
            body = response.json()
            assert isinstance(body, list)
            assert len(body) == 0
        finally:
            await db.close()


class TestCircuitsDBUnavailable:
    """Tests for circuit endpoints when DB is unavailable."""

    @pytest.mark.asyncio
    async def test_circuits_db_unavailable_returns_503(self) -> None:
        """GIVEN no database is available (dependency yields None)
        WHEN GET /circuits is called
        THEN response is 503.
        """
        app = _create_test_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/circuits")

        assert response.status_code == 503
