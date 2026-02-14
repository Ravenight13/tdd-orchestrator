"""Mock-only test detector.

Detects test functions where ALL assertions verify mock behavior
(e.g., assert_called_with, assert mock.called) with zero real assertions.
These tests pass VERIFY but prove nothing about actual behavior.
"""

from __future__ import annotations

import ast

from .models import ASTViolation

MOCK_ASSERT_METHODS: frozenset[str] = frozenset({
    "assert_called_with",
    "assert_called_once_with",
    "assert_called_once",
    "assert_called",
    "assert_not_called",
    "assert_has_calls",
    "assert_any_call",
})

MOCK_ASSERT_ATTRS: frozenset[str] = frozenset({
    "call_count",
    "called",
    "call_args",
    "call_args_list",
})


class MockOnlyDetector(ast.NodeVisitor):
    """Detect test functions where all assertions check mock behavior.

    Only flags when 100% of assertions are mock-only. Mixed tests
    (real assert + mock assert) are not flagged.

    Only checks test_* functions. Severity: warning (shadow mode).
    """

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check test functions for mock-only assertions."""
        self._check_test_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async test functions for mock-only assertions."""
        self._check_test_function(node)
        self.generic_visit(node)

    def _check_test_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Core mock-only detection logic."""
        if not node.name.startswith("test_"):
            return

        mock_count = 0
        real_count = 0

        for child in ast.walk(node):
            # Check mock assert method calls (mock.assert_called_with(...))
            if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                call = child.value
                if isinstance(call.func, ast.Attribute):
                    if call.func.attr in MOCK_ASSERT_METHODS:
                        mock_count += 1
                        continue

            # Check assert statements
            if isinstance(child, ast.Assert):
                if self._is_mock_assertion(child):
                    mock_count += 1
                else:
                    real_count += 1

            # Check pytest.raises as a real assertion
            if isinstance(child, ast.With):
                for item in child.items:
                    if self._is_pytest_raises(item.context_expr):
                        real_count += 1

        # Only flag if there are mock assertions and zero real assertions
        if mock_count > 0 and real_count == 0:
            snippet = ""
            if 0 < node.lineno <= len(self.source_lines):
                snippet = self.source_lines[node.lineno - 1].strip()
            self.violations.append(
                ASTViolation(
                    pattern="mock_only_test",
                    line_number=node.lineno,
                    message=(
                        f"Test '{node.name}' has {mock_count} assertion(s), "
                        f"all against mocks — no real behavior is verified"
                    ),
                    severity="warning",
                    code_snippet=snippet,
                )
            )

    def _is_mock_assertion(self, node: ast.Assert) -> bool:
        """Check if an assert statement references mock attributes."""
        test = node.test

        # assert mock.called / assert mock.call_count (bare attribute)
        if isinstance(test, ast.Attribute) and test.attr in MOCK_ASSERT_ATTRS:
            return True

        # assert mock.call_count == N (comparison with mock attr on left)
        if isinstance(test, ast.Compare):
            if isinstance(test.left, ast.Attribute):
                if test.left.attr in MOCK_ASSERT_ATTRS:
                    return True

        return False

    def _is_pytest_raises(self, node: ast.expr) -> bool:
        """Check if an expression is pytest.raises(...)."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "raises":
                return True
        return False
