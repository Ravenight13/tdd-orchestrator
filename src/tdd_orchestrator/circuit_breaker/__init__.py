"""Circuit breaker implementation for TDD orchestrator.

Implements the circuit breaker pattern at stage level to prevent
infinite retries when stages fail repeatedly.

The circuit breaker has three states:
- CLOSED: Normal operation, failures are counted
- OPEN: Circuit tripped, requests immediately fail
- HALF_OPEN: Testing recovery, limited requests allowed
"""

from .exceptions import CircuitBreakerError, CircuitOpenError
from .registry import CircuitBreakerRegistry
from .stage import StageCircuitBreaker
from .system import SystemCircuitBreaker
from .worker import WorkerCircuitBreaker

__all__ = [
    "CircuitBreakerError",
    "CircuitOpenError",
    "StageCircuitBreaker",
    "WorkerCircuitBreaker",
    "SystemCircuitBreaker",
    "CircuitBreakerRegistry",
]
