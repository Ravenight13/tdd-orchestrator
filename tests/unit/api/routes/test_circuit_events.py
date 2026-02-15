"""Tests for the circuit breaker events endpoint.

Tests the GET /circuits/{circuit_id}/events endpoint that returns
recent events for a circuit breaker from the circuit_breaker_events table.
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


def _mock_cursor(
    rows: list[_MockRow],
    *,
    fetchone_value: _MockRow | None = ...,  # type: ignore[assignment]
) -> _DualMock:
    """Return a dual-protocol mock whose cursor yields *rows*.

    Args:
        rows: Rows returned by fetchall.
        fetchone_value: Value returned by fetchone. Defaults to rows[0] if
            rows is non-empty, else None.
    """
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    if fetchone_value is ...:
        cursor.fetchone = AsyncMock(return_value=rows[0] if rows else None)
    else:
        cursor.fetchone = AsyncMock(return_value=fetchone_value)
    return _DualMock(cursor)


def _make_mock_db() -> MagicMock:
    """Create a mock db object with a mock _conn attribute."""
    db = MagicMock()
    db._conn = MagicMock()
    db._conn.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Row factory
# ---------------------------------------------------------------------------


def _make_event_row(
    id: int = 1,
    event_type: str = "state_change",
    from_state: str | None = "closed",
    to_state: str | None = "open",
    created_at: str = "2026-02-14T10:00:00",
    error_context: str | None = None,
) -> _MockRow:
    """Build a mock row for circuit_breaker_events query."""
    return _MockRow(
        {
            "id": id,
            "event_type": event_type,
            "from_state": from_state,
            "to_state": to_state,
            "created_at": created_at,
            "error_context": error_context,
        }
    )


def _make_events_side_effect(
    exists_row: _MockRow | None,
    event_rows: list[_MockRow],
) -> Any:
    """Create a side_effect for 2-sequential-query pattern.

    Call 1: existence check (fetchone returns exists_row)
    Call 2: events query (fetchall returns event_rows)
    """
    call_count = 0

    def _side_effect(*args: Any, **kwargs: Any) -> _DualMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_cursor([], fetchone_value=exists_row)
        return _mock_cursor(event_rows)

    return _side_effect


# ---------------------------------------------------------------------------
# TestGetCircuitEventsSuccess
# ---------------------------------------------------------------------------


class TestGetCircuitEventsSuccess:
    """Tests for GET /circuits/{circuit_id}/events with valid data."""

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
        """GET /circuits/1/events returns 200 when circuit exists."""
        exists_row = _MockRow({"id": 1})
        event_rows = [
            _make_event_row(id=1, event_type="state_change"),
            _make_event_row(id=2, event_type="failure"),
        ]
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, event_rows)
        )
        assert client.get("/circuits/1/events").status_code == 200

    def test_response_has_events_key(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Response body has an 'events' list."""
        exists_row = _MockRow({"id": 1})
        event_rows = [_make_event_row()]
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, event_rows)
        )
        body = client.get("/circuits/1/events").json()
        assert "events" in body
        assert isinstance(body["events"], list)

    def test_event_fields_present(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Each event has id, event_type, from_state, to_state, created_at, error_context."""
        exists_row = _MockRow({"id": 1})
        event_rows = [
            _make_event_row(
                id=1,
                event_type="state_change",
                from_state="closed",
                to_state="open",
                created_at="2026-02-14T10:00:00",
                error_context=None,
            )
        ]
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, event_rows)
        )
        body = client.get("/circuits/1/events").json()
        event = body["events"][0]
        assert event["id"] == 1
        assert event["event_type"] == "state_change"
        assert event["from_state"] == "closed"
        assert event["to_state"] == "open"
        assert event["created_at"] == "2026-02-14T10:00:00"
        assert event["error_context"] is None

    def test_nullable_fields(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Event with from_state=None, to_state=None, error_context=None."""
        exists_row = _MockRow({"id": 1})
        event_rows = [
            _make_event_row(from_state=None, to_state=None, error_context=None)
        ]
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, event_rows)
        )
        body = client.get("/circuits/1/events").json()
        event = body["events"][0]
        assert event["from_state"] is None
        assert event["to_state"] is None
        assert event["error_context"] is None

    def test_error_context_present(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Event with error_context returns the string value."""
        exists_row = _MockRow({"id": 1})
        event_rows = [_make_event_row(error_context="timeout")]
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, event_rows)
        )
        body = client.get("/circuits/1/events").json()
        assert body["events"][0]["error_context"] == "timeout"


# ---------------------------------------------------------------------------
# TestGetCircuitEventsEmpty
# ---------------------------------------------------------------------------


class TestGetCircuitEventsEmpty:
    """Tests for GET /circuits/{circuit_id}/events with no events."""

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

    def test_returns_200_with_empty_events(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """Circuit exists but no events returns 200 with empty events list."""
        exists_row = _MockRow({"id": 1})
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, [])
        )
        body = client.get("/circuits/1/events").json()
        assert body == {"events": []}


# ---------------------------------------------------------------------------
# TestGetCircuitEventsWithLimit
# ---------------------------------------------------------------------------


class TestGetCircuitEventsWithLimit:
    """Tests for GET /circuits/{circuit_id}/events with limit parameter."""

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

    def test_custom_limit_parameter(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/1/events?limit=10 returns 200."""
        exists_row = _MockRow({"id": 1})
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, [_make_event_row()])
        )
        assert client.get("/circuits/1/events", params={"limit": 10}).status_code == 200

    def test_default_limit(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/1/events without limit returns 200 (default 50)."""
        exists_row = _MockRow({"id": 1})
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(exists_row, [_make_event_row()])
        )
        assert client.get("/circuits/1/events").status_code == 200


# ---------------------------------------------------------------------------
# TestGetCircuitEventsNotFound
# ---------------------------------------------------------------------------


class TestGetCircuitEventsNotFound:
    """Tests for GET /circuits/{circuit_id}/events when circuit not found."""

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

    def test_returns_404(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """GET /circuits/999/events returns 404 when circuit does not exist."""
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(None, [])
        )
        assert client.get("/circuits/999/events").status_code == 404

    def test_404_detail(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        """404 response detail contains 'not found'."""
        mock_db._conn.execute = MagicMock(
            side_effect=_make_events_side_effect(None, [])
        )
        body = client.get("/circuits/999/events").json()
        assert "not found" in body["detail"].lower()


# ---------------------------------------------------------------------------
# TestGetCircuitEventsNonNumericId
# ---------------------------------------------------------------------------


class TestGetCircuitEventsNonNumericId:
    """Tests for GET /circuits/{circuit_id}/events with non-numeric ID."""

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

    def test_returns_404_for_non_numeric_id(
        self, client: TestClient
    ) -> None:
        """GET /circuits/abc/events returns 404 for non-numeric circuit_id."""
        assert client.get("/circuits/abc/events").status_code == 404


# ---------------------------------------------------------------------------
# TestGetCircuitEventsDbUnavailable
# ---------------------------------------------------------------------------


class TestGetCircuitEventsDbUnavailable:
    """Tests that events endpoint returns 503 when db is None."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router, prefix="/circuits")
        return app

    @pytest.fixture()
    def client(self, app: FastAPI) -> TestClient:
        app.dependency_overrides[get_db_dep] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_503_when_db_is_none(self, client: TestClient) -> None:
        """GET /circuits/1/events returns 503 when database is unavailable."""
        assert client.get("/circuits/1/events").status_code == 503
