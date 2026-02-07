"""System-level circuit breaker implementation.

Halts execution when widespread failures indicate a systemic issue
such as API outages, network problems, or rate limiting.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ..circuit_breaker_config import (
    CircuitBreakerConfig,
    CircuitLevel,
    CircuitState,
    DEFAULT_CONFIG,
)

if TYPE_CHECKING:
    from ..database import OrchestratorDB

logger = logging.getLogger(__name__)


class SystemCircuitBreaker:
    """Circuit breaker for system-level failure protection.

    Halts execution when widespread failures indicate a systemic issue
    such as API outages, network problems, or rate limiting.

    Unlike stage/worker circuits which protect individual components,
    system circuits protect the entire execution by monitoring the
    aggregate health of all workers.

    Usage:
        circuit = SystemCircuitBreaker(db, config=config)
        circuit.set_total_workers(4)
        await circuit.load_state()

        # Record worker failures as they occur
        await circuit.record_worker_failure(worker_id=2, reason="timeout")

        # Check if system should halt
        if await circuit.should_halt():
            # Stop accepting new tasks, wait for in-flight
            pass

    Attributes:
        db: Database connection for persistence.
        config: Circuit breaker configuration.
        state: Current circuit state.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize the system circuit breaker.

        Args:
            db: Database connection for state persistence.
            config: Configuration settings. Uses DEFAULT_CONFIG if None.
        """
        self._db = db
        self._identifier = "system"
        self._config = config or DEFAULT_CONFIG
        self._system_config = self._config.system

        # In-memory state
        self._state = CircuitState.CLOSED
        self._version = 1
        self._opened_at: datetime | None = None
        self._circuit_id: int | None = None

        # Worker tracking
        self._total_workers: int = 0
        self._failed_workers: set[int] = set()
        self._worker_failures: dict[int, list[datetime]] = {}  # worker_id -> failure times

        # In-flight task tracking
        self._in_flight_tasks: set[int] = set()

        # Snapshot captured when circuit opens
        self._trip_snapshot: dict[str, Any] | None = None

        # Concurrency protection
        self._lock = asyncio.Lock()

        # Run context
        self._run_id: int | None = None

    @property
    def identifier(self) -> str:
        """Return the circuit identifier."""
        return self._identifier

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if system circuit is open (execution halted)."""
        return self._state == CircuitState.OPEN

    @property
    def failed_worker_count(self) -> int:
        """Return count of currently failed workers."""
        return len(self._failed_workers)

    @property
    def failure_percentage(self) -> float:
        """Return current failure percentage."""
        if self._total_workers == 0:
            return 0.0
        return (len(self._failed_workers) / self._total_workers) * 100

    @property
    def trip_snapshot(self) -> dict[str, Any] | None:
        """Return snapshot captured when circuit tripped."""
        return self._trip_snapshot

    def set_run_id(self, run_id: int) -> None:
        """Associate circuit with an execution run."""
        self._run_id = run_id

    def set_total_workers(self, count: int) -> None:
        """Set the total number of workers in the pool."""
        self._total_workers = count

    def register_in_flight_task(self, task_id: int) -> None:
        """Register a task as in-flight (being processed)."""
        self._in_flight_tasks.add(task_id)

    def complete_in_flight_task(self, task_id: int) -> None:
        """Mark an in-flight task as complete."""
        self._in_flight_tasks.discard(task_id)

    @property
    def in_flight_count(self) -> int:
        """Return count of in-flight tasks."""
        return len(self._in_flight_tasks)

    async def load_state(self) -> None:
        """Load circuit state from database."""
        async with self._lock:
            await self._load_state_internal()

    async def _load_state_internal(self) -> None:
        """Internal state loading without lock."""
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        async with self._db._conn.execute(
            """
            SELECT id, state, version, opened_at, config_snapshot
            FROM circuit_breakers
            WHERE level = ? AND identifier = ?
            """,
            (CircuitLevel.SYSTEM.value, self._identifier),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            self._circuit_id = row["id"]
            self._state = CircuitState(row["state"])
            self._version = row["version"]
            self._opened_at = datetime.fromisoformat(row["opened_at"]) if row["opened_at"] else None
            # Restore snapshot if available
            if row["config_snapshot"]:
                try:
                    snapshot_data = json.loads(row["config_snapshot"])
                    if "trip_snapshot" in snapshot_data:
                        self._trip_snapshot = snapshot_data["trip_snapshot"]
                except json.JSONDecodeError:
                    pass

            logger.debug(
                "Loaded system circuit: state=%s",
                self._state.value,
            )
        else:
            await self._create_circuit()

    async def _create_circuit(self) -> None:
        """Create a new system circuit breaker record."""
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        config_snapshot = json.dumps(
            {
                "failure_threshold_percent": self._system_config.failure_threshold_percent,
                "monitoring_window_seconds": self._system_config.monitoring_window_seconds,
                "auto_recovery_enabled": self._system_config.auto_recovery_enabled,
                "recovery_delay_seconds": self._system_config.recovery_delay_seconds,
                "min_workers_for_threshold": self._system_config.min_workers_for_threshold,
            }
        )

        cursor = await self._db._conn.execute(
            """
            INSERT INTO circuit_breakers (level, identifier, run_id, config_snapshot)
            VALUES (?, ?, ?, ?)
            """,
            (CircuitLevel.SYSTEM.value, self._identifier, self._run_id, config_snapshot),
        )
        await self._db._conn.commit()
        self._circuit_id = cursor.lastrowid
        logger.info("Created system circuit breaker (id=%d)", self._circuit_id)

    async def should_halt(self) -> bool:
        """Check if system should halt execution.

        Returns:
            True if execution should stop, False if can continue.
        """
        async with self._lock:
            await self._load_state_internal()

            if self._state == CircuitState.CLOSED:
                return False

            if self._state == CircuitState.OPEN:
                # Check for auto-recovery
                if self._should_attempt_recovery():
                    await self._transition_to_half_open()
                    return False  # Allow testing
                return True

            if self._state == CircuitState.HALF_OPEN:
                # In testing mode - allow execution
                return False

            return False

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed for recovery attempt."""
        if not self._system_config.auto_recovery_enabled:
            return False

        if not self._opened_at:
            return True

        elapsed = datetime.now() - self._opened_at
        return elapsed.total_seconds() >= self._system_config.recovery_delay_seconds

    def get_time_until_recovery(self) -> float:
        """Get seconds until system can attempt recovery."""
        if self._state != CircuitState.OPEN or not self._opened_at:
            return 0.0

        if not self._system_config.auto_recovery_enabled:
            return float("inf")

        elapsed = datetime.now() - self._opened_at
        remaining = self._system_config.recovery_delay_seconds - elapsed.total_seconds()
        return max(0.0, remaining)

    async def record_worker_failure(
        self,
        worker_id: int,
        reason: str,
        error_context: dict[str, Any] | None = None,
    ) -> bool:
        """Record a worker failure and check if system should trip.

        Args:
            worker_id: ID of the failed worker.
            reason: Human-readable failure reason.
            error_context: Additional context.

        Returns:
            True if system circuit tripped, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            now = datetime.now()

            # Track failure in sliding window
            if worker_id not in self._worker_failures:
                self._worker_failures[worker_id] = []
            self._worker_failures[worker_id].append(now)

            # Clean up old failures outside monitoring window
            window_start = now - timedelta(seconds=self._system_config.monitoring_window_seconds)
            self._worker_failures[worker_id] = [
                t for t in self._worker_failures[worker_id] if t >= window_start
            ]

            # Mark worker as failed if it has recent failures
            if self._worker_failures[worker_id]:
                self._failed_workers.add(worker_id)

            await self._record_event(
                event_type="failure_recorded",
                error_context={
                    "worker_id": worker_id,
                    "reason": reason,
                    "failed_workers": list(self._failed_workers),
                    "failure_percentage": self.failure_percentage,
                    **(error_context or {}),
                },
            )

            logger.warning(
                "System: worker %d failed - %d/%d workers failing (%.1f%%)",
                worker_id,
                len(self._failed_workers),
                self._total_workers,
                self.failure_percentage,
            )

            # Check if threshold reached
            tripped = False
            if self._state == CircuitState.CLOSED:
                if self._should_trip():
                    await self._transition_to_open(reason)
                    tripped = True

            elif self._state == CircuitState.HALF_OPEN:
                # Failure during recovery test - back to open
                await self._transition_to_open(reason, from_half_open=True)
                tripped = True

            await self._update_state()
            return tripped

    def _should_trip(self) -> bool:
        """Check if system should trip based on current failures."""
        # Don't trip if below minimum worker threshold
        if self._total_workers < self._system_config.min_workers_for_threshold:
            return False

        # Check failure percentage
        return self.failure_percentage >= self._system_config.failure_threshold_percent

    async def record_worker_success(self, worker_id: int) -> bool:
        """Record a worker success, potentially closing circuit.

        Args:
            worker_id: ID of the successful worker.

        Returns:
            True if circuit closed, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            # Clear worker from failed set
            self._failed_workers.discard(worker_id)

            # Clear failure history for this worker
            if worker_id in self._worker_failures:
                del self._worker_failures[worker_id]

            await self._record_event(
                event_type="success_recorded",
                error_context={
                    "worker_id": worker_id,
                    "failed_workers": list(self._failed_workers),
                    "failure_percentage": self.failure_percentage,
                },
            )

            closed = False
            if self._state == CircuitState.HALF_OPEN:
                # Success during recovery - close if enough workers healthy
                if self.failure_percentage < self._system_config.failure_threshold_percent:
                    await self._transition_to_closed()
                    closed = True

            await self._update_state()
            return closed

    async def reset(self) -> None:
        """Manually reset system circuit to closed state."""
        async with self._lock:
            await self._load_state_internal()

            if self._state != CircuitState.CLOSED:
                await self._record_event(
                    event_type="manual_reset",
                    from_state=self._state.value,
                    to_state=CircuitState.CLOSED.value,
                )

                self._state = CircuitState.CLOSED
                self._failed_workers.clear()
                self._worker_failures.clear()
                self._trip_snapshot = None
                self._opened_at = None

                await self._update_state()

                logger.info("System circuit manually reset to CLOSED")

    async def wait_for_in_flight(self, timeout: float | None = None) -> bool:
        """Wait for in-flight tasks to complete (graceful shutdown).

        Args:
            timeout: Maximum seconds to wait. Uses config default if None.

        Returns:
            True if all tasks completed, False if timeout.
        """
        effective_timeout: float = (
            float(self._system_config.graceful_shutdown_timeout) if timeout is None else timeout
        )

        start = datetime.now()
        while self._in_flight_tasks:
            elapsed = (datetime.now() - start).total_seconds()
            if elapsed >= effective_timeout:
                logger.warning(
                    "Graceful shutdown timeout: %d tasks still in-flight",
                    len(self._in_flight_tasks),
                )
                return False
            await asyncio.sleep(0.5)

        logger.info("Graceful shutdown complete: all in-flight tasks finished")
        return True

    async def _transition_to_open(
        self,
        reason: str,
        from_half_open: bool = False,
    ) -> None:
        """Transition to OPEN state (halt execution)."""
        from_state = self._state.value
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now()

        # Capture snapshot for debugging
        self._trip_snapshot = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "total_workers": self._total_workers,
            "failed_workers": list(self._failed_workers),
            "failure_percentage": self.failure_percentage,
            "in_flight_tasks": list(self._in_flight_tasks),
        }

        event_type = "recovery_failed" if from_half_open else "threshold_reached"
        await self._record_event(
            event_type=event_type,
            from_state=from_state,
            to_state=CircuitState.OPEN.value,
            error_context=self._trip_snapshot,
        )

        logger.error(
            "SYSTEM CIRCUIT OPENED: %s (%.1f%% workers failing)",
            reason,
            self.failure_percentage,
        )

    async def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN for recovery testing."""
        from_state = self._state.value
        self._state = CircuitState.HALF_OPEN

        await self._record_event(
            event_type="recovery_started",
            from_state=from_state,
            to_state=CircuitState.HALF_OPEN.value,
        )

        logger.info("System circuit entering HALF_OPEN for recovery test")

    async def _transition_to_closed(self) -> None:
        """Transition to CLOSED after successful recovery."""
        from_state = self._state.value
        self._state = CircuitState.CLOSED
        self._trip_snapshot = None
        self._opened_at = None

        await self._record_event(
            event_type="recovery_succeeded",
            from_state=from_state,
            to_state=CircuitState.CLOSED.value,
        )

        logger.info("System circuit CLOSED after successful recovery")

    async def _update_state(self) -> None:
        """Persist state to database."""
        if self._circuit_id is None:
            return

        await self._db._ensure_connected()
        if not self._db._conn:
            return

        # Store snapshot in config_snapshot field
        config_with_snapshot = {
            "failure_threshold_percent": self._system_config.failure_threshold_percent,
            "monitoring_window_seconds": self._system_config.monitoring_window_seconds,
            "trip_snapshot": self._trip_snapshot,
        }

        new_version = self._version + 1
        cursor = await self._db._conn.execute(
            """
            UPDATE circuit_breakers
            SET state = ?,
                version = ?,
                opened_at = ?,
                config_snapshot = ?,
                last_state_change_at = datetime('now')
            WHERE id = ? AND version = ?
            """,
            (
                self._state.value,
                new_version,
                self._opened_at.isoformat() if self._opened_at else None,
                json.dumps(config_with_snapshot),
                self._circuit_id,
                self._version,
            ),
        )
        await self._db._conn.commit()

        if cursor.rowcount == 0:
            logger.warning("System circuit optimistic lock failed, reloading")
            await self._load_state_internal()
        else:
            self._version = new_version

    async def _record_event(
        self,
        event_type: str,
        from_state: str | None = None,
        to_state: str | None = None,
        error_context: dict[str, Any] | None = None,
    ) -> None:
        """Record a circuit breaker event."""
        if self._circuit_id is None:
            return

        await self._db._ensure_connected()
        if not self._db._conn:
            return

        await self._db._conn.execute(
            """
            INSERT INTO circuit_breaker_events
            (circuit_id, run_id, event_type, from_state, to_state, error_context)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self._circuit_id,
                self._run_id,
                event_type,
                from_state,
                to_state,
                json.dumps(error_context) if error_context else None,
            ),
        )
        await self._db._conn.commit()
