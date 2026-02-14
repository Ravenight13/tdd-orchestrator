"""Unit tests for StubDetector — detects non-functional function bodies."""

import ast

from tdd_orchestrator.ast_checker.stub_detector import StubDetector


class TestStubDetections:
    """Tests for stub patterns that SHOULD be flagged (severity: error)."""

    def test_catches_pass_only(self) -> None:
        """Function with only pass is a stub."""
        code = """
def foo():
    pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert detector.violations[0].severity == "error"
        assert "pass" in detector.violations[0].message.lower()

    def test_catches_async_pass(self) -> None:
        """Async function with only pass is a stub."""
        code = """
async def foo():
    pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert detector.violations[0].severity == "error"

    def test_catches_not_implemented_parens(self) -> None:
        """raise NotImplementedError() is a stub."""
        code = """
def foo():
    raise NotImplementedError()
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert "NotImplementedError" in detector.violations[0].message

    def test_catches_not_implemented_no_parens(self) -> None:
        """raise NotImplementedError (no parens) is a stub."""
        code = """
def foo():
    raise NotImplementedError
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert "NotImplementedError" in detector.violations[0].message

    def test_catches_ellipsis(self) -> None:
        """Function with only ... (Ellipsis) is a stub."""
        code = """
def foo():
    ...
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert "ellipsis" in detector.violations[0].message.lower()

    def test_catches_docstring_only(self) -> None:
        """Function with only a docstring and no implementation is a stub."""
        code = '''
def foo():
    """This function does something."""
'''
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert "docstring" in detector.violations[0].message.lower()

    def test_catches_return_none(self) -> None:
        """Function with only return None is a stub."""
        code = """
def foo():
    return None
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"
        assert "return" in detector.violations[0].message.lower()

    def test_catches_return_empty_dict(self) -> None:
        """Function with only return {} is a stub."""
        code = """
def foo():
    return {}
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"

    def test_catches_return_empty_list(self) -> None:
        """Function with only return [] is a stub."""
        code = """
def foo():
    return []
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"

    def test_catches_class_method_stub(self) -> None:
        """Method in a regular class with pass is a stub."""
        code = """
class MyClass:
    def do_something(self):
        pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "stub_detected"

    def test_catches_nested_stub(self) -> None:
        """Inner function with pass is a stub."""
        code = """
def outer():
    def inner():
        pass
    return inner
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert "inner" in detector.violations[0].message


class TestStubExclusions:
    """Tests for patterns that should NOT be flagged."""

    def test_allows_real_implementation(self) -> None:
        """Function with real logic is not a stub."""
        code = """
def multiply(x, y):
    return x * y
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_docstring_plus_impl(self) -> None:
        """Function with docstring AND implementation is not a stub."""
        code = '''
def multiply(x, y):
    """Multiply two numbers."""
    return x * y
'''
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_abstractmethod(self) -> None:
        """@abstractmethod with pass is not a stub."""
        code = """
from abc import abstractmethod

class Base:
    @abstractmethod
    def do_something(self):
        pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_protocol_method(self) -> None:
        """Method in a Protocol class with ... is not a stub."""
        code = """
from typing import Protocol

class Serializable(Protocol):
    def serialize(self) -> str:
        ...
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_pyi_file(self) -> None:
        """Stubs in .pyi mode are not flagged."""
        code = """
def foo() -> int:
    ...

def bar() -> str:
    ...
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.set_pyi_mode(True)
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_init_super_only(self) -> None:
        """__init__ with only super().__init__() is not a stub."""
        code = """
class Child(Base):
    def __init__(self):
        super().__init__()
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_init_pass(self) -> None:
        """__init__ with only pass is not a stub."""
        code = """
class Simple:
    def __init__(self):
        pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_fixture(self) -> None:
        """@pytest.fixture function with pass is not a stub."""
        code = """
import pytest

@pytest.fixture
def my_fixture():
    pass
"""
        tree = ast.parse(code)
        detector = StubDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0
