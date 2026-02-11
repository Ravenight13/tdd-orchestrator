"""Circuit breaker CRUD endpoints.

Endpoints:
- GET /circuits - List circuits with optional level/state filters
- GET /circuits/{id} - Get a circuit by ID
- POST /circuits/{id}/reset - Reset a circuit
- GET /circuits/health - Get circuit health summary
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CircuitBreakerResponse(BaseModel):
    """Response model for circuit breaker data."""

    id: str
    level: str
    state: str
    failure_count: int
    last_failure_at: datetime | None
    opened_at: datetime | None


class CircuitHealthSummary(BaseModel):
    """Response model for circuit health summary."""

    total_circuits: int
    closed: int
    open: int
    half_open: int
    healthy: bool


def list_circuits(level: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    """List circuits with optional filters.

    This is a placeholder that will be mocked in tests.

    Args:
        level: Optional level filter (task, phase, pipeline)
        state: Optional state filter (closed, open, half_open)

    Returns:
        List of circuit dictionaries
    """
    return []


def get_circuit_by_id(circuit_id: str) -> dict[str, Any] | None:
    """Get a circuit by ID.

    This is a placeholder that will be mocked in tests.

    Args:
        circuit_id: The circuit ID to fetch

    Returns:
        Circuit dictionary if found, None otherwise
    """
    return None


def reset_circuit(circuit_id: str) -> dict[str, Any] | None:
    """Reset a circuit by ID.

    This is a placeholder that will be mocked in tests.

    Args:
        circuit_id: The circuit ID to reset

    Returns:
        Updated circuit dictionary if found, None otherwise
    """
    return None


def get_circuit_health_summary() -> dict[str, Any]:
    """Get circuit health summary.

    This is a placeholder that will be mocked in tests.

    Returns:
        Health summary dictionary
    """
    return {
        "total_circuits": 0,
        "closed": 0,
        "open": 0,
        "half_open": 0,
        "healthy": True,
    }


@router.get("", response_model=list[CircuitBreakerResponse])
def get_circuits(level: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    """List circuits with optional level and state filters.

    Args:
        level: Optional level filter (task, phase, pipeline)
        state: Optional state filter (closed, open, half_open)

    Returns:
        List of circuit breaker data
    """
    return list_circuits(level=level, state=state)


@router.get("/health", response_model=CircuitHealthSummary)
def get_health_summary() -> dict[str, Any]:
    """Get circuit health summary.

    Returns:
        Health summary with counts and healthy status
    """
    return get_circuit_health_summary()


@router.get("/{circuit_id}", response_model=CircuitBreakerResponse)
def get_circuit(circuit_id: str) -> dict[str, Any]:
    """Get a circuit by ID.

    Args:
        circuit_id: The circuit ID to fetch

    Returns:
        Circuit breaker data

    Raises:
        HTTPException: 404 if circuit not found
    """
    circuit = get_circuit_by_id(circuit_id)
    if circuit is None:
        raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")
    return circuit


@router.post("/{circuit_id}/reset", response_model=CircuitBreakerResponse)
def reset_circuit_endpoint(circuit_id: str) -> dict[str, Any]:
    """Reset a circuit by ID.

    Args:
        circuit_id: The circuit ID to reset

    Returns:
        Updated circuit breaker data

    Raises:
        HTTPException: 404 if circuit not found
    """
    circuit = reset_circuit(circuit_id)
    if circuit is None:
        raise HTTPException(status_code=404, detail=f"Circuit {circuit_id} not found")
    return circuit
