"""Tests for the TestRunner protocol and NoOpTestRunner.

Verifies that:
- TestRunner is a runtime-checkable Protocol
- NoOpTestRunner structurally satisfies the TestRunner Protocol
- Each NoOpTestRunner method returns (True, "no-op")
- The protocol is importable and well-typed
"""

from __future__ import annotations

from tdd_orchestrator.test_runner import NoOpTestRunner, TestRunner


class TestTestRunnerProtocol:
    """Tests for the TestRunner Protocol definition."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """TestRunner should be decorated with @runtime_checkable."""
        assert hasattr(TestRunner, "__protocol_attrs__") or hasattr(
            TestRunner, "__abstractmethods__"
        )
        # The definitive check: isinstance works without raising TypeError
        noop = NoOpTestRunner()
        assert isinstance(noop, TestRunner)

    def test_protocol_defines_run_tests(self) -> None:
        """TestRunner should declare a run_tests method."""
        assert hasattr(TestRunner, "run_tests")

    def test_protocol_defines_check_types(self) -> None:
        """TestRunner should declare a check_types method."""
        assert hasattr(TestRunner, "check_types")

    def test_protocol_defines_lint(self) -> None:
        """TestRunner should declare a lint method."""
        assert hasattr(TestRunner, "lint")

    def test_protocol_defines_verify_all(self) -> None:
        """TestRunner should declare a verify_all method."""
        assert hasattr(TestRunner, "verify_all")


class TestNoOpTestRunner:
    """Tests for the NoOpTestRunner implementation."""

    def test_isinstance_check(self) -> None:
        """NoOpTestRunner should satisfy isinstance(obj, TestRunner)."""
        runner = NoOpTestRunner()
        assert isinstance(runner, TestRunner)

    async def test_run_tests_returns_noop(self) -> None:
        """run_tests should return (True, 'no-op')."""
        runner = NoOpTestRunner()
        passed, output = await runner.run_tests("tests/test_foo.py")
        assert passed is True
        assert output == "no-op"

    async def test_check_types_returns_noop(self) -> None:
        """check_types should return (True, 'no-op')."""
        runner = NoOpTestRunner()
        passed, output = await runner.check_types("src/foo.py")
        assert passed is True
        assert output == "no-op"

    async def test_lint_returns_noop(self) -> None:
        """lint should return (True, 'no-op')."""
        runner = NoOpTestRunner()
        passed, output = await runner.lint("src/foo.py")
        assert passed is True
        assert output == "no-op"

    async def test_verify_all_returns_noop(self) -> None:
        """verify_all should return (True, 'no-op')."""
        runner = NoOpTestRunner()
        passed, output = await runner.verify_all(
            "tests/test_foo.py", "src/foo.py"
        )
        assert passed is True
        assert output == "no-op"

    async def test_run_tests_ignores_argument(self) -> None:
        """run_tests should succeed regardless of the file path provided."""
        runner = NoOpTestRunner()
        passed, output = await runner.run_tests("/nonexistent/path.py")
        assert passed is True
        assert output == "no-op"

    async def test_verify_all_ignores_arguments(self) -> None:
        """verify_all should succeed regardless of file paths provided."""
        runner = NoOpTestRunner()
        passed, output = await runner.verify_all(
            "/no/test.py", "/no/impl.py"
        )
        assert passed is True
        assert output == "no-op"
