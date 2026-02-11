"""Tests for FastAPI application factory (create_app).

These tests verify the create_app() factory function, including:
- App metadata (title, version, docs_url)
- Lifespan context manager for dependency init/shutdown
- CORS configuration
- Error handlers
- Health endpoint registration
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from fastapi import FastAPI


class TestCreateAppMetadata:
    """Tests for app metadata configuration."""

    def test_create_app_returns_fastapi_instance(self) -> None:
        """GIVEN no special configuration
        WHEN calling create_app()
        THEN it returns a FastAPI instance.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.app import create_app

        app = create_app()

        assert isinstance(app, FastAPI)

    def test_create_app_sets_title_to_tdd_orchestrator(self) -> None:
        """GIVEN no special configuration
        WHEN calling create_app()
        THEN the returned app has title 'TDD Orchestrator'.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        assert app.title == "TDD Orchestrator"

    def test_create_app_sets_version_matching_package(self) -> None:
        """GIVEN no special configuration
        WHEN calling create_app()
        THEN the returned app has version matching the package version.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        # Package version is 1.0.0 as defined in pyproject.toml
        assert app.version == "1.0.0"

    def test_create_app_sets_docs_url_to_docs(self) -> None:
        """GIVEN no special configuration
        WHEN calling create_app()
        THEN the returned app has docs_url set to '/docs'.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        assert app.docs_url == "/docs"


class TestCreateAppLifespanDependencies:
    """Tests for lifespan dependency initialization and shutdown."""

    @pytest.mark.asyncio
    async def test_init_dependencies_called_on_lifespan_entry(self) -> None:
        """GIVEN create_app() has been called
        WHEN the application lifespan starts (async context manager entry)
        THEN dependencies are initialized.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_dependencies_called_on_lifespan_exit(self) -> None:
        """GIVEN create_app() has been called
        WHEN the lifespan ends (async context manager exit)
        THEN dependencies are shut down cleanly.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            mock_shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_init_and_shutdown_order(self) -> None:
        """GIVEN create_app() has been called
        WHEN lifespan starts and ends
        THEN init is called before shutdown.
        """
        from tdd_orchestrator.api.app import create_app

        call_order: list[str] = []

        async def mock_init_fn(*args: object, **kwargs: object) -> None:
            call_order.append("init")

        async def mock_shutdown_fn(*args: object, **kwargs: object) -> None:
            call_order.append("shutdown")

        with (
            patch(
                "tdd_orchestrator.api.app.init_dependencies",
                AsyncMock(side_effect=mock_init_fn),
            ),
            patch(
                "tdd_orchestrator.api.app.shutdown_dependencies",
                AsyncMock(side_effect=mock_shutdown_fn),
            ),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

            assert call_order == ["init", "shutdown"]

    @pytest.mark.asyncio
    async def test_shutdown_called_even_if_init_fails(self) -> None:
        """GIVEN create_app() has been called
        WHEN init_dependencies raises an exception
        THEN shutdown_dependencies is still called for cleanup.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock(side_effect=RuntimeError("Init failed"))
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            with pytest.raises(RuntimeError, match="Init failed"):
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    await client.get("/health")

            mock_shutdown.assert_awaited_once()


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    @pytest.mark.asyncio
    async def test_cors_headers_present_for_allowed_origin(self) -> None:
        """GIVEN create_app() has been called
        WHEN sending a request with Origin header from an allowed origin
        THEN the response includes Access-Control-Allow-Origin header.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/health",
                    headers={"Origin": "http://localhost:3000"},
                )

            # CORS should be configured and return appropriate headers
            assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_cors_allows_methods_header_present(self) -> None:
        """GIVEN create_app() has been called
        WHEN sending a preflight OPTIONS request from an allowed origin
        THEN the response includes Access-Control-Allow-Methods header.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.options(
                    "/health",
                    headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": "GET",
                    },
                )

            assert "access-control-allow-methods" in response.headers

    @pytest.mark.asyncio
    async def test_cors_preflight_rejected_for_disallowed_origin(self) -> None:
        """GIVEN create_app() has been called
        WHEN sending a preflight OPTIONS request from a disallowed origin
        THEN the CORS headers are absent or the request is rejected.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.options(
                    "/health",
                    headers={
                        "Origin": "http://malicious-site.com",
                        "Access-Control-Request-Method": "GET",
                    },
                )

            # Either no CORS headers or rejected request
            cors_origin = response.headers.get("access-control-allow-origin", "")
            # Should not allow the malicious origin explicitly
            assert cors_origin != "http://malicious-site.com"


class TestErrorHandlers:
    """Tests for error handler configuration."""

    @pytest.mark.asyncio
    async def test_value_error_returns_422_with_json_detail(self) -> None:
        """GIVEN create_app() has been called with its error handlers registered
        WHEN a request triggers an unhandled ValueError
        THEN the response is JSON with status code 422 and 'detail' field.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()

            # Add a test route that raises ValueError
            @app.get("/test-value-error")
            async def raise_value_error() -> dict[str, str]:
                raise ValueError("Test validation error")

            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test-value-error")

            assert response.status_code == 422
            json_body = response.json()
            assert json_body is not None
            assert "detail" in json_body

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500_generic_error(self) -> None:
        """GIVEN create_app() has been called with its error handlers registered
        WHEN a request triggers an unexpected Exception
        THEN the response is 500 with a generic JSON error body.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()

            # Add a test route that raises an unexpected exception
            @app.get("/test-unexpected-error")
            async def raise_unexpected() -> dict[str, str]:
                raise RuntimeError("Unexpected internal error")

            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test-unexpected-error")

            assert response.status_code == 500
            json_body = response.json()
            assert json_body is not None
            assert "detail" in json_body

    @pytest.mark.asyncio
    async def test_unexpected_exception_does_not_leak_stack_trace(self) -> None:
        """GIVEN create_app() has been called with its error handlers registered
        WHEN a request triggers an unexpected Exception
        THEN the response does not leak stack traces.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()

            # Add a test route that raises an exception with sensitive info
            @app.get("/test-stack-trace")
            async def raise_with_sensitive_info() -> dict[str, str]:
                raise RuntimeError("Secret database password: hunter2")

            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test-stack-trace")

            assert response.status_code == 500
            response_text = response.text
            # Should not contain the sensitive error message
            assert "hunter2" not in response_text
            assert "Secret database password" not in response_text
            # Should not contain stack trace indicators
            assert "Traceback" not in response_text


