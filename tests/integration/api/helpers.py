"""Shared helpers and response models for API integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Response Models
# =============================================================================


class WorkerResponse(BaseModel):
    """Response model for a single worker."""

    id: str
    status: str
    registered_at: datetime


class WorkerListResponse(BaseModel):
    """Response model for list of workers."""

    workers: list[WorkerResponse]


class RunResponse(BaseModel):
    """Response model for a single run."""

    id: str
    task_id: str
    status: str
    started_at: datetime
    worker_id: str | None = None


class RunListResponse(BaseModel):
    """Response model for list of runs."""

    runs: list[RunResponse]


class RunDetailResponse(BaseModel):
    """Response model for run detail with log."""

    id: str
    task_id: str
    status: str
    started_at: datetime
    log: str
    worker_id: str | None = None


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint."""

    pending_count: int
    running_count: int
    passed_count: int
    failed_count: int
    total_count: int
    avg_duration_seconds: float | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def register_error_handlers(app: FastAPI) -> None:
    """Register error handlers on the application.

    Args:
        app: The FastAPI application instance.
    """
    # Import the internal function from the app module
    from tdd_orchestrator.api.app import _register_error_handlers

    _register_error_handlers(app)


def configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware on the application.

    Args:
        app: The FastAPI application instance.
    """
    # Import the internal function from the app module
    from tdd_orchestrator.api.app import _configure_cors

    _configure_cors(app)


def _create_test_app() -> FastAPI:
    """Create a test FastAPI app with all routes registered.

    Returns:
        A configured FastAPI application for testing.
    """
    from fastapi import FastAPI

    from tdd_orchestrator.api.routes import register_routes

    # Create app without lifespan to avoid async context issues in tests
    app = FastAPI(title="TDD Orchestrator Test", version="1.0.0")

    # Register all routes
    register_routes(app)

    return app


async def _create_seeded_test_app() -> tuple[FastAPI, Any]:
    """Create a test app with a seeded in-memory database.

    Seeds workers, tasks with varying statuses, and an execution run
    so integration tests can exercise DB-backed route handlers.

    Returns:
        Tuple of (app, db) where db must be closed by the caller.
    """
    from tdd_orchestrator.api.dependencies import get_db_dep
    from tdd_orchestrator.database.core import OrchestratorDB

    db = OrchestratorDB(":memory:")
    await db.connect()

    await db.register_worker(1)
    await db.register_worker(2)

    await db.create_task("TDD-T01", "Test Task 1", phase=0, sequence=0)
    await db.create_task("TDD-T02", "Test Task 2", phase=0, sequence=1)
    await db.create_task("TDD-T03", "Test Task 3", phase=0, sequence=2)
    await db.update_task_status("TDD-T02", "in_progress")
    await db.update_task_status("TDD-T03", "complete")

    await db.start_execution_run(max_workers=2)

    app = _create_test_app()

    async def override_get_db() -> AsyncGenerator[Any, None]:
        yield db

    app.dependency_overrides[get_db_dep] = override_get_db

    return app, db


async def _create_circuits_seeded_test_app() -> tuple[FastAPI, Any]:
    """Create a test app with a seeded in-memory database containing circuit breakers.

    Seeds circuit_breakers table with varying levels (stage, worker, system)
    and states (closed, open, half_open) for integration testing of circuit routes.

    Returns:
        Tuple of (app, db) where db must be closed by the caller.
    """
    from tdd_orchestrator.api.dependencies import get_db_dep
    from tdd_orchestrator.database.core import OrchestratorDB

    db = OrchestratorDB(":memory:")
    await db.connect()

    # Seed circuit breakers with varying levels and states
    circuit_inserts = [
        # (level, identifier, state, failure_count, success_count)
        ("stage", "TDD-T01:red", "closed", 0, 5),
        ("stage", "TDD-T02:green", "open", 5, 0),
        ("stage", "TDD-T03:verify", "half_open", 3, 1),
        ("worker", "worker_1", "closed", 0, 10),
        ("worker", "worker_2", "open", 8, 0),
        ("system", "system", "closed", 0, 20),
    ]
    for level, identifier, state, fail_count, success_count in circuit_inserts:
        opened_at = "datetime('now')" if state in ("open", "half_open") else "NULL"
        await db._conn.execute(
            "INSERT INTO circuit_breakers "
            "(level, identifier, state, failure_count, success_count, opened_at) "
            "VALUES (?, ?, ?, ?, ?, "
            + ("datetime('now')" if state in ("open", "half_open") else "NULL")
            + ")",
            (level, identifier, state, fail_count, success_count),
        )
    await db._conn.commit()

    app = _create_test_app()

    async def override_get_db() -> AsyncGenerator[Any, None]:
        yield db

    app.dependency_overrides[get_db_dep] = override_get_db

    return app, db
