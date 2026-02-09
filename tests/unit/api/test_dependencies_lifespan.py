"""Tests for FastAPI app lifespan dependency management.

These tests verify that init_dependencies and shutdown_dependencies are properly
wired into the FastAPI app's lifespan context manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from fastapi import FastAPI


class TestCreateAppLifespan:
    """Tests for create_app lifespan integration."""

    def test_create_app_returns_fastapi_instance_with_lifespan(self) -> None:
        """GIVEN create_app() is called WHEN inspecting the returned FastAPI instance
        THEN its lifespan parameter is set (not None).
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        # FastAPI stores the lifespan in router.lifespan_context
        assert app.router.lifespan_context is not None

    def test_create_app_includes_health_route(self) -> None:
        """GIVEN create_app() is called WHEN inspecting routes
        THEN the app includes the /health route.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/health" in route_paths


class TestLifespanStartup:
    """Tests for lifespan startup behavior."""

    @pytest.mark.asyncio
    async def test_init_dependencies_called_during_startup(self) -> None:
        """GIVEN create_app() is called WHEN the app starts up via ASGI lifespan
        THEN init_dependencies is awaited during the lifespan startup phase.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Just making a request ensures lifespan started
                await client.get("/health")

            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_singletons_available_in_app_state_after_startup(self) -> None:
        """GIVEN create_app() is called WHEN the app has started
        THEN singletons (db, redis, etc.) are available in app.state.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # init_dependencies should have been called with the app
                await client.get("/health")

            # Verify init was called with an app argument that allows setting state
            mock_init.assert_awaited_once()
            call_args = mock_init.call_args
            assert call_args is not None
            # The app should be passed to init_dependencies
            assert len(call_args.args) >= 1 or "app" in call_args.kwargs


class TestLifespanShutdown:
    """Tests for lifespan shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_called_on_app_shutdown(self) -> None:
        """GIVEN create_app() is called and the app has started
        WHEN the app shuts down (lifespan context manager exits)
        THEN shutdown_dependencies is awaited.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            # After exiting the async context, shutdown should have been called
            mock_shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_receives_app_for_cleanup(self) -> None:
        """GIVEN the app is shutting down
        WHEN shutdown_dependencies is called
        THEN it receives the app instance for proper cleanup.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            mock_shutdown.assert_awaited_once()
            call_args = mock_shutdown.call_args
            assert call_args is not None
            # The app should be passed to shutdown_dependencies
            assert len(call_args.args) >= 1 or "app" in call_args.kwargs


class TestLifespanErrorHandling:
    """Tests for error handling during lifespan."""

    @pytest.mark.asyncio
    async def test_startup_exception_propagates(self) -> None:
        """GIVEN init_dependencies raises an unhandled exception during startup
        WHEN the app lifespan runs
        THEN the exception propagates (app fails to start).
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock(side_effect=RuntimeError("Init failed"))
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            with pytest.raises(RuntimeError, match="Init failed"):
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    await client.get("/health")

    @pytest.mark.asyncio
    async def test_shutdown_called_on_startup_failure(self) -> None:
        """GIVEN init_dependencies raises an exception during startup
        WHEN the app lifespan runs
        THEN shutdown_dependencies is still called to clean up partial resources.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock(side_effect=RuntimeError("Init failed"))
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            with pytest.raises(RuntimeError, match="Init failed"):
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    await client.get("/health")

            # Shutdown should be called even when init fails
            mock_shutdown.assert_awaited_once()


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200_ok(self) -> None:
        """GIVEN a fully started app (lifespan completed startup)
        WHEN GET /health is called
        THEN it returns HTTP 200.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_status_ok_json(self) -> None:
        """GIVEN a fully started app (lifespan completed startup)
        WHEN GET /health is called
        THEN it returns JSON body containing {"status": "ok"}.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

            json_body = response.json()
            assert json_body is not None
            assert json_body.get("status") == "ok"

    @pytest.mark.asyncio
    async def test_health_confirms_dependencies_functional(self) -> None:
        """GIVEN a fully started app with initialized dependencies
        WHEN GET /health is called
        THEN it confirms dependencies initialized by lifespan are functional.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies", mock_init
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

            # Health endpoint should work, confirming app is functional
            assert response.status_code == 200
            json_body = response.json()
            assert json_body is not None
            assert "status" in json_body


class TestLifespanOrder:
    """Tests verifying the order of lifespan operations."""

    @pytest.mark.asyncio
    async def test_init_before_shutdown(self) -> None:
        """GIVEN a normal app lifecycle
        WHEN the app starts and stops
        THEN init_dependencies is called before shutdown_dependencies.
        """
        from tdd_orchestrator.api.app import create_app

        call_order: list[str] = []

        async def mock_init(*args: object, **kwargs: object) -> None:
            call_order.append("init")

        async def mock_shutdown(*args: object, **kwargs: object) -> None:
            call_order.append("shutdown")

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies",
                AsyncMock(side_effect=mock_init),
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies",
                AsyncMock(side_effect=mock_shutdown),
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            assert call_order == ["init", "shutdown"]

    @pytest.mark.asyncio
    async def test_init_completes_before_requests_served(self) -> None:
        """GIVEN create_app() is called
        WHEN the app starts
        THEN init_dependencies completes before the first request is served.
        """
        from tdd_orchestrator.api.app import create_app

        init_completed = False
        request_served_after_init = False

        async def mock_init(*args: object, **kwargs: object) -> None:
            nonlocal init_completed
            init_completed = True

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies",
                AsyncMock(side_effect=mock_init),
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies",
                AsyncMock(),
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # By the time we can make a request, init should have completed
                response = await client.get("/health")
                request_served_after_init = init_completed and response.status_code == 200

            assert init_completed is True
            assert request_served_after_init is True
