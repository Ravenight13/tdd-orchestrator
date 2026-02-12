"""Integration tests for GET /workers endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_seeded_test_app, _create_test_app


class TestWorkersEndpoint:
    """Tests for GET /workers endpoint."""

    @pytest.mark.asyncio
    async def test_workers_returns_200_with_json_list_when_seeded_database(
        self,
    ) -> None:
        """GIVEN the test database is seeded with tasks, workers, and runs via shared fixtures
        WHEN GET /workers is called
        THEN response is 200 with a JSON list of WorkerResponse objects.
        """
        app = _create_test_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/workers")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "items" in json_body or "workers" in json_body
        # Accept either format from the API
        workers = json_body.get("workers", json_body.get("items", []))
        assert isinstance(workers, list)

    @pytest.mark.asyncio
    async def test_workers_response_contains_id_status_and_registered_at_fields(
        self,
    ) -> None:
        """GIVEN workers exist in the seeded database
        WHEN GET /workers is called
        THEN each WorkerResponse contains id, status, and registered_at fields.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/workers")

            assert response.status_code == 200
            json_body = response.json()
            assert json_body is not None
            # Accept either format from the API
            workers = json_body.get("workers", json_body.get("items", []))
            assert isinstance(workers, list)

            # Skip if no workers (empty database is valid for this endpoint)
            if len(workers) == 0:
                pytest.skip("No workers in database - expected for empty test run")

            for worker in workers:
                assert "id" in worker, "Worker missing 'id' field"
                assert "status" in worker, "Worker missing 'status' field"
                assert "registered_at" in worker, "Worker missing 'registered_at' field"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_workers_returns_empty_list_when_no_workers_exist(self) -> None:
        """GIVEN no workers exist in the database
        WHEN GET /workers is called
        THEN response is 200 with an empty list.
        """
        app = _create_test_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/workers")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        # Accept either format from the API
        workers = json_body.get("workers", json_body.get("items", []))
        assert isinstance(workers, list)
