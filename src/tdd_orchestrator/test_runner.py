"""Test runner protocol for language-agnostic test execution.

This module defines the TestRunner Protocol that abstracts test execution,
type checking, and linting behind a common interface. This makes the TDD
Orchestrator ready for language-agnostic test execution — any language can
provide a TestRunner implementation.

The NoOpTestRunner is provided for dry-run and non-Python contexts where
actual tool execution is not needed.

Pattern reference: follows the LLMClient Protocol pattern from
``tdd_orchestrator.decomposition.llm_client``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TestRunner(Protocol):
    """Protocol for language-agnostic test execution.

    Implementations run tests, type checkers, and linters for a given
    language or toolchain. The protocol is ``runtime_checkable`` so that
    ``isinstance()`` can verify structural conformance at runtime.

    Each method returns a ``(passed, output)`` tuple where *passed* is
    ``True`` when the tool exits cleanly and *output* contains the
    captured stdout/stderr or a summary message.
    """

    async def run_tests(self, test_file: str) -> tuple[bool, str]:
        """Run the test suite for a given test file.

        Args:
            test_file: Path to the test file to execute.

        Returns:
            Tuple of (passed, output).
        """
        ...

    async def check_types(self, impl_file: str) -> tuple[bool, str]:
        """Run a type checker against an implementation file.

        Args:
            impl_file: Path to the implementation file.

        Returns:
            Tuple of (passed, output).
        """
        ...

    async def lint(self, impl_file: str) -> tuple[bool, str]:
        """Run a linter against an implementation file.

        Args:
            impl_file: Path to the implementation file.

        Returns:
            Tuple of (passed, output).
        """
        ...

    async def verify_all(
        self, test_file: str, impl_file: str
    ) -> tuple[bool, str]:
        """Run all checks (tests, types, lint) and return an aggregate result.

        Args:
            test_file: Path to the test file.
            impl_file: Path to the implementation file.

        Returns:
            Tuple of (all_passed, combined_output).
        """
        ...


class NoOpTestRunner:
    """A no-op test runner for dry-run and non-Python contexts.

    Every method unconditionally returns ``(True, "no-op")``.  This is
    useful when the orchestrator needs a ``TestRunner`` instance but
    actual tool execution should be skipped (e.g., during plan-only or
    dry-run modes, or when targeting a language without local tooling).
    """

    async def run_tests(self, test_file: str) -> tuple[bool, str]:
        """Return a passing no-op result.

        Args:
            test_file: Ignored.

        Returns:
            ``(True, "no-op")``.
        """
        return True, "no-op"

    async def check_types(self, impl_file: str) -> tuple[bool, str]:
        """Return a passing no-op result.

        Args:
            impl_file: Ignored.

        Returns:
            ``(True, "no-op")``.
        """
        return True, "no-op"

    async def lint(self, impl_file: str) -> tuple[bool, str]:
        """Return a passing no-op result.

        Args:
            impl_file: Ignored.

        Returns:
            ``(True, "no-op")``.
        """
        return True, "no-op"

    async def verify_all(
        self, test_file: str, impl_file: str
    ) -> tuple[bool, str]:
        """Return a passing no-op result.

        Args:
            test_file: Ignored.
            impl_file: Ignored.

        Returns:
            ``(True, "no-op")``.
        """
        return True, "no-op"
