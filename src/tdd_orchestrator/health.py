"""Health check endpoint for circuit breaker monitoring.

Provides API-compatible health status for circuit breakers at all levels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)


class CircuitHealthStatus(Enum):
    """Overall health status for circuit breaker system."""

    HEALTHY = "HEALTHY"  # All circuits closed
    DEGRADED = "DEGRADED"  # Some circuits open/half-open
    UNHEALTHY = "UNHEALTHY"  # System circuit open or multiple failures
    UNKNOWN = "UNKNOWN"  # Unable to determine status


@dataclass
class CircuitHealthResponse:
    """Health check response for /health/circuits endpoint."""

    status: CircuitHealthStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_circuits: int = 0
    circuits_closed: int = 0
    circuits_open: int = 0
    circuits_half_open: int = 0
    flapping_circuits: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "total_circuits": self.total_circuits,
            "circuits_closed": self.circuits_closed,
            "circuits_open": self.circuits_open,
            "circuits_half_open": self.circuits_half_open,
            "flapping_circuits": self.flapping_circuits,
            "details": self.details,
        }


@dataclass
class CircuitDetail:
    """Detail for individual circuit in health response."""

    level: str
    identifier: str
    state: str
    failure_count: int
    opened_at: str | None
    minutes_open: int | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level,
            "identifier": self.identifier,
            "state": self.state,
            "failure_count": self.failure_count,
            "opened_at": self.opened_at,
            "minutes_open": self.minutes_open,
        }


async def get_circuit_health(db: OrchestratorDB) -> CircuitHealthResponse:
    """Get health status of all circuit breakers.

    Queries the circuit breaker views to determine overall system health.
    Returns a comprehensive health response suitable for monitoring endpoints.

    Args:
        db: OrchestratorDB instance with active connection.

    Returns:
        CircuitHealthResponse with current circuit breaker health.
    """
    try:
        await db._ensure_connected()
        if not db._conn:
            return CircuitHealthResponse(
                status=CircuitHealthStatus.UNKNOWN,
                details={"error": "Database not connected"},
            )

        # Get health summary by level from v_circuit_health_summary view
        summary_rows: list[dict[str, Any]] = []
        async with db._conn.execute("SELECT * FROM v_circuit_health_summary") as cursor:
            rows = await cursor.fetchall()
            summary_rows = [dict(row) for row in rows]

        total = 0
        closed = 0
        open_count = 0
        half_open = 0

        for row in summary_rows:
            total += row["total_circuits"]
            closed += row["closed_count"]
            open_count += row["open_count"]
            half_open += row["half_open_count"]

        # Get flapping count from v_flapping_circuits view
        async with db._conn.execute("SELECT COUNT(*) as count FROM v_flapping_circuits") as cursor:
            flapping_row = await cursor.fetchone()
            flapping_count = flapping_row["count"] if flapping_row else 0

        # Get open circuit details from v_open_circuits view
        open_circuits: list[dict[str, Any]] = []
        async with db._conn.execute("SELECT * FROM v_open_circuits") as cursor:
            rows = await cursor.fetchall()
            open_circuits = [dict(row) for row in rows]

        details: dict[str, Any] = {
            "by_level": {
                row["level"]: {
                    "total": row["total_circuits"],
                    "closed": row["closed_count"],
                    "open": row["open_count"],
                    "half_open": row["half_open_count"],
                }
                for row in summary_rows
            },
            "open_circuits": [
                CircuitDetail(
                    level=row["level"],
                    identifier=row["identifier"],
                    state=row["state"],
                    failure_count=row["failure_count"],
                    opened_at=row["opened_at"],
                    minutes_open=row["minutes_open"],
                ).to_dict()
                for row in open_circuits
            ],
        }

        # Determine overall status
        status = _calculate_health_status(
            open_count=open_count,
            half_open=half_open,
            flapping_count=flapping_count,
            open_circuits=open_circuits,
        )

        return CircuitHealthResponse(
            status=status,
            total_circuits=total,
            circuits_closed=closed,
            circuits_open=open_count,
            circuits_half_open=half_open,
            flapping_circuits=flapping_count,
            details=details,
        )

    except Exception as e:
        logger.error("Failed to get circuit health: %s", e)
        return CircuitHealthResponse(
            status=CircuitHealthStatus.UNKNOWN,
            details={"error": str(e)},
        )


def _calculate_health_status(
    open_count: int,
    half_open: int,
    flapping_count: int,
    open_circuits: list[dict[str, Any]],
) -> CircuitHealthStatus:
    """Calculate overall health status from circuit states.

    The health status hierarchy:
    - UNHEALTHY: System circuit open OR 3+ open circuits
    - DEGRADED: Any open/half-open circuits OR flapping detected
    - HEALTHY: All circuits closed, no flapping

    Args:
        open_count: Number of circuits in OPEN state.
        half_open: Number of circuits in HALF_OPEN state.
        flapping_count: Number of circuits detected as flapping.
        open_circuits: List of open circuit details (includes level info).

    Returns:
        CircuitHealthStatus indicating overall system health.
    """
    # Check for system circuit open (critical - immediate UNHEALTHY)
    for circuit in open_circuits:
        if circuit["level"] == "system":
            return CircuitHealthStatus.UNHEALTHY

    # Check for multiple open circuits (3+ indicates systemic issue)
    if open_count >= 3:
        return CircuitHealthStatus.UNHEALTHY

    # Check for any open, half-open, or flapping circuits
    if open_count > 0 or half_open > 0 or flapping_count > 0:
        return CircuitHealthStatus.DEGRADED

    return CircuitHealthStatus.HEALTHY
