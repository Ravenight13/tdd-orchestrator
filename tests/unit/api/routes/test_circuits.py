"""Tests for circuit breaker CRUD endpoints.

Tests the following endpoints:
- GET /circuits - List circuits with optional level/state filters
- GET /circuits/{id} - Get a circuit by ID
- POST /circuits/{id}/reset - Reset a circuit
- GET /circuits/health - Get circuit health summary
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.circuits import router


class TestListCircuitsNoFilters:
    """Tests for GET /circuits with no filters."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def circuits_data(self) -> list[dict[str, Any]]:
        """Create mock circuit data with varying levels and states."""
        return [
            {
                "id": str(uuid4()),
                "level": "task",
                "state": "closed",
                "failure_count": 0,
                "last_failure_at": None,
                "opened_at": None,
            },
            {
                "id": str(uuid4()),
                "level": "phase",
                "state": "open",
                "failure_count": 3,
                "last_failure_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                "opened_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            },
            {
                "id": str(uuid4()),
                "level": "pipeline",
                "state": "half_open",
                "failure_count": 1,
                "last_failure_at": datetime(2024, 1, 15, 10, 25, 0, tzinfo=timezone.utc),
                "opened_at": datetime(2024, 1, 15, 10, 25, 0, tzinfo=timezone.utc),
            },
        ]

    def test_get_circuits_returns_200_when_circuits_exist(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits returns HTTP 200 when circuits exist."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            assert response.status_code == 200

    def test_get_circuits_returns_list_of_circuits(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits returns a list of CircuitBreakerResponse objects."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert isinstance(json_body, list)
            assert len(json_body) == 3

    def test_get_circuits_response_contains_id_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include id field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "id" in json_body[0]

    def test_get_circuits_response_contains_level_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include level field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "level" in json_body[0]

    def test_get_circuits_response_contains_state_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include state field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "state" in json_body[0]

    def test_get_circuits_response_contains_failure_count_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include failure_count field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "failure_count" in json_body[0]

    def test_get_circuits_response_contains_last_failure_at_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include last_failure_at field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "last_failure_at" in json_body[0]

    def test_get_circuits_response_contains_opened_at_field(
        self, client: TestClient, circuits_data: list[dict[str, Any]]
    ) -> None:
        """GET /circuits response items include opened_at field."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=circuits_data,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert "opened_at" in json_body[0]


class TestListCircuitsWithFilters:
    """Tests for GET /circuits with level and state filters."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def filtered_circuits(self) -> list[dict[str, Any]]:
        """Create mock filtered circuit data (task level, open state)."""
        return [
            {
                "id": str(uuid4()),
                "level": "task",
                "state": "open",
                "failure_count": 5,
                "last_failure_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                "opened_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            },
        ]

    def test_get_circuits_with_level_and_state_filter_returns_200(
        self, client: TestClient, filtered_circuits: list[dict[str, Any]]
    ) -> None:
        """GET /circuits?level=task&state=open returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=filtered_circuits,
        ):
            response = client.get("/circuits?level=task&state=open")
            assert response.status_code == 200

    def test_get_circuits_with_level_and_state_filter_returns_matching_circuits(
        self, client: TestClient, filtered_circuits: list[dict[str, Any]]
    ) -> None:
        """GET /circuits?level=task&state=open returns only matching circuits."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=filtered_circuits,
        ):
            response = client.get("/circuits?level=task&state=open")
            json_body = response.json()
            assert isinstance(json_body, list)
            assert len(json_body) == 1
            assert json_body[0]["level"] == "task"
            assert json_body[0]["state"] == "open"

    def test_get_circuits_with_nonexistent_level_returns_200_empty_list(
        self, client: TestClient
    ) -> None:
        """GET /circuits?level=nonexistent returns HTTP 200 with empty list."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=[],
        ):
            response = client.get("/circuits?level=nonexistent")
            assert response.status_code == 200
            json_body = response.json()
            assert isinstance(json_body, list)
            assert len(json_body) == 0

    def test_get_circuits_when_no_circuits_exist_returns_200_empty_list(
        self, client: TestClient
    ) -> None:
        """GET /circuits returns HTTP 200 with empty list when no circuits exist."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=[],
        ):
            response = client.get("/circuits")
            assert response.status_code == 200
            json_body = response.json()
            assert isinstance(json_body, list)
            assert len(json_body) == 0

    def test_get_circuits_with_level_only_filter_returns_200(
        self, client: TestClient, filtered_circuits: list[dict[str, Any]]
    ) -> None:
        """GET /circuits?level=task returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=filtered_circuits,
        ):
            response = client.get("/circuits?level=task")
            assert response.status_code == 200

    def test_get_circuits_with_state_only_filter_returns_200(
        self, client: TestClient, filtered_circuits: list[dict[str, Any]]
    ) -> None:
        """GET /circuits?state=open returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=filtered_circuits,
        ):
            response = client.get("/circuits?state=open")
            assert response.status_code == 200


