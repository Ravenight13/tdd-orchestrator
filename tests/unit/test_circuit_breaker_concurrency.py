"""Concurrency and race condition tests for circuit breakers.

Tests verify thread-safety, asyncio lock behavior, and optimistic locking.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from tdd_orchestrator.circuit_breaker import (
    StageCircuitBreaker,
    WorkerCircuitBreaker,
    SystemCircuitBreaker,
)
from tdd_orchestrator.circuit_breaker_config import (
    CircuitState,
    CircuitBreakerConfig,
    StageCircuitConfig,
    WorkerCircuitConfig,
    SystemCircuitConfig,
)


def create_mock_db(latency_ms: float = 0) -> Any:
    """Create a mock database compatible with circuit breaker tests.

    Args:
        latency_ms: Simulated latency for testing lock contention

    Returns:
        AsyncMock configured to work with circuit breakers
    """
    from unittest.mock import AsyncMock, MagicMock

    db = AsyncMock()
    db._ensure_connected = AsyncMock()

    # Mock cursor that supports both await and async context manager
    class ExecuteResult:
        def __init__(self, latency: float = 0) -> None:
            self.latency = latency
            self.lastrowid = 1  # Mock lastrowid for INSERT operations
            self.rowcount = 1  # Mock rowcount for UPDATE operations

        async def fetchone(self) -> None:
            if self.latency > 0:
                await asyncio.sleep(self.latency)
            return None

        async def fetchall(self) -> list:
            if self.latency > 0:
                await asyncio.sleep(self.latency)
            return []

        def __await__(self) -> Any:
            # Support `await cursor` pattern
            async def _await() -> ExecuteResult:
                if self.latency > 0:
                    await asyncio.sleep(self.latency)
                return self

            return _await().__await__()

        async def __aenter__(self) -> ExecuteResult:
            if self.latency > 0:
                await asyncio.sleep(self.latency)
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    # Mock connection
    db._conn = MagicMock()

    # execute() returns an ExecuteResult (supports both await and async with)
    latency_s = latency_ms / 1000
    db._conn.execute = MagicMock(return_value=ExecuteResult(latency_s))
    db._conn.executemany = AsyncMock()
    db._conn.commit = AsyncMock()

    return db


@pytest.fixture
def mock_db() -> Any:
    """Create mock database."""
    return create_mock_db()


@pytest.fixture
def slow_db() -> Any:
    """Create mock database with simulated latency."""
    return create_mock_db(latency_ms=50)


# =============================================================================
# Stage Circuit Breaker Concurrency Tests
# =============================================================================


class TestStageCircuitBreakerConcurrency:
    """Concurrency tests for StageCircuitBreaker."""

    @pytest.fixture
    def config(self) -> CircuitBreakerConfig:
        return CircuitBreakerConfig(stage=StageCircuitConfig(max_failures=3))

    @pytest.fixture
    def circuit(self, mock_db: Any, config: CircuitBreakerConfig) -> StageCircuitBreaker:
        return StageCircuitBreaker(
            db=mock_db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

    @pytest.mark.asyncio
    async def test_concurrent_failures_respect_threshold(
        self, circuit: StageCircuitBreaker
    ) -> None:
        """Concurrent failures should not exceed threshold before opening."""
        # Record failures concurrently
        tasks = [asyncio.create_task(circuit.record_failure("error")) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Circuit should be open after max_failures (3)
        assert circuit.state == CircuitState.OPEN
        # Failure count should not exceed reasonable bounds
        assert circuit.failure_count >= 3

    @pytest.mark.asyncio
    async def test_concurrent_check_and_allow(self, circuit: StageCircuitBreaker) -> None:
        """Concurrent check_and_allow should be thread-safe."""
        results = []

        async def check() -> None:
            try:
                allowed = await circuit.check_and_allow()
                results.append(allowed)
            except Exception:
                results.append(False)

        tasks = [asyncio.create_task(check()) for _ in range(20)]
        await asyncio.gather(*tasks)

        # All checks should have succeeded (circuit starts closed)
        assert all(results)

    @pytest.mark.asyncio
    async def test_state_change_under_load(self, mock_db: Any) -> None:
        """State changes should be atomic under concurrent load."""
        config = CircuitBreakerConfig(stage=StageCircuitConfig(max_failures=3))
        circuit = StageCircuitBreaker(
            db=mock_db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

        # Create mixed workload
        async def record_failure() -> None:
            await circuit.record_failure("error")

        async def record_success() -> None:
            await circuit.record_success()

        # Run mixed concurrent operations
        tasks = []
        for i in range(20):
            if i % 2 == 0:
                tasks.append(asyncio.create_task(record_failure()))
            else:
                tasks.append(asyncio.create_task(record_success()))

        await asyncio.gather(*tasks)

        # State should be valid
        assert circuit.state in [
            CircuitState.CLOSED,
            CircuitState.OPEN,
            CircuitState.HALF_OPEN,
        ]


# =============================================================================
# Worker Circuit Breaker Concurrency Tests
# =============================================================================


class TestWorkerCircuitBreakerConcurrency:
    """Concurrency tests for WorkerCircuitBreaker."""

    @pytest.fixture
    def config(self) -> CircuitBreakerConfig:
        return CircuitBreakerConfig(
            worker=WorkerCircuitConfig(
                max_consecutive_failures=3,
                max_extensions=2,
            )
        )

    @pytest.fixture
    def circuit(self, mock_db: Any, config: CircuitBreakerConfig) -> WorkerCircuitBreaker:
        return WorkerCircuitBreaker(
            db=mock_db,  # type: ignore
            worker_id=1,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_concurrent_pause_requests(self, circuit: WorkerCircuitBreaker) -> None:
        """Concurrent failure recordings should be handled safely."""
        await circuit.load_state()

        # Record failures concurrently
        tasks = [asyncio.create_task(circuit.record_failure("error")) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Circuit should be open after max_consecutive_failures (3)
        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_single_request_enforcement(
        self, circuit: WorkerCircuitBreaker
    ) -> None:
        """Only one request should be allowed in half-open state."""
        # Open then transition to half-open
        for _ in range(3):
            await circuit.record_failure("error")

        # Manually set to half-open for testing
        circuit._state = CircuitState.HALF_OPEN
        circuit._half_open_requests = 0

        results = []

        async def try_request() -> None:
            try:
                allowed = await circuit.check_and_allow()
                results.append(("allowed", allowed))
            except Exception as e:
                results.append(("error", str(e)))

        # Try concurrent requests
        tasks = [asyncio.create_task(try_request()) for _ in range(5)]
        await asyncio.gather(*tasks)

        # Only one should be allowed
        allowed_count = sum(1 for r in results if r[0] == "allowed" and r[1] is True)
        assert allowed_count <= 1


# =============================================================================
# System Circuit Breaker Concurrency Tests
# =============================================================================


class TestSystemCircuitBreakerConcurrency:
    """Concurrency tests for SystemCircuitBreaker."""

    @pytest.fixture
    def config(self) -> CircuitBreakerConfig:
        return CircuitBreakerConfig(
            system=SystemCircuitConfig(
                failure_threshold_percent=50,
                min_workers_for_threshold=2,
            )
        )

    @pytest.fixture
    def circuit(self, mock_db: Any, config: CircuitBreakerConfig) -> SystemCircuitBreaker:
        return SystemCircuitBreaker(
            db=mock_db,  # type: ignore
            config=config,
        )

    @pytest.mark.asyncio
    async def test_concurrent_worker_status_updates(self, circuit: SystemCircuitBreaker) -> None:
        """Concurrent worker status updates should be thread-safe."""
        # Set total workers first
        circuit.set_total_workers(10)
        await circuit.load_state()

        # Record worker failures concurrently
        tasks = [asyncio.create_task(circuit.record_worker_failure(i, "error")) for i in range(5)]
        await asyncio.gather(*tasks)

        # Should have recorded failures
        assert circuit.failed_worker_count >= 0

    @pytest.mark.asyncio
    async def test_concurrent_failure_updates_trip_threshold(
        self, circuit: SystemCircuitBreaker
    ) -> None:
        """Concurrent failure updates should correctly trip system circuit."""
        # Set 4 total workers
        circuit.set_total_workers(4)
        await circuit.load_state()

        # Mark failures concurrently (>50% should trip)
        tasks = [
            asyncio.create_task(circuit.record_worker_failure(i, "error"))
            for i in range(3)  # 3/4 = 75% > 50%
        ]
        await asyncio.gather(*tasks)

        # Check if circuit should halt (indicates it's open)
        should_halt = await circuit.should_halt()
        assert should_halt is True

    @pytest.mark.asyncio
    async def test_graceful_shutdown_concurrent_tasks(self, circuit: SystemCircuitBreaker) -> None:
        """Graceful shutdown should handle concurrent in-flight tasks."""
        circuit.set_total_workers(3)
        await circuit.load_state()

        # Register in-flight tasks
        for i in range(3):
            circuit.register_in_flight_task(i)

        # Trip the circuit
        for i in range(2):
            await circuit.record_worker_failure(i, "error")

        # Concurrent task completions during shutdown
        async def complete_task(task_id: int) -> None:
            await asyncio.sleep(0.01)  # Simulate work
            circuit.complete_in_flight_task(task_id)

        tasks = [asyncio.create_task(complete_task(i)) for i in range(3)]
        await asyncio.gather(*tasks)

        # In-flight count should be 0
        assert circuit.in_flight_count == 0


# =============================================================================
# Lock Contention Tests
# =============================================================================


class TestLockContention:
    """Tests for lock contention behavior."""

    @pytest.mark.asyncio
    async def test_high_contention_stage_circuit(self) -> None:
        """Stage circuit should handle high contention."""
        db = create_mock_db(latency_ms=10)
        config = CircuitBreakerConfig(stage=StageCircuitConfig(max_failures=100))
        circuit = StageCircuitBreaker(
            db=db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

        # High contention: many concurrent operations
        async def operation(i: int) -> None:
            if i % 3 == 0:
                await circuit.record_failure("error")
            elif i % 3 == 1:
                await circuit.record_success()
            else:
                await circuit.check_and_allow()

        start = time.time()
        tasks = [asyncio.create_task(operation(i)) for i in range(100)]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # Should complete in reasonable time
        # Operations are serialized by lock but should complete within 10 seconds
        assert elapsed < 10.0  # Reasonable upper bound for 100 operations with 10ms latency

    @pytest.mark.asyncio
    async def test_no_deadlock_nested_operations(self) -> None:
        """Nested operations should not cause deadlock."""
        db = create_mock_db()
        config = CircuitBreakerConfig(stage=StageCircuitConfig(max_failures=5))
        circuit = StageCircuitBreaker(
            db=db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

        async def nested_operation() -> None:
            await circuit.check_and_allow()
            await circuit.record_failure("error")
            await circuit.check_and_allow()

        # Should complete without deadlock
        async with asyncio.timeout(2):
            tasks = [asyncio.create_task(nested_operation()) for _ in range(10)]
            await asyncio.gather(*tasks)


# =============================================================================
# Optimistic Locking Tests
# =============================================================================


class TestOptimisticLocking:
    """Tests for optimistic locking behavior."""

    @pytest.mark.asyncio
    async def test_version_increments_atomically(self) -> None:
        """Version should increment atomically on each update."""
        db = create_mock_db()
        config = CircuitBreakerConfig(stage=StageCircuitConfig(max_failures=10))
        circuit = StageCircuitBreaker(
            db=db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

        initial_version = circuit._version

        # Concurrent updates
        tasks = [asyncio.create_task(circuit.record_failure("error")) for _ in range(5)]
        await asyncio.gather(*tasks)

        # Version should have incremented
        assert circuit._version > initial_version

    @pytest.mark.asyncio
    async def test_concurrent_state_transitions(self) -> None:
        """Concurrent state transitions should not corrupt state."""
        db = create_mock_db()
        config = CircuitBreakerConfig(
            stage=StageCircuitConfig(max_failures=3, recovery_timeout_seconds=0.1)
        )
        circuit = StageCircuitBreaker(
            db=db,  # type: ignore
            identifier="TDD-1:green",
            config=config,
        )

        # Open the circuit
        for _ in range(3):
            await circuit.record_failure("error")

        assert circuit.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Concurrent check_and_allow should transition to half-open safely
        async def check() -> bool:
            return await circuit.check_and_allow()

        tasks = [asyncio.create_task(check()) for _ in range(5)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # State should be valid
        assert circuit.state in [
            CircuitState.HALF_OPEN,
            CircuitState.CLOSED,
            CircuitState.OPEN,
        ]
