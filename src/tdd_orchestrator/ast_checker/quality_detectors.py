"""General code quality detectors for any Python file.

This module provides AST visitors that detect common code quality issues:
hardcoded secrets, bare except clauses, print statements, and missing docstrings.
"""

from __future__ import annotations

import ast

from .models import (
    AWS_KEY_PATTERN,
    LONG_SECRET_PATTERN,
    SECRET_VAR_NAMES,
    ASTViolation,
)


class SecretDetector(ast.NodeVisitor):
    """AST visitor that detects hardcoded secrets in assignments."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check assignment statements for hardcoded secrets."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_assignment(target.id, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Check annotated assignments for hardcoded secrets."""
        if isinstance(node.target, ast.Name) and node.value:
            self._check_assignment(node.target.id, node.value, node.lineno)
        self.generic_visit(node)

    def _check_assignment(self, var_name: str, value: ast.expr, lineno: int) -> None:
        """Check if an assignment contains a hardcoded secret.

        Args:
            var_name: Name of the variable being assigned.
            value: AST node representing the value.
            lineno: Line number of the assignment.
        """
        # Check if variable name suggests a secret
        var_lower = var_name.lower()

        # Skip URL/endpoint constants (e.g., SANDBOX_TOKEN_URL, API_KEY_ENDPOINT)
        # These contain secret-related words but are just URL paths, not secrets
        url_suffixes = ("_url", "_endpoint", "_uri", "_path", "_route")
        if any(var_lower.endswith(suffix) for suffix in url_suffixes):
            return
        # Also skip if _url_ appears in the middle (e.g., token_url_base)
        if "_url_" in var_lower or "_endpoint_" in var_lower:
            return

        is_secret_name = var_lower in SECRET_VAR_NAMES or any(
            keyword in var_lower for keyword in ("key", "secret", "password", "token", "credential")
        )

        # Get the string value if it's a constant string
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            string_value = value.value

            # Skip empty strings and placeholders
            if not string_value or string_value in (
                "",
                "...",
                "placeholder",
                "your_key_here",
                "CHANGE_ME",
            ):
                return

            # Skip dummy/test/mock values (common in development/testing)
            string_lower = string_value.lower()
            placeholder_markers = ("dummy", "test_", "mock_", "fake_", "example_", "sample_")
            if any(marker in string_lower for marker in placeholder_markers):
                return

            # Skip enum values where value == name.lower()
            # Example: MISSING_TOKEN = "missing_token" (enum member, not a secret)
            if string_value.lower() == var_lower:
                return

            # Check for AWS keys
            if AWS_KEY_PATTERN.search(string_value):
                self._add_violation(
                    lineno,
                    f"AWS access key detected in '{var_name}'",
                )
                return

            # Check if secret variable name with non-trivial value
            if is_secret_name and len(string_value) >= 8:
                self._add_violation(
                    lineno,
                    f"Hardcoded secret in variable '{var_name}'",
                )
                return

            # Check for long alphanumeric strings that look like secrets
            if is_secret_name and LONG_SECRET_PATTERN.match(string_value):
                self._add_violation(
                    lineno,
                    f"Potential hardcoded secret in '{var_name}'",
                )

    def _add_violation(self, lineno: int, message: str) -> None:
        """Add a secret violation.

        Args:
            lineno: Line number of the violation.
            message: Description of the violation.
        """
        snippet = self._get_snippet(lineno)
        self.violations.append(
            ASTViolation(
                pattern="hardcoded_secret",
                line_number=lineno,
                message=message,
                severity="error",
                code_snippet=snippet,
            )
        )

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number.

        Args:
            lineno: 1-based line number.

        Returns:
            The source code line, stripped.
        """
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class BareExceptDetector(ast.NodeVisitor):
    """AST visitor that detects bare except clauses."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Check except handlers for bare except or overly broad Exception."""
        if node.type is None:
            # Bare except clause
            self.violations.append(
                ASTViolation(
                    pattern="bare_except",
                    line_number=node.lineno,
                    message="Bare except clause - specify exception type",
                    severity="error",
                    code_snippet=self._get_snippet(node.lineno),
                )
            )
        self.generic_visit(node)

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class PrintDetector(ast.NodeVisitor):
    """AST visitor that detects print statements in production code."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []
        self._in_main_block = False

    def visit_If(self, node: ast.If) -> None:
        """Track if we're inside a __name__ == '__main__' block."""
        if self._is_main_check(node.test):
            old_state = self._in_main_block
            self._in_main_block = True
            self.generic_visit(node)
            self._in_main_block = old_state
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for print() calls outside of __main__ blocks."""
        if self._in_main_block:
            self.generic_visit(node)
            return

        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.violations.append(
                ASTViolation(
                    pattern="print_statement",
                    line_number=node.lineno,
                    message="Use logger instead of print()",
                    severity="warning",
                    code_snippet=self._get_snippet(node.lineno),
                )
            )
        self.generic_visit(node)

    def _is_main_check(self, test: ast.expr) -> bool:
        """Check if an expression is `if __name__ == '__main__'`."""
        if isinstance(test, ast.Compare):
            if (
                isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
        return False

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class DocstringChecker(ast.NodeVisitor):
    """AST visitor that checks for missing docstrings on public entities."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function definitions for docstrings."""
        self._check_docstring(node, "function")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async function definitions for docstrings."""
        self._check_docstring(node, "async function")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check class definitions for docstrings."""
        self._check_docstring(node, "class")
        self.generic_visit(node)

    def _check_docstring(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, kind: str
    ) -> None:
        """Check if a node has a docstring.

        Args:
            node: AST node to check.
            kind: Type of entity (function, class, etc.).
        """
        # Skip private/dunder methods
        if node.name.startswith("_"):
            return

        docstring = ast.get_docstring(node)
        if docstring is None:
            self.violations.append(
                ASTViolation(
                    pattern="missing_docstring",
                    line_number=node.lineno,
                    message=f"Missing docstring for public {kind} '{node.name}'",
                    severity="warning",
                    code_snippet=self._get_snippet(node.lineno),
                )
            )

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""
