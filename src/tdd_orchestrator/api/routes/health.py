"""Health check router for liveness endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/live")
def get_health_live() -> dict[str, str]:
    """Return liveness status.

    Returns:
        A dictionary with status "alive".
    """
    return {"status": "alive"}
