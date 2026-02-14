"""Stub detector for non-functional function bodies.

Detects functions that contain only placeholder code: pass, raise NotImplementedError,
ellipsis, docstring-only, or sentinel returns (None, {}, []).
"""

from __future__ import annotations

import ast

from .models import ASTViolation


def _is_abstractmethod(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function has the @abstractmethod decorator."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod":
            return True
    return False


def _is_pytest_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function has the @pytest.fixture decorator."""
    for decorator in node.decorator_list:
        # @pytest.fixture
        if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
            if isinstance(decorator.value, ast.Name) and decorator.value.id == "pytest":
                return True
        # @pytest.fixture(...)
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Attribute) and func.attr == "fixture":
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    return True
    return False


def _is_super_init_call(stmt: ast.stmt) -> bool:
    """Check if a statement is super().__init__(...)."""
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "__init__":
        return False
    # Check for super() call
    if isinstance(func.value, ast.Call):
        inner = func.value
        if isinstance(inner.func, ast.Name) and inner.func.id == "super":
            return True
    return False


def _is_docstring(stmt: ast.stmt) -> bool:
    """Check if a statement is a standalone docstring."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_pass(stmt: ast.stmt) -> bool:
    """Check if a statement is 'pass'."""
    return isinstance(stmt, ast.Pass)


def _is_ellipsis(stmt: ast.stmt) -> bool:
    """Check if a statement is '...' (Ellipsis)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def _is_raise_not_implemented(stmt: ast.stmt) -> bool:
    """Check if a statement is 'raise NotImplementedError' (with or without parens)."""
    if not isinstance(stmt, ast.Raise) or stmt.exc is None:
        return False
    exc = stmt.exc
    # raise NotImplementedError
    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
        return True
    # raise NotImplementedError()
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name) and func.id == "NotImplementedError":
            return True
    return False


def _is_sentinel_return(stmt: ast.stmt) -> bool:
    """Check if a statement is 'return None', 'return {}', or 'return []'."""
    if not isinstance(stmt, ast.Return):
        return False
    val = stmt.value
    if val is None:
        # bare 'return' — same as return None
        return True
    if isinstance(val, ast.Constant) and val.value is None:
        return True
    if isinstance(val, ast.Dict) and not val.keys:
        return True
    if isinstance(val, ast.List) and not val.elts:
        return True
    return False


class StubDetector(ast.NodeVisitor):
    """Detect non-functional function bodies.

    Flags functions whose bodies contain only placeholder code:
    pass, raise NotImplementedError, ellipsis, docstring-only, or
    sentinel returns (None, {}, []).

    Exclusions: @abstractmethod, Protocol methods, .pyi files,
    __init__ with pass/super().__init__(), @pytest.fixture.
    """

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.violations: list[ASTViolation] = []
        self._in_protocol: bool = False
        self._is_pyi: bool = False

    def set_pyi_mode(self, is_pyi: bool) -> None:
        """Enable .pyi stub file mode (suppresses all violations)."""
        self._is_pyi = is_pyi

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track Protocol classes to exclude their methods."""
        is_protocol = any(
            (isinstance(base, ast.Name) and base.id == "Protocol")
            or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
            for base in node.bases
        )
        old = self._in_protocol
        if is_protocol:
            self._in_protocol = True
        self.generic_visit(node)
        self._in_protocol = old

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function for stub body."""
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async function for stub body."""
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Core stub detection logic."""
        # Global exclusions
        if self._is_pyi:
            return
        if self._in_protocol:
            return
        if _is_abstractmethod(node):
            return
        if _is_pytest_fixture(node):
            return

        body = node.body
        if not body:
            return

        # Strip leading docstring for analysis
        effective_body = body
        has_docstring = _is_docstring(body[0])
        if has_docstring:
            effective_body = body[1:]

        # Docstring-only: docstring present but nothing after it
        if has_docstring and not effective_body:
            self._add_violation(
                node, "Stub: function has docstring but no implementation"
            )
            return

        # Single-statement stubs
        if len(effective_body) == 1:
            stmt = effective_body[0]

            # __init__ exclusions
            if node.name == "__init__":
                if _is_pass(stmt):
                    return
                if _is_super_init_call(stmt):
                    return

            if _is_pass(stmt):
                self._add_violation(node, "Stub: function body is only 'pass'")
                return
            if _is_ellipsis(stmt):
                self._add_violation(node, "Stub: function body is only ellipsis (...)")
                return
            if _is_raise_not_implemented(stmt):
                self._add_violation(
                    node, "Stub: function raises NotImplementedError"
                )
                return
            if _is_sentinel_return(stmt):
                self._add_violation(
                    node, "Stub: function returns a sentinel value (None/{}/[])"
                )
                return

    def _add_violation(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, message: str
    ) -> None:
        """Record a stub violation."""
        snippet = ""
        if 0 < node.lineno <= len(self.source_lines):
            snippet = self.source_lines[node.lineno - 1].strip()
        self.violations.append(
            ASTViolation(
                pattern="stub_detected",
                line_number=node.lineno,
                message=f"{message} in '{node.name}'",
                severity="error",
                code_snippet=snippet,
            )
        )
