"""Tests for route registration functionality.

Tests the register_routes() function that wires all route modules
(health, tasks, workers, circuits, runs, metrics) to a FastAPI app.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.routes.__init__ import register_routes


class TestRegisterRoutesModuleInclusion:
    """Tests that register_routes includes all required route modules."""

    def test_registers_health_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN health routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        health_routes = [p for p in route_paths if p.startswith("/health")]

        assert len(health_routes) > 0, "Expected at least one /health route"

    def test_registers_tasks_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN tasks routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        tasks_routes = [p for p in route_paths if p.startswith("/tasks")]

        assert len(tasks_routes) > 0, "Expected at least one /tasks route"

    def test_registers_workers_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN workers routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        workers_routes = [p for p in route_paths if p.startswith("/workers")]

        assert len(workers_routes) > 0, "Expected at least one /workers route"

    def test_registers_circuits_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN circuits routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        circuits_routes = [p for p in route_paths if p.startswith("/circuits")]

        assert len(circuits_routes) > 0, "Expected at least one /circuits route"

    def test_registers_runs_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN runs routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        runs_routes = [p for p in route_paths if p.startswith("/runs")]

        assert len(runs_routes) > 0, "Expected at least one /runs route"

    def test_registers_metrics_routes_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN metrics routes are included."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        metrics_routes = [p for p in route_paths if p.startswith("/metrics")]

        assert len(metrics_routes) > 0, "Expected at least one /metrics route"

    def test_registers_all_six_modules_when_called(self) -> None:
        """GIVEN a fresh FastAPI app WHEN register_routes is called THEN all six modules are registered."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]

        expected_prefixes = ["/health", "/tasks", "/workers", "/circuits", "/runs", "/metrics"]
        for prefix in expected_prefixes:
            matching_routes = [p for p in route_paths if p.startswith(prefix)]
            assert len(matching_routes) > 0, f"Expected at least one route with prefix {prefix}"


class TestRegisterRoutesCorrectPrefixes:
    """Tests that routes are mounted under correct URL prefixes."""

    def test_tasks_routes_mounted_under_tasks_prefix(self) -> None:
        """GIVEN a FastAPI app with register_routes THEN tasks routes are under /tasks not /."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        # Verify tasks routes start with /tasks, not just /
        tasks_routes = [p for p in route_paths if "/tasks" in p]

        assert all(
            p.startswith("/tasks") for p in tasks_routes
        ), "All tasks routes should start with /tasks"

    def test_health_routes_mounted_at_health_not_api_health(self) -> None:
        """GIVEN a FastAPI app with register_routes THEN health routes are at /health not /api/health."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        health_routes = [p for p in route_paths if "health" in p.lower()]

        # Should have /health, not /api/health
        assert any(
            p.startswith("/health") for p in health_routes
        ), "Health routes should start with /health"
        assert not any(
            p.startswith("/api/health") for p in health_routes
        ), "Health routes should not be under /api/health"

    def test_all_module_routes_have_correct_prefix_membership(self) -> None:
        """GIVEN a FastAPI app with register_routes THEN each module's paths have correct prefixes."""
        app = FastAPI()
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]

        prefix_map = {
            "/health": "health",
            "/tasks": "tasks",
            "/workers": "workers",
            "/circuits": "circuits",
            "/runs": "runs",
            "/metrics": "metrics",
        }

        for prefix, module_name in prefix_map.items():
            module_routes = [p for p in route_paths if p.startswith(prefix)]
            assert len(module_routes) > 0, f"Module {module_name} should have routes under {prefix}"


