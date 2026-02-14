"""Constants and data classes for AST-based code quality checking.

This module provides the building blocks used by all detector classes:
patterns for secret detection, TODO markers, and the core data classes
for violations, results, and configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Secret detection patterns
AWS_KEY_PATTERN = re.compile(r"AKIA[A-Z0-9]{16}")
SECRET_VAR_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "api_secret",
        "password",
        "passwd",
        "token",
        "secret",
        "secret_key",
        "secretkey",
        "credential",
        "credentials",
        "access_key",
        "accesskey",
        "private_key",
        "privatekey",
        "auth_token",
        "authtoken",
    }
)

# Long alphanumeric string pattern (potential secrets)
LONG_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")

# TODO/FIXME patterns
TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


@dataclass
class ASTViolation:
    """A single AST-based code quality violation.

    Attributes:
        pattern: The pattern type that was violated (e.g., "hardcoded_secret").
        line_number: The line number where the violation occurred.
        message: Human-readable description of the violation.
        severity: Either "error" (blocking) or "warning" (non-blocking).
        code_snippet: The offending line of code (optional).
    """

    pattern: str
    line_number: int
    message: str
    severity: str
    code_snippet: str = ""


@dataclass
class ASTCheckResult:
    """Result from running AST quality checks on a file.

    Attributes:
        violations: List of all violations found.
        is_blocking: True if any ERROR-level violations exist.
        file_path: Path to the file that was checked.
    """

    violations: list[ASTViolation] = field(default_factory=list)
    is_blocking: bool = False
    file_path: str = ""

    def __post_init__(self) -> None:
        """Calculate is_blocking based on violations."""
        self.is_blocking = any(v.severity == "error" for v in self.violations)


@dataclass
class ASTCheckConfig:
    """Configuration for AST quality checks.

    Attributes:
        check_secrets: Enable hardcoded secret detection (P0).
        check_todos: Enable TODO/FIXME marker detection (P0).
        check_docstrings: Enable missing docstring detection (warning only).
        check_bare_except: Enable bare except clause detection (P0).
        check_prints: Enable print statement detection (warning only).
        check_missing_assertions: Enable test assertion detection (error only, test files).
        check_empty_assertions: Enable empty assertion detection (warning only, test files).
        check_lambda_iteration: Enable lambda iteration guard detection (warning, Phase 1B).
        check_unguarded_methods: Enable unguarded string method detection (warning, Phase 1B).
        check_semantic_contradictions: Enable semantic contradiction detection (warning, test files).
    """

    check_secrets: bool = True
    check_todos: bool = True
    check_docstrings: bool = False
    check_bare_except: bool = True
    check_prints: bool = False
    check_missing_assertions: bool = True
    check_empty_assertions: bool = True
    check_lambda_iteration: bool = True
    check_unguarded_methods: bool = True
    check_semantic_contradictions: bool = True
    check_stubs: bool = True
    check_mock_only_tests: bool = True