class TestGetCircuitById:
    """Tests for GET /circuits/{id} endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def open_circuit(self) -> dict[str, Any]:
        """Create mock open circuit data."""
        return {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "level": "task",
            "state": "open",
            "failure_count": 5,
            "last_failure_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "opened_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }

    def test_get_circuit_by_id_returns_200_when_circuit_exists(
        self, client: TestClient, open_circuit: dict[str, Any]
    ) -> None:
        """GET /circuits/{id} returns HTTP 200 when circuit exists."""
        circuit_id = open_circuit["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_by_id",
            return_value=open_circuit,
        ):
            response = client.get(f"/circuits/{circuit_id}")
            assert response.status_code == 200

    def test_get_circuit_by_id_returns_full_circuit_response(
        self, client: TestClient, open_circuit: dict[str, Any]
    ) -> None:
        """GET /circuits/{id} returns full CircuitBreakerResponse."""
        circuit_id = open_circuit["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_by_id",
            return_value=open_circuit,
        ):
            response = client.get(f"/circuits/{circuit_id}")
            json_body = response.json()
            assert json_body.get("id") == circuit_id
            assert json_body.get("level") == "task"
            assert json_body.get("state") == "open"
            assert json_body.get("failure_count") == 5
            assert "last_failure_at" in json_body
            assert "opened_at" in json_body

    def test_get_circuit_by_id_returns_404_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /circuits/{id} returns HTTP 404 when circuit does not exist."""
        nonexistent_id = str(uuid4())
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_by_id",
            return_value=None,
        ):
            response = client.get(f"/circuits/{nonexistent_id}")
            assert response.status_code == 404

    def test_get_circuit_by_id_returns_error_detail_when_not_found(
        self, client: TestClient
    ) -> None:
        """GET /circuits/{id} returns detail message when circuit not found."""
        nonexistent_id = str(uuid4())
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_by_id",
            return_value=None,
        ):
            response = client.get(f"/circuits/{nonexistent_id}")
            json_body = response.json()
            detail = json_body.get("detail", "")
            assert "not found" in detail.lower() or detail != ""


