"""Tests for the health router liveness endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.health import router


class TestHealthLiveEndpoint:
    """Tests for GET /health/live endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_health_live_returns_200(self, client: TestClient) -> None:
        """GET /health/live returns HTTP 200 status code."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_get_health_live_returns_alive_status(self, client: TestClient) -> None:
        """GET /health/live returns JSON body with status 'alive'."""
        response = client.get("/health/live")
        assert response.json() == {"status": "alive"}

    def test_get_health_live_returns_json_content_type(self, client: TestClient) -> None:
        """GET /health/live returns Content-Type application/json."""
        response = client.get("/health/live")
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_get_health_live_with_query_params_returns_200(self, client: TestClient) -> None:
        """GET /health/live with arbitrary query parameters still returns 200."""
        response = client.get("/health/live?foo=bar")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_get_health_live_with_multiple_query_params_returns_200(self, client: TestClient) -> None:
        """GET /health/live with multiple query parameters still returns 200."""
        response = client.get("/health/live?foo=bar&baz=qux&num=123")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_get_health_live_ignores_extraneous_input(self, client: TestClient) -> None:
        """GET /health/live ignores extraneous query input and returns alive status."""
        response = client.get("/health/live?unexpected=value&another=param")
        json_body = response.json()
        assert json_body == {"status": "alive"}
        assert "unexpected" not in json_body
        assert "another" not in json_body


class TestHealthLiveMethodNotAllowed:
    """Tests for non-GET methods on /health/live returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_health_live_returns_405(self, client: TestClient) -> None:
        """POST /health/live returns HTTP 405 Method Not Allowed."""
        response = client.post("/health/live")
        assert response.status_code == 405

    def test_put_health_live_returns_405(self, client: TestClient) -> None:
        """PUT /health/live returns HTTP 405 Method Not Allowed."""
        response = client.put("/health/live")
        assert response.status_code == 405

    def test_delete_health_live_returns_405(self, client: TestClient) -> None:
        """DELETE /health/live returns HTTP 405 Method Not Allowed."""
        response = client.delete("/health/live")
        assert response.status_code == 405

    def test_patch_health_live_returns_405(self, client: TestClient) -> None:
        """PATCH /health/live returns HTTP 405 Method Not Allowed."""
        response = client.patch("/health/live")
        assert response.status_code == 405


class TestHealthRouterMounting:
    """Tests for health router mountability."""

    def test_router_is_mountable_on_fastapi_app(self) -> None:
        """The health router can be mounted on a FastAPI app."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_router_mounted_at_custom_prefix(self) -> None:
        """The health router can be mounted at a custom prefix."""
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/health")
        client = TestClient(app)
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_full_path_health_live_is_routable(self) -> None:
        """The full path /health/live is routable via include_router."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        client = TestClient(app)
        # Verify the route exists and is accessible
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


class TestHealthLivePerformance:
    """Tests for health endpoint performance characteristics."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_health_live_responds_quickly(self, client: TestClient) -> None:
        """GET /health/live responds within acceptable latency (no I/O)."""
        import time

        start = time.perf_counter()
        response = client.get("/health/live")
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        # A static response with no I/O should be very fast (< 100ms)
        assert elapsed < 0.1, f"Response took {elapsed:.3f}s, expected < 0.1s"
