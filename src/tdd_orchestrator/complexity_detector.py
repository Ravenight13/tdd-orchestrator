"""Task complexity detection for prompt enhancement and model selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Define complexity signal keywords by category and level
COMPLEXITY_SIGNALS: dict[str, dict[str, list[str]]] = {
    "security_crypto": {
        "high": ["jwt", "rs256", "pkce", "encryption", "signing", "oauth2", "openid"],
        "medium": ["oauth", "authentication", "token", "session", "cookie"],
    },
    "concurrency": {
        "high": ["concurrent", "race condition", "semaphore", "lock", "mutex"],
        "medium": ["async", "parallel", "timeout", "await", "asyncio"],
    },
    "state_management": {
        "high": ["state machine", "circuit breaker", "saga", "transaction"],
        "medium": ["retry", "backoff", "cache", "queue"],
    },
    "data_processing": {
        "high": ["streaming", "batch processing", "etl", "transformation"],
        "medium": ["parsing", "validation", "serialization"],
    },
}

# Keywords that reduce complexity score (unless high-priority signals present)
COMPLEXITY_REDUCERS: list[str] = ["simple", "basic", "stub", "mock", "log", "print", "hello"]

# High-priority signals that override reducers
HIGH_PRIORITY_SIGNALS: list[str] = ["jwt", "encryption", "signing"]

# File path patterns that increase complexity
COMPLEX_PATH_PATTERNS: list[str] = ["auth/", "security/", "crypto/"]


@dataclass
class ComplexityResult:
    """Result of complexity detection."""

    level: str  # "low" | "medium" | "high"
    score: float
    signals: list[str] = field(default_factory=list)  # Keywords that contributed


def detect_complexity(
    title: str,
    acceptance_criteria: list[str],
    impl_file: str,
) -> ComplexityResult:
    """Detect task complexity using multi-factor scoring.

    Combines title, acceptance criteria, and file path to determine task
    complexity. Used for prompt enhancement and model selection decisions.

    Args:
        title: Task title.
        acceptance_criteria: List of acceptance criteria strings.
        impl_file: Path to implementation file.

    Returns:
        ComplexityResult with level, score, and contributing signals.
    """
    # Combine all text for analysis
    text = f"{title} {' '.join(acceptance_criteria)}".lower()
    matched_signals: list[str] = []

    # Helper function for word boundary matching (avoids "log" matching in "backoff")
    def word_match(keyword: str, content: str) -> bool:
        """Check if keyword exists as a word (not substring) in content."""
        # Use word boundaries for short keywords to avoid false positives
        if len(keyword) <= 4:
            return bool(re.search(rf"\b{re.escape(keyword)}\b", content))
        return keyword in content

    # Check reducers first - if present and no high-priority signals, return low
    has_reducer = any(word_match(reducer, text) for reducer in COMPLEXITY_REDUCERS)
    has_high_priority = any(word_match(signal, text) for signal in HIGH_PRIORITY_SIGNALS)

    if has_reducer and not has_high_priority:
        # Find which reducer matched for reporting
        for reducer in COMPLEXITY_REDUCERS:
            if word_match(reducer, text):
                matched_signals.append(f"reducer:{reducer}")
                break
        return ComplexityResult(level="low", score=0.0, signals=matched_signals)

    # Score based on complexity signals
    score = 0.0
    for category, levels in COMPLEXITY_SIGNALS.items():
        # Check high-level keywords first
        for keyword in levels.get("high", []):
            if word_match(keyword, text):
                score += 0.3
                matched_signals.append(f"{category}:high:{keyword}")
                break  # Only count one high signal per category

        # Check medium-level keywords (only if no high match in this category)
        if not any(f"{category}:high:" in s for s in matched_signals):
            for keyword in levels.get("medium", []):
                if word_match(keyword, text):
                    score += 0.15
                    matched_signals.append(f"{category}:medium:{keyword}")
                    break  # Only count one medium signal per category

    # File path heuristics
    impl_file_lower = impl_file.lower()
    for pattern in COMPLEX_PATH_PATTERNS:
        if pattern in impl_file_lower:
            score += 0.2
            matched_signals.append(f"path:{pattern}")
            break  # Only count one path pattern

    # Determine level based on thresholds
    if score >= 0.5:
        level = "high"
    elif score >= 0.25:
        level = "medium"
    else:
        level = "low"

    return ComplexityResult(level=level, score=score, signals=matched_signals)
