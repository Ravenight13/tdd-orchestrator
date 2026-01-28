"""Circuit breaker implementation for TDD orchestrator.

Implements the circuit breaker pattern at stage level to prevent
infinite retries when stages fail repeatedly.

The circuit breaker has three states:
- CLOSED: Normal operation, failures are counted
- OPEN: Circuit tripped, requests immediately fail
- HALF_OPEN: Testing recovery, limited requests allowed
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from .circuit_breaker_config import (
    CircuitBreakerConfig,
    CircuitLevel,
    CircuitState,
    DEFAULT_CONFIG,
)

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""

    pass


class CircuitOpenError(CircuitBreakerError):
    """Raised when circuit is open and request is blocked."""

    def __init__(self, identifier: str, time_until_retry: float) -> None:
        self.identifier = identifier
        self.time_until_retry = time_until_retry
        super().__init__(f"Circuit {identifier} is open. Retry in {time_until_retry:.1f}s")


class StageCircuitBreaker:
    """Circuit breaker for stage-level failure protection.

    Prevents a single stage from consuming unlimited retries by
    tracking consecutive failures and opening the circuit when
    a threshold is reached.

    Usage:
        circuit = StageCircuitBreaker(db, "task_123:GREEN", config)
        await circuit.load_state()  # Load from database

        if await circuit.check_and_allow():
            try:
                # Execute stage
                await circuit.record_success()
            except Exception as e:
                await circuit.record_failure(str(e))

    Attributes:
        db: Database connection for persistence.
        identifier: Unique identifier (task_id:stage).
        config: Circuit breaker configuration.
        state: Current circuit state.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        identifier: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            db: Database connection for state persistence.
            identifier: Unique identifier for this circuit (task_id:stage).
            config: Configuration settings. Uses DEFAULT_CONFIG if None.
        """
        self._db = db
        self._identifier = identifier
        self._config = config or DEFAULT_CONFIG
        self._stage_config = self._config.stage

        # In-memory state (synced with database)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_requests = 0
        self._version = 1
        self._opened_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._circuit_id: int | None = None

        # Concurrency protection
        self._lock = asyncio.Lock()

        # Run context (set when associated with a run)
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
    def failure_count(self) -> int:
        """Return the current failure count."""
        return self._failure_count

    @property
    def is_open(self) -> bool:
        """Check if circuit is currently open (blocking requests)."""
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is currently closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    def set_run_id(self, run_id: int) -> None:
        """Associate circuit with an execution run for tracking."""
        self._run_id = run_id

    async def load_state(self) -> None:
        """Load circuit state from database.

        Creates a new circuit record if one doesn't exist.
        """
        async with self._lock:
            await self._load_state_internal()

    async def _load_state_internal(self) -> None:
        """Internal state loading without lock (called within locked context)."""
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        async with self._db._conn.execute(
            """
            SELECT id, state, version, failure_count, success_count,
                   half_open_requests, opened_at, last_failure_at, last_success_at
            FROM circuit_breakers
            WHERE level = ? AND identifier = ?
            """,
            (CircuitLevel.STAGE.value, self._identifier),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            self._circuit_id = row["id"]
            self._state = CircuitState(row["state"])
            self._version = row["version"]
            self._failure_count = row["failure_count"]
            self._success_count = row["success_count"]
            self._half_open_requests = row["half_open_requests"]
            self._opened_at = datetime.fromisoformat(row["opened_at"]) if row["opened_at"] else None
            self._last_failure_at = (
                datetime.fromisoformat(row["last_failure_at"]) if row["last_failure_at"] else None
            )
            self._last_success_at = (
                datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None
            )
            logger.debug(
                "Loaded circuit %s: state=%s, failures=%d",
                self._identifier,
                self._state.value,
                self._failure_count,
            )
        else:
            # Create new circuit record
            await self._create_circuit()

    async def _create_circuit(self) -> None:
        """Create a new circuit breaker record in the database."""
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        config_snapshot = json.dumps(
            {
                "max_failures": self._stage_config.max_failures,
                "recovery_timeout_seconds": self._stage_config.recovery_timeout_seconds,
                "skip_to_next_task": self._stage_config.skip_to_next_task,
            }
        )

        cursor = await self._db._conn.execute(
            """
            INSERT INTO circuit_breakers (level, identifier, run_id, config_snapshot)
            VALUES (?, ?, ?, ?)
            """,
            (
                CircuitLevel.STAGE.value,
                self._identifier,
                self._run_id,
                config_snapshot,
            ),
        )
        await self._db._conn.commit()
        self._circuit_id = cursor.lastrowid
        logger.info("Created circuit breaker: %s (id=%d)", self._identifier, self._circuit_id)

    async def check_and_allow(self) -> bool:
        """Check if a request should be allowed through the circuit.

        This is the main entry point for checking circuit state before
        executing an operation.

        Returns:
            True if the request is allowed, False if blocked.

        Raises:
            CircuitOpenError: If circuit is open (optional, based on usage).
        """
        async with self._lock:
            # Reload state to get latest from database (multi-worker scenario)
            await self._load_state_internal()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if enough time has passed to try half-open
                if self._should_attempt_recovery():
                    await self._transition_to_half_open()
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                # Allow limited requests in half-open state
                if self._half_open_requests < 1:  # Only 1 test request
                    self._half_open_requests += 1
                    await self._update_state()
                    return True
                return False

            return False

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self._opened_at:
            return True

        elapsed = datetime.now() - self._opened_at
        return elapsed.total_seconds() >= self._stage_config.recovery_timeout_seconds

    def get_time_until_retry(self) -> float:
        """Get seconds until circuit can attempt recovery."""
        if self._state != CircuitState.OPEN or not self._opened_at:
            return 0.0

        elapsed = datetime.now() - self._opened_at
        remaining = self._stage_config.recovery_timeout_seconds - elapsed.total_seconds()
        return max(0.0, remaining)

    async def record_failure(
        self,
        reason: str,
        error_context: dict[str, Any] | None = None,
    ) -> bool:
        """Record a failure and potentially open the circuit.

        Args:
            reason: Human-readable failure reason.
            error_context: Additional context (stack trace, error codes, etc.)

        Returns:
            True if circuit transitioned to OPEN state, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            now = datetime.now()
            self._failure_count += 1
            self._last_failure_at = now

            # Record the event
            await self._record_event(
                event_type="failure_recorded",
                error_context=error_context or {"reason": reason},
            )

            logger.warning(
                "Circuit %s failure %d/%d: %s",
                self._identifier,
                self._failure_count,
                self._stage_config.max_failures,
                reason,
            )

            # Check if we should open the circuit
            should_open = False
            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self._stage_config.max_failures:
                    should_open = True
                    await self._transition_to_open(reason)

            elif self._state == CircuitState.HALF_OPEN:
                # Failure in half-open means back to open
                await self._transition_to_open(reason, from_half_open=True)
                should_open = True

            await self._update_state()
            return should_open

    async def record_success(self) -> bool:
        """Record a success and potentially close the circuit.

        Returns:
            True if circuit transitioned to CLOSED state, False otherwise.
        """
        async with self._lock:
            await self._load_state_internal()

            now = datetime.now()
            self._success_count += 1
            self._last_success_at = now

            # Record the event
            await self._record_event(event_type="success_recorded")

            should_close = False
            if self._state == CircuitState.HALF_OPEN:
                # Success in half-open closes the circuit
                await self._transition_to_closed()
                should_close = True
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success (consecutive mode)
                if self._config.failure_mode == "consecutive":
                    self._failure_count = 0

            await self._update_state()

            logger.debug(
                "Circuit %s success: state=%s, failures_reset=%s",
                self._identifier,
                self._state.value,
                should_close or self._config.failure_mode == "consecutive",
            )
            return should_close

    async def reset(self) -> None:
        """Manually reset the circuit to closed state.

        This is typically used for administrative intervention.
        """
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
                self._opened_at = None

                await self._update_state()

                logger.info("Circuit %s manually reset to CLOSED", self._identifier)

    async def _transition_to_open(
        self,
        reason: str,
        from_half_open: bool = False,
    ) -> None:
        """Transition circuit to OPEN state."""
        from_state = self._state.value
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now()
        self._half_open_requests = 0

        event_type = "recovery_failed" if from_half_open else "threshold_reached"
        await self._record_event(
            event_type=event_type,
            from_state=from_state,
            to_state=CircuitState.OPEN.value,
            error_context={"reason": reason},
        )

        logger.warning(
            "Circuit %s OPENED: %s (failures=%d)",
            self._identifier,
            reason,
            self._failure_count,
        )

    async def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state for recovery testing."""
        from_state = self._state.value
        self._state = CircuitState.HALF_OPEN
        self._half_open_requests = 0

        await self._record_event(
            event_type="recovery_started",
            from_state=from_state,
            to_state=CircuitState.HALF_OPEN.value,
        )

        logger.info("Circuit %s entering HALF_OPEN for recovery test", self._identifier)

    async def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state after successful recovery."""
        from_state = self._state.value
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_requests = 0
        self._opened_at = None

        await self._record_event(
            event_type="recovery_succeeded",
            from_state=from_state,
            to_state=CircuitState.CLOSED.value,
        )

        logger.info("Circuit %s CLOSED after successful recovery", self._identifier)

    async def _update_state(self) -> None:
        """Persist current state to database with optimistic locking."""
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
                self._opened_at.isoformat() if self._opened_at else None,
                self._last_failure_at.isoformat() if self._last_failure_at else None,
                self._last_success_at.isoformat() if self._last_success_at else None,
                self._circuit_id,
                self._version,
            ),
        )
        await self._db._conn.commit()

        if cursor.rowcount == 0:
            # Optimistic lock failure - reload and retry
            logger.warning(
                "Circuit %s optimistic lock failed, reloading state",
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
        """Record a circuit breaker event for audit trail."""
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


class CircuitBreakerRegistry:
    """Central registry for all circuit breakers.

    Provides factory methods to get or create circuit breakers at all
    levels, with caching to avoid recreating circuits and cleanup
    methods to prevent memory leaks.

    Usage:
        registry = CircuitBreakerRegistry(db, config)

        # Get circuits
        stage_circuit = await registry.get_stage_circuit(task_id=123, stage="green")
        worker_circuit = await registry.get_worker_circuit(worker_id=1)
        system_circuit = await registry.get_system_circuit(total_workers=4)

        # Cleanup when tasks complete
        await registry.cleanup_completed_tasks([123, 124, 125])

    Attributes:
        db: Database connection for persistence.
        config: Circuit breaker configuration.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize the circuit breaker registry.

        Args:
            db: Database connection for state persistence.
            config: Configuration settings. Uses DEFAULT_CONFIG if None.
        """
        self._db = db
        self._config = config or DEFAULT_CONFIG

        # Circuit caches
        self._stage_circuits: dict[str, StageCircuitBreaker] = {}
        self._worker_circuits: dict[int, WorkerCircuitBreaker] = {}
        self._system_circuit: SystemCircuitBreaker | None = None

        # Concurrency protection
        self._lock = asyncio.Lock()

        # Run context
        self._run_id: int | None = None

        # LRU tracking for stage circuits (bounded to prevent memory issues)
        self._stage_circuit_access_order: list[str] = []
        self._max_stage_circuits: int = 1000

    def set_run_id(self, run_id: int) -> None:
        """Associate all circuits with an execution run."""
        self._run_id = run_id

    async def get_stage_circuit(
        self,
        task_id: int,
        stage: str,
    ) -> StageCircuitBreaker:
        """Get or create a stage-level circuit breaker.

        Args:
            task_id: ID of the task.
            stage: Stage name (e.g., "green", "verify").

        Returns:
            StageCircuitBreaker for this task/stage.
        """
        key = f"{task_id}:{stage}"

        async with self._lock:
            if key not in self._stage_circuits:
                # Check if we need to evict old circuits (LRU)
                await self._maybe_evict_stage_circuits()

                circuit = StageCircuitBreaker(self._db, key, self._config)
                if self._run_id:
                    circuit.set_run_id(self._run_id)
                await circuit.load_state()
                self._stage_circuits[key] = circuit

            # Update access order for LRU
            if key in self._stage_circuit_access_order:
                self._stage_circuit_access_order.remove(key)
            self._stage_circuit_access_order.append(key)

            return self._stage_circuits[key]

    async def get_worker_circuit(self, worker_id: int) -> WorkerCircuitBreaker:
        """Get or create a worker-level circuit breaker.

        Args:
            worker_id: ID of the worker.

        Returns:
            WorkerCircuitBreaker for this worker.
        """
        async with self._lock:
            if worker_id not in self._worker_circuits:
                circuit = WorkerCircuitBreaker(self._db, worker_id, self._config)
                if self._run_id:
                    circuit.set_run_id(self._run_id)
                await circuit.load_state()
                self._worker_circuits[worker_id] = circuit

            return self._worker_circuits[worker_id]

    async def get_system_circuit(self, total_workers: int) -> SystemCircuitBreaker:
        """Get or create the system-level circuit breaker.

        Args:
            total_workers: Total number of workers in the pool.

        Returns:
            SystemCircuitBreaker for system-wide monitoring.
        """
        async with self._lock:
            if self._system_circuit is None:
                circuit = SystemCircuitBreaker(self._db, self._config)
                if self._run_id:
                    circuit.set_run_id(self._run_id)
                await circuit.load_state()
                self._system_circuit = circuit

            # Always update total workers (may change between phases)
            self._system_circuit.set_total_workers(total_workers)
            return self._system_circuit

    async def cleanup_completed_tasks(self, task_ids: list[int]) -> int:
        """Remove stage circuits for completed tasks.

        This prevents memory leaks when tasks complete. Call this
        periodically or after a batch of tasks finishes.

        Args:
            task_ids: List of completed task IDs.

        Returns:
            Number of circuits removed.
        """
        async with self._lock:
            removed = 0
            for task_id in task_ids:
                # Find and remove all stage circuits for this task
                prefix = f"{task_id}:"
                keys_to_remove = [k for k in self._stage_circuits if k.startswith(prefix)]
                for key in keys_to_remove:
                    del self._stage_circuits[key]
                    if key in self._stage_circuit_access_order:
                        self._stage_circuit_access_order.remove(key)
                    removed += 1

            if removed > 0:
                logger.debug("Cleaned up %d stage circuits for %d tasks", removed, len(task_ids))

            return removed

    async def get_all_open_circuits(
        self,
    ) -> list[StageCircuitBreaker | WorkerCircuitBreaker | SystemCircuitBreaker]:
        """Get all circuits currently in OPEN or HALF_OPEN state.

        Useful for monitoring and health checks.

        Returns:
            List of open circuits across all levels.
        """
        async with self._lock:
            open_circuits: list[
                StageCircuitBreaker | WorkerCircuitBreaker | SystemCircuitBreaker
            ] = []

            for stage_circuit in self._stage_circuits.values():
                if stage_circuit.state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                    open_circuits.append(stage_circuit)

            for worker_circuit in self._worker_circuits.values():
                if worker_circuit.state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                    open_circuits.append(worker_circuit)

            if self._system_circuit and self._system_circuit.state != CircuitState.CLOSED:
                open_circuits.append(self._system_circuit)

            return open_circuits

    async def get_circuit_stats(self) -> dict[str, Any]:
        """Get statistics about cached circuits.

        Returns:
            Dictionary with cache sizes and open circuit counts.
        """
        async with self._lock:
            open_stages = sum(
                1 for c in self._stage_circuits.values() if c.state != CircuitState.CLOSED
            )
            open_workers = sum(
                1 for c in self._worker_circuits.values() if c.state != CircuitState.CLOSED
            )
            system_state = (
                self._system_circuit.state.value if self._system_circuit else "not_initialized"
            )

            return {
                "stage_circuits_cached": len(self._stage_circuits),
                "stage_circuits_open": open_stages,
                "worker_circuits_cached": len(self._worker_circuits),
                "worker_circuits_open": open_workers,
                "system_circuit_state": system_state,
                "max_stage_circuits": self._max_stage_circuits,
            }

    async def reset_all(self) -> int:
        """Reset all cached circuits to CLOSED state.

        Administrative function for recovery from widespread issues.

        Returns:
            Number of circuits reset.
        """
        async with self._lock:
            reset_count = 0

            for stage_circuit in self._stage_circuits.values():
                if stage_circuit.state != CircuitState.CLOSED:
                    await stage_circuit.reset()
                    reset_count += 1

            for worker_circuit in self._worker_circuits.values():
                if worker_circuit.state != CircuitState.CLOSED:
                    await worker_circuit.reset()
                    reset_count += 1

            if self._system_circuit and self._system_circuit.state != CircuitState.CLOSED:
                await self._system_circuit.reset()
                reset_count += 1

            logger.info("Reset %d circuits via registry.reset_all()", reset_count)
            return reset_count

    async def _maybe_evict_stage_circuits(self) -> None:
        """Evict oldest stage circuits if at capacity (LRU policy)."""
        while len(self._stage_circuits) >= self._max_stage_circuits:
            if not self._stage_circuit_access_order:
                break

            # Remove least recently used
            oldest_key = self._stage_circuit_access_order.pop(0)
            if oldest_key in self._stage_circuits:
                del self._stage_circuits[oldest_key]
                logger.debug("Evicted stage circuit %s (LRU)", oldest_key)
