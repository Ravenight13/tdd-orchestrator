"""Tests for the main health endpoint with circuit breaker status."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.health import router


class TestHealthEndpointNominalStatus:
    """Tests for GET /health when circuit breakers are in nominal state."""

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

    @pytest.fixture
    def nominal_health_data(self) -> dict[str, Any]:
        """Create nominal circuit health data with all circuits closed."""
        return {
            "status": "healthy",
            "circuits": [
                {
                    "name": "database",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                },
                {
                    "name": "external_api",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                },
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }

    def test_get_health_returns_200_when_nominal(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns HTTP 200 when all circuits are closed."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            assert response.status_code == 200

    def test_get_health_returns_healthy_status_when_nominal(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns overall status 'healthy' when circuits are nominal."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert json_body.get("status") == "healthy"

    def test_get_health_returns_circuits_list_when_nominal(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns list of circuit breaker statuses."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            assert isinstance(circuits, list)
            assert len(circuits) == 2

    def test_get_health_circuits_show_closed_state_when_nominal(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health circuit entries show state='closed' when nominal."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            for circuit in circuits:
                assert circuit.get("state") == "closed"

    def test_get_health_returns_valid_iso8601_timestamp(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns a valid ISO-8601 formatted timestamp."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            timestamp_str = json_body.get("timestamp", "")
            # Should not raise if valid ISO-8601
            parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            assert parsed is not None
            assert parsed.tzinfo is not None or "Z" in timestamp_str or "+" in timestamp_str


class TestHealthEndpointDegradedStatus:
    """Tests for GET /health when circuit breakers are in degraded state."""

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

    @pytest.fixture
    def degraded_health_data(self) -> dict[str, Any]:
        """Create degraded circuit health data with half-open circuits."""
        return {
            "status": "degraded",
            "circuits": [
                {
                    "name": "database",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                },
                {
                    "name": "external_api",
                    "state": "half-open",
                    "failure_count": 2,
                    "last_failure_time": "2024-01-15T10:25:00Z",
                },
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }

    def test_get_health_returns_200_when_degraded(
        self, client: TestClient, degraded_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns HTTP 200 when circuits are degraded."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=degraded_health_data,
        ):
            response = client.get("/health")
            assert response.status_code == 200

    def test_get_health_returns_degraded_status(
        self, client: TestClient, degraded_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns overall status 'degraded' when circuits are half-open."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=degraded_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert json_body.get("status") == "degraded"

    def test_get_health_shows_affected_circuit_state_when_degraded(
        self, client: TestClient, degraded_health_data: dict[str, Any]
    ) -> None:
        """GET /health shows half-open state for affected circuits."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=degraded_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            half_open_circuits = [c for c in circuits if c.get("state") == "half-open"]
            assert len(half_open_circuits) >= 1

    def test_get_health_shows_failure_count_when_degraded(
        self, client: TestClient, degraded_health_data: dict[str, Any]
    ) -> None:
        """GET /health shows failure counts for affected circuits."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=degraded_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            affected_circuit = next(
                (c for c in circuits if c.get("state") == "half-open"), None
            )
            assert affected_circuit is not None
            assert affected_circuit.get("failure_count", 0) > 0


class TestHealthEndpointUnhealthyStatus:
    """Tests for GET /health when circuit breakers are fully open (unhealthy)."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def unhealthy_health_data(self) -> dict[str, Any]:
        """Create unhealthy circuit health data with open circuits."""
        return {
            "status": "unhealthy",
            "circuits": [
                {
                    "name": "database",
                    "state": "open",
                    "failure_count": 5,
                    "last_failure_time": "2024-01-15T10:28:00Z",
                },
                {
                    "name": "external_api",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                },
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }

    def test_get_health_returns_503_when_unhealthy(
        self, client: TestClient, unhealthy_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns HTTP 503 when circuits are fully open."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=unhealthy_health_data,
        ):
            response = client.get("/health")
            assert response.status_code == 503

    def test_get_health_returns_unhealthy_status(
        self, client: TestClient, unhealthy_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns overall status 'unhealthy' when circuits are open."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=unhealthy_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert json_body.get("status") == "unhealthy"

    def test_get_health_shows_open_state_for_tripped_circuits(
        self, client: TestClient, unhealthy_health_data: dict[str, Any]
    ) -> None:
        """GET /health shows state='open' for tripped circuit breakers."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=unhealthy_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            open_circuits = [c for c in circuits if c.get("state") == "open"]
            assert len(open_circuits) >= 1

    def test_get_health_shows_failure_count_for_open_circuits(
        self, client: TestClient, unhealthy_health_data: dict[str, Any]
    ) -> None:
        """GET /health shows failure_count for open circuits."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=unhealthy_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            open_circuit = next((c for c in circuits if c.get("state") == "open"), None)
            assert open_circuit is not None
            assert open_circuit.get("failure_count", 0) > 0

    def test_get_health_shows_last_failure_time_for_open_circuits(
        self, client: TestClient, unhealthy_health_data: dict[str, Any]
    ) -> None:
        """GET /health shows last_failure_time for open circuits."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=unhealthy_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            circuits = json_body.get("circuits", [])
            open_circuit = next((c for c in circuits if c.get("state") == "open"), None)
            assert open_circuit is not None
            last_failure = open_circuit.get("last_failure_time")
            assert last_failure is not None
            assert isinstance(last_failure, str)
            assert len(last_failure) > 0


class TestHealthEndpointExceptionHandling:
    """Tests for GET /health when get_circuit_health raises an exception."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_health_returns_503_when_exception_raised(
        self, client: TestClient
    ) -> None:
        """GET /health returns HTTP 503 when get_circuit_health raises an exception."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=RuntimeError("Unexpected error in health check"),
        ):
            response = client.get("/health")
            assert response.status_code == 503

    def test_get_health_returns_unhealthy_status_when_exception_raised(
        self, client: TestClient
    ) -> None:
        """GET /health returns status 'unhealthy' when exception is raised."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=RuntimeError("Unexpected error"),
        ):
            response = client.get("/health")
            json_body = response.json()
            assert json_body.get("status") == "unhealthy"

    def test_get_health_returns_error_message_when_exception_raised(
        self, client: TestClient
    ) -> None:
        """GET /health returns error message indicating health check failure."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=RuntimeError("Unexpected error"),
        ):
            response = client.get("/health")
            json_body = response.json()
            # Should have some indication of error
            error_msg = json_body.get("error", "") or json_body.get("detail", "")
            assert len(error_msg) > 0 or json_body.get("status") == "unhealthy"

    def test_get_health_never_returns_500_on_exception(
        self, client: TestClient
    ) -> None:
        """GET /health never returns 500 unhandled error, always gracefully returns 503."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=Exception("Completely unexpected error"),
        ):
            response = client.get("/health")
            # Should be 503, not 500
            assert response.status_code == 503
            assert response.status_code != 500

    def test_get_health_handles_attribute_error(self, client: TestClient) -> None:
        """GET /health handles AttributeError gracefully."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=AttributeError("Missing attribute"),
        ):
            response = client.get("/health")
            assert response.status_code == 503
            json_body = response.json()
            assert json_body.get("status") == "unhealthy"

    def test_get_health_handles_value_error(self, client: TestClient) -> None:
        """GET /health handles ValueError gracefully."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            side_effect=ValueError("Invalid value"),
        ):
            response = client.get("/health")
            assert response.status_code == 503
            json_body = response.json()
            assert json_body.get("status") == "unhealthy"


