"""AST-based code quality checker for TDD pipeline.

This package provides the ASTQualityChecker class that performs static analysis
using Python's ast module to detect code quality issues that external tools miss.

Detection patterns:
    - Hardcoded secrets (API keys, passwords, tokens)
    - TODO/FIXME markers in comments
    - Missing docstrings on public functions/classes
    - Bare except clauses
    - Print statements in production code

Usage:
    checker = ASTQualityChecker()
    result = await checker.check_file(Path("src/foo.py"))
    if result.is_blocking:
        print("Blocking violations found!")
"""

from __future__ import annotations

from .checker import ASTQualityChecker
from .models import ASTCheckConfig, ASTCheckResult, ASTViolation
from .quality_detectors import (
    BareExceptDetector,
    DocstringChecker,
    PrintDetector,
    SecretDetector,
)
from .mock_only_detector import MockOnlyDetector
from .stub_detector import StubDetector
from .test_detectors import (
    EmptyAssertionCheck,
    LambdaIterationCheck,
    MissingAssertionCheck,
    SemanticContradictionCheck,
    UnguardedMethodCheck,
)

__all__ = [
    "ASTCheckConfig",
    "ASTCheckResult",
    "ASTQualityChecker",
    "ASTViolation",
    "BareExceptDetector",
    "DocstringChecker",
    "EmptyAssertionCheck",
    "LambdaIterationCheck",
    "MissingAssertionCheck",
    "MockOnlyDetector",
    "PrintDetector",
    "SemanticContradictionCheck",
    "SecretDetector",
    "StubDetector",
    "UnguardedMethodCheck",
]
