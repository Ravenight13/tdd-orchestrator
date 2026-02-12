"""Workers router for listing workers and fetching worker details."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from tdd_orchestrator.api.dependencies import get_db_dep

router = APIRouter()


def list_workers() -> dict[str, Any]:
    """List all workers.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns an empty result structure.

    Returns:
        A dictionary with items list and total count.
    """
    return {
        "items": [],
        "total": 0,
    }


def get_worker_by_id(worker_id: str) -> dict[str, Any] | None:
    """Get a worker by ID.

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns None.

    Args:
        worker_id: The unique worker identifier.

    Returns:
        A dictionary with worker details, or None if not found.
    """
    return None


def list_stale_workers() -> dict[str, Any]:
    """List stale workers (workers with old heartbeats).

    This is a placeholder function that will be replaced with actual
    database queries. For now, it returns an empty result structure.

    Returns:
        A dictionary with items list and total count.
    """
    return {
        "items": [],
        "total": 0,
    }


@router.get("")
async def get_workers(db: Any = Depends(get_db_dep)) -> dict[str, Any]:
    """Get list of all workers.

    Returns:
        WorkerListResponse with workers list and total count.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute(
            "SELECT worker_id, status, registered_at FROM workers ORDER BY registered_at"
        ) as cursor:
            rows = await cursor.fetchall()
        workers = [
            {
                "id": str(row["worker_id"]),
                "status": str(row["status"]),
                "registered_at": str(row["registered_at"]),
            }
            for row in rows
        ]
        return {"workers": workers, "total": len(workers)}
    return list_workers()


@router.get("/stale")
async def get_stale_workers(db: Any = Depends(get_db_dep)) -> dict[str, Any]:
    """Get list of stale workers.

    Returns:
        WorkerListResponse with stale workers list and total count.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute("SELECT * FROM v_stale_workers") as cursor:
            rows = await cursor.fetchall()
        workers = [
            {
                "id": str(row["worker_id"]),
                "status": str(row["status"]),
                "registered_at": str(row["registered_at"]),
            }
            for row in rows
        ]
        return {"items": workers, "total": len(workers)}
    return list_stale_workers()


@router.get("/{worker_id}")
async def get_worker(
    worker_id: str, db: Any = Depends(get_db_dep)
) -> dict[str, Any]:
    """Get a worker by ID.

    Args:
        worker_id: The unique worker identifier.

    Returns:
        WorkerResponse with worker details.

    Raises:
        HTTPException: 404 if worker not found.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        param: int | str = int(worker_id) if worker_id.isdigit() else worker_id
        async with db._conn.execute(
            "SELECT worker_id, status, registered_at FROM workers WHERE worker_id = ?",
            (param,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is not None:
            return {
                "id": str(row["worker_id"]),
                "status": str(row["status"]),
                "registered_at": str(row["registered_at"]),
            }
        raise HTTPException(status_code=404, detail="Worker not found")
    worker = get_worker_by_id(worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker
