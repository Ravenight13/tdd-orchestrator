"""Circuit breaker exception classes."""

from __future__ import annotations


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""

    pass


class CircuitOpenError(CircuitBreakerError):
    """Raised when circuit is open and request is blocked."""

    def __init__(self, identifier: str, time_until_retry: float) -> None:
        self.identifier = identifier
        self.time_until_retry = time_until_retry
        super().__init__(f"Circuit {identifier} is open. Retry in {time_until_retry:.1f}s")
