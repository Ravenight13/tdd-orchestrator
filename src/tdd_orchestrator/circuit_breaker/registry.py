"""Circuit breaker registry for managing all circuit breaker instances.

Provides factory methods to get or create circuit breakers at all
levels, with caching to avoid recreating circuits and cleanup
methods to prevent memory leaks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..circuit_breaker_config import (
    CircuitBreakerConfig,
    CircuitState,
    DEFAULT_CONFIG,
)
from .stage import StageCircuitBreaker
from .system import SystemCircuitBreaker
from .worker import WorkerCircuitBreaker

if TYPE_CHECKING:
    from ..database import OrchestratorDB

logger = logging.getLogger(__name__)


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
