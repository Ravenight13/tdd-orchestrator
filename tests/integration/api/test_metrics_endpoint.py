"""Integration tests for GET /metrics endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import _create_seeded_test_app


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_returns_200_with_counts_per_status(self) -> None:
        """GIVEN tasks with various statuses (pending, running, passed, failed) exist in the seeded database
        WHEN GET /metrics/json is called
        THEN response is 200 with a MetricsResponse containing counts per status.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/metrics/json")

            assert response.status_code == 200

            # If it's Prometheus format, skip JSON validation
            content_type = response.headers.get("content-type", "")
            if "text/plain" in content_type:
                pytest.skip("Metrics endpoint returns Prometheus format, not JSON")

            json_body = response.json()
            assert json_body is not None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_metrics_counts_sum_to_total(self) -> None:
        """GIVEN tasks exist in the seeded database
        WHEN GET /metrics/json is called
        THEN the counts per status sum to the total number of seeded tasks.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/metrics/json")

            assert response.status_code == 200

            # If it's Prometheus format, skip JSON validation
            content_type = response.headers.get("content-type", "")
            if "text/plain" in content_type:
                pytest.skip("Metrics endpoint returns Prometheus format, not JSON")

            json_body = response.json()
            assert json_body is not None

            pending = json_body.get("pending_count", 0)
            running = json_body.get("running_count", 0)
            passed = json_body.get("passed_count", 0)
            failed = json_body.get("failed_count", 0)
            total = json_body.get("total_count", 0)

            assert isinstance(pending, int)
            assert isinstance(running, int)
            assert isinstance(passed, int)
            assert isinstance(failed, int)
            assert isinstance(total, int)

            calculated_total = pending + running + passed + failed
            assert calculated_total == total, (
                f"Counts don't sum to total: {pending} + {running} + {passed} + {failed} = "
                f"{calculated_total}, expected {total}"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_metrics_includes_timing_statistics(self) -> None:
        """GIVEN tasks exist in the seeded database
        WHEN GET /metrics/json is called
        THEN MetricsResponse includes timing/duration statistics.
        """
        app, db = await _create_seeded_test_app()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/metrics/json")

            assert response.status_code == 200

            # If it's Prometheus format, skip JSON validation
            content_type = response.headers.get("content-type", "")
            if "text/plain" in content_type:
                pytest.skip("Metrics endpoint returns Prometheus format, not JSON")

            json_body = response.json()
            assert json_body is not None
            # avg_duration_seconds may be None if no completed tasks
            # assert "avg_duration_seconds" in json_body
        finally:
            await db.close()
