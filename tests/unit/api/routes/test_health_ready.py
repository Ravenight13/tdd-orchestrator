"""Tests for the health router readiness endpoint."""

import asyncio
from typing import Any, AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.routes.health import router


class TestHealthReadyEndpointSuccess:
    """Tests for GET /health/ready when database is reachable."""

    @pytest.fixture
    def mock_db(self) -> Any:
        """Create a mock database object."""

        class MockDB:
            """Mock database that simulates successful connectivity."""

            pass

        return MockDB()

    @pytest.fixture
    def app(self, mock_db: Any) -> FastAPI:
        """Create a FastAPI app with the health router and mocked db dependency."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        async def override_get_db_dep() -> AsyncGenerator[Any, None]:
            yield mock_db

        app.dependency_overrides[get_db_dep] = override_get_db_dep
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_health_ready_returns_200_when_db_reachable(
        self, client: TestClient
    ) -> None:
        """GET /health/ready returns HTTP 200 when database is reachable."""
        response = client.get("/health/ready")
        assert response.status_code == 200

    def test_get_health_ready_returns_ok_status_when_db_reachable(
        self, client: TestClient
    ) -> None:
        """GET /health/ready returns JSON body with status 'ok' when db is reachable."""
        response = client.get("/health/ready")
        json_body = response.json()
        assert json_body == {"status": "ok"}

    def test_get_health_ready_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """GET /health/ready returns Content-Type application/json."""
        response = client.get("/health/ready")
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type


class TestHealthReadyEndpointDatabaseFailure:
    """Tests for GET /health/ready when database connection fails."""

    @pytest.fixture
    def app_with_db_exception(self) -> FastAPI:
        """Create a FastAPI app with db dependency that raises an exception."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        async def override_get_db_dep_raises() -> AsyncGenerator[Any, None]:
            raise RuntimeError("Database connection failed")
            yield  # type: ignore[misc]  # unreachable but needed for generator

        app.dependency_overrides[get_db_dep] = override_get_db_dep_raises
        return app

    @pytest.fixture
    def client_with_db_exception(self, app_with_db_exception: FastAPI) -> TestClient:
        """Create a test client for the app with failing db."""
        return TestClient(app_with_db_exception, raise_server_exceptions=False)

    def test_get_health_ready_returns_503_when_db_connection_fails(
        self, client_with_db_exception: TestClient
    ) -> None:
        """GET /health/ready returns HTTP 503 when database connection fails."""
        response = client_with_db_exception.get("/health/ready")
        assert response.status_code == 503

    def test_get_health_ready_returns_unavailable_status_when_db_fails(
        self, client_with_db_exception: TestClient
    ) -> None:
        """GET /health/ready returns status 'unavailable' when db connection fails."""
        response = client_with_db_exception.get("/health/ready")
        json_body = response.json()
        assert json_body.get("status") == "unavailable"

    def test_get_health_ready_returns_detail_field_when_db_fails(
        self, client_with_db_exception: TestClient
    ) -> None:
        """GET /health/ready returns detail field describing connectivity issue."""
        response = client_with_db_exception.get("/health/ready")
        json_body = response.json()
        assert "detail" in json_body
        assert isinstance(json_body["detail"], str)
        assert len(json_body["detail"]) > 0


class TestHealthReadyEndpointDatabaseTimeout:
    """Tests for GET /health/ready when database query times out."""

    @pytest.fixture
    def app_with_db_timeout(self) -> FastAPI:
        """Create a FastAPI app with db dependency that simulates a timeout."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        async def override_get_db_dep_timeout() -> AsyncGenerator[Any, None]:
            raise asyncio.TimeoutError("Database query timed out")
            yield  # type: ignore[misc]  # unreachable but needed for generator

        app.dependency_overrides[get_db_dep] = override_get_db_dep_timeout
        return app

    @pytest.fixture
    def client_with_db_timeout(self, app_with_db_timeout: FastAPI) -> TestClient:
        """Create a test client for the app with timing out db."""
        return TestClient(app_with_db_timeout, raise_server_exceptions=False)

    def test_get_health_ready_returns_503_when_db_times_out(
        self, client_with_db_timeout: TestClient
    ) -> None:
        """GET /health/ready returns HTTP 503 when database times out."""
        response = client_with_db_timeout.get("/health/ready")
        assert response.status_code == 503

    def test_get_health_ready_returns_unavailable_status_when_db_times_out(
        self, client_with_db_timeout: TestClient
    ) -> None:
        """GET /health/ready returns unavailable status when db times out."""
        response = client_with_db_timeout.get("/health/ready")
        json_body = response.json()
        assert json_body.get("status") == "unavailable"

    def test_get_health_ready_does_not_hang_on_timeout(
        self, client_with_db_timeout: TestClient
    ) -> None:
        """GET /health/ready does not hang indefinitely on timeout."""
        import time

        start = time.perf_counter()
        response = client_with_db_timeout.get("/health/ready")
        elapsed = time.perf_counter() - start

        assert response.status_code == 503
        # Should respond quickly, not hang (less than 5 seconds)
        assert elapsed < 5.0, f"Response took {elapsed:.3f}s, should not hang"


class TestHealthReadyRouterIntegration:
    """Tests for /health/ready being on the same router as /health/live."""

    @pytest.fixture
    def mock_db(self) -> Any:
        """Create a mock database object."""

        class MockDB:
            pass

        return MockDB()

    @pytest.fixture
    def app(self, mock_db: Any) -> FastAPI:
        """Create a FastAPI app with the health router."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        async def override_get_db_dep() -> AsyncGenerator[Any, None]:
            yield mock_db

        app.dependency_overrides[get_db_dep] = override_get_db_dep
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_health_live_and_ready_both_accessible_on_same_router(
        self, client: TestClient
    ) -> None:
        """Both /health/live and /health/ready are accessible on the same router."""
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")

        assert live_response.status_code == 200
        assert ready_response.status_code == 200

    def test_health_ready_endpoint_exists_alongside_live(
        self, client: TestClient
    ) -> None:
        """The /health/ready endpoint is registered on the existing health router."""
        response = client.get("/health/ready")
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code == 200


