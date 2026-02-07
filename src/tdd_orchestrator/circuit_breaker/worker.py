"""Worker-level circuit breaker implementation.

Pauses workers that fail consecutive tasks, preventing them
from consuming resources on operations that will likely fail.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
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


class WorkerCircuitBreaker:
    """Circuit breaker for worker-level failure protection.

    Pauses workers that fail consecutive tasks, preventing them
    from consuming resources on operations that will likely fail.

    Unlike stage circuits which track failures within a task,
    worker circuits track failures across multiple tasks.

    Usage:
        circuit = WorkerCircuitBreaker(db, worker_id=5, config=config)
        await circuit.load_state()

        if await circuit.check_and_allow():
            try:
                # Process task
                await circuit.record_success()
            except Exception as e:
                await circuit.record_failure(str(e))

    Attributes:
        db: Database connection for persistence.
        worker_id: ID of the worker this circuit protects.
        config: Circuit breaker configuration.
        state: Current circuit state.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        worker_id: int,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize the worker circuit breaker.

        Args:
            db: Database connection for state persistence.
            worker_id: ID of the worker to protect.
            config: Configuration settings. Uses DEFAULT_CONFIG if None.
        """
        self._db = db
        self._worker_id = worker_id
        self._identifier = f"worker_{worker_id}"
        self._config = config or DEFAULT_CONFIG
        self._worker_config = self._config.worker

        # In-memory state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_requests = 0
        self._extensions_count = 0
        self._version = 1
        self._opened_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._circuit_id: int | None = None

        # Concurrency protection
        self._lock = asyncio.Lock()

        # Run context
        self._run_id: int | None = None

    @property
    def worker_id(self) -> int:
        """Return the worker ID."""
        return self._worker_id

    @property
    def identifier(self) -> str:
        """Return the circuit identifier."""
        return self._identifier

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Return the current failure count."""
        return self._failure_count

    @property
    def extensions_count(self) -> int:
        """Return how many times the pause has been extended."""
        return self._extensions_count

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (worker paused)."""
        return self._state == CircuitState.OPEN

    @property
    def is_permanently_open(self) -> bool:
        """Check if circuit is permanently open (max extensions reached)."""
        return (
            self._state == CircuitState.OPEN
            and self._extensions_count >= self._worker_config.max_extensions
        )

    def set_run_id(self, run_id: int) -> None:
        """Associate circuit with an execution run."""
        self._run_id = run_id

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
            SELECT id, state, version, failure_count, success_count,
                   half_open_requests, extensions_count, opened_at,
                   last_failure_at, last_success_at
            FROM circuit_breakers
            WHERE level = ? AND identifier = ?
            """,
            (CircuitLevel.WORKER.value, self._identifier),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            self._circuit_id = row["id"]
            self._state = CircuitState(row["state"])
            self._version = row["version"]
            self._failure_count = row["failure_count"]
            self._success_count = row["success_count"]
            self._half_open_requests = row["half_open_requests"]
            self._extensions_count = row["extensions_count"]
            self._opened_at = datetime.fromisoformat(row["opened_at"]) if row["opened_at"] else None
            self._last_failure_at = (
                datetime.fromisoformat(row["last_failure_at"]) if row["last_failure_at"] else None
            )
            self._last_success_at = (
                datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None
            )
            logger.debug(
                "Loaded worker circuit %s: state=%s, failures=%d, extensions=%d",
                self._identifier,
                self._state.value,
                self._failure_count,
                self._extensions_count,
            )
        else:
            await self._create_circuit()

    async def _create_circuit(self) -> None:
        """Create a new worker circuit breaker record."""
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        config_snapshot = json.dumps(
            {
                "max_consecutive_failures": self._worker_config.max_consecutive_failures,
                "pause_duration_seconds": self._worker_config.pause_duration_seconds,
                "half_open_max_requests": self._worker_config.half_open_max_requests,
                "max_extensions": self._worker_config.max_extensions,
            }
        )

        cursor = await self._db._conn.execute(
            """
            INSERT INTO circuit_breakers (level, identifier, run_id, config_snapshot)
            VALUES (?, ?, ?, ?)
            """,
            (
                CircuitLevel.WORKER.value,
                self._identifier,
                self._run_id,
                config_snapshot,
            ),
        )
        await self._db._conn.commit()
        self._circuit_id = cursor.lastrowid
        logger.info(
            "Created worker circuit breaker: %s (id=%d)",
            self._identifier,
            self._circuit_id,
        )

    async def check_and_allow(self) -> bool:
        """Check if worker is allowed to process a task.

        Returns:
            True if worker can proceed, False if paused.
        """
        async with self._lock:
            await self._load_state_internal()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check for permanent open (max extensions reached)
                if self.is_permanently_open:
                    logger.warning(
                        "Worker %d permanently paused (max extensions reached)",
                        self._worker_id,
                    )
                    return False

                # Check if pause duration has elapsed
                if self._should_attempt_recovery():
                    await self._transition_to_half_open()
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                # Enforce strict half-open request limit
                if self._half_open_requests < self._worker_config.half_open_max_requests:
                    self._half_open_requests += 1
                    await self._update_state()
                    logger.info(
                        "Worker %d half-open test %d/%d",
                        self._worker_id,
                        self._half_open_requests,
                        self._worker_config.half_open_max_requests,
                    )
                    return True
                logger.debug(
                    "Worker %d half-open request limit reached",
                    self._worker_id,
                )
                return False

            return False

    def _should_attempt_recovery(self) -> bool:
        """Check if pause duration has elapsed."""
        if not self._opened_at:
            return True

        elapsed = datetime.now() - self._opened_at
        return elapsed.total_seconds() >= self._worker_config.pause_duration_seconds

    def get_time_until_retry(self) -> float:
        """Get seconds until worker can attempt recovery."""
        if self._state != CircuitState.OPEN or not self._opened_at:
            return 0.0

        elapsed = datetime.now() - self._opened_at
        remaining = self._worker_config.pause_duration_seconds - elapsed.total_seconds()
        return max(0.0, remaining)

    async def record_failure(
        self,
        reason: str,
        task_key: str | None = None,
        error_context: dict[str, Any] | None = None,
    ) -> bool:
        """Record a task failure for this worker.

        Args:
            reason: Human-readable failure reason.
            task_key: Key of the failed task (for context).
            error_context: Additional context.

        Returns:
            True if circuit opened or extended, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            now = datetime.now()
            self._failure_count += 1
            self._last_failure_at = now

            context = error_context or {}
            if task_key:
                context["task_key"] = task_key
            context["reason"] = reason

            await self._record_event(
                event_type="failure_recorded",
                error_context=context,
            )

            logger.warning(
                "Worker %d failure %d/%d: %s",
                self._worker_id,
                self._failure_count,
                self._worker_config.max_consecutive_failures,
                reason,
            )

            state_changed = False

            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self._worker_config.max_consecutive_failures:
                    await self._transition_to_open(reason)
                    state_changed = True

            elif self._state == CircuitState.HALF_OPEN:
                # Failure in half-open: extend pause
                await self._extend_pause(reason)
                state_changed = True

            await self._update_state()
            return state_changed

    async def record_success(self, task_key: str | None = None) -> bool:
        """Record a successful task completion.

        Args:
            task_key: Key of the successful task (for context).

        Returns:
            True if circuit closed, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            now = datetime.now()
            self._success_count += 1
            self._last_success_at = now

            await self._record_event(
                event_type="success_recorded",
                error_context={"task_key": task_key} if task_key else None,
            )

            state_changed = False

            if self._state == CircuitState.HALF_OPEN:
                # Success in half-open: close circuit
                if self._success_count >= self._worker_config.success_threshold:
                    await self._transition_to_closed()
                    state_changed = True
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success (consecutive mode)
                self._failure_count = 0

            await self._update_state()

            logger.debug(
                "Worker %d success: state=%s, failures_reset=%s",
                self._worker_id,
                self._state.value,
                state_changed or self._state == CircuitState.CLOSED,
            )
            return state_changed

    async def reset(self) -> None:
        """Manually reset worker circuit to closed state."""
        async with self._lock:
            await self._load_state_internal()

            if self._state != CircuitState.CLOSED:
                await self._record_event(
                    event_type="manual_reset",
                    from_state=self._state.value,
                    to_state=CircuitState.CLOSED.value,
                )

                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._half_open_requests = 0
                self._extensions_count = 0
                self._opened_at = None

                await self._update_state()

                logger.info(
                    "Worker %d circuit manually reset to CLOSED",
                    self._worker_id,
                )

    async def _transition_to_open(self, reason: str) -> None:
        """Transition circuit to OPEN state (pause worker)."""
        from_state = self._state.value
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now()
        self._half_open_requests = 0

        await self._record_event(
            event_type="threshold_reached",
            from_state=from_state,
            to_state=CircuitState.OPEN.value,
            error_context={"reason": reason},
        )

        logger.warning(
            "Worker %d PAUSED: %s (failures=%d, pause=%ds)",
            self._worker_id,
            reason,
            self._failure_count,
            self._worker_config.pause_duration_seconds,
        )

    async def _extend_pause(self, reason: str) -> None:
        """Extend pause duration after half-open failure."""
        self._extensions_count += 1
        self._opened_at = datetime.now()  # Reset timer
        self._half_open_requests = 0
        self._state = CircuitState.OPEN

        await self._record_event(
            event_type="extension_applied",
            from_state=CircuitState.HALF_OPEN.value,
            to_state=CircuitState.OPEN.value,
            error_context={
                "reason": reason,
                "extensions": self._extensions_count,
                "max_extensions": self._worker_config.max_extensions,
            },
        )

        if self.is_permanently_open:
            logger.error(
                "Worker %d PERMANENTLY PAUSED: max extensions reached (%d/%d)",
                self._worker_id,
                self._extensions_count,
                self._worker_config.max_extensions,
            )
        else:
            logger.warning(
                "Worker %d pause EXTENDED: %s (extension %d/%d)",
                self._worker_id,
                reason,
                self._extensions_count,
                self._worker_config.max_extensions,
            )

    async def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN for recovery testing."""
        from_state = self._state.value
        self._state = CircuitState.HALF_OPEN
        self._half_open_requests = 0
        self._success_count = 0  # Reset for threshold counting

        await self._record_event(
            event_type="recovery_started",
            from_state=from_state,
            to_state=CircuitState.HALF_OPEN.value,
        )

        logger.info(
            "Worker %d entering HALF_OPEN for recovery test",
            self._worker_id,
        )

    async def _transition_to_closed(self) -> None:
        """Transition to CLOSED after successful recovery."""
        from_state = self._state.value
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_requests = 0
        self._extensions_count = 0  # Reset extensions on successful recovery
        self._opened_at = None

        await self._record_event(
            event_type="recovery_succeeded",
            from_state=from_state,
            to_state=CircuitState.CLOSED.value,
        )

        logger.info(
            "Worker %d RESUMED after successful recovery",
            self._worker_id,
        )

    async def _update_state(self) -> None:
        """Persist state to database with optimistic locking."""
        if self._circuit_id is None:
            return

        await self._db._ensure_connected()
        if not self._db._conn:
            return

        new_version = self._version + 1
        cursor = await self._db._conn.execute(
            """
            UPDATE circuit_breakers
            SET state = ?,
                version = ?,
                failure_count = ?,
                success_count = ?,
                half_open_requests = ?,
                extensions_count = ?,
                opened_at = ?,
                last_failure_at = ?,
                last_success_at = ?,
                last_state_change_at = datetime('now')
            WHERE id = ? AND version = ?
            """,
            (
                self._state.value,
                new_version,
                self._failure_count,
                self._success_count,
                self._half_open_requests,
                self._extensions_count,
                self._opened_at.isoformat() if self._opened_at else None,
                self._last_failure_at.isoformat() if self._last_failure_at else None,
                self._last_success_at.isoformat() if self._last_success_at else None,
                self._circuit_id,
                self._version,
            ),
        )
        await self._db._conn.commit()

        if cursor.rowcount == 0:
            logger.warning(
                "Worker circuit %s optimistic lock failed, reloading",
                self._identifier,
            )
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
