"""Test-file-specific detectors used during RED stage.

This module provides AST visitors that detect issues specific to test files:
missing assertions, empty assertions, unguarded lambda iteration,
unguarded method calls on potentially None values, and semantic contradictions.
"""

from __future__ import annotations

import ast

from .models import ASTViolation


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
