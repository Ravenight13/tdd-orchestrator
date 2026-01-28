"""Domain models for the TDD orchestrator pipeline.

This module defines the core data structures used throughout the TDD orchestrator,
including stage enumerations and result dataclasses for tracking pipeline execution.

The TDD pipeline follows this stage progression:
    RED -> GREEN -> VERIFY -> (FIX -> RE_VERIFY if needed)

Each stage produces a StageResult that captures success/failure state,
output, and any issues encountered during execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ast_checker import ASTCheckResult


class Stage(Enum):
    """TDD pipeline stages.

    The orchestrator progresses through these stages:
    - RED: Write failing tests that define expected behavior
    - RED_FIX: Fix static review issues in RED stage tests
    - GREEN: Implement minimal code to make tests pass
    - VERIFY: Run pytest, ruff, and mypy to validate implementation
    - FIX: Address any issues found during verification
    - RE_VERIFY: Re-run verification after fixes applied
    """

    RED = "red"
    RED_FIX = "red_fix"
    GREEN = "green"
    VERIFY = "verify"
    FIX = "fix"
    RE_VERIFY = "re_verify"


@dataclass
class StageResult:
    """Result from executing a TDD pipeline stage.

    Captures the outcome of a single stage execution, including
    success state, output, errors, and any issues that need attention.

    Attributes:
        stage: The pipeline stage that was executed.
        success: Whether the stage completed successfully.
        output: Standard output from the stage execution.
        error: Error message if the stage failed, None otherwise.
        issues: List of issue dictionaries for VERIFY stage failures.
            Each issue dict may contain keys like 'type', 'message',
            'file', 'line' depending on the verification tool.
    """

    stage: Stage
    success: bool
    output: str
    error: str | None = None
    issues: list[dict[str, Any]] | None = None


@dataclass
class VerifyResult:
    """Result from code verification checks.

    Aggregates results from pytest, ruff, mypy, and AST quality verification tools.
    Used during the VERIFY and RE_VERIFY stages to determine if the
    implementation meets quality standards.

    Attributes:
        pytest_passed: Whether all pytest tests passed.
        pytest_output: Full output from pytest execution.
        ruff_passed: Whether ruff linting found no issues.
        ruff_output: Full output from ruff check.
        mypy_passed: Whether mypy type checking passed.
        mypy_output: Full output from mypy execution.
        ast_result: Optional AST quality check result (None if not run).
    """

    pytest_passed: bool
    pytest_output: str
    ruff_passed: bool
    ruff_output: str
    mypy_passed: bool
    mypy_output: str
    ast_result: ASTCheckResult | None = field(default=None)

    @property
    def all_passed(self) -> bool:
        """Check if all verification checks passed.

        Returns:
            True if pytest, ruff, mypy all passed and AST has no blocking violations.
        """
        ast_ok = self.ast_result is None or not self.ast_result.is_blocking
        return self.pytest_passed and self.ruff_passed and self.mypy_passed and ast_ok
