"""Health check router for liveness endpoint."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request, Response

router = APIRouter()


def get_circuit_health() -> dict[str, Any]:
    """Get circuit breaker health status.

    This function should be implemented to return actual circuit health data.
    For now, it returns a basic structure that can be mocked in tests.

    Returns:
        A dictionary containing:
        - status: Overall health status (healthy/degraded/unhealthy)
        - circuits: List of circuit breaker statuses
        - timestamp: ISO-8601 formatted timestamp
    """
    # This is a placeholder implementation that will be replaced
    # with actual circuit breaker health checks
    from datetime import datetime, timezone

    return {
        "status": "healthy",
        "circuits": [],
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.get("")
def get_health(response: Response) -> dict[str, Any]:
    """Return health status including circuit breaker information.

    Args:
        response: FastAPI response object to set status code.

    Returns:
        A dictionary with status, circuits, and timestamp.
        Status code is 200 for healthy/degraded, 503 for unhealthy.
    """
    try:
        health_data = get_circuit_health()

        # Set appropriate status code based on health status
        status = health_data.get("status", "healthy")
        if status == "unhealthy":
            response.status_code = 503
        else:
            response.status_code = 200

        return health_data

    except Exception as e:
        # Never return 500 - always handle gracefully with 503
        response.status_code = 503
        from datetime import datetime, timezone

        return {
            "status": "unhealthy",
            "circuits": [],
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "error": f"Health check failed: {str(e)}",
        }



@router.get("/live")
def get_health_live() -> dict[str, str]:
    """Return liveness status.

    Returns:
        A dictionary with status "alive".
    """
    return {"status": "alive"}


@router.get("/ready")
async def get_health_ready(
    request: Request, response: Response
) -> dict[str, str] | dict[str, Any]:
    """Return readiness status by checking database connectivity.

    Args:
        request: FastAPI request object to access dependency overrides.
        response: FastAPI response object to set status code.

    Returns:
        A dictionary with status "ok" if database is reachable,
        or status "unavailable" with detail if database check fails.
    """
    try:
        # Import here to avoid circular dependency issues
        from tdd_orchestrator.api.dependencies import get_db_dep

        # Get the dependency function (checking for overrides)
        dependency_func = get_db_dep
        if hasattr(request.app, "dependency_overrides"):
            dependency_func = request.app.dependency_overrides.get(
                get_db_dep, get_db_dep
            )

        # Try to invoke the dependency
        async for _ in dependency_func():
            # Successfully got the db, it's reachable
            return {"status": "ok"}
        # If we exit the loop without returning, still consider it OK
        return {"status": "ok"}
    except (RuntimeError, asyncio.TimeoutError) as e:
        response.status_code = 503
        return {"status": "unavailable", "detail": str(e)}
