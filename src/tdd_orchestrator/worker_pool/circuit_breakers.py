"""Circuit breakers for worker pool resilience.

RedFixAttemptTracker prevents infinite RED_FIX loops.
StaticReviewCircuitBreaker auto-disables static review after consecutive failures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..ast_checker import ASTViolation


@dataclass
class RedFixAttemptTracker:
    """Track RED_FIX attempts to prevent infinite loops.

    Implements PLAN12 loop safeguards:
    - Max 2 fix attempts (hard-coded)
    - Oscillation detection (A->B->A pattern)
    - 5-minute aggregate timeout
    """

    max_attempts: int = 2
    attempts: int = 0
    issue_fingerprints: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    aggregate_timeout_seconds: int = 300  # 5 minutes

    def can_attempt(self) -> tuple[bool, str]:
        """Check if another fix attempt is allowed.

        Returns:
            Tuple of (can_attempt, reason_if_not).
        """
        # Check max attempts
        if self.attempts >= self.max_attempts:
            return False, f"Max fix attempts ({self.max_attempts}) reached"

        # Check aggregate timeout
        elapsed = time.time() - self.start_time
        if elapsed > self.aggregate_timeout_seconds:
            return False, f"Aggregate timeout ({self.aggregate_timeout_seconds}s) exceeded"

        # Check for oscillation (A->B->A pattern)
        if len(self.issue_fingerprints) >= 3:
            if self.issue_fingerprints[-1] == self.issue_fingerprints[-3]:
                return False, "Oscillation detected (same issue reappeared)"

        return True, ""

    def record_attempt(self, issues: list[ASTViolation]) -> None:
        """Record a fix attempt with issue fingerprint.

        Args:
            issues: List of AST violations from static review.
        """
        self.attempts += 1
        # Create fingerprint: sorted list of (pattern:line)
        fingerprint = "|".join(sorted(f"{i.pattern}:{i.line_number}" for i in issues))
        self.issue_fingerprints.append(fingerprint)


@dataclass
class StaticReviewCircuitBreaker:
    """Circuit breaker to auto-disable static review after consecutive failures.

    If the static review system itself fails (not the checks finding issues,
    but the system crashing), this circuit breaker will temporarily disable
    static review to prevent blocking all tasks.

    Implements a simple circuit breaker pattern:
    - After max_consecutive_failures, circuit opens (disabled)
    - After cooldown_seconds, circuit closes (re-enabled)
    - Success resets the failure counter
    """

    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    disabled_until: float | None = None
    cooldown_seconds: float = 300.0  # 5 minutes

    def record_success(self) -> None:
        """Reset failure count on success."""
        self.consecutive_failures = 0
        self.disabled_until = None

    def record_failure(self) -> bool:
        """Record failure, return True if circuit is now open (disabled).

        Returns:
            True if the circuit breaker just opened (static review now disabled).
        """
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.disabled_until = time.time() + self.cooldown_seconds
            return True
        return False

    def is_enabled(self) -> bool:
        """Check if static review should run.

        Returns:
            True if static review is enabled and should run.
        """
        if self.disabled_until is None:
            return True
        if time.time() >= self.disabled_until:
            # Cooldown expired, reset and re-enable
            self.disabled_until = None
            self.consecutive_failures = 0
            return True
        return False
