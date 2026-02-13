"""Circuit breaker CRUD endpoints.

Endpoints:
- GET /circuits - List circuits with optional level/state filters
- GET /circuits/{circuit_id} - Get a circuit by ID
- POST /circuits/{circuit_id}/reset - Reset a circuit
- GET /circuits/health - Get circuit health summary (per-level)
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from tdd_orchestrator.api.dependencies import get_db_dep
from tdd_orchestrator.api.models.responses import (
    CircuitBreakerResponse,
    CircuitHealthSummary,
)

router = APIRouter()


def _circuit_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a v_circuit_breaker_status row to a CircuitBreakerResponse-compatible dict."""
    return {
        "id": str(row["id"]),
        "level": str(row["level"]),
        "identifier": str(row["identifier"]),
        "state": str(row["state"]),
        "failure_count": int(row["failure_count"]),
        "success_count": int(row["success_count"]),
        "extensions_count": int(row["extensions_count"]),
        "opened_at": str(row["opened_at"]) if row["opened_at"] else None,
        "last_failure_at": str(row["last_failure_at"]) if row["last_failure_at"] else None,
        "last_success_at": str(row["last_success_at"]) if row["last_success_at"] else None,
        "last_state_change_at": (
            str(row["last_state_change_at"]) if row["last_state_change_at"] else None
        ),
        "version": int(row["version"]),
        "run_id": int(row["run_id"]) if row["run_id"] else None,
    }


@router.get("")
async def get_circuits(
    level: str | None = None,
    state: str | None = None,
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """List circuits with optional level and state filters.

    Args:
        level: Optional level filter (stage, worker, system).
        state: Optional state filter (closed, open, half_open).
        db: Database dependency (injected).

    Returns:
        Dict with circuits list and total count.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        query = "SELECT * FROM v_circuit_breaker_status WHERE 1=1"
        params: list[Any] = []
        if level is not None:
            query += " AND level = ?"
            params.append(level)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        async with db._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        circuits = [_circuit_row_to_dict(row) for row in rows]
        return {"circuits": circuits, "total": len(circuits)}
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/health", response_model=list[CircuitHealthSummary])
async def get_health_summary(
    db: Any = Depends(get_db_dep),
) -> list[dict[str, Any]]:
    """Get circuit health summary grouped by level.

    Args:
        db: Database dependency (injected).

    Returns:
        List of per-level health summaries from v_circuit_health_summary.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        async with db._conn.execute("SELECT * FROM v_circuit_health_summary") as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "level": str(row["level"]),
                "total_circuits": int(row["total_circuits"]),
                "closed_count": int(row["closed_count"]),
                "open_count": int(row["open_count"]),
                "half_open_count": int(row["half_open_count"]),
            }
            for row in rows
        ]
    raise HTTPException(status_code=503, detail="Database not available")


@router.get("/{circuit_id}", response_model=CircuitBreakerResponse)
async def get_circuit(
    circuit_id: str,
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get a circuit by ID.

    Args:
        circuit_id: The circuit ID to fetch.
        db: Database dependency (injected).

    Returns:
        CircuitBreakerResponse data.

    Raises:
        HTTPException: 404 if circuit not found, 503 if DB unavailable.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        try:
            circuit_id_int = int(circuit_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")
        async with db._conn.execute(
            "SELECT * FROM v_circuit_breaker_status WHERE id = ?", (circuit_id_int,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")
        return _circuit_row_to_dict(row)
    raise HTTPException(status_code=503, detail="Database not available")


@router.post("/{circuit_id}/reset", response_model=CircuitBreakerResponse)
async def reset_circuit_endpoint(
    circuit_id: str,
    db: Any = Depends(get_db_dep),
) -> dict[str, Any]:
    """Reset a circuit by ID.

    Resets state to 'closed' with zeroed counters and inserts a manual_reset
    audit event into circuit_breaker_events.

    Args:
        circuit_id: The circuit ID to reset.
        db: Database dependency (injected).

    Returns:
        Updated CircuitBreakerResponse data.

    Raises:
        HTTPException: 404 if circuit not found, 503 if DB unavailable.
    """
    if db is not None and hasattr(db, "_conn") and db._conn is not None:
        try:
            circuit_id_int = int(circuit_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")

        # Fetch current state for audit trail
        async with db._conn.execute(
            "SELECT id, state FROM circuit_breakers WHERE id = ?", (circuit_id_int,)
        ) as cursor:
            existing = await cursor.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")

        old_state = str(existing["state"])

        # Reset the circuit
        await db._conn.execute(
            "UPDATE circuit_breakers "
            "SET state = 'closed', failure_count = 0, success_count = 0, "
            "    half_open_requests = 0, opened_at = NULL, "
            "    last_state_change_at = datetime('now') "
            "WHERE id = ?",
            (circuit_id_int,),
        )

        # Insert audit event
        await db._conn.execute(
            "INSERT INTO circuit_breaker_events "
            "(circuit_id, event_type, from_state, to_state) "
            "VALUES (?, 'manual_reset', ?, 'closed')",
            (circuit_id_int, old_state),
        )

        await db._conn.commit()

        # Return updated row from view
        async with db._conn.execute(
            "SELECT * FROM v_circuit_breaker_status WHERE id = ?", (circuit_id_int,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")
        return _circuit_row_to_dict(row)
    raise HTTPException(status_code=503, detail="Database not available")
