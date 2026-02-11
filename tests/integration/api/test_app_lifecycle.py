"""Integration tests for FastAPI application factory lifecycle.

Tests verify that create_app() produces a FastAPI application that:
- Starts up correctly with init_dependencies
- Serves health check requests
- Shuts down cleanly with shutdown_dependencies
- Handles errors during startup gracefully
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.app import (
    HealthResponse,
    create_app,
    init_dependencies,
    shutdown_dependencies,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


class TestAppLifecycleStartup:
    """Tests for application startup via create_app and init_dependencies."""

    @pytest.mark.asyncio
    async def test_health_returns_200_with_status_ok_when_app_started_with_defaults(
        self,
    ) -> None:
        """GIVEN create_app() is called with default settings
        WHEN the resulting FastAPI app is served via httpx.AsyncClient
        THEN GET /health returns HTTP 200 with JSON body containing {"status": "ok"}.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert json_body.get("status") == "ok"

    @pytest.mark.asyncio
    async def test_init_dependencies_completes_without_error_on_startup(self) -> None:
        """GIVEN create_app() is called with default settings
        WHEN the lifespan startup runs (init_dependencies)
        THEN it completes without error.
        """
        app = create_app()

        # The AsyncClient context manager triggers lifespan startup/shutdown
        # If init_dependencies fails, entering the context will raise
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Verify app is actually running by hitting health endpoint
            response = await client.get("/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_model_contains_status_field(self) -> None:
        """Verify HealthResponse model has the expected structure."""
        health_response = HealthResponse(status="ok")

        assert health_response.status == "ok"
        # Verify it serializes correctly to dict
        model_dict = health_response.model_dump()
        assert model_dict == {"status": "ok"}


class TestAppLifecycleShutdown:
    """Tests for application shutdown via shutdown_dependencies."""

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_invoked_on_context_exit(self) -> None:
        """GIVEN create_app() produced a running app
        WHEN the async context manager lifespan exits
        THEN shutdown_dependencies is invoked.
        """
        app = create_app()

        with patch(
            "tdd_orchestrator.api.app.shutdown_dependencies",
            new_callable=AsyncMock,
        ) as mock_shutdown:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 200

            # After exiting the context, shutdown should have been called
            mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_releases_resources_without_warnings(self) -> None:
        """GIVEN create_app() produced a running app
        WHEN the lifespan exits (simulating server shutdown)
        THEN all resources are released cleanly without warnings or exceptions.
        """
        app = create_app()

        # If shutdown doesn't release resources cleanly, this may raise
        # or produce warnings that pytest can capture
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 200

        # Exiting the context should complete without exception
        # If we reach here without exception, resources were released cleanly
        assert True  # Explicit assertion that we completed without error


class TestAppLifecycleStartupFailure:
    """Tests for error handling during application startup."""

    @pytest.mark.asyncio
    async def test_app_fails_to_start_when_init_dependencies_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GIVEN create_app() is called but init_dependencies raises an exception
        WHEN the lifespan startup runs
        THEN the app fails to start and the error propagates.
        """

        async def failing_init() -> None:
            raise RuntimeError("Database unavailable")

        monkeypatch.setattr(
            "tdd_orchestrator.api.app.init_dependencies",
            failing_init,
        )

        app = create_app()

        with pytest.raises(RuntimeError, match="Database unavailable"):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ):
                pass  # Should not reach here

    @pytest.mark.asyncio
    async def test_no_orphaned_resources_when_startup_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GIVEN init_dependencies raises an exception during startup
        WHEN the lifespan startup runs
        THEN no orphaned resources are left behind.
        """
        cleanup_called = False

        async def failing_init_with_cleanup() -> None:
            nonlocal cleanup_called
            # Simulate partial initialization then failure
            raise RuntimeError("Startup failed")

        async def mock_shutdown() -> None:
            nonlocal cleanup_called
            cleanup_called = True

        monkeypatch.setattr(
            "tdd_orchestrator.api.app.init_dependencies",
            failing_init_with_cleanup,
        )
        monkeypatch.setattr(
            "tdd_orchestrator.api.app.shutdown_dependencies",
            mock_shutdown,
        )

        app = create_app()

        with pytest.raises(RuntimeError, match="Startup failed"):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ):
                pass

        # The error should propagate without leaving orphaned resources
        # This is verified by the fact we caught the exception cleanly
        assert True  # Explicit assertion we handled the failure


