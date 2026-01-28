"""Unit tests for MissingAssertionCheck and EmptyAssertionCheck."""

import ast

from tdd_orchestrator.ast_checker import (
    EmptyAssertionCheck,
    MissingAssertionCheck,
)


class TestMissingAssertionCheck:
    """Tests for MissingAssertionCheck (Check 3 - ERROR)."""

    def test_catches_test_without_assertion(self) -> None:
        """Test function with no assert is flagged."""
        code = """
def test_something():
    result = calculate(5)
    print(result)  # No assertion!
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 1
        assert checker.violations[0].pattern == "missing_assertion"
        assert checker.violations[0].severity == "error"
        assert "test_something" in checker.violations[0].message

    def test_allows_test_with_assertion(self) -> None:
        """Test function with assert passes."""
        code = """
def test_something():
    result = calculate(5)
    assert result == 10
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_allows_pytest_raises(self) -> None:
        """Test function using pytest.raises passes."""
        code = """
def test_raises_error():
    with pytest.raises(ValueError):
        dangerous_function()
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_ignores_non_test_functions(self) -> None:
        """Non-test functions without assertions are ignored."""
        code = """
def helper_function():
    return calculate(5)

def setup():
    initialize()
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_catches_multiple_test_functions(self) -> None:
        """Multiple test functions without assertions are all caught."""
        code = """
def test_first():
    print("no assert")

def test_second():
    x = 1

def test_third():
    assert True  # This one has assertion
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 2
        names = [v.message for v in checker.violations]
        assert any("test_first" in n for n in names)
        assert any("test_second" in n for n in names)

    def test_nested_assertions_detected(self) -> None:
        """Assertions in nested blocks (if/for/while) are detected."""
        code = """
def test_conditional_assertion():
    result = calculate()
    if result > 0:
        assert result == 10
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_pytest_raises_with_attribute(self) -> None:
        """pytest.raises detected even with attribute access."""
        code = """
def test_raises_with_match():
    with pytest.raises(ValueError, match="invalid"):
        process_invalid_data()
"""
        tree = ast.parse(code)
        checker = MissingAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0


class TestEmptyAssertionCheck:
    """Tests for EmptyAssertionCheck (Check 4 - WARNING)."""

    def test_catches_assert_true(self) -> None:
        """assert True is flagged as empty."""
        code = """
def test_something():
    assert True
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 1
        assert checker.violations[0].pattern == "empty_assertion"
        assert checker.violations[0].severity == "warning"
        assert "always true" in checker.violations[0].message.lower()

    def test_catches_assert_constant(self) -> None:
        """assert 1, assert 'string' are flagged."""
        code = """
def test_something():
    assert 1
    assert "non-empty"
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 2

    def test_catches_bare_variable_assertion(self) -> None:
        """assert variable (no comparison) is flagged."""
        code = """
def test_something():
    result = calculate()
    assert result  # What should it equal?
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 1
        assert "result" in checker.violations[0].message
        assert "expected_value" in checker.violations[0].message.lower()

    def test_allows_comparison_assertion(self) -> None:
        """assert x == value passes."""
        code = """
def test_something():
    result = calculate()
    assert result == 10
    assert result is not None
    assert len(result) == 5
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_allows_assert_false_constant(self) -> None:
        """assert False is NOT flagged (it's meaningful - always fails)."""
        code = """
def test_not_implemented():
    assert False, "Not implemented yet"
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        # assert False is falsy, so shouldn't be caught by "always true" check
        assert len(checker.violations) == 0

    def test_allows_assert_none(self) -> None:
        """assert None is NOT flagged (it's falsy)."""
        code = """
def test_check_none():
    assert None  # This will always fail
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        # None is falsy, so shouldn't be caught
        assert len(checker.violations) == 0

    def test_allows_boolean_expressions(self) -> None:
        """assert with boolean operators (and/or/not) passes."""
        code = """
def test_boolean_logic():
    x = True
    y = False
    assert x and not y
    assert x or y
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 0

    def test_allows_function_call_assertions(self) -> None:
        """assert with function calls passes."""
        code = """
def test_function_calls():
    assert is_valid()
    assert calculate() == 10
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        # Note: bare function call (no comparison) should NOT be flagged
        # because it's common to assert boolean functions like is_valid()
        assert len(checker.violations) == 0

    def test_multiple_bare_variables(self) -> None:
        """Multiple bare variable assertions are all caught."""
        code = """
def test_multiple():
    result1 = foo()
    result2 = bar()
    assert result1
    assert result2
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        assert len(checker.violations) == 2
        messages = [v.message for v in checker.violations]
        assert any("result1" in m for m in messages)
        assert any("result2" in m for m in messages)

    def test_assert_zero_not_flagged(self) -> None:
        """assert 0 is NOT flagged (it's falsy, will fail)."""
        code = """
def test_zero():
    assert 0
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        # 0 is falsy, shouldn't be flagged as "always true"
        assert len(checker.violations) == 0

    def test_assert_empty_string_not_flagged(self) -> None:
        """assert '' is NOT flagged (it's falsy, will fail)."""
        code = """
def test_empty_string():
    assert ""
"""
        tree = ast.parse(code)
        checker = EmptyAssertionCheck(code.splitlines())
        checker.visit(tree)

        # Empty string is falsy, shouldn't be flagged
        assert len(checker.violations) == 0


class TestCombinedScenarios:
    """Test both checks working together."""

    def test_missing_and_empty_assertions_separate(self) -> None:
        """Missing assertion and empty assertion are different violations."""
        code_missing = """
def test_no_assert():
    x = 1
"""
        code_empty = """
def test_empty_assert():
    assert True
"""

        tree_missing = ast.parse(code_missing)
        missing_checker = MissingAssertionCheck(code_missing.splitlines())
        missing_checker.visit(tree_missing)

        tree_empty = ast.parse(code_empty)
        empty_checker = EmptyAssertionCheck(code_empty.splitlines())
        empty_checker.visit(tree_empty)

        # Missing assertion is ERROR
        assert len(missing_checker.violations) == 1
        assert missing_checker.violations[0].severity == "error"

        # Empty assertion is WARNING
        assert len(empty_checker.violations) == 1
        assert empty_checker.violations[0].severity == "warning"

    def test_good_test_passes_both_checks(self) -> None:
        """Well-written test passes both MissingAssertionCheck and EmptyAssertionCheck."""
        code = """
def test_proper_assertion():
    result = calculate(10)
    assert result == 20
    assert isinstance(result, int)
"""
        tree = ast.parse(code)

        missing_checker = MissingAssertionCheck(code.splitlines())
        missing_checker.visit(tree)

        empty_checker = EmptyAssertionCheck(code.splitlines())
        empty_checker.visit(tree)

        assert len(missing_checker.violations) == 0
        assert len(empty_checker.violations) == 0
