"""Integration tests for Static RED Review (PLAN12).

These tests verify the complete static review flow, including:
- AST-based assertion checks
- Pytest collection verification
- Integration with the TDD pipeline
"""

from __future__ import annotations

from pathlib import Path
from tdd_orchestrator.ast_checker import (
    ASTCheckConfig,
    ASTQualityChecker,
)


class TestStaticReviewIntegration:
    """Integration tests for the static review flow."""

    def test_catches_test_without_assertion_in_file(self, tmp_path: Path) -> None:
        """Full file check catches missing assertions."""
        test_file = tmp_path / "test_bad.py"
        test_file.write_text(
            """
def test_something():
    result = calculate(5)
    print(result)  # No assertion!

def test_another():
    x = 1 + 1
    # Also no assertion
"""
        )

        config = ASTCheckConfig(
            check_missing_assertions=True,
            check_empty_assertions=True,
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        assert result.is_blocking is True
        assert len([v for v in result.violations if v.pattern == "missing_assertion"]) == 2

    def test_catches_empty_assertions_in_file(self, tmp_path: Path) -> None:
        """Full file check catches empty assertions."""
        test_file = tmp_path / "test_empty.py"
        test_file.write_text(
            """
def test_something():
    assert True  # Empty!

def test_another():
    result = calculate()
    assert result  # Just truthiness
"""
        )

        config = ASTCheckConfig(
            check_missing_assertions=True,
            check_empty_assertions=True,
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        # Empty assertions are warnings, not errors
        assert result.is_blocking is False
        assert len([v for v in result.violations if v.pattern == "empty_assertion"]) == 2

    def test_well_written_test_passes(self, tmp_path: Path) -> None:
        """Well-written test file passes static review."""
        test_file = tmp_path / "test_good.py"
        test_file.write_text(
            """
def test_addition():
    result = 1 + 1
    assert result == 2

def test_subtraction():
    result = 5 - 3
    assert result == 2
    assert result > 0

def test_raises_error():
    import pytest
    with pytest.raises(ValueError):
        int("not a number")
"""
        )

        config = ASTCheckConfig(
            check_missing_assertions=True,
            check_empty_assertions=True,
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        assert result.is_blocking is False
        # Should have no violations at all
        missing = [v for v in result.violations if v.pattern == "missing_assertion"]
        empty = [v for v in result.violations if v.pattern == "empty_assertion"]
        assert len(missing) == 0
        assert len(empty) == 0

    def test_htmx_tdd_01_03_regression(self, tmp_path: Path) -> None:
        """Regression test for the bug that triggered PLAN12.

        The original bug was a lambda in BeautifulSoup find() that iterated
        over a potentially None value without a guard.
        """
        # Note: The lambda iteration check is Phase 1B, so this just tests
        # that the basic assertion checks work on complex test files
        test_file = tmp_path / "test_htmx_regression.py"
        test_file.write_text(
            '''
from bs4 import BeautifulSoup

def test_loading_spinner():
    """Test that triggered PLAN12 - lambda bug in BS4 class search."""
    html = "<div class=\\"loading-indicator\\">Loading...</div>"
    soup = BeautifulSoup(html, "html.parser")

    # This is the fixed version with proper None handling
    def has_indicator_class(c):
        if c is None:
            return False
        keywords = ["indicator", "spinner", "loading"]
        if isinstance(c, str):
            return any(kw in c.lower() for kw in keywords)
        return any(kw in cls.lower() for cls in c for kw in keywords)

    indicator = soup.find(class_=has_indicator_class)
    assert indicator is not None  # Proper assertion
'''
        )

        config = ASTCheckConfig(
            check_missing_assertions=True,
            check_empty_assertions=True,
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        # The fixed version should pass
        assert result.is_blocking is False
        missing = [v for v in result.violations if v.pattern == "missing_assertion"]
        assert len(missing) == 0

    def test_mixed_good_and_bad_tests(self, tmp_path: Path) -> None:
        """File with mix of good and bad tests reports only bad ones."""
        test_file = tmp_path / "test_mixed.py"
        test_file.write_text(
            """
def test_good():
    assert 1 == 1

def test_bad_no_assert():
    print("oops")

def test_good_with_raises():
    import pytest
    with pytest.raises(Exception):
        raise Exception("expected")

def test_bad_assert_true():
    assert True
"""
        )

        config = ASTCheckConfig(
            check_missing_assertions=True,
            check_empty_assertions=True,
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        # Should have 1 error (missing) and 1 warning (empty)
        missing = [v for v in result.violations if v.pattern == "missing_assertion"]
        empty = [v for v in result.violations if v.pattern == "empty_assertion"]

        assert len(missing) == 1
        assert "test_bad_no_assert" in missing[0].message

        assert len(empty) == 1
        assert result.is_blocking is True  # Because of missing assertion error


class TestStaticReviewConfig:
    """Tests for static review configuration."""

    def test_can_disable_checks(self, tmp_path: Path) -> None:
        """Checks can be individually disabled via config."""
        test_file = tmp_path / "test_no_assert.py"
        test_file.write_text(
            """
def test_something():
    print("no assert")
"""
        )

        config = ASTCheckConfig(
            check_missing_assertions=False,  # Disabled
            check_empty_assertions=False,  # Disabled
            check_secrets=False,
            check_todos=False,
            check_bare_except=False,
        )
        checker = ASTQualityChecker(config)

        import asyncio

        result = asyncio.run(checker.check_file(test_file))

        # No violations because checks are disabled
        assert result.is_blocking is False
        assert len(result.violations) == 0