class TestRegisterRoutesHealthEndpoint:
    """Tests for health endpoint reachability via TestClient."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200_when_routes_registered(self) -> None:
        """GIVEN a FastAPI app with register_routes WHEN GET /health THEN status is 200."""
        app = FastAPI()
        register_routes(app)

        async with ASGITransport(app=app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

        assert response.status_code == 200, "Health endpoint should return 200"

    @pytest.mark.asyncio
    async def test_health_endpoint_reachable_without_404(self) -> None:
        """GIVEN a FastAPI app with register_routes WHEN GET /health THEN no 404 error."""
        app = FastAPI()
        register_routes(app)

        async with ASGITransport(app=app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

        assert response.status_code != 404, "Health endpoint should not return 404"


class TestRegisterRoutesUnregisteredPaths:
    """Tests for behavior with unregistered paths."""

    @pytest.mark.asyncio
    async def test_unregistered_path_returns_404(self) -> None:
        """GIVEN a FastAPI app with register_routes WHEN GET /nonexistent THEN status is 404."""
        app = FastAPI()
        register_routes(app)

        async with ASGITransport(app=app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/nonexistent")

        assert response.status_code == 404, "Unregistered path should return 404"

    @pytest.mark.asyncio
    async def test_no_catchall_route_installed(self) -> None:
        """GIVEN a FastAPI app with register_routes THEN no catch-all or wildcard route exists."""
        app = FastAPI()
        register_routes(app)

        async with ASGITransport(app=app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Test multiple random paths to ensure no catch-all
                response1 = await client.get("/random/path/that/does/not/exist")
                response2 = await client.get("/another-nonexistent")
                response3 = await client.get("/foo/bar/baz")

        assert response1.status_code == 404, "Random path should return 404"
        assert response2.status_code == 404, "Another random path should return 404"
        assert response3.status_code == 404, "Yet another random path should return 404"


class TestRegisterRoutesIdempotency:
    """Tests for idempotency when register_routes is called multiple times."""

    def test_routes_not_duplicated_when_called_twice(self) -> None:
        """GIVEN register_routes called twice THEN routes are not duplicated."""
        app = FastAPI()

        register_routes(app)
        routes_after_first_call = len([r for r in app.routes if hasattr(r, "path")])

        register_routes(app)
        routes_after_second_call = len([r for r in app.routes if hasattr(r, "path")])

        assert routes_after_first_call == routes_after_second_call, (
            "Route count should remain same after second call"
        )

    def test_health_route_count_unchanged_after_multiple_calls(self) -> None:
        """GIVEN register_routes called multiple times THEN health route count unchanged."""
        app = FastAPI()

        register_routes(app)
        health_count_first = len([
            r for r in app.routes
            if hasattr(r, "path") and r.path.startswith("/health")
        ])

        register_routes(app)
        register_routes(app)
        health_count_after = len([
            r for r in app.routes
            if hasattr(r, "path") and r.path.startswith("/health")
        ])

        assert health_count_first == health_count_after, (
            "Health route count should not increase after multiple calls"
        )

    def test_each_prefix_route_count_stable_after_multiple_calls(self) -> None:
        """GIVEN register_routes called multiple times THEN each prefix route count is stable."""
        app = FastAPI()
        prefixes = ["/health", "/tasks", "/workers", "/circuits", "/runs", "/metrics"]

        register_routes(app)
        counts_first: dict[str, int] = {}
        for prefix in prefixes:
            counts_first[prefix] = len([
                r for r in app.routes
                if hasattr(r, "path") and r.path.startswith(prefix)
            ])

        register_routes(app)
        register_routes(app)

        for prefix in prefixes:
            count_after = len([
                r for r in app.routes
                if hasattr(r, "path") and r.path.startswith(prefix)
            ])
            assert counts_first[prefix] == count_after, (
                f"Route count for {prefix} should remain {counts_first[prefix]}, got {count_after}"
            )


class TestRegisterRoutesEdgeCases:
    """Edge case tests for register_routes."""

    def test_accepts_fresh_fastapi_app(self) -> None:
        """GIVEN a brand new FastAPI app WHEN register_routes is called THEN no error raised."""
        app = FastAPI()
        # Should not raise any exception
        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert len(route_paths) > 0, "Should have registered some routes"

    def test_works_with_app_that_has_existing_routes(self) -> None:
        """GIVEN a FastAPI app with existing routes WHEN register_routes is called THEN both work."""
        app = FastAPI()

        @app.get("/custom")
        def custom_route() -> dict[str, str]:
            return {"custom": "route"}

        register_routes(app)

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]

        # Should have both custom and registered routes
        assert "/custom" in route_paths, "Custom route should still exist"
        assert any(p.startswith("/health") for p in route_paths), "Health routes should be added"

    @pytest.mark.asyncio
    async def test_registered_routes_functional_after_registration(self) -> None:
        """GIVEN register_routes is called THEN registered routes are functional."""
        app = FastAPI()
        register_routes(app)

        async with ASGITransport(app=app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Health should be functional
                health_response = await client.get("/health")

        # At minimum, health should not 404 (meaning route is registered and functional)
        assert health_response.status_code != 404, "Health route should be functional"
