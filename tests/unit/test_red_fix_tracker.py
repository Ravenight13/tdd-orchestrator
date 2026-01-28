"""Unit tests for RedFixAttemptTracker loop safeguards."""

from __future__ import annotations

import time
from unittest.mock import patch

from tdd_orchestrator.ast_checker import ASTViolation
from tdd_orchestrator.worker_pool import RedFixAttemptTracker


class TestRedFixAttemptTracker:
    """Tests for RedFixAttemptTracker (PLAN12 loop safeguards)."""

    def _make_violation(self, pattern: str, line: int) -> ASTViolation:
        """Helper to create test violations."""
        return ASTViolation(
            pattern=pattern,
            line_number=line,
            message=f"Test violation at line {line}",
            severity="error",
        )

    def test_allows_first_attempt(self) -> None:
        """First attempt should always be allowed."""
        tracker = RedFixAttemptTracker()
        can_attempt, reason = tracker.can_attempt()

        assert can_attempt is True
        assert reason == ""

    def test_allows_second_attempt(self) -> None:
        """Second attempt (up to max) should be allowed."""
        tracker = RedFixAttemptTracker()
        tracker.record_attempt([self._make_violation("test", 10)])

        can_attempt, reason = tracker.can_attempt()

        assert can_attempt is True
        assert reason == ""

    def test_blocks_third_attempt(self) -> None:
        """Third attempt exceeds max_attempts=2."""
        tracker = RedFixAttemptTracker()
        tracker.record_attempt([self._make_violation("test", 10)])
        tracker.record_attempt([self._make_violation("test", 20)])

        can_attempt, reason = tracker.can_attempt()

        assert can_attempt is False
        assert "Max fix attempts" in reason
        assert "2" in reason

    def test_detects_oscillation(self) -> None:
        """Detects A→B→A oscillation pattern."""
        tracker = RedFixAttemptTracker(max_attempts=10)  # High limit to test oscillation

        issues_a = [self._make_violation("check_a", 10)]
        issues_b = [self._make_violation("check_b", 20)]

        tracker.record_attempt(issues_a)  # Attempt 1: A
        tracker.record_attempt(issues_b)  # Attempt 2: B
        tracker.record_attempt(issues_a)  # Attempt 3: A (same as 1!)

        can_attempt, reason = tracker.can_attempt()

        assert can_attempt is False
        assert "Oscillation" in reason

    def test_no_oscillation_with_different_issues(self) -> None:
        """No oscillation when issues keep changing."""
        tracker = RedFixAttemptTracker(max_attempts=10)

        tracker.record_attempt([self._make_violation("a", 10)])
        tracker.record_attempt([self._make_violation("b", 20)])
        tracker.record_attempt([self._make_violation("c", 30)])

        can_attempt, reason = tracker.can_attempt()

        assert can_attempt is True

    def test_aggregate_timeout(self) -> None:
        """Blocks after aggregate timeout exceeded."""
        tracker = RedFixAttemptTracker(aggregate_timeout_seconds=1)

        # Simulate time passing
        with patch.object(time, "time", return_value=tracker.start_time + 2):
            can_attempt, reason = tracker.can_attempt()

        assert can_attempt is False
        assert "timeout" in reason.lower()

    def test_fingerprint_includes_pattern_and_line(self) -> None:
        """Issue fingerprints include both pattern and line number."""
        tracker = RedFixAttemptTracker()

        issues = [
            self._make_violation("missing_assertion", 10),
            self._make_violation("empty_assertion", 25),
        ]
        tracker.record_attempt(issues)

        fingerprint = tracker.issue_fingerprints[0]
        assert "missing_assertion:10" in fingerprint
        assert "empty_assertion:25" in fingerprint

    def test_fingerprint_is_sorted(self) -> None:
        """Fingerprints are sorted for consistent comparison."""
        tracker = RedFixAttemptTracker()

        # Add in different order
        issues1 = [
            self._make_violation("z_check", 100),
            self._make_violation("a_check", 5),
        ]
        issues2 = [
            self._make_violation("a_check", 5),
            self._make_violation("z_check", 100),
        ]

        tracker.record_attempt(issues1)
        tracker.record_attempt(issues2)

        # Same fingerprint despite different order
        assert tracker.issue_fingerprints[0] == tracker.issue_fingerprints[1]

    def test_custom_max_attempts(self) -> None:
        """Can configure custom max_attempts."""
        tracker = RedFixAttemptTracker(max_attempts=5)

        for i in range(4):
            tracker.record_attempt([self._make_violation("test", i * 10)])

        can_attempt, _ = tracker.can_attempt()
        assert can_attempt is True

        tracker.record_attempt([self._make_violation("test", 50)])

        can_attempt, reason = tracker.can_attempt()
        assert can_attempt is False
        assert "5" in reason