class TestResetCircuit:
    """Tests for POST /circuits/{id}/reset endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def open_circuit_before_reset(self) -> dict[str, Any]:
        """Create mock open circuit data before reset."""
        return {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "level": "task",
            "state": "open",
            "failure_count": 5,
            "last_failure_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "opened_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }

    @pytest.fixture
    def reset_circuit_result(self) -> dict[str, Any]:
        """Create mock circuit data after reset."""
        return {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "level": "task",
            "state": "closed",
            "failure_count": 0,
            "last_failure_at": None,
            "opened_at": None,
        }

    def test_reset_circuit_returns_200_when_circuit_exists(
        self, client: TestClient, reset_circuit_result: dict[str, Any]
    ) -> None:
        """POST /circuits/{id}/reset returns HTTP 200 when circuit exists."""
        circuit_id = reset_circuit_result["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=reset_circuit_result,
        ):
            response = client.post(f"/circuits/{circuit_id}/reset")
            assert response.status_code == 200

    def test_reset_circuit_returns_closed_state_after_reset(
        self, client: TestClient, reset_circuit_result: dict[str, Any]
    ) -> None:
        """POST /circuits/{id}/reset returns circuit with state='closed'."""
        circuit_id = reset_circuit_result["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=reset_circuit_result,
        ):
            response = client.post(f"/circuits/{circuit_id}/reset")
            json_body = response.json()
            assert json_body.get("state") == "closed"

    def test_reset_circuit_returns_zero_failure_count_after_reset(
        self, client: TestClient, reset_circuit_result: dict[str, Any]
    ) -> None:
        """POST /circuits/{id}/reset returns circuit with failure_count=0."""
        circuit_id = reset_circuit_result["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=reset_circuit_result,
        ):
            response = client.post(f"/circuits/{circuit_id}/reset")
            json_body = response.json()
            assert json_body.get("failure_count") == 0

    def test_reset_circuit_returns_404_when_not_found(
        self, client: TestClient
    ) -> None:
        """POST /circuits/{id}/reset returns HTTP 404 when circuit does not exist."""
        nonexistent_id = str(uuid4())
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=None,
        ):
            response = client.post(f"/circuits/{nonexistent_id}/reset")
            assert response.status_code == 404

    def test_reset_circuit_returns_error_detail_when_not_found(
        self, client: TestClient
    ) -> None:
        """POST /circuits/{id}/reset returns detail message when circuit not found."""
        nonexistent_id = str(uuid4())
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=None,
        ):
            response = client.post(f"/circuits/{nonexistent_id}/reset")
            json_body = response.json()
            detail = json_body.get("detail", "")
            assert "not found" in detail.lower() or detail != ""


class TestCircuitHealth:
    """Tests for GET /circuits/health endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mixed_health_summary(self) -> dict[str, Any]:
        """Create health summary with mixed states (some open circuits)."""
        return {
            "total_circuits": 6,
            "closed": 3,
            "open": 2,
            "half_open": 1,
            "healthy": False,
        }

    @pytest.fixture
    def healthy_summary(self) -> dict[str, Any]:
        """Create health summary with all circuits closed."""
        return {
            "total_circuits": 5,
            "closed": 5,
            "open": 0,
            "half_open": 0,
            "healthy": True,
        }

    def test_get_circuit_health_returns_200(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns HTTP 200."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            assert response.status_code == 200

    def test_get_circuit_health_returns_total_circuits(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns total_circuits count."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("total_circuits") == 6

    def test_get_circuit_health_returns_closed_count(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns closed circuit count."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("closed") == 3

    def test_get_circuit_health_returns_open_count(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns open circuit count."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("open") == 2

    def test_get_circuit_health_returns_half_open_count(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns half_open circuit count."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("half_open") == 1

    def test_get_circuit_health_returns_healthy_false_when_open_circuits_exist(
        self, client: TestClient, mixed_health_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns healthy=False when any circuit is open."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=mixed_health_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("healthy") is False

    def test_get_circuit_health_returns_healthy_true_when_all_closed(
        self, client: TestClient, healthy_summary: dict[str, Any]
    ) -> None:
        """GET /circuits/health returns healthy=True when all circuits are closed."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=healthy_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            assert json_body.get("healthy") is True


class TestCircuitHealthEdgeCases:
    """Tests for edge cases in circuit health endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_circuit_health_with_no_circuits_returns_200(
        self, client: TestClient
    ) -> None:
        """GET /circuits/health returns HTTP 200 when no circuits exist."""
        empty_summary = {
            "total_circuits": 0,
            "closed": 0,
            "open": 0,
            "half_open": 0,
            "healthy": True,
        }
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=empty_summary,
        ):
            response = client.get("/circuits/health")
            assert response.status_code == 200
            json_body = response.json()
            assert json_body.get("total_circuits") == 0
            assert json_body.get("healthy") is True

    def test_get_circuit_health_with_only_half_open_returns_healthy_true(
        self, client: TestClient
    ) -> None:
        """GET /circuits/health returns healthy=True when only half_open circuits exist (no open)."""
        half_open_summary = {
            "total_circuits": 2,
            "closed": 0,
            "open": 0,
            "half_open": 2,
            "healthy": True,
        }
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=half_open_summary,
        ):
            response = client.get("/circuits/health")
            json_body = response.json()
            # healthy is based on no open circuits, half_open is acceptable
            assert json_body.get("healthy") is True


class TestCircuitsMethodNotAllowed:
    """Tests for non-allowed HTTP methods on circuit endpoints."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_circuits_list_returns_405(self, client: TestClient) -> None:
        """POST /circuits returns HTTP 405 Method Not Allowed."""
        response = client.post("/circuits")
        assert response.status_code == 405

    def test_put_circuits_list_returns_405(self, client: TestClient) -> None:
        """PUT /circuits returns HTTP 405 Method Not Allowed."""
        response = client.put("/circuits")
        assert response.status_code == 405

    def test_delete_circuits_list_returns_405(self, client: TestClient) -> None:
        """DELETE /circuits returns HTTP 405 Method Not Allowed."""
        response = client.delete("/circuits")
        assert response.status_code == 405

    def test_put_circuit_by_id_returns_405(self, client: TestClient) -> None:
        """PUT /circuits/{id} returns HTTP 405 Method Not Allowed."""
        circuit_id = str(uuid4())
        response = client.put(f"/circuits/{circuit_id}")
        assert response.status_code == 405

    def test_delete_circuit_by_id_returns_405(self, client: TestClient) -> None:
        """DELETE /circuits/{id} returns HTTP 405 Method Not Allowed."""
        circuit_id = str(uuid4())
        response = client.delete(f"/circuits/{circuit_id}")
        assert response.status_code == 405

    def test_get_circuit_reset_returns_405(self, client: TestClient) -> None:
        """GET /circuits/{id}/reset returns HTTP 405 Method Not Allowed."""
        circuit_id = str(uuid4())
        response = client.get(f"/circuits/{circuit_id}/reset")
        assert response.status_code == 405


class TestCircuitsResponseFormat:
    """Tests for response format validation."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the circuits router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def single_circuit(self) -> list[dict[str, Any]]:
        """Create single circuit data for response format tests."""
        return [
            {
                "id": str(uuid4()),
                "level": "task",
                "state": "closed",
                "failure_count": 0,
                "last_failure_at": None,
                "opened_at": None,
            }
        ]

    def test_get_circuits_returns_json_content_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """GET /circuits returns Content-Type application/json."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=single_circuit,
        ):
            response = client.get("/circuits")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_circuit_by_id_returns_json_content_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """GET /circuits/{id} returns Content-Type application/json."""
        circuit_data = single_circuit[0]
        circuit_id = circuit_data["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_by_id",
            return_value=circuit_data,
        ):
            response = client.get(f"/circuits/{circuit_id}")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_circuit_health_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """GET /circuits/health returns Content-Type application/json."""
        health_summary = {
            "total_circuits": 1,
            "closed": 1,
            "open": 0,
            "half_open": 0,
            "healthy": True,
        }
        with patch(
            "tdd_orchestrator.api.routes.circuits.get_circuit_health_summary",
            return_value=health_summary,
        ):
            response = client.get("/circuits/health")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_post_circuit_reset_returns_json_content_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """POST /circuits/{id}/reset returns Content-Type application/json."""
        circuit_data = single_circuit[0]
        circuit_id = circuit_data["id"]
        with patch(
            "tdd_orchestrator.api.routes.circuits.reset_circuit",
            return_value=circuit_data,
        ):
            response = client.post(f"/circuits/{circuit_id}/reset")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_circuit_id_is_string_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """Circuit id field is a string."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=single_circuit,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert isinstance(json_body[0].get("id"), str)

    def test_circuit_level_is_string_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """Circuit level field is a string."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=single_circuit,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert isinstance(json_body[0].get("level"), str)

    def test_circuit_state_is_string_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """Circuit state field is a string."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=single_circuit,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert isinstance(json_body[0].get("state"), str)

    def test_circuit_failure_count_is_integer_type(
        self, client: TestClient, single_circuit: list[dict[str, Any]]
    ) -> None:
        """Circuit failure_count field is an integer."""
        with patch(
            "tdd_orchestrator.api.routes.circuits.list_circuits",
            return_value=single_circuit,
        ):
            response = client.get("/circuits")
            json_body = response.json()
            assert len(json_body) >= 1
            assert isinstance(json_body[0].get("failure_count"), int)
