"""Tests for the async TDD Orchestrator client library."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tdd_orchestrator.client import (
    ClientError,
    NotFoundError,
    ServerError,
    TDDOrchestratorClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(handler: Any) -> TDDOrchestratorClient:
    """Build a TDDOrchestratorClient wired to an httpx.MockTransport."""
    transport = httpx.MockTransport(handler)
    client = TDDOrchestratorClient(base_url="http://test")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client


def _json_response(
    status_code: int = 200, json: Any = None
) -> httpx.Response:
    return httpx.Response(status_code, json=json)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


async def test_context_manager_enter_exit() -> None:
    """async with should return the client and close cleanly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"status": "ok"})

    async with TDDOrchestratorClient(base_url="http://test") as client:
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test"
        )
        result = await client.health()
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


async def test_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return _json_response(200, {"status": "ok"})

    client = _make_client(handler)
    result = await client.health()
    assert result == {"status": "ok"}
    await client.close()


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


async def test_list_tasks_default_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks"
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "0"
        return _json_response(200, {"tasks": [], "total": 0, "limit": 20, "offset": 0})

    client = _make_client(handler)
    result = await client.list_tasks()
    assert result["total"] == 0
    await client.close()


async def test_list_tasks_with_filters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["status"] == "pending"
        assert request.url.params["phase"] == "red"
        assert request.url.params["complexity"] == "high"
        assert request.url.params["limit"] == "5"
        assert request.url.params["offset"] == "10"
        return _json_response(200, {"tasks": [], "total": 0, "limit": 5, "offset": 10})

    client = _make_client(handler)
    result = await client.list_tasks(
        status="pending", phase="red", complexity="high", limit=5, offset=10
    )
    assert result["limit"] == 5
    await client.close()


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------


async def test_get_task() -> None:
    task_payload = {"id": "task-1", "title": "First task", "status": "running"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks/task-1"
        return _json_response(200, task_payload)

    client = _make_client(handler)
    result = await client.get_task("task-1")
    assert result["id"] == "task-1"
    await client.close()


# ---------------------------------------------------------------------------
# retry_task
# ---------------------------------------------------------------------------


async def test_retry_task() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tasks/task-2/retry"
        return _json_response(200, {"task_key": "task-2", "status": "pending"})

    client = _make_client(handler)
    result = await client.retry_task("task-2")
    assert result["status"] == "pending"
    await client.close()


# ---------------------------------------------------------------------------
# task_stats
# ---------------------------------------------------------------------------


async def test_task_stats() -> None:
    stats = {"pending": 3, "running": 1, "passed": 5, "failed": 0, "total": 9}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks/stats"
        return _json_response(200, stats)

    client = _make_client(handler)
    result = await client.task_stats()
    assert result["total"] == 9
    await client.close()


# ---------------------------------------------------------------------------
# task_progress
# ---------------------------------------------------------------------------


async def test_task_progress() -> None:
    progress = {"total": 10, "completed": 7, "percentage": 70.0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks/progress"
        return _json_response(200, progress)

    client = _make_client(handler)
    result = await client.task_progress()
    assert result["percentage"] == 70.0
    await client.close()


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_404_raises_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(404, {"detail": "Task not found"})

    client = _make_client(handler)
    with pytest.raises(NotFoundError) as exc_info:
        await client.get_task("nonexistent")
    assert exc_info.value.status_code == 404
    assert "Task not found" in exc_info.value.message
    await client.close()


async def test_500_raises_server_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(500, {"detail": "Internal server error"})

    client = _make_client(handler)
    with pytest.raises(ServerError) as exc_info:
        await client.health()
    assert exc_info.value.status_code == 500
    await client.close()


async def test_503_raises_server_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(503, {"detail": "Database not available"})

    client = _make_client(handler)
    with pytest.raises(ServerError) as exc_info:
        await client.health()
    assert exc_info.value.status_code == 503
    assert "Database not available" in exc_info.value.message
    await client.close()


async def test_409_raises_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(409, {"detail": "Conflict"})

    client = _make_client(handler)
    with pytest.raises(ClientError) as exc_info:
        await client.retry_task("task-x")
    assert exc_info.value.status_code == 409
    await client.close()