class TestHealthEndpoint:
    """Tests for the /health endpoint registration."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self) -> None:
        """GIVEN create_app() has been called
        WHEN sending GET /health
        THEN the response status is 200.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_status_ok_json(self) -> None:
        """GIVEN create_app() has been called
        WHEN sending GET /health
        THEN the JSON body contains {"status": "ok"}.
        """
        from tdd_orchestrator.api.app import create_app

        mock_init = AsyncMock()
        mock_shutdown = AsyncMock()

        with (
            patch("tdd_orchestrator.api.app.init_dependencies", mock_init),
            patch("tdd_orchestrator.api.app.shutdown_dependencies", mock_shutdown),
        ):
            app = create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

            json_body = response.json()
            assert json_body is not None
            assert json_body.get("status") == "ok"

    def test_health_route_is_registered(self) -> None:
        """GIVEN create_app() has been called
        WHEN inspecting the app routes
        THEN /health route is registered.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/health" in route_paths


class TestOpenAPIMetadata:
    """Tests for OpenAPI metadata configuration."""

    def test_openapi_schema_has_correct_title(self) -> None:
        """GIVEN create_app() has been called
        WHEN accessing the OpenAPI schema
        THEN it has the title 'TDD Orchestrator'.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()
        openapi_schema = app.openapi()

        assert openapi_schema is not None
        assert openapi_schema.get("info", {}).get("title") == "TDD Orchestrator"

    def test_openapi_schema_has_correct_version(self) -> None:
        """GIVEN create_app() has been called
        WHEN accessing the OpenAPI schema
        THEN it has the version matching the package version.
        """
        from tdd_orchestrator.api.app import create_app

        app = create_app()
        openapi_schema = app.openapi()

        assert openapi_schema is not None
        assert openapi_schema.get("info", {}).get("version") == "1.0.0"
