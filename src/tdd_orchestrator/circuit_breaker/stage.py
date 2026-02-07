"""Stage-level circuit breaker implementation.

Prevents a single stage from consuming unlimited retries by
tracking consecutive failures and opening the circuit when
a threshold is reached.
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