class TestHealthEndpointPublicAccess:
    """Tests for GET /health being publicly accessible."""

    @pytest.fixture
    def nominal_health_data(self) -> dict[str, Any]:
        """Create nominal circuit health data."""
        return {
            "status": "healthy",
            "circuits": [
                {
                    "name": "database",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                }
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }

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

    def test_get_health_accessible_without_authentication(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health is accessible without any authentication headers."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            # No Authorization header, no API key, nothing
            response = client.get("/health")
            assert response.status_code == 200

    def test_get_health_accessible_without_special_headers(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health is accessible without any special headers."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health", headers={})
            assert response.status_code == 200

    def test_get_health_response_contains_status_field(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health response contains required 'status' field (str)."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert "status" in json_body
            assert isinstance(json_body["status"], str)

    def test_get_health_response_contains_circuits_field(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health response contains required 'circuits' field (list)."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert "circuits" in json_body
            assert isinstance(json_body["circuits"], list)

    def test_get_health_response_contains_timestamp_field(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health response contains required 'timestamp' field (str)."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert "timestamp" in json_body
            assert isinstance(json_body["timestamp"], str)

    def test_get_health_returns_json_content_type(
        self, client: TestClient, nominal_health_data: dict[str, Any]
    ) -> None:
        """GET /health returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=nominal_health_data,
        ):
            response = client.get("/health")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type


class TestHealthEndpointEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the health router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_health_with_empty_circuits_list(self, client: TestClient) -> None:
        """GET /health handles empty circuits list."""
        health_data = {
            "status": "healthy",
            "circuits": [],
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=health_data,
        ):
            response = client.get("/health")
            json_body = response.json()
            assert json_body.get("status") == "healthy"
            assert json_body.get("circuits") == []

    def test_get_health_with_multiple_open_circuits(self, client: TestClient) -> None:
        """GET /health handles multiple open circuits."""
        health_data = {
            "status": "unhealthy",
            "circuits": [
                {
                    "name": "database",
                    "state": "open",
                    "failure_count": 5,
                    "last_failure_time": "2024-01-15T10:28:00Z",
                },
                {
                    "name": "cache",
                    "state": "open",
                    "failure_count": 3,
                    "last_failure_time": "2024-01-15T10:27:00Z",
                },
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=health_data,
        ):
            response = client.get("/health")
            assert response.status_code == 503
            json_body = response.json()
            open_circuits = [
                c for c in json_body.get("circuits", []) if c.get("state") == "open"
            ]
            assert len(open_circuits) == 2

    def test_get_health_with_mixed_circuit_states(self, client: TestClient) -> None:
        """GET /health handles mix of closed, half-open, and open circuits."""
        health_data = {
            "status": "unhealthy",
            "circuits": [
                {
                    "name": "database",
                    "state": "closed",
                    "failure_count": 0,
                    "last_failure_time": None,
                },
                {
                    "name": "cache",
                    "state": "half-open",
                    "failure_count": 2,
                    "last_failure_time": "2024-01-15T10:25:00Z",
                },
                {
                    "name": "external_api",
                    "state": "open",
                    "failure_count": 5,
                    "last_failure_time": "2024-01-15T10:28:00Z",
                },
            ],
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=health_data,
        ):
            response = client.get("/health")
            assert response.status_code == 503
            json_body = response.json()
            assert json_body.get("status") == "unhealthy"
            circuits = json_body.get("circuits", [])
            states = [c.get("state") for c in circuits]
            assert "closed" in states
            assert "half-open" in states
            assert "open" in states

    def test_get_health_with_query_params_still_works(self, client: TestClient) -> None:
        """GET /health with query parameters still returns health data."""
        health_data = {
            "status": "healthy",
            "circuits": [],
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with patch(
            "tdd_orchestrator.api.routes.health.get_circuit_health",
            return_value=health_data,
        ):
            response = client.get("/health?verbose=true&format=json")
            assert response.status_code == 200
            json_body = response.json()
            assert json_body.get("status") == "healthy"


class TestHealthEndpointMethodNotAllowed:
    """Tests for non-GET methods on /health returning 405."""

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

    def test_post_health_returns_405(self, client: TestClient) -> None:
        """POST /health returns HTTP 405 Method Not Allowed."""
        response = client.post("/health")
        assert response.status_code == 405

    def test_put_health_returns_405(self, client: TestClient) -> None:
        """PUT /health returns HTTP 405 Method Not Allowed."""
        response = client.put("/health")
        assert response.status_code == 405

    def test_delete_health_returns_405(self, client: TestClient) -> None:
        """DELETE /health returns HTTP 405 Method Not Allowed."""
        response = client.delete("/health")
        assert response.status_code == 405

    def test_patch_health_returns_405(self, client: TestClient) -> None:
        """PATCH /health returns HTTP 405 Method Not Allowed."""
        response = client.patch("/health")
        assert response.status_code == 405
