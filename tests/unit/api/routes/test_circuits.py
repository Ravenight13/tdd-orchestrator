"""Tests for the circuits router endpoints.

Tests the GET /circuits, GET /circuits/health, GET /circuits/{circuit_id},
and POST /circuits/{circuit_id}/reset endpoints that return circuit breaker
data from the v_circuit_breaker_status and v_circuit_health_summary views.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.routes.circuits import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockRow(dict[str, Any]):
    """Dict subclass that supports bracket access for aiosqlite row compat."""

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


def _make_circuit_row(**overrides: Any) -> _MockRow:
    """Build a mock row mimicking v_circuit_breaker_status columns."""
    defaults: dict[str, Any] = {
        "id": 1,
        "level": "stage",
        "identifier": "TDD-1:green",
        "state": "closed",
        "failure_count": 0,
        "success_count": 0,
        "extensions_count": 0,
        "opened_at": None,
        "last_failure_at": None,
        "last_success_at": None,
        "last_state_change_at": None,
        "version": 1,
        "run_id": None,
    }
    defaults.update(overrides)
    return _MockRow(defaults)


def _make_health_row(**overrides: Any) -> _MockRow:
    """Build a mock row mimicking v_circuit_health_summary columns."""
    defaults: dict[str, Any] = {
        "level": "stage",
        "total_circuits": 3,
        "closed_count": 2,
        "open_count": 1,
        "half_open_count": 0,
    }
    defaults.update(overrides)
    return _MockRow(defaults)


class _DualMock:
    """Object that works as both an async context manager and an awaitable.

    ``async with db._conn.execute(...)`` needs ``__aenter__``/``__aexit__``.
    ``await db._conn.execute(...)`` needs the object to be awaitable.
    This wrapper satisfies both protocols by delegating to the inner cursor.
    """

    def __init__(self, cursor: AsyncMock) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> AsyncMock:
        return self._cursor

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def __await__(self) -> Any:
        async def _resolve() -> AsyncMock:
            return self._cursor

        return _resolve().__await__()


def _mock_cursor(rows: list[_MockRow]) -> _DualMock:
    """Return a dual-protocol mock whose cursor yields *rows*."""
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    cursor.fetchone = AsyncMock(return_value=rows[0] if rows else None)
    return _DualMock(cursor)


def _make_mock_db() -> MagicMock:
    """Create a mock db object with a mock _conn attribute."""
    db = MagicMock()
    db._conn = MagicMock()
    db._conn.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# TestGetCircuitsList
# ---------------------------------------------------------------------------


class TestGetCircuitsList:
    """Tests for GET /circuits endpoint."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_with_circuits(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits returns 200 with a list of circuits."""
        rows = [
            _make_circuit_row(id=1, level="stage", state="closed"),
            _make_circuit_row(id=2, level="worker", state="open"),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        response = client.get("/circuits")
        assert response.status_code == 200

    def test_returns_correct_total(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits total matches number of circuits returned."""
        rows = [
            _make_circuit_row(id=1),
            _make_circuit_row(id=2),
            _make_circuit_row(id=3),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/circuits").json()
        assert body["total"] == 3

    def test_returns_circuits_list(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits returns a circuits key with list entries."""
        rows = [_make_circuit_row(id=1)]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/circuits").json()
        assert isinstance(body["circuits"], list)
        assert len(body["circuits"]) == 1

    def test_filters_by_level(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits?level=stage passes level filter to query."""
        rows = [_make_circuit_row(id=1, level="stage")]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        response = client.get("/circuits", params={"level": "stage"})
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_filters_by_state(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits?state=open passes state filter to query."""
        rows = [_make_circuit_row(id=2, state="open")]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        response = client.get("/circuits", params={"state": "open"})
        assert response.status_code == 200

    def test_empty_result(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits returns empty list and total 0 when no circuits."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/circuits").json()
        assert body["circuits"] == []
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# TestGetCircuitsHealth
# ---------------------------------------------------------------------------


class TestGetCircuitsHealth:
    """Tests for GET /circuits/health endpoint."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/health returns 200."""
        rows = [_make_health_row(level="stage")]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        assert client.get("/circuits/health").status_code == 200

    def test_returns_list_of_summaries(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/health returns a list with per-level health dicts."""
        rows = [
            _make_health_row(level="stage", total_circuits=3),
            _make_health_row(level="worker", total_circuits=2),
        ]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/circuits/health").json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_summary_contains_required_fields(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Each health summary contains level, total, closed, open, half_open counts."""
        rows = [_make_health_row()]
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor(rows))
        body = client.get("/circuits/health").json()
        entry = body[0]
        for key in ("level", "total_circuits", "closed_count", "open_count", "half_open_count"):
            assert key in entry

    def test_empty_health(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/health returns empty list when no circuits exist."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/circuits/health").json()
        assert body == []


# ---------------------------------------------------------------------------
# TestGetCircuitById
# ---------------------------------------------------------------------------


class TestGetCircuitById:
    """Tests for GET /circuits/{circuit_id} endpoint."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_when_found(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/1 returns 200 when circuit exists."""
        row = _make_circuit_row(id=1, level="stage", state="closed")
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([row]))
        assert client.get("/circuits/1").status_code == 200

    def test_returns_circuit_data(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/1 returns the circuit's fields."""
        row = _make_circuit_row(id=1, level="worker", state="open", failure_count=5)
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([row]))
        body = client.get("/circuits/1").json()
        assert body["id"] == "1"
        assert body["level"] == "worker"
        assert body["state"] == "open"
        assert body["failure_count"] == 5

    def test_returns_404_when_not_found(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/999 returns 404 when circuit does not exist."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        response = client.get("/circuits/999")
        assert response.status_code == 404

    def test_returns_404_detail_when_not_found(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/999 returns detail message containing 'not found'."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        body = client.get("/circuits/999").json()
        assert "not found" in body["detail"].lower()

    def test_returns_404_for_non_numeric_id(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/abc returns 404 for non-numeric circuit_id."""
        response = client.get("/circuits/abc")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestResetCircuit
# ---------------------------------------------------------------------------


class TestResetCircuit:
    """Tests for POST /circuits/{circuit_id}/reset endpoint."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return _make_mock_db()

    @pytest.fixture()
    def client(self, app: FastAPI, mock_db: MagicMock) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: mock_db
        return TestClient(app, raise_server_exceptions=False)

    def test_reset_returns_200(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """POST /circuits/1/reset returns 200 on success."""
        existing_row = _MockRow({"id": 1, "state": "open"})
        reset_row = _make_circuit_row(id=1, state="closed", failure_count=0)

        call_count = 0

        def _execute_side_effect(*args: Any, **kwargs: Any) -> _DualMock:
            nonlocal call_count
            call_count += 1
            # 1st call: SELECT id, state FROM circuit_breakers
            if call_count == 1:
                return _mock_cursor([existing_row])
            # 2nd call: UPDATE circuit_breakers (returns no rows)
            if call_count == 2:
                return _mock_cursor([])
            # 3rd call: INSERT INTO circuit_breaker_events (returns no rows)
            if call_count == 3:
                return _mock_cursor([])
            # 4th call: SELECT * FROM v_circuit_breaker_status (returns reset row)
            return _mock_cursor([reset_row])

        mock_db._conn.execute = MagicMock(side_effect=_execute_side_effect)
        response = client.post("/circuits/1/reset")
        assert response.status_code == 200

    def test_reset_returns_updated_circuit(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """POST /circuits/1/reset returns the circuit with state='closed'."""
        existing_row = _MockRow({"id": 1, "state": "open"})
        reset_row = _make_circuit_row(id=1, state="closed", failure_count=0)

        call_count = 0

        def _execute_side_effect(*args: Any, **kwargs: Any) -> _DualMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_cursor([existing_row])
            if call_count in (2, 3):
                return _mock_cursor([])
            return _mock_cursor([reset_row])

        mock_db._conn.execute = MagicMock(side_effect=_execute_side_effect)
        body = client.post("/circuits/1/reset").json()
        assert body["state"] == "closed"
        assert body["failure_count"] == 0

    def test_reset_returns_404_when_not_found(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """POST /circuits/999/reset returns 404 when circuit does not exist."""
        mock_db._conn.execute = MagicMock(return_value=_mock_cursor([]))
        response = client.post("/circuits/999/reset")
        assert response.status_code == 404

    def test_reset_returns_404_for_non_numeric_id(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """POST /circuits/abc/reset returns 404 for non-numeric circuit_id."""
        response = client.post("/circuits/abc/reset")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestCircuitsDbUnavailable
# ---------------------------------------------------------------------------


class TestCircuitsDbUnavailable:
    """Tests that all circuit endpoints return 503 when db is None."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def client(self, app: FastAPI) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    def test_get_circuits_returns_503(self, client: TestClient) -> None:
        """GET /circuits returns 503 when database is unavailable."""
        assert client.get("/circuits").status_code == 503

    def test_get_health_returns_503(self, client: TestClient) -> None:
        """GET /circuits/health returns 503 when database is unavailable."""
        assert client.get("/circuits/health").status_code == 503

    def test_get_circuit_by_id_returns_503(self, client: TestClient) -> None:
        """GET /circuits/1 returns 503 when database is unavailable."""
        assert client.get("/circuits/1").status_code == 503

    def test_reset_circuit_returns_503(self, client: TestClient) -> None:
        """POST /circuits/1/reset returns 503 when database is unavailable."""
        assert client.post("/circuits/1/reset").status_code == 503
