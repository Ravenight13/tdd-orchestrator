# Phase 1: API Layer -- Detailed Implementation Plan

**Status:** Proposed
**Author:** Cliff Clarke
**Date:** 2026-02-07
**Prerequisite:** All 324+ tests passing, mypy strict clean, ruff clean
**Goal:** Wrap the existing async engine with a FastAPI REST API + SSE for real-time events

---

## Table of Contents

1. [Build Sequence](#1-build-sequence)
2. [Every File to Create](#2-every-file-to-create)
3. [Every File to Modify](#3-every-file-to-modify)
4. [Pydantic Models](#4-pydantic-models)
5. [SSE Event System](#5-sse-event-system)
6. [CLI serve Command](#6-cli-serve-command)
7. [Database Additions](#7-database-additions)
8. [Test Strategy](#8-test-strategy)
9. [Dependency Changes](#9-dependency-changes)
10. [Verification Checklist](#10-verification-checklist)
11. [Open Questions](#11-open-questions-for-debate)

---

## 1. Build Sequence

Build order is driven by dependency chains. Each step depends on the prior step being complete and passing mypy strict + ruff.

### Step 1: Dependencies and Pydantic Models (no runtime dependencies)

**Files:** `pyproject.toml`, `src/tdd_orchestrator/api/__init__.py`, `src/tdd_orchestrator/api/models/__init__.py`, `src/tdd_orchestrator/api/models/responses.py`, `src/tdd_orchestrator/api/models/requests.py`

**Why first:** Pydantic models are pure data with zero imports from the rest of the API layer. Everything else depends on them. Installing FastAPI/uvicorn/pydantic also unblocks all subsequent steps.

**Verification:** `mypy src/tdd_orchestrator/api/models/ --strict` passes. Import from a Python REPL.

### Step 2: Database Query Additions

**Files:** `src/tdd_orchestrator/database/tasks.py`, `src/tdd_orchestrator/database/workers.py`, `src/tdd_orchestrator/database/runs.py`

**Why second:** API routes need query methods that do not yet exist (e.g., `get_tasks_by_status`, `get_execution_runs`). Adding these to the database layer first means route handlers have real methods to call.

**Verification:** Unit tests for new DB methods pass. Existing 324+ tests still pass.

### Step 3: SSE Broadcaster (standalone, no FastAPI dependency)

**Files:** `src/tdd_orchestrator/api/sse.py`

**Why third:** The SSE broadcaster is a standalone async class with no FastAPI dependency (it only uses `asyncio.Queue`). Building it early lets us write isolated unit tests. The FastAPI route that exposes it comes later.

**Verification:** Unit test with a mock subscriber can connect, receive events, and disconnect.

### Step 4: Dependency Injection

**Files:** `src/tdd_orchestrator/api/dependencies.py`

**Why fourth:** FastAPI route handlers need `Depends(get_db)` and `Depends(get_broadcaster)`. These are thin wrappers around the existing singleton and the SSE broadcaster from Step 3.

**Verification:** Can instantiate dependencies in a test. mypy clean.

### Step 5: Error Handling and CORS Middleware

**Files:** `src/tdd_orchestrator/api/middleware/__init__.py`, `src/tdd_orchestrator/api/middleware/error_handler.py`, `src/tdd_orchestrator/api/middleware/cors.py`

**Why fifth:** Middleware must exist before the app factory wires it up. These are self-contained.

**Verification:** mypy clean. Unit test for error handler transforms exceptions into structured JSON.

### Step 6: Route Handlers (can be parallelized across files)

**Files:** `src/tdd_orchestrator/api/routes/__init__.py`, `src/tdd_orchestrator/api/routes/health.py`, `src/tdd_orchestrator/api/routes/tasks.py`, `src/tdd_orchestrator/api/routes/workers.py`, `src/tdd_orchestrator/api/routes/circuits.py`, `src/tdd_orchestrator/api/routes/runs.py`, `src/tdd_orchestrator/api/routes/metrics.py`

**Why sixth:** Routes import models (Step 1), call DB methods (Step 2), use SSE broadcaster (Step 3), use dependencies (Step 4). All prerequisites are met.

**Build sub-order (if sequential):**
1. `health.py` -- simplest, validates the pattern
2. `metrics.py` -- trivial (one endpoint, one existing function)
3. `tasks.py` -- most endpoints, highest value
4. `workers.py` -- moderate
5. `circuits.py` -- moderate, includes reset mutation
6. `runs.py` -- moderate

**Verification:** Each route file gets a unit test file written immediately after.

### Step 7: App Factory

**Files:** `src/tdd_orchestrator/api/app.py`

**Why seventh:** The app factory imports all routes and middleware. It must be built after them.

**Verification:** `TestClient(create_app())` can hit `/health` and get a 200.

### Step 8: CLI `serve` Command

**Files:** `src/tdd_orchestrator/api/serve.py` (uvicorn wrapper), `src/tdd_orchestrator/cli.py` (add `serve` command)

**Why eighth:** The serve command imports the app factory and runs uvicorn. It is the final integration point.

**Verification:** `tdd-orchestrator serve --port 8420 &` starts, `curl localhost:8420/health` returns JSON, process stops cleanly.

### Step 9: Hook Integration (SSE event publishing)

**Files:** `src/tdd_orchestrator/hooks.py` (modify)

**Why ninth:** Connecting hooks to the SSE broadcaster is the last wiring step. It requires the broadcaster (Step 3) and the running app (Step 7) to be in place.

**Verification:** Start server, trigger a task status change, SSE client receives event.

### Step 10: Tests and Final Verification

**Files:** All test files in `tests/unit/api/` and `tests/integration/api/`

**Why last:** While tests are written alongside each step, the final step is integration tests that exercise the full stack (app + DB + SSE + routes).

**Verification:** Full suite passes. See Section 10.

---

## 2. Every File to Create

### `src/tdd_orchestrator/api/__init__.py`

**Purpose:** Package init. Exports `create_app` for programmatic use.

```python
from .app import create_app

__all__ = ["create_app"]
```

**Imports from:** `.app`
**Estimated lines:** 10

---

### `src/tdd_orchestrator/api/models/__init__.py`

**Purpose:** Package init. Re-exports all model classes for convenient imports.

```python
from .requests import (
    CircuitResetRequest,
    TaskRetryRequest,
    TaskFilterParams,
)
from .responses import (
    TaskResponse,
    TaskListResponse,
    TaskDetailResponse,
    AttemptResponse,
    WorkerResponse,
    WorkerListResponse,
    CircuitBreakerResponse,
    CircuitBreakerListResponse,
    HealthResponse,
    RunResponse,
    RunListResponse,
    ProgressResponse,
    StatsResponse,
    ErrorResponse,
    SSEEventData,
)
```

**Imports from:** `.requests`, `.responses`
**Estimated lines:** 30

---

### `src/tdd_orchestrator/api/models/responses.py`

**Purpose:** Pydantic v2 response schemas. Maps SQLite row dicts to typed JSON responses.

**Key classes:**

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSING = "passing"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    BLOCKED_STATIC_REVIEW = "blocked-static-review"

class TaskResponse(BaseModel):
    id: int
    task_key: str
    title: str
    status: TaskStatus
    phase: int
    sequence: int
    goal: str | None = None
    test_file: str | None = None
    impl_file: str | None = None
    complexity: str = "medium"
    depends_on: list[str] = Field(default_factory=list)
    claimed_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

class TaskDetailResponse(TaskResponse):
    acceptance_criteria: list[str] = Field(default_factory=list)
    verify_command: str | None = None
    done_criteria: str | None = None
    implementation_hints: str | None = None
    module_exports: list[str] = Field(default_factory=list)
    attempts: list[AttemptResponse] = Field(default_factory=list)

class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
    filters_applied: dict[str, str] = Field(default_factory=dict)

class AttemptResponse(BaseModel):
    id: int
    task_id: int
    stage: str
    attempt_number: int
    success: bool
    error_message: str | None = None
    pytest_exit_code: int | None = None
    mypy_exit_code: int | None = None
    ruff_exit_code: int | None = None
    started_at: str | None = None
    completed_at: str | None = None

class WorkerResponse(BaseModel):
    id: int
    worker_id: int
    status: str
    registered_at: str | None = None
    last_heartbeat: str | None = None
    current_task_key: str | None = None
    branch_name: str | None = None
    total_claims: int = 0
    completed_claims: int = 0
    failed_claims: int = 0
    total_invocations: int = 0

class WorkerListResponse(BaseModel):
    workers: list[WorkerResponse]
    total: int

class CircuitBreakerResponse(BaseModel):
    id: int
    level: str          # "stage", "worker", "system"
    identifier: str
    state: str          # "closed", "open", "half_open"
    failure_count: int
    success_count: int
    extensions_count: int = 0
    opened_at: str | None = None
    last_failure_at: str | None = None
    last_success_at: str | None = None
    last_state_change_at: str | None = None
    version: int = 1
    minutes_open: int | None = None

class CircuitBreakerListResponse(BaseModel):
    circuits: list[CircuitBreakerResponse]
    total: int
    by_state: dict[str, int] = Field(default_factory=dict)

class HealthResponse(BaseModel):
    status: str         # "HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"
    total_circuits: int = 0
    circuits_closed: int = 0
    circuits_open: int = 0
    circuits_half_open: int = 0
    flapping_circuits: int = 0
    timestamp: str
    details: dict = Field(default_factory=dict)

class RunResponse(BaseModel):
    id: int
    started_at: str
    completed_at: str | None = None
    total_invocations: int = 0
    max_workers: int | None = None
    status: str = "running"

class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int

class ProgressResponse(BaseModel):
    total: int
    completed: int
    percentage: float
    by_status: dict[str, int] = Field(default_factory=dict)

class StatsResponse(BaseModel):
    pending: int = 0
    in_progress: int = 0
    passing: int = 0
    complete: int = 0
    blocked: int = 0

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int = 500

class SSEEventData(BaseModel):
    event_type: str     # "task_status_changed", "circuit_state_changed", etc.
    timestamp: str
    data: dict = Field(default_factory=dict)
```

**Imports from:** `pydantic`, `datetime`, `enum` (stdlib only -- no project imports)
**Estimated lines:** 200

---

### `src/tdd_orchestrator/api/models/requests.py`

**Purpose:** Pydantic v2 request/query parameter schemas.

**Key classes:**

```python
from pydantic import BaseModel, Field

class TaskFilterParams(BaseModel):
    """Query parameters for task listing."""
    status: str | None = None
    phase: int | None = None
    complexity: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

class TaskRetryRequest(BaseModel):
    """Request body for retrying a failed task."""
    reset_attempts: bool = False   # Whether to clear attempt history

class CircuitResetRequest(BaseModel):
    """Request body for resetting a circuit breaker."""
    force: bool = False            # Skip confirmation logic
```

**Imports from:** `pydantic` (stdlib only -- no project imports)
**Estimated lines:** 40

---

### `src/tdd_orchestrator/api/dependencies.py`

**Purpose:** FastAPI dependency injection. Provides `get_db`, `get_broadcaster`, and `get_config` as injectable singletons. Manages the DB lifecycle (startup/shutdown).

**Key functions:**

```python
from __future__ import annotations

from typing import AsyncGenerator
from fastapi import Request

from ..database import OrchestratorDB
from .sse import SSEBroadcaster

# Module-level singletons (set during app lifespan)
_db: OrchestratorDB | None = None
_broadcaster: SSEBroadcaster | None = None


async def init_dependencies(db_path: str | None = None) -> None:
    """Initialize DB and broadcaster. Called during app startup."""
    ...

async def shutdown_dependencies() -> None:
    """Close DB and broadcaster. Called during app shutdown."""
    ...

async def get_db_dep() -> AsyncGenerator[OrchestratorDB, None]:
    """FastAPI dependency that yields the DB instance."""
    ...

def get_broadcaster_dep() -> SSEBroadcaster:
    """FastAPI dependency that returns the SSE broadcaster."""
    ...

def get_db_path_from_request(request: Request) -> str | None:
    """Extract db_path from app state (set by CLI options)."""
    ...
```

**Imports from:** `..database.OrchestratorDB`, `.sse.SSEBroadcaster`, `fastapi`
**Estimated lines:** 120

---

### `src/tdd_orchestrator/api/sse.py`

**Purpose:** Server-Sent Events broadcaster. Manages subscriber queues, publishes events, handles client disconnect cleanup. No FastAPI imports -- pure asyncio.

**Key classes:**

```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """A single SSE event."""
    event_type: str                           # e.g., "task_status_changed"
    data: dict[str, Any]                     # Arbitrary JSON-serializable payload
    id: str | None = None                    # Optional event ID for reconnection
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def format(self) -> str:
        """Format as SSE wire protocol."""
        ...


class SSEBroadcaster:
    """Fan-out broadcaster for SSE events.

    Thread-safe (all methods are async and use a lock).
    Subscribers are asyncio.Queues. When a subscriber disconnects,
    its queue is removed from the set.
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        ...

    async def subscribe(self) -> AsyncGenerator[SSEEvent, None]:
        """Yield events as they arrive. Cleans up on generator close."""
        ...

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers. Non-blocking."""
        ...

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        ...

    async def shutdown(self) -> None:
        """Close all subscriber queues."""
        ...
```

**Imports from:** `asyncio`, `json`, `datetime`, `dataclasses`, `logging` (stdlib only)
**Estimated lines:** 180

---

### `src/tdd_orchestrator/api/middleware/__init__.py`

**Purpose:** Package init.

**Estimated lines:** 5

---

### `src/tdd_orchestrator/api/middleware/error_handler.py`

**Purpose:** Global exception handler middleware. Catches unhandled exceptions and returns structured `ErrorResponse` JSON. Catches `ValueError` as 400, `KeyError`/`LookupError` as 404, everything else as 500.

**Key functions:**

```python
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..models.responses import ErrorResponse


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the app."""
    ...

async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle validation errors as 400."""
    ...

async def lookup_error_handler(request: Request, exc: LookupError) -> JSONResponse:
    """Handle not-found errors as 404."""
    ...

async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors as 500."""
    ...
```

**Imports from:** `fastapi`, `..models.responses.ErrorResponse`
**Estimated lines:** 80

---

### `src/tdd_orchestrator/api/middleware/cors.py`

**Purpose:** CORS configuration for dashboard and external clients. Configurable origins via environment variable `TDD_CORS_ORIGINS` (default: `["http://localhost:5173", "http://localhost:3000"]` for Vite dev server).

**Key functions:**

```python
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def configure_cors(app: FastAPI) -> None:
    """Add CORS middleware with configured origins."""
    ...
```

**Imports from:** `fastapi`, `os`
**Estimated lines:** 40

---

### `src/tdd_orchestrator/api/routes/__init__.py`

**Purpose:** Package init. Exports a function that registers all routers on the app.

```python
from fastapi import FastAPI

from .health import router as health_router
from .tasks import router as tasks_router
from .workers import router as workers_router
from .circuits import router as circuits_router
from .runs import router as runs_router
from .metrics import router as metrics_router


def register_routes(app: FastAPI) -> None:
    """Register all API route handlers."""
    app.include_router(health_router)
    app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
    app.include_router(workers_router, prefix="/workers", tags=["workers"])
    app.include_router(circuits_router, prefix="/circuits", tags=["circuits"])
    app.include_router(runs_router, prefix="/runs", tags=["runs"])
    app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
```

**Imports from:** All route modules
**Estimated lines:** 25

---

### `src/tdd_orchestrator/api/routes/health.py`

**Purpose:** Health check endpoints. Delegates to `health.get_circuit_health()`.

**Endpoints:**

```
GET /health         -- Overall health (circuit breaker summary)
GET /health/ready   -- Readiness probe (DB connected?)
GET /health/live    -- Liveness probe (always 200)
```

**Key code:**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...health import get_circuit_health
from ...database import OrchestratorDB
from ..dependencies import get_db_dep
from ..models.responses import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: OrchestratorDB = Depends(get_db_dep),
) -> HealthResponse:
    """Get overall system health including circuit breaker status."""
    health = await get_circuit_health(db)
    return HealthResponse(
        status=health.status.value,
        total_circuits=health.total_circuits,
        circuits_closed=health.circuits_closed,
        circuits_open=health.circuits_open,
        circuits_half_open=health.circuits_half_open,
        flapping_circuits=health.flapping_circuits,
        timestamp=health.timestamp.isoformat(),
        details=health.details,
    )


@router.get("/health/ready")
async def readiness_probe(
    db: OrchestratorDB = Depends(get_db_dep),
) -> dict[str, bool]:
    """Readiness probe -- verifies DB is connected."""
    ...


@router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Liveness probe -- always returns OK."""
    return {"status": "ok"}
```

**Imports from:** `...health`, `...database`, `..dependencies`, `..models.responses`
**Estimated lines:** 80

---

### `src/tdd_orchestrator/api/routes/tasks.py`

**Purpose:** Task CRUD and listing endpoints. The richest route file.

**Endpoints:**

```
GET  /tasks              -- List tasks (filter by status, phase, complexity)
GET  /tasks/stats        -- Task status summary
GET  /tasks/progress     -- Completion progress
GET  /tasks/{task_key}   -- Get task detail + attempt history
POST /tasks/{task_key}/retry  -- Reset a blocked task to pending
```

**Key code:**

```python
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import OrchestratorDB
from ..dependencies import get_db_dep, get_broadcaster_dep
from ..models.requests import TaskRetryRequest
from ..models.responses import (
    AttemptResponse,
    ProgressResponse,
    StatsResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
)
from ..sse import SSEBroadcaster

router = APIRouter()


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    phase: int | None = Query(None, description="Filter by phase"),
    complexity: str | None = Query(None, description="Filter by complexity"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: OrchestratorDB = Depends(get_db_dep),
) -> TaskListResponse:
    """List tasks with optional filters."""
    ...


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: OrchestratorDB = Depends(get_db_dep),
) -> StatsResponse:
    """Get task status summary counts."""
    stats = await db.get_stats()
    return StatsResponse(**stats)


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(
    db: OrchestratorDB = Depends(get_db_dep),
) -> ProgressResponse:
    """Get completion progress."""
    progress = await db.get_progress()
    return ProgressResponse(**progress)


@router.get("/{task_key}", response_model=TaskDetailResponse)
async def get_task(
    task_key: str,
    db: OrchestratorDB = Depends(get_db_dep),
) -> TaskDetailResponse:
    """Get task details including attempt history."""
    ...


@router.post("/{task_key}/retry", response_model=TaskResponse)
async def retry_task(
    task_key: str,
    body: TaskRetryRequest | None = None,
    db: OrchestratorDB = Depends(get_db_dep),
    broadcaster: SSEBroadcaster = Depends(get_broadcaster_dep),
) -> TaskResponse:
    """Reset a blocked/failed task to pending for retry."""
    ...
```

**Conversion logic:** Each DB row dict (`dict[str, Any]`) is converted to a Pydantic model:

```python
# Per Q9 verdict: Use model_validate instead of explicit converters.
# JSON-encoded fields (depends_on, acceptance_criteria, module_exports)
# are handled by @field_validator(mode="before") on the Pydantic models.
task = TaskResponse.model_validate(row)
```

**Imports from:** `...database`, `..dependencies`, `..models.*`, `..sse`
**Estimated lines:** 250

---

### `src/tdd_orchestrator/api/routes/workers.py`

**Purpose:** Worker status endpoints.

**Endpoints:**

```
GET /workers            -- List all workers with stats
GET /workers/{id}       -- Get single worker detail
GET /workers/stale      -- Get stale workers (heartbeat > 10 min)
```

**Key code:**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...database import OrchestratorDB
from ..dependencies import get_db_dep
from ..models.responses import WorkerListResponse, WorkerResponse

router = APIRouter()


@router.get("", response_model=WorkerListResponse)
async def list_workers(
    db: OrchestratorDB = Depends(get_db_dep),
) -> WorkerListResponse:
    """List all workers with health stats."""
    # Uses v_worker_stats view via db.execute_query()
    ...


@router.get("/stale", response_model=WorkerListResponse)
async def list_stale_workers(
    db: OrchestratorDB = Depends(get_db_dep),
) -> WorkerListResponse:
    """List workers with stale heartbeats."""
    stale = await db.get_stale_workers()
    ...
```

**Imports from:** `...database`, `..dependencies`, `..models.responses`
**Estimated lines:** 120

---

### `src/tdd_orchestrator/api/routes/circuits.py`

**Purpose:** Circuit breaker management endpoints.

**Endpoints:**

```
GET  /circuits            -- List all circuits (filter by level, state)
GET  /circuits/{id}       -- Get single circuit detail
POST /circuits/{id}/reset -- Reset a circuit to closed
GET  /circuits/health     -- Circuit health summary (delegates to health.py module)
```

**Key code:**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import OrchestratorDB
from ...health import get_circuit_health
from ..dependencies import get_db_dep, get_broadcaster_dep
from ..models.requests import CircuitResetRequest
from ..models.responses import (
    CircuitBreakerListResponse,
    CircuitBreakerResponse,
    HealthResponse,
)
from ..sse import SSEBroadcaster

router = APIRouter()


@router.get("", response_model=CircuitBreakerListResponse)
async def list_circuits(
    level: str | None = Query(None, description="Filter by level"),
    state: str | None = Query(None, description="Filter by state"),
    db: OrchestratorDB = Depends(get_db_dep),
) -> CircuitBreakerListResponse:
    """List all circuit breakers with optional filters."""
    # Queries v_circuit_breaker_status view via db.execute_query()
    # Same logic as cli.py _circuits_status_async but returns JSON
    ...


@router.post("/{circuit_id}/reset", response_model=CircuitBreakerResponse)
async def reset_circuit(
    circuit_id: str,
    body: CircuitResetRequest | None = None,
    db: OrchestratorDB = Depends(get_db_dep),
    broadcaster: SSEBroadcaster = Depends(get_broadcaster_dep),
) -> CircuitBreakerResponse:
    """Reset a circuit breaker to closed state.

    circuit_id format: level:identifier (e.g., 'worker:worker_1')
    """
    # Reuses logic from cli.py _circuits_reset_async
    # After reset, publishes SSE event
    ...
```

**Imports from:** `...database`, `...health`, `..dependencies`, `..models.*`, `..sse`
**Estimated lines:** 200

---

### `src/tdd_orchestrator/api/routes/runs.py`

**Purpose:** Execution run history endpoints.

**Endpoints:**

```
GET /runs               -- List execution runs (most recent first)
GET /runs/{run_id}      -- Get run details with invocation count
GET /runs/current       -- Get the currently active run (if any)
```

**Key code:**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...database import OrchestratorDB
from ..dependencies import get_db_dep
from ..models.responses import RunListResponse, RunResponse

router = APIRouter()


@router.get("", response_model=RunListResponse)
async def list_runs(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    db: OrchestratorDB = Depends(get_db_dep),
) -> RunListResponse:
    """List execution runs."""
    runs = await db.get_execution_runs(status=status, limit=limit)
    ...


@router.get("/current", response_model=RunResponse | None)
async def get_current_run(
    db: OrchestratorDB = Depends(get_db_dep),
) -> RunResponse | None:
    """Get the currently active execution run, if any."""
    run = await db.get_current_run()
    ...
```

**Imports from:** `...database`, `..dependencies`, `..models.responses`
**Estimated lines:** 120

---

### `src/tdd_orchestrator/api/routes/metrics.py`

**Purpose:** Prometheus metrics export endpoint.

**Endpoints:**

```
GET /metrics            -- Prometheus text format
```

**Key code:**

```python
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ...metrics import get_metrics_collector

router = APIRouter()


@router.get("", response_class=PlainTextResponse)
async def export_metrics() -> str:
    """Export metrics in Prometheus exposition format."""
    collector = get_metrics_collector()
    return collector.export_prometheus()
```

**Imports from:** `...metrics`
**Estimated lines:** 25

---

### `src/tdd_orchestrator/api/app.py`

**Purpose:** FastAPI application factory. Creates the app, configures middleware, registers routes, sets up lifespan events for DB connection management.

**Key code:**

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from .dependencies import init_dependencies, shutdown_dependencies
from .middleware.cors import configure_cors
from .middleware.error_handler import register_error_handlers
from .routes import register_routes

logger = logging.getLogger(__name__)


def create_app(
    db_path: str | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database. None uses default.
        cors_origins: Allowed CORS origins. None uses defaults.

    Returns:
        Configured FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Manage application lifecycle."""
        await init_dependencies(db_path)
        yield
        await shutdown_dependencies()

    app = FastAPI(
        title="TDD Orchestrator",
        description="Parallel TDD task execution with circuit breakers",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Store config on app state for access in dependencies
    app.state.db_path = db_path

    # Configure middleware
    configure_cors(app, cors_origins)
    register_error_handlers(app)

    # Register routes
    register_routes(app)

    # SSE events endpoint (registered separately due to streaming)
    _register_sse_route(app)

    return app


def _register_sse_route(app: FastAPI) -> None:
    """Register the SSE events endpoint."""
    from sse_starlette.sse import EventSourceResponse
    from .dependencies import get_broadcaster_dep

    @app.get("/events", tags=["events"])
    async def event_stream() -> EventSourceResponse:
        """SSE endpoint for real-time events."""
        broadcaster = get_broadcaster_dep()

        async def event_generator():
            async for event in broadcaster.subscribe():
                yield {
                    "event": event.event_type,
                    "data": event.format(),
                    "id": event.id,
                }

        return EventSourceResponse(event_generator())
```

**Imports from:** `fastapi`, `.dependencies`, `.middleware.*`, `.routes`, `sse_starlette`
**Estimated lines:** 120

---

### `src/tdd_orchestrator/api/serve.py`

**Purpose:** Uvicorn runner wrapper. Called by the CLI `serve` command.

**Key code:**

```python
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8420,
    db_path: str | None = None,
    reload: bool = False,
    log_level: str = "info",
    cors_origins: list[str] | None = None,
) -> None:
    """Start the API server using uvicorn.

    Args:
        host: Bind address.
        port: Bind port.
        db_path: Path to SQLite database.
        reload: Enable auto-reload for development.
        log_level: Uvicorn log level.
        cors_origins: Allowed CORS origins.
    """
    import uvicorn

    from .app import create_app

    app = create_app(db_path=db_path, cors_origins=cors_origins)

    logger.info("Starting TDD Orchestrator API on %s:%d", host, port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
```

Note: When `reload=True`, uvicorn requires a string import path instead of an app instance. The `serve.py` module handles this by conditionally passing `"tdd_orchestrator.api.app:create_app"` as a factory string. However, for the initial implementation, `reload` mode is deferred (it requires the factory to be invocable without arguments, which means default db_path).

**Imports from:** `uvicorn`, `.app`
**Estimated lines:** 60

---

## 3. Every File to Modify

### `src/tdd_orchestrator/pyproject.toml`

**What:** Add `api` optional dependency group. Add new packages to the optional group so FastAPI remains optional (like the SDK).

**Where:** `[project.optional-dependencies]` section.

**Change:**

```toml
# Add after the existing "sdk" and "dev" groups:
api = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "sse-starlette>=2.2.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "mypy>=1.18.2",
    "ruff>=0.13.1",
    "httpx>=0.28.1",        # Already a core dep, but TestClient needs it
]
```

---

### `src/tdd_orchestrator/cli.py`

**What:** Add the `serve` command to the Click CLI group.

**Where:** After the `circuits` command group (around line 420), before `main()`.

**Change (add ~35 lines):**

```python
@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=8420, help="Bind port")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--reload", is_flag=True, help="Enable auto-reload (development)")
@click.option("--log-level", default="info", type=click.Choice(["debug", "info", "warning", "error"]))
def serve(host: str, port: int, db: str | None, reload: bool, log_level: str) -> None:
    """Start the API server (requires tdd-orchestrator[api])."""
    try:
        from .api.serve import run_server
    except ImportError:
        click.echo(
            "Error: API dependencies not installed.\n"
            "Install with: pip install tdd-orchestrator[api]",
            err=True,
        )
        sys.exit(1)

    run_server(
        host=host,
        port=port,
        db_path=db,
        reload=reload,
        log_level=log_level,
    )
```

**Existing code to reuse:** The pattern from `mcp_tools.py` for optional dependency imports with try/except.

---

### `src/tdd_orchestrator/database/tasks.py`

**What:** Add `get_tasks_by_status()` and `get_tasks_filtered()` methods.

**Where:** After `get_all_tasks()` (around line 88), in the "Task Queries" section.

**Add (~60 lines):**

```python
async def get_tasks_by_status(self, status: str) -> list[dict[str, Any]]:
    """Get all tasks with a specific status.

    Args:
        status: Task status to filter by.

    Returns:
        List of task dicts matching the status.
    """
    await self._ensure_connected()
    if not self._conn:
        return []

    async with self._conn.execute(
        "SELECT * FROM tasks WHERE status = ? ORDER BY phase, sequence",
        (status,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_tasks_filtered(
    self,
    *,
    status: str | None = None,
    phase: int | None = None,
    complexity: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Get tasks with optional filters and pagination.

    Args:
        status: Filter by status.
        phase: Filter by phase number.
        complexity: Filter by complexity level.
        limit: Maximum results to return.
        offset: Number of results to skip.

    Returns:
        Tuple of (task_list, total_count).
    """
    await self._ensure_connected()
    if not self._conn:
        return [], 0

    where_clauses: list[str] = []
    params: list[Any] = []

    if status is not None:
        where_clauses.append("status = ?")
        params.append(status)
    if phase is not None:
        where_clauses.append("phase = ?")
        params.append(phase)
    if complexity is not None:
        where_clauses.append("complexity = ?")
        params.append(complexity)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Get total count
    count_query = f"SELECT COUNT(*) FROM tasks {where_sql}"
    async with self._conn.execute(count_query, tuple(params)) as cursor:
        row = await cursor.fetchone()
        total = row[0] if row else 0

    # Get paginated results
    data_query = (
        f"SELECT * FROM tasks {where_sql} "
        "ORDER BY phase, sequence LIMIT ? OFFSET ?"
    )
    data_params = tuple(params) + (limit, offset)
    async with self._conn.execute(data_query, data_params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows], total
```

Note: The `f"SELECT ... {where_sql}"` is safe here because `where_sql` is constructed from hardcoded column names, not user input. The actual values are always parameterized with `?`.

---

### `src/tdd_orchestrator/database/runs.py`

**What:** Add `get_execution_runs()` and `get_current_run()` methods.

**Where:** After `complete_execution_run()` (around line 161), in the "Execution Runs" section.

**Add (~50 lines):**

```python
async def get_execution_runs(
    self,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get execution runs ordered by most recent first.

    Args:
        status: Optional status filter.
        limit: Maximum runs to return.

    Returns:
        List of run dicts.
    """
    await self._ensure_connected()
    if not self._conn:
        return []

    if status:
        async with self._conn.execute(
            "SELECT * FROM execution_runs WHERE status = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (status, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    else:
        async with self._conn.execute(
            "SELECT * FROM execution_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def get_current_run(self) -> dict[str, Any] | None:
    """Get the currently active execution run.

    Returns:
        Run dict if a run is active, None otherwise.
    """
    await self._ensure_connected()
    if not self._conn:
        return None

    async with self._conn.execute(
        "SELECT * FROM execution_runs WHERE status = 'running' "
        "ORDER BY started_at DESC LIMIT 1"
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None
```

---

### `src/tdd_orchestrator/database/workers.py`

**What:** Add `get_all_workers()` method that queries `v_worker_stats` view.

**Where:** After `register_worker()` (around line 58), in the "Worker Management" section.

**Add (~25 lines):**

```python
async def get_all_workers(self) -> list[dict[str, Any]]:
    """Get all workers with statistics from v_worker_stats view.

    Returns:
        List of worker dicts with stats.
    """
    await self._ensure_connected()
    if not self._conn:
        return []

    async with self._conn.execute(
        "SELECT * FROM v_worker_stats ORDER BY worker_id"
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
```

---

### `src/tdd_orchestrator/hooks.py`

**What:** Wire the SSE broadcaster reference for the database-level observer pattern. The actual event publishing happens via callbacks registered on DB mixin classes (see Q5 verdict). hooks.py retains its existing SDK tool use interception role.

**Where:** At the module level, add a reference to the broadcaster. This reference is passed to `db.register_status_callback()` during API startup.

**Change:**

1. Add broadcaster reference at module level (~10 lines):

```python
# SSE integration (set when API server is running)
_broadcaster: Any = None


def set_sse_broadcaster(broadcaster: Any) -> None:
    """Set the SSE broadcaster for event publishing.

    Called by the API layer during startup. The broadcaster is then
    registered as a callback on DB mixin classes for mutation events.
    """
    global _broadcaster
    _broadcaster = broadcaster


def get_sse_broadcaster() -> Any:
    """Get the SSE broadcaster if available (for registration on DB callbacks)."""
    return _broadcaster
```

2. No changes to `post_tool_use_hook` or `stop_hook` — event publishing is handled by DB-level callbacks, not hook interception (per Q5 verdict).

---

### `src/tdd_orchestrator/__init__.py`

**What:** Add conditional import of the `api` package (same pattern as `mcp_tools`).

**Where:** After the `mcp_tools` try/except block.

**Add (~10 lines):**

```python
try:
    from .api import create_app
except ImportError:
    create_app = None  # type: ignore[assignment]
```

And add `"create_app"` to `__all__`.

---

## 4. Pydantic Models (Request/Response)

All models defined in Section 2 under `models/responses.py` and `models/requests.py`. Key design decisions:

### Mapping from DB Rows to Pydantic

DB rows are `dict[str, Any]` (from `aiosqlite.Row` via `dict(row)`). Per Q9 verdict, mapping uses Pydantic v2's `model_validate()` with `@field_validator(mode="before")` for JSON-encoded fields:

```python
# In api/models/responses.py — JSON field validators
class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # ... fields ...
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("depends_on", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []
```

This pattern (per Q9 verdict):
- Eliminates ~400-600 lines of converter boilerplate across 16 models
- Co-locates JSON parsing logic with the field definition (high cohesion)
- Handles `None` vs missing keys via Pydantic defaults
- Works because DB column names match Pydantic field names
- JSON-encoded columns parsed by `@field_validator(mode="before")`

### JSON-Encoded Columns

The `tasks` table stores these as JSON strings:
- `depends_on` -- `TEXT DEFAULT '[]'` -- list of task_key strings
- `acceptance_criteria` -- `TEXT` -- list of criterion strings
- `module_exports` -- `TEXT DEFAULT '[]'` -- list of export name strings
- `implementation_hints` -- `TEXT` -- JSON dict with hints

The converter functions parse these from strings to native Python types before constructing Pydantic models.

### Timestamp Handling

DB timestamps are stored as strings (SQLite `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` returns strings like `"2026-02-07 12:00:00"`). Pydantic models expose these as `str | None` rather than `datetime` to avoid parsing ambiguity. Clients can parse as needed.

---

## 5. SSE Event System

### Architecture

```
+-------------------+         +------------------+         +------------------+
| Worker Pool /     |         |                  |         |                  |
| Circuit Breakers  | ------> | SSEBroadcaster   | ------> | SSE Clients      |
| / hooks.py        |  publish|                  |  stream |  (browser, curl) |
+-------------------+         +------------------+         +------------------+
                                     ^
                                     |
                              asyncio.Queue per
                              subscriber
```

### Event Types

| Event Type | Trigger | Payload |
|---|---|---|
| `task_status_changed` | `update_task_status()` called | `{task_key, old_status, new_status, worker_id}` |
| `task_claimed` | `claim_task()` succeeds | `{task_key, worker_id, timeout}` |
| `task_released` | `release_task()` called | `{task_key, worker_id, outcome}` |
| `worker_heartbeat` | `update_worker_heartbeat()` | `{worker_id, task_id, timestamp}` |
| `circuit_state_changed` | Circuit transitions state | `{level, identifier, from_state, to_state, reason}` |
| `run_started` | `start_execution_run()` | `{run_id, max_workers}` |
| `run_completed` | `complete_execution_run()` | `{run_id, status, total_invocations}` |
| `system_health_changed` | Health status changes | `{old_status, new_status, details}` |

### SSEBroadcaster Implementation

```python
class SSEBroadcaster:
    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: set[asyncio.Queue[SSEEvent | None]] = set()
        self._lock = asyncio.Lock()
        self._event_counter = 0
        self._max_queue_size = max_queue_size

    async def subscribe(self) -> AsyncGenerator[SSEEvent, None]:
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(
            maxsize=self._max_queue_size
        )
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:  # Shutdown signal
                    break
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        self._event_counter += 1
        event = SSEEvent(
            event_type=event_type,
            data=data,
            id=str(self._event_counter),
        )
        async with self._lock:
            dead_queues: list[asyncio.Queue[SSEEvent | None]] = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Slow consumer -- drop events (log warning)
                    dead_queues.append(queue)
            for q in dead_queues:
                self._subscribers.discard(q)
```

### Integration with hooks.py

The connection point between the engine and SSE is `hooks.py`. When the API server starts, `dependencies.py` calls `hooks.set_sse_broadcaster(broadcaster)` to wire the broadcaster into the hook system. When running in CLI-only mode, the broadcaster is never set, so `_publish_sse_event` is a no-op.

For events that originate from DB operations (like `update_task_status`), there are two integration approaches:

**Approach chosen: Hook-based publishing.** The `post_tool_use_hook` already detects when pytest runs, git commits happen, etc. We extend this to detect task status changes and publish SSE events. This keeps the DB layer clean (no SSE awareness) and centralizes event publishing in one place.

**Alternative considered:** Database triggers or callback registration on `OrchestratorDB`. Rejected because it would couple the DB layer to the event system and complicate testing.

For circuit breaker events specifically, the `MetricsCollector` already has a callback mechanism (`register_callback`). Per Q10 verdict, we reuse this for Phase 1 with the constraint that the adapter lives in the API layer:

```python
# In api/sse_bridge.py (NOT in core modules):
from ..metrics import get_metrics_collector

def wire_circuit_breaker_sse(broadcaster: SSEBroadcaster) -> None:
    """Register MetricsCollector callback to publish circuit events to SSE.

    Phase 1 approach. Migrate to dedicated EventBus in Phase 2 when
    additional event sources need SSE or when from_state/reason fields
    are required.
    """
    collector = get_metrics_collector()
    collector.register_callback(lambda metric: _publish_metric_as_sse(metric, broadcaster))
```

---

## 6. CLI `serve` Command

### Usage

```bash
# Start server with defaults (127.0.0.1:8420)
tdd-orchestrator serve

# Custom host/port
tdd-orchestrator serve --host 127.0.0.1 --port 9000

# With specific database
tdd-orchestrator serve --db /path/to/orchestrator.db

# Development mode (auto-reload)
tdd-orchestrator serve --reload --log-level debug

# Verbose logging
tdd-orchestrator -v serve
```

### Implementation

The `serve` command is a Click command on the `cli` group. It uses a lazy import to avoid importing FastAPI/uvicorn when they are not installed:

```python
@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
@click.option("--port", default=8420, help="Bind port (default: 8420)")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--reload", is_flag=True, help="Enable auto-reload (development)")
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"]),
    help="Log level",
)
def serve(host: str, port: int, db: str | None, reload: bool, log_level: str) -> None:
    """Start the API server.

    Requires: pip install tdd-orchestrator[api]
    Default: http://127.0.0.1:8420
    """
    try:
        from .api.serve import run_server
    except ImportError:
        click.echo(
            "Error: API dependencies not installed.\n"
            "Install with: pip install tdd-orchestrator[api]",
            err=True,
        )
        sys.exit(1)

    run_server(
        host=host,
        port=port,
        db_path=db,
        reload=reload,
        log_level=log_level,
    )
```

### Graceful Shutdown

Uvicorn handles SIGINT/SIGTERM. The FastAPI lifespan context manager (`app.py`) ensures:
1. DB connection is closed
2. SSE broadcaster shuts down (sends `None` sentinel to all subscriber queues)
3. No orphaned asyncio tasks

### Port Selection

Default port `8420` chosen to avoid conflicts with common services (8000=Django, 8080=proxy, 3000=React, 5173=Vite).

---

## 7. Database Additions

### New Methods on TaskMixin

| Method | Signature | Purpose |
|---|---|---|
| `get_tasks_by_status` | `(status: str) -> list[dict[str, Any]]` | Filter tasks by status for API |
| `get_tasks_filtered` | `(*, status, phase, complexity, limit, offset) -> tuple[list, int]` | Paginated filtered query |

### New Methods on RunsMixin

| Method | Signature | Purpose |
|---|---|---|
| `get_execution_runs` | `(*, status, limit) -> list[dict[str, Any]]` | List runs for API |
| `get_current_run` | `() -> dict[str, Any] \| None` | Get active run |

### New Methods on WorkerMixin

| Method | Signature | Purpose |
|---|---|---|
| `get_all_workers` | `() -> list[dict[str, Any]]` | List workers with stats via `v_worker_stats` |

### No Schema Changes Required

All new queries use existing tables and views. No `ALTER TABLE`, no new views, no new indexes needed. The existing `v_worker_stats`, `v_circuit_breaker_status`, `v_open_circuits`, and `v_circuit_health_summary` views already provide the data the API needs.

---

## 8. Test Strategy

### Test File Structure

```
tests/
├── unit/
│   └── api/
│       ├── __init__.py
│       ├── test_models.py            # Pydantic model validation
│       ├── test_sse.py               # SSEBroadcaster unit tests
│       ├── test_error_handler.py     # Error handler middleware
│       ├── test_routes_health.py     # Health endpoint tests
│       ├── test_routes_tasks.py      # Task endpoint tests
│       ├── test_routes_workers.py    # Worker endpoint tests
│       ├── test_routes_circuits.py   # Circuit endpoint tests
│       ├── test_routes_runs.py       # Run endpoint tests
│       ├── test_routes_metrics.py    # Metrics endpoint tests
│       └── test_db_additions.py      # New DB method tests
├── integration/
│   └── api/
│       ├── __init__.py
│       ├── test_app_lifecycle.py     # App startup/shutdown
│       ├── test_sse_integration.py   # SSE with real events
│       └── test_full_api.py          # Full endpoint integration
```

### Testing Approach

**Unit tests (`tests/unit/api/`):**
- Use FastAPI `TestClient` (synchronous wrapper around httpx)
- Use in-memory SQLite (`:memory:`) via the existing test pattern
- Mock the SSE broadcaster where not under test
- Each route file gets its own test file
- ~15-20 tests per route file

**Example test pattern:**

```python
"""Tests for task API endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tdd_orchestrator.api.app import create_app
from tdd_orchestrator.database import OrchestratorDB


async def _seed_db(db: OrchestratorDB) -> None:
    """Seed database with test tasks."""
    await db.create_task("TDD-01", "First task", phase=0, sequence=0)
    await db.create_task("TDD-02", "Second task", phase=0, sequence=1)


def test_list_tasks_empty() -> None:
    """GET /tasks returns empty list when no tasks exist."""
    app = create_app(db_path=":memory:")
    client = TestClient(app)
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["tasks"] == []
    assert data["total"] == 0


def test_list_tasks_with_filter() -> None:
    """GET /tasks?status=pending returns filtered results."""
    ...


def test_get_task_not_found() -> None:
    """GET /tasks/NONEXISTENT returns 404."""
    app = create_app(db_path=":memory:")
    client = TestClient(app)
    response = client.get("/tasks/NONEXISTENT")
    assert response.status_code == 404
```

**Integration tests (`tests/integration/api/`):**
- Use a temporary SQLite file (not `:memory:`) to test real I/O
- Test full request/response cycle with seeded data
- Test SSE with real event publishing
- Test app startup and shutdown lifecycle

### Testing SSE

SSE testing requires an async approach since `TestClient` is synchronous:

```python
"""SSE broadcaster unit tests."""
import asyncio

from tdd_orchestrator.api.sse import SSEBroadcaster


async def test_broadcaster_publish_and_subscribe() -> None:
    """Published events are received by subscribers."""
    broadcaster = SSEBroadcaster()

    received: list[dict] = []

    async def consumer() -> None:
        async for event in broadcaster.subscribe():
            received.append(event.data)
            if len(received) >= 2:
                break

    task = asyncio.create_task(consumer())

    await broadcaster.publish("test_event", {"key": "value1"})
    await broadcaster.publish("test_event", {"key": "value2"})

    await asyncio.wait_for(task, timeout=2.0)
    assert len(received) == 2
    assert received[0]["key"] == "value1"


async def test_broadcaster_multiple_subscribers() -> None:
    """Multiple subscribers each receive all events."""
    ...


async def test_broadcaster_slow_consumer_dropped() -> None:
    """Slow consumers are dropped when queue fills."""
    broadcaster = SSEBroadcaster(max_queue_size=2)
    # Subscribe but never consume
    ...


async def test_broadcaster_shutdown() -> None:
    """Shutdown sends sentinel to all subscribers."""
    ...
```

### Testing New DB Methods

```python
"""Tests for new database query methods."""

from tdd_orchestrator.database import OrchestratorDB


async def test_get_tasks_by_status() -> None:
    async with OrchestratorDB(":memory:") as db:
        await db.create_task("T-1", "Task 1", phase=0, sequence=0)
        await db.create_task("T-2", "Task 2", phase=0, sequence=1)
        await db.update_task_status("T-1", "complete")

        pending = await db.get_tasks_by_status("pending")
        assert len(pending) == 1
        assert pending[0]["task_key"] == "T-2"

        complete = await db.get_tasks_by_status("complete")
        assert len(complete) == 1


async def test_get_tasks_filtered_pagination() -> None:
    async with OrchestratorDB(":memory:") as db:
        for i in range(10):
            await db.create_task(f"T-{i}", f"Task {i}", phase=0, sequence=i)

        tasks, total = await db.get_tasks_filtered(limit=3, offset=0)
        assert len(tasks) == 3
        assert total == 10

        tasks2, total2 = await db.get_tasks_filtered(limit=3, offset=3)
        assert len(tasks2) == 3
        assert total2 == 10
        assert tasks2[0]["task_key"] != tasks[0]["task_key"]
```

### Estimated Test Count

| Test File | Tests |
|---|---|
| `test_models.py` | 15 |
| `test_sse.py` | 10 |
| `test_error_handler.py` | 5 |
| `test_routes_health.py` | 8 |
| `test_routes_tasks.py` | 20 |
| `test_routes_workers.py` | 8 |
| `test_routes_circuits.py` | 12 |
| `test_routes_runs.py` | 8 |
| `test_routes_metrics.py` | 3 |
| `test_db_additions.py` | 12 |
| `test_app_lifecycle.py` | 5 |
| `test_sse_integration.py` | 8 |
| `test_full_api.py` | 10 |
| **Total** | **~124** |

---

## 9. Dependency Changes

### `pyproject.toml` Changes

```toml
[project.optional-dependencies]
sdk = ["claude-agent-sdk>=0.1.19"]
api = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "sse-starlette>=2.2.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "mypy>=1.18.2",
    "ruff>=0.13.1",
]
```

### Why These Versions

| Package | Pin | Reason |
|---|---|---|
| `fastapi>=0.115.0` | v0.115+ uses Pydantic v2, lifespan context managers, modern typing |
| `uvicorn[standard]>=0.32.0` | Standard includes uvloop for performance, httptools for speed |
| `pydantic>=2.10.0` | v2.10+ has stable model_validate, improved performance |
| `sse-starlette>=2.2.0` | v2.2+ supports async generators with proper cleanup |

### Installation

```bash
# API server (includes FastAPI + uvicorn)
pip install -e ".[api]"

# Full development (includes api + dev + sdk)
pip install -e ".[dev,api,sdk]"

# Existing CLI-only usage (unchanged)
pip install -e .
```

### API is Optional

The `api` extra follows the same pattern as `sdk`:
- Imports guarded with `try/except ImportError`
- CLI `serve` command shows a helpful error if dependencies are missing
- Core engine functionality works without FastAPI installed
- mypy strict still passes when API deps are not installed

---

## 10. Verification Checklist

Execute these commands in order. All must pass.

### Pre-flight

```bash
# 1. Existing tests still pass (regression check)
.venv/bin/pytest tests/ -v

# 2. Existing linting still clean
.venv/bin/ruff check src/
.venv/bin/mypy src/ --strict
```

### Install and Basic Checks

```bash
# 3. Install API dependencies
.venv/bin/pip install -e ".[dev,api]"

# 4. New code passes linting
.venv/bin/ruff check src/tdd_orchestrator/api/
.venv/bin/mypy src/tdd_orchestrator/api/ --strict

# 5. All tests pass (old + new)
.venv/bin/pytest tests/ -v
```

### Server Smoke Test

```bash
# 6. Server starts
tdd-orchestrator serve --port 8420 &
SERVER_PID=$!
sleep 2

# 7. Health endpoint
curl -s http://localhost:8420/health | python -m json.tool

# 8. Tasks endpoint
curl -s http://localhost:8420/tasks | python -m json.tool

# 9. Stats endpoint
curl -s http://localhost:8420/tasks/stats | python -m json.tool

# 10. Workers endpoint
curl -s http://localhost:8420/workers | python -m json.tool

# 11. Circuits endpoint
curl -s http://localhost:8420/circuits | python -m json.tool

# 12. Runs endpoint
curl -s http://localhost:8420/runs | python -m json.tool

# 13. Metrics endpoint
curl -s http://localhost:8420/metrics

# 14. Liveness probe
curl -s http://localhost:8420/health/live

# 15. OpenAPI spec generated
curl -s http://localhost:8420/openapi.json | python -m json.tool | head -20

# 16. SSE endpoint (connect for 3 seconds)
timeout 3 curl -s http://localhost:8420/events || true

# 17. Cleanup
kill $SERVER_PID
```

### CLI Check

```bash
# 18. serve command appears in help
tdd-orchestrator --help | grep serve

# 19. serve without API deps shows helpful error (test in clean venv)
# (Manual verification -- create a venv without [api] extra)
```

### Final Validation

```bash
# 20. Full test suite
.venv/bin/pytest tests/ -v --tb=short

# 21. Full lint + type check
.venv/bin/ruff check src/ && .venv/bin/mypy src/ --strict

# 22. Check file sizes (none should exceed 400 lines)
wc -l src/tdd_orchestrator/api/*.py src/tdd_orchestrator/api/**/*.py
```

---

## 11. Open Questions for Debate

These are design decisions where legitimate alternatives exist. Each should be discussed before implementation begins.

### Q1: FastAPI as optional dependency vs core dependency

**Decision made:** FastAPI is an optional extra (`[api]`), guarded by try/except, following the SDK pattern.

**Strongest counterargument:** Making it optional adds import-guarding complexity in every file that touches the API layer. If the project is evolving toward always being a daemon (Phase 2+), the API layer will become the primary interface, making optionality a premature abstraction that creates maintenance overhead without serving real users.

**VERDICT:** Keep optional — with sunset clause. **Confidence: MEDIUM.** The optional pattern is proven and the API module is cleanly isolated under `api/`. The added testing cost is manageable. **Would change if:** Phase 2 daemon work begins and API becomes the default entry point, more than 3 files outside `api/` require import guards, or CI matrix testing of both configurations becomes a recurring source of failures.

---

### Q2: SSE vs WebSocket for real-time events

**Decision made:** Server-Sent Events (SSE) via `sse-starlette`.

**Strongest counterargument:** WebSocket is bidirectional, allowing the dashboard to send commands (retry task, reset circuit) over the same connection instead of separate HTTP requests. SSE is unidirectional and requires separate HTTP calls for mutations. As the dashboard grows (Phase 3), the bidirectional channel becomes increasingly valuable, and migrating from SSE to WebSocket later means rewriting both server and client code.

**VERDICT:** Keep SSE. **Confidence: HIGH.** The system's mutation surface is REST. Events are read-only broadcasts to 1-5 clients. SSE has built-in reconnection via `Last-Event-ID`, works through proxies without upgrade negotiation, and is simpler to implement. The "two transport" concern is moot — REST endpoints exist for mutations regardless. **Would change if:** Dashboard requires sub-100ms interactive command loops, client-driven event filtering becomes essential, or concurrent clients exceed ~50.

---

### Q3: Pydantic models separate from domain models

**Decision made:** API Pydantic models are separate from the existing `models.py` dataclasses (`Stage`, `StageResult`, `VerifyResult`). Converter functions translate between them.

**Strongest counterargument:** This creates parallel model hierarchies that must be kept in sync. If `TaskResponse` diverges from the DB schema silently, clients get stale data. A single source of truth (making the domain models Pydantic-based) would eliminate the conversion layer entirely and guarantee consistency, at the cost of adding pydantic as a core dependency.

**VERDICT:** Keep separate models. **Confidence: HIGH.** This is a pip-installable library first, API second. The API is an optional layer (`[api]` extra). Forcing Pydantic into core dependencies violates the project's dependency-isolation principle. The staleness risk is managed by a `test_api_models.py` that asserts API model fields match DB schema columns. **Would change if:** API becomes the primary interface and CLI/library usage becomes negligible — at that point, Pydantic moves to core deps and unified models eliminate the conversion layer.

---

### Q4: DB query methods on OrchestratorDB vs dedicated read-only query service

**Decision made:** Add `get_tasks_filtered()`, `get_execution_runs()`, etc. directly to the existing mixin classes.

**Strongest counterargument:** The mixin classes (`TaskMixin`, `RunsMixin`) mix read and write operations. API queries are purely read-only and should not share a write lock. A dedicated `QueryService` class with its own connection could use a read-only SQLite connection (`?mode=ro`) for better separation of concerns and potentially better concurrent read performance under WAL mode.

**VERDICT:** Keep on existing mixins. **Confidence: HIGH.** Five methods across three established mixins is well within the pattern's capacity. The project enforces 800-line file limits, providing a natural extraction trigger. A separate read connection adds lifecycle management complexity not justified by the current load (1-5 clients + 1-3 workers). **Would change if:** API read methods grow past 10, observed write-lock contention during concurrent API + worker operations, or a second read consumer needs its own connection.

---

### Q5: Event publishing via hooks.py vs database-level observer

**Decision made:** The `hooks.py` module publishes SSE events by checking for state changes in `post_tool_use_hook`.

**Strongest counterargument:** `hooks.py` hooks are designed for the Claude Agent SDK context (tool use interception). Task status changes made directly via DB methods (e.g., `db.update_task_status()` called from the API `retry` endpoint) bypass hooks entirely, creating a gap where SSE events are not published. A database-level callback pattern (e.g., `db.on_status_change(callback)`) would capture all mutations regardless of origin, providing more reliable event delivery.

**VERDICT: OVERTURNED — Use database-level observer pattern.** **Confidence: HIGH.** The hooks-based approach has a structural gap: the API retry endpoint calls `db.update_task_status()` directly, bypassing hooks entirely. SSE subscribers would miss those events. Fix: add `_callbacks: list[Callable]` to `TaskMixin` with dispatch after `commit()` in `update_task_status()`. ~8 lines, follows the `MetricsCollector.register_callback()` precedent. hooks.py stays focused on Claude SDK tool use interception. **Would change if:** All mutations flow through SDK tool calls (making the gap theoretical).

---

### Q6: Default bind address 0.0.0.0 vs 127.0.0.1

**Decision made:** Default to `0.0.0.0` (all interfaces) for convenience in local networks and Docker-less deployment.

**Strongest counterargument:** Binding to `0.0.0.0` exposes the API to the local network by default, which is a security concern. Most users will run this on a development machine, and `127.0.0.1` (localhost only) is the safer default. Users who need network access can explicitly set `--host 0.0.0.0`. This follows the principle of least privilege.

**VERDICT: OVERTURNED — Default to 127.0.0.1.** **Confidence: HIGH.** No auth in Phase 1 + mutation endpoints + developer laptops on untrusted networks = silent exposure risk. Failure mode of `127.0.0.1` is loud (connection refused, one-flag fix). Failure mode of `0.0.0.0` is silent (unintended network access). Docker users already expect to configure bind addresses. **Would change if:** Phase 1 ships with basic auth (token header), or tool becomes primarily container-deployed.

---

### Q7: Single app factory vs separate app instances per test

**Decision made:** Each test creates its own `create_app(db_path=":memory:")` instance, ensuring full isolation.

**Strongest counterargument:** Creating a new app per test is slow because it initializes the DB schema each time. A shared app fixture with per-test transaction rollback would be faster and still provide isolation. The `create_app` factory approach also makes it harder to test interactions between requests (e.g., "create task then list tasks") because each request might hit a different DB state.

**VERDICT:** Keep app-per-test. **Confidence: HIGH.** Schema init is ~5ms per test — 124 tests adds under 2 seconds. No ORM means no built-in transaction rollback; building a custom one introduces untested infrastructure. The existing 324-test suite validates this pattern at scale. Multi-request flows work fine within a single test (same app instance). **Would change if:** Schema init exceeds 200ms per test, or project adopts an ORM with built-in transaction rollback.

---

### Q8: Port 8420 as default

**Decision made:** Use port `8420` as the default bind port.

**Strongest counterargument:** Non-standard ports are hard to remember. Port `8000` is the Python convention (Django, uvicorn default, FastAPI docs). Using `8420` means every tutorial, script, and documentation example must include `--port 8420` or the non-standard URL. The risk of conflicts with Django is low for a TDD tool (users are unlikely to run both simultaneously), and if they do, `--port` is easily available.

**VERDICT:** Keep port 8420. **Confidence: HIGH.** This tool is a companion process to web applications, not a web application itself. The target user is likely to have port 8000 in use. A clean first-run experience (no conflict) outweighs the minor cost of a non-standard port. The CLI prints the URL at startup for discoverability. **Would change if:** User research shows port conflicts are actually rare among the target audience.

---

### Q9: Thin converter functions vs Pydantic model_validate

**Decision made:** Explicit converter functions (`_row_to_task_response`) that manually map fields.

**Strongest counterargument:** Pydantic v2's `model_validate(dict_data)` with `model_config = ConfigDict(from_attributes=True)` can handle the conversion automatically. This eliminates boilerplate converter functions that are boring to write and easy to forget updating when the schema changes. The JSON-encoded fields (`depends_on`, `acceptance_criteria`) can be handled with Pydantic validators (`@field_validator`) that parse JSON strings.

**VERDICT: OVERTURNED — Use model_validate with @field_validator.** **Confidence: HIGH.** With 16 models and matching column/field names, explicit converters are pure duplication (~400-600 lines of boilerplate). JSON-encoded columns are handled by `@field_validator(mode="before")` — 3-4 lines each, co-located with the field. Eliminates an entire category of drift bugs (forgetting to update converter when model changes). **Would change if:** Column names diverge from field names, conversion logic grows complex enough to warrant its own test suite, or Pydantic's `model_validate` produces mypy `Any` leaks under strict mode.

---

### Q10: Where to publish circuit breaker SSE events

**Decision made:** Register a callback on `MetricsCollector` to publish circuit breaker events to SSE.

**Strongest counterargument:** `MetricsCollector` is a metrics system, not an event bus. Overloading it with SSE responsibilities violates single responsibility. A dedicated `EventBus` class that both the metrics collector and SSE broadcaster subscribe to would be cleaner. The circuit breaker classes (`StageCircuitBreaker`, `WorkerCircuitBreaker`) should publish events to the event bus directly in their `_transition_to_open`, `_transition_to_closed` methods.

**VERDICT:** MetricsCollector callbacks for Phase 1, migrate to EventBus in Phase 2. **Confidence: MEDIUM.** MetricsCollector callback works for MVP (~5 lines to wire). Constraint: callback adapter must live in API layer (`api/sse_bridge.py`), never in core modules. **Would change if:** A second event source needs SSE, SSE schema requires `from_state`/`reason` fields that MetricsCollector doesn't carry, or the callback reverse-engineering becomes fragile.

---

## Summary

| Metric | Value |
|---|---|
| New files to create | 18 |
| Existing files to modify | 7 |
| New Pydantic models | 16 |
| API endpoints | 15 |
| SSE event types | 8 |
| New DB methods | 5 |
| Estimated new test count | ~124 |
| Estimated new lines of code | ~2,500 (production) + ~1,500 (tests) |
| New dependencies | 4 (all optional) |
| Build steps | 10 (sequential with dependencies) |
