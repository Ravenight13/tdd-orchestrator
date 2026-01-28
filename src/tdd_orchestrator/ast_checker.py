"""AST-based code quality checker for TDD pipeline.

This module provides the ASTQualityChecker class that performs static analysis
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

import ast
import io
import logging
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

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


class MissingAssertionCheck(ast.NodeVisitor):
    """AST visitor that detects test functions without assertions."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check test functions for assertions."""
        if node.name.startswith("test_"):
            has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
            # Also check for pytest.raises context manager
            has_pytest_raises = self._has_pytest_raises(node)
            if not has_assert and not has_pytest_raises:
                self.violations.append(
                    ASTViolation(
                        pattern="missing_assertion",
                        line_number=node.lineno,
                        message=f"Test function '{node.name}' has no assertions",
                        severity="error",
                        code_snippet=self._get_snippet(node.lineno),
                    )
                )
        self.generic_visit(node)

    def _has_pytest_raises(self, node: ast.FunctionDef) -> bool:
        """Check if function uses pytest.raises context manager.

        Args:
            node: FunctionDef node to check.

        Returns:
            True if pytest.raises is used, False otherwise.
        """
        for child in ast.walk(node):
            if isinstance(child, ast.With):
                for item in child.items:
                    if isinstance(item.context_expr, ast.Call):
                        func = item.context_expr.func
                        # Check for pytest.raises(...)
                        if isinstance(func, ast.Attribute) and func.attr == "raises":
                            return True
        return False

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class EmptyAssertionCheck(ast.NodeVisitor):
    """AST visitor that detects meaningless assertions."""

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        """Check assertions for meaningfulness."""
        # Check for: assert True, assert 1, assert "string"
        if isinstance(node.test, ast.Constant) and node.test.value:
            self.violations.append(
                ASTViolation(
                    pattern="empty_assertion",
                    line_number=node.lineno,
                    message="Assertion is always true (assert True/constant)",
                    severity="warning",
                    code_snippet=self._get_snippet(node.lineno),
                )
            )
        # Check for: assert x (just a variable, no comparison)
        elif isinstance(node.test, ast.Name):
            self.violations.append(
                ASTViolation(
                    pattern="empty_assertion",
                    line_number=node.lineno,
                    message=f"Consider 'assert {node.test.id} == expected_value' instead of truthiness check",
                    severity="warning",
                    code_snippet=self._get_snippet(node.lineno),
                )
            )
        self.generic_visit(node)

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class LambdaIterationCheck(ast.NodeVisitor):
    """AST visitor that detects unguarded iteration over lambda parameters.

    Detects patterns like: lambda c: [x for x in c]
    Should be: lambda c: [x for x in c] if c else []
    Or: lambda c: [] if c is None else [x for x in c]

    Fix guidance: Add `if param is None: return []` or use `param or []` as
    iteration target.
    """

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Check lambda expressions for unguarded iteration over parameters."""
        # Get parameter names from lambda
        param_names: set[str] = set()
        for arg in node.args.args:
            param_names.add(arg.arg)

        # Walk lambda body looking for comprehensions
        for child in ast.walk(node.body):
            if isinstance(child, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                self._check_comprehension(child, param_names, node.lineno)

        self.generic_visit(node)

    def _check_comprehension(
        self,
        comp: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
        param_names: set[str],
        lambda_lineno: int,
    ) -> None:
        """Check if comprehension iterates over a lambda parameter without guard.

        Args:
            comp: Comprehension node to check.
            param_names: Set of lambda parameter names.
            lambda_lineno: Line number of the lambda for reporting.
        """
        for generator in comp.generators:
            if isinstance(generator.iter, ast.Name):
                iter_name = generator.iter.id
                if iter_name in param_names:
                    # Check if there's a guard (ternary expression wrapping comprehension)
                    # This is a heuristic - we report warning if iterating directly
                    # over a param that could be None
                    self.violations.append(
                        ASTViolation(
                            pattern="lambda_iteration",
                            line_number=lambda_lineno,
                            message=(
                                f"Lambda iterates over parameter '{iter_name}' without None guard. "
                                f"Use '{iter_name} or []' or add 'if {iter_name}' condition."
                            ),
                            severity="warning",
                            code_snippet=self._get_snippet(lambda_lineno),
                        )
                    )

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class UnguardedMethodCheck(ast.NodeVisitor):
    """AST visitor that detects unguarded string method calls on potentially None values.

    Detects patterns like: result.lower() where result could be None.
    Common sources of None: .find(), .get(), .select_one(), function params.

    Fix guidance: Add None check before calling string methods:
    `if var is not None:`
    """

    # Methods that return potentially None values
    NONE_RETURNING_METHODS: frozenset[str] = frozenset(
        {"find", "get", "select_one", "search", "match", "find_one"}
    )

    # String methods that will fail on None
    STRING_METHODS: frozenset[str] = frozenset(
        {
            "lower",
            "upper",
            "strip",
            "split",
            "get_text",
            "lstrip",
            "rstrip",
            "replace",
            "startswith",
            "endswith",
        }
    )

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []
        # Track variables that could be None: {var_name: line_number}
        self._potentially_none_vars: dict[str, int] = {}
        # Track function/method parameters
        self._current_params: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function parameters as potentially None."""
        old_params = self._current_params
        self._current_params = {arg.arg for arg in node.args.args}
        self.generic_visit(node)
        self._current_params = old_params

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function parameters as potentially None."""
        old_params = self._current_params
        self._current_params = {arg.arg for arg in node.args.args}
        self.generic_visit(node)
        self._current_params = old_params

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track assignments from methods that return potentially None."""
        # Check if value is a call to a None-returning method
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Attribute):
                if node.value.func.attr in self.NONE_RETURNING_METHODS:
                    # Track all simple name targets
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self._potentially_none_vars[target.id] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for string method calls on potentially None values."""
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if method_name in self.STRING_METHODS:
                # Check if receiver is a potentially None variable
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    if var_name in self._potentially_none_vars:
                        source_line = self._potentially_none_vars[var_name]
                        self.violations.append(
                            ASTViolation(
                                pattern="unguarded_method",
                                line_number=node.lineno,
                                message=(
                                    f"Calling .{method_name}() on '{var_name}' which may be None "
                                    f"(assigned from None-returning method at line {source_line}). "
                                    f"Add None check: 'if {var_name} is not None:'"
                                ),
                                severity="warning",
                                code_snippet=self._get_snippet(node.lineno),
                            )
                        )
                    elif var_name in self._current_params:
                        self.violations.append(
                            ASTViolation(
                                pattern="unguarded_method",
                                line_number=node.lineno,
                                message=(
                                    f"Calling .{method_name}() on parameter '{var_name}' which may be None. "
                                    f"Add None check: 'if {var_name} is not None:'"
                                ),
                                severity="warning",
                                code_snippet=self._get_snippet(node.lineno),
                            )
                        )
        self.generic_visit(node)

    def _get_snippet(self, lineno: int) -> str:
        """Get source code snippet for a line number."""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""


class SemanticContradictionCheck(ast.NodeVisitor):
    """Detect test functions with contradictory assertions on identical inputs.

    Finds cases where different tests call the same function with same arguments
    but assert different boolean results (True vs False).

    Handles the common pattern:
        result = func(args)
        assert result is True/False
    """

    def __init__(self, source_lines: list[str]) -> None:
        """Initialize with source lines for snippet extraction.

        Args:
            source_lines: List of source code lines.
        """
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []
        # Maps "func(args)" -> [(test_name, expected_bool, line_no), ...]
        self.call_expectations: dict[str, list[tuple[str, bool, int]]] = {}
        # Maps variable_name -> call_signature within current test function
        self._current_var_assignments: dict[str, str] = {}

    def check(self, tree: ast.AST) -> list[ASTViolation]:
        """Run the semantic contradiction check.

        Args:
            tree: AST to analyze.

        Returns:
            List of violations found.
        """
        self.violations = []
        self.call_expectations = {}
        self.visit(tree)
        self._analyze_contradictions()
        return self.violations

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit test function definitions."""
        if node.name.startswith("test_"):
            self._extract_assertions(node)
        self.generic_visit(node)

    def _extract_assertions(self, func_node: ast.FunctionDef) -> None:
        """Extract assertion patterns from a test function.

        First extracts variable assignments (result = func(...)),
        then analyzes assertions using those assignments.

        Args:
            func_node: Test function AST node.
        """
        # Reset variable assignments for this function
        self._current_var_assignments = {}

        # First pass: extract assignments like `result = func(...)`
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                # Handle: result = func(...)
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    var_name = node.targets[0].id
                    if isinstance(node.value, ast.Call):
                        call_sig = self._call_to_string(node.value)
                        if call_sig:
                            self._current_var_assignments[var_name] = call_sig

        # Second pass: extract assertions
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assert):
                self._analyze_assert(func_node.name, node)

    def _analyze_assert(self, test_name: str, assert_node: ast.Assert) -> None:
        """Analyze an assert statement for boolean expectations.

        Args:
            test_name: Name of the test function.
            assert_node: Assert AST node.
        """
        test_expr = assert_node.test

        # Pattern: assert result is True / assert result is False
        if isinstance(test_expr, ast.Compare):
            if len(test_expr.ops) == 1 and isinstance(test_expr.ops[0], ast.Is):
                left = test_expr.left
                right = test_expr.comparators[0]

                # Check if comparing to True or False
                if isinstance(right, ast.Constant) and isinstance(right.value, bool):
                    expected = right.value
                    call_sig = self._get_call_signature(left)
                    if call_sig:
                        if call_sig not in self.call_expectations:
                            self.call_expectations[call_sig] = []
                        self.call_expectations[call_sig].append(
                            (test_name, expected, assert_node.lineno)
                        )

        # Pattern: assert result == True / assert result == False
        if isinstance(test_expr, ast.Compare):
            if len(test_expr.ops) == 1 and isinstance(test_expr.ops[0], ast.Eq):
                left = test_expr.left
                right = test_expr.comparators[0]

                if isinstance(right, ast.Constant) and isinstance(right.value, bool):
                    expected = right.value
                    call_sig = self._get_call_signature(left)
                    if call_sig:
                        if call_sig not in self.call_expectations:
                            self.call_expectations[call_sig] = []
                        self.call_expectations[call_sig].append(
                            (test_name, expected, assert_node.lineno)
                        )

    def _get_call_signature(self, node: ast.AST) -> str | None:
        """Get a normalized string signature for a function call.

        Handles both direct calls and variable references that were assigned from calls.

        Args:
            node: AST node to analyze.

        Returns:
            String signature like "func(arg1, arg2)" or None if not traceable.
        """
        # Handle Name (variable that was assigned from a call)
        if isinstance(node, ast.Name):
            # Look up in current function's variable assignments
            return self._current_var_assignments.get(node.id)

        # Handle direct Call
        if isinstance(node, ast.Call):
            return self._call_to_string(node)

        return None

    def _call_to_string(self, call: ast.Call) -> str:
        """Convert a Call node to a normalized string.

        Args:
            call: Call AST node.

        Returns:
            String representation like "func(arg1, arg2)" or empty string on error.
        """
        try:
            # Get function name
            if isinstance(call.func, ast.Name):
                func_name = call.func.id
            elif isinstance(call.func, ast.Attribute):
                func_name = call.func.attr
            else:
                return ""

            # Get arguments
            args: list[str] = []
            for arg in call.args:
                args.append(ast.unparse(arg))
            for kw in call.keywords:
                args.append(f"{kw.arg}={ast.unparse(kw.value)}")

            return f"{func_name}({', '.join(args)})"
        except Exception:
            return ""

    def _analyze_contradictions(self) -> None:
        """Analyze collected expectations for contradictions."""
        for call_sig, expectations in self.call_expectations.items():
            if len(expectations) < 2:
                continue

            # Check for True vs False contradiction
            true_tests = [(t, line) for t, e, line in expectations if e is True]
            false_tests = [(t, line) for t, e, line in expectations if e is False]

            if true_tests and false_tests:
                true_names = [t for t, _ in true_tests]
                false_names = [t for t, _ in false_tests]
                first_line = min(line for _, _, line in expectations)

                self.violations.append(
                    ASTViolation(
                        pattern="semantic_contradiction",
                        line_number=first_line,
                        message=(
                            f"Contradictory assertions: {call_sig} "
                            f"expected True in [{', '.join(true_names[:2])}] "
                            f"but False in [{', '.join(false_names[:2])}]. "
                            f"Same function call cannot return both True and False."
                        ),
                        severity="warning",
                        code_snippet=self._get_snippet(first_line),
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