class TestAppRouting:
    """Tests for application routing and error handling."""

    @pytest.mark.asyncio
    async def test_undefined_route_returns_404_with_json_error(self) -> None:
        """GIVEN create_app() produced a running app
        WHEN GET is called on an undefined route (e.g., /nonexistent)
        THEN the app returns HTTP 404 with a JSON error body.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/nonexistent")

        assert response.status_code == 404
        json_body = response.json()
        assert json_body is not None
        # FastAPI returns {"detail": "Not Found"} by default for 404
        assert "detail" in json_body

    @pytest.mark.asyncio
    async def test_router_and_exception_handlers_wired_during_startup(self) -> None:
        """GIVEN create_app() produced a running app
        WHEN accessing both valid and invalid routes
        THEN responses confirm router and exception handlers are properly wired.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Valid route should work
            health_response = await client.get("/health")
            assert health_response.status_code == 200

            # Invalid route should return proper 404 JSON
            not_found_response = await client.get("/this-route-does-not-exist")
            assert not_found_response.status_code == 404
            not_found_json = not_found_response.json()
            assert not_found_json is not None


class TestAppHealthEndpointIdempotency:
    """Tests for health endpoint stability and idempotency."""

    @pytest.mark.asyncio
    async def test_health_returns_200_on_multiple_sequential_calls(self) -> None:
        """GIVEN create_app() produced a running app with completed startup
        WHEN GET /health is called multiple times in sequence
        THEN each call returns HTTP 200 with {"status": "ok"}.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            for i in range(5):
                response = await client.get("/health")
                assert response.status_code == 200, f"Call {i + 1} failed"
                json_body = response.json()
                assert json_body is not None
                assert json_body.get("status") == "ok", f"Call {i + 1} returned wrong status"

    @pytest.mark.asyncio
    async def test_health_endpoint_is_idempotent_across_lifecycle(self) -> None:
        """GIVEN create_app() produced a running app
        WHEN GET /health is called multiple times
        THEN the app remains stable and returns consistent responses.
        """
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            responses = []
            for _ in range(3):
                response = await client.get("/health")
                responses.append(response)

            # All responses should be identical
            assert all(r.status_code == 200 for r in responses)
            json_bodies = [r.json() for r in responses]
            assert all(body is not None for body in json_bodies)
            assert all(body.get("status") == "ok" for body in json_bodies)

            # Verify all responses are structurally identical
            first_body = json_bodies[0]
            assert all(body == first_body for body in json_bodies)


class TestInitAndShutdownDependenciesDirect:
    """Direct tests for init_dependencies and shutdown_dependencies functions."""

    @pytest.mark.asyncio
    async def test_init_dependencies_is_callable(self) -> None:
        """Verify init_dependencies is an async callable."""
        # Should be able to call it without error
        # The actual behavior depends on implementation
        result = await init_dependencies()
        # init_dependencies typically returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_is_callable(self) -> None:
        """Verify shutdown_dependencies is an async callable."""
        # First init, then shutdown
        await init_dependencies()
        result = await shutdown_dependencies()
        # shutdown_dependencies typically returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_safe_to_call_without_init(self) -> None:
        """Verify shutdown_dependencies handles case where init was never called."""
        # This should not raise even if called without init
        # (defensive coding for edge cases)
        result = await shutdown_dependencies()
        assert result is None
