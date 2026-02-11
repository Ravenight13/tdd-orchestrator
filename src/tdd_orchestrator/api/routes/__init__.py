"""Route registration for FastAPI app.

Wires all route modules (health, tasks, workers, circuits, runs, metrics)
to the FastAPI app with correct URL prefixes.
"""

from __future__ import annotations

from fastapi import FastAPI

from tdd_orchestrator.api.routes import (
    circuits,
    health,
    metrics,
    runs,
    tasks,
    workers,
)


def register_routes(app: FastAPI) -> None:
    """Register all route modules to the FastAPI app.

    Includes routes for health, tasks, workers, circuits, runs, and metrics
    under their respective URL prefixes.

    This function is idempotent - calling it multiple times on the same app
    will not duplicate routes.

    Args:
        app: The FastAPI application instance.
    """
    # Guard against duplicate registration
    if hasattr(app, "_routes_registered") and app._routes_registered:
        return

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
    app.include_router(workers.router, prefix="/workers", tags=["workers"])
    app.include_router(circuits.router, prefix="/circuits", tags=["circuits"])
    app.include_router(runs.router, prefix="/runs", tags=["runs"])
    app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

    # Mark routes as registered
    app._routes_registered = True  # type: ignore[attr-defined]