class TestHealthReadyMultipleInvocations:
    """Tests for multiple sequential calls to /health/ready."""

    @pytest.fixture
    def invocation_counter(self) -> dict[str, int]:
        """Create a mutable counter to track invocations."""
        return {"count": 0}

    @pytest.fixture
    def app_with_counting_db(self, invocation_counter: dict[str, int]) -> FastAPI:
        """Create a FastAPI app that counts db dependency invocations."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        class CountingMockDB:
            """Mock DB that tracks how many times it was accessed."""

            def __init__(self, counter: dict[str, int]) -> None:
                self.counter = counter
                self.counter["count"] += 1

        async def override_get_db_dep() -> AsyncGenerator[Any, None]:
            yield CountingMockDB(invocation_counter)

        app.dependency_overrides[get_db_dep] = override_get_db_dep
        return app

    @pytest.fixture
    def client_with_counting_db(
        self, app_with_counting_db: FastAPI
    ) -> TestClient:
        """Create a test client for the app with counting db."""
        return TestClient(app_with_counting_db)

    def test_multiple_ready_calls_each_verify_db_connectivity(
        self, client_with_counting_db: TestClient, invocation_counter: dict[str, int]
    ) -> None:
        """Each GET /health/ready call independently verifies database connectivity."""
        # Reset counter
        invocation_counter["count"] = 0

        # Make 3 sequential calls
        for i in range(3):
            response = client_with_counting_db.get("/health/ready")
            assert response.status_code == 200
            # Each call should have incremented the counter
            assert invocation_counter["count"] == i + 1

    def test_multiple_ready_calls_all_return_200(
        self, client_with_counting_db: TestClient
    ) -> None:
        """Multiple sequential GET /health/ready calls all return HTTP 200."""
        responses = [client_with_counting_db.get("/health/ready") for _ in range(5)]

        for response in responses:
            assert response.status_code == 200

    def test_no_connection_state_leaked_between_invocations(
        self, client_with_counting_db: TestClient, invocation_counter: dict[str, int]
    ) -> None:
        """No connection state is leaked between probe invocations."""
        invocation_counter["count"] = 0

        # First call
        response1 = client_with_counting_db.get("/health/ready")
        count_after_first = invocation_counter["count"]

        # Second call
        response2 = client_with_counting_db.get("/health/ready")
        count_after_second = invocation_counter["count"]

        # Each call should independently create/access db
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert count_after_first == 1
        assert count_after_second == 2


class TestHealthReadyMethodNotAllowed:
    """Tests for non-GET methods on /health/ready returning 405."""

    @pytest.fixture
    def mock_db(self) -> Any:
        """Create a mock database object."""

        class MockDB:
            pass

        return MockDB()

    @pytest.fixture
    def app(self, mock_db: Any) -> FastAPI:
        """Create a FastAPI app with the health router."""
        app = FastAPI()
        app.include_router(router, prefix="/health")

        async def override_get_db_dep() -> AsyncGenerator[Any, None]:
            yield mock_db

        app.dependency_overrides[get_db_dep] = override_get_db_dep
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_health_ready_returns_405(self, client: TestClient) -> None:
        """POST /health/ready returns HTTP 405 Method Not Allowed."""
        response = client.post("/health/ready")
        assert response.status_code == 405

    def test_put_health_ready_returns_405(self, client: TestClient) -> None:
        """PUT /health/ready returns HTTP 405 Method Not Allowed."""
        response = client.put("/health/ready")
        assert response.status_code == 405

    def test_delete_health_ready_returns_405(self, client: TestClient) -> None:
        """DELETE /health/ready returns HTTP 405 Method Not Allowed."""
        response = client.delete("/health/ready")
        assert response.status_code == 405

    def test_patch_health_ready_returns_405(self, client: TestClient) -> None:
        """PATCH /health/ready returns HTTP 405 Method Not Allowed."""
        response = client.patch("/health/ready")
        assert response.status_code == 405
