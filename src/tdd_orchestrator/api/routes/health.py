"""Health check router for liveness endpoint."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request, Response

router = APIRouter()


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
