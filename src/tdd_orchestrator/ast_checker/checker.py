"""Main AST quality checker orchestrator.

This module provides the ASTQualityChecker class that coordinates all
AST-based code quality checks on Python files.
"""

from __future__ import annotations

import ast
import io
import logging
import tokenize
from pathlib import Path

from .models import ASTCheckConfig, ASTCheckResult, ASTViolation, TODO_PATTERN
from .quality_detectors import (
    BareExceptDetector,
    DocstringChecker,
    PrintDetector,
    SecretDetector,
)
from .test_detectors import (
    EmptyAssertionCheck,
    LambdaIterationCheck,
    MissingAssertionCheck,
    SemanticContradictionCheck,
    UnguardedMethodCheck,
)

logger = logging.getLogger(__name__)


class ASTQualityChecker:
    """Run AST-based code quality checks on Python files.

    This class coordinates multiple AST visitors and the tokenize module
    to detect code quality issues that external tools like ruff and mypy
    may not catch.

    Attributes:
        config: Configuration for which checks to run.
    """

    def __init__(self, config: ASTCheckConfig | None = None) -> None:
        """Initialize with optional configuration.

        Args:
            config: Check configuration. Uses defaults if not provided.
        """
        self.config = config or ASTCheckConfig()

    async def check_file(self, file_path: Path) -> ASTCheckResult:
        """Run all enabled AST checks on a file.

        Args:
            file_path: Path to the Python file to check.

        Returns:
            ASTCheckResult with all violations found.
        """
        logger.debug("Running AST checks on %s", file_path)

        # Guard: skip non-Python files (defense-in-depth)
        if file_path.suffix not in (".py", ".pyi"):
            return ASTCheckResult(violations=[], file_path=str(file_path))

        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Failed to read file %s: %s", file_path, e)
            return ASTCheckResult(
                violations=[
                    ASTViolation(
                        pattern="file_error",
                        line_number=0,
                        message=f"Failed to read file: {e}",
                        severity="error",
                    )
                ],
                file_path=str(file_path),
            )

        source_lines = source.splitlines()
        violations: list[ASTViolation] = []

        # Parse AST
        try:
            tree = ast.parse(source, filename=str(file_path), type_comments=True)
        except SyntaxError as e:
            logger.error("Syntax error in %s: %s", file_path, e)
            return ASTCheckResult(
                violations=[
                    ASTViolation(
                        pattern="syntax_error",
                        line_number=e.lineno or 0,
                        message=f"Syntax error: {e.msg}",
                        severity="error",
                    )
                ],
                file_path=str(file_path),
            )

        # Check if this is a test file (exclude from print checks)
        is_test_file = "test" in str(file_path).lower()

        # Run AST-based checks
        # Skip secret detection for test files - they legitimately need mock tokens
        if self.config.check_secrets and not is_test_file:
            secret_detector = SecretDetector(source_lines)
            secret_detector.visit(tree)
            violations.extend(secret_detector.violations)

        if self.config.check_bare_except:
            except_detector = BareExceptDetector(source_lines)
            except_detector.visit(tree)
            violations.extend(except_detector.violations)

        if self.config.check_prints and not is_test_file:
            print_detector = PrintDetector(source_lines)
            print_detector.visit(tree)
            violations.extend(print_detector.violations)

        if self.config.check_docstrings:
            docstring_checker = DocstringChecker(source_lines)
            docstring_checker.visit(tree)
            violations.extend(docstring_checker.violations)

        # RED stage checks (test files only)
        if is_test_file:
            if self.config.check_missing_assertions:
                missing_check = MissingAssertionCheck(source_lines)
                missing_check.visit(tree)
                violations.extend(missing_check.violations)

            if self.config.check_empty_assertions:
                empty_check = EmptyAssertionCheck(source_lines)
                empty_check.visit(tree)
                violations.extend(empty_check.violations)

            if self.config.check_lambda_iteration:
                lambda_check = LambdaIterationCheck(source_lines)
                lambda_check.visit(tree)
                violations.extend(lambda_check.violations)

            if self.config.check_unguarded_methods:
                method_check = UnguardedMethodCheck(source_lines)
                method_check.visit(tree)
                violations.extend(method_check.violations)

            if self.config.check_semantic_contradictions:
                contradiction_check = SemanticContradictionCheck(source_lines)
                violations.extend(contradiction_check.check(tree))

        # Run tokenize-based checks (for comments)
        if self.config.check_todos:
            todo_violations = self._check_todos(source, source_lines)
            violations.extend(todo_violations)

        result = ASTCheckResult(
            violations=violations,
            file_path=str(file_path),
        )

        logger.info(
            "AST check complete for %s: %d violations, blocking=%s",
            file_path,
            len(violations),
            result.is_blocking,
        )

        return result

    def _check_todos(self, source: str, source_lines: list[str]) -> list[ASTViolation]:
        """Check for TODO/FIXME markers using tokenize.

        Args:
            source: Source code as a string.
            source_lines: Source code split into lines.

        Returns:
            List of TODO-related violations.
        """
        violations: list[ASTViolation] = []

        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    match = TODO_PATTERN.search(token.string)
                    if match:
                        marker = match.group(1).upper()
                        lineno = token.start[0]
                        snippet = ""
                        if 0 < lineno <= len(source_lines):
                            snippet = source_lines[lineno - 1].strip()

                        violations.append(
                            ASTViolation(
                                pattern="todo_marker",
                                line_number=lineno,
                                message=f"{marker} marker found - resolve before committing",
                                severity="error",
                                code_snippet=snippet,
                            )
                        )
        except tokenize.TokenError as e:
            logger.warning("Tokenize error: %s", e)

        return violations
