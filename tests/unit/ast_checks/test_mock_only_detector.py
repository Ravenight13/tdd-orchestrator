"""Unit tests for MockOnlyDetector — detects tests with only mock assertions."""

import ast

from tdd_orchestrator.ast_checker.mock_only_detector import MockOnlyDetector


class TestMockOnlyDetections:
    """Tests for mock-only patterns that SHOULD be flagged (severity: warning)."""

    def test_catches_assert_called_with(self) -> None:
        """Test with only mock.assert_called_with is flagged."""
        code = """
def test_calls_service():
    service = mock.Mock()
    handler(service)
    service.assert_called_with("data")
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "mock_only_test"
        assert detector.violations[0].severity == "warning"

    def test_catches_assert_called_once_with(self) -> None:
        """Test with only mock.assert_called_once_with is flagged."""
        code = """
def test_calls_once():
    service = mock.Mock()
    handler(service)
    service.assert_called_once_with("data", key="value")
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert detector.violations[0].pattern == "mock_only_test"

    def test_catches_assert_called_once(self) -> None:
        """Test with only mock.assert_called_once() is flagged."""
        code = """
def test_called_once():
    service = mock.Mock()
    handler(service)
    service.assert_called_once()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_assert_not_called(self) -> None:
        """Test with only mock.assert_not_called() is flagged."""
        code = """
def test_not_called():
    service = mock.Mock()
    handler(service, skip=True)
    service.assert_not_called()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_assert_mock_called_attr(self) -> None:
        """Test with only assert mock.called is flagged."""
        code = """
def test_was_called():
    service = mock.Mock()
    handler(service)
    assert service.called
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_assert_call_count(self) -> None:
        """Test with only assert mock.call_count == N is flagged."""
        code = """
def test_call_count():
    service = mock.Mock()
    handler(service)
    handler(service)
    assert service.call_count == 2
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_multiple_mock_asserts(self) -> None:
        """Test with 3 mock asserts and 0 real asserts is flagged."""
        code = """
def test_full_mock():
    service = mock.Mock()
    handler(service)
    service.assert_called_once()
    service.assert_called_with("data")
    assert service.called
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert "3" in detector.violations[0].message

    def test_catches_assert_has_calls(self) -> None:
        """Test with only mock.assert_has_calls is flagged."""
        code = """
def test_has_calls():
    service = mock.Mock()
    handler(service)
    service.assert_has_calls([mock.call("a"), mock.call("b")])
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_assert_any_call(self) -> None:
        """Test with only mock.assert_any_call is flagged."""
        code = """
def test_any_call():
    service = mock.Mock()
    handler(service)
    service.assert_any_call("data")
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1

    def test_catches_async_test(self) -> None:
        """Async test with only mock assertions is flagged."""
        code = """
async def test_async_mock():
    service = mock.AsyncMock()
    await handler(service)
    service.assert_called_once()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1


class TestMockOnlyNonViolations:
    """Tests for patterns that should NOT be flagged."""

    def test_allows_mixed_assertions(self) -> None:
        """Test with real assert + mock assert is not flagged."""
        code = """
def test_mixed():
    service = mock.Mock()
    result = handler(service)
    assert result == "success"
    service.assert_called_once()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_only_real_assertions(self) -> None:
        """Test with only real assertions is not flagged."""
        code = """
def test_real():
    result = calculate(5)
    assert result == 42
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_pytest_raises(self) -> None:
        """Test with pytest.raises is not flagged."""
        code = """
def test_raises():
    with pytest.raises(ValueError):
        process_invalid()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_no_assertions(self) -> None:
        """Test with no assertions at all is not flagged (MissingAssertionCheck's job)."""
        code = """
def test_no_asserts():
    result = calculate(5)
    print(result)
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_ignores_non_test_functions(self) -> None:
        """Helper function with mock.assert_called is not flagged."""
        code = """
def verify_mock(mock_obj):
    mock_obj.assert_called_once()
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0

    def test_allows_assert_on_return_value(self) -> None:
        """Test with assert on return value (alongside mock setup) is not flagged."""
        code = """
def test_return_value():
    service = mock.Mock(return_value="data")
    result = handler(service)
    assert result == "data"
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 0


class TestMockOnlyEdgeCases:
    """Edge cases for MockOnlyDetector."""

    def test_multiple_tests_independent(self) -> None:
        """One mock-only test and one real test -> 1 violation."""
        code = """
def test_mock_only():
    service = mock.Mock()
    handler(service)
    service.assert_called_once()

def test_real():
    result = calculate(5)
    assert result == 42
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert "test_mock_only" in detector.violations[0].message

    def test_class_method_test(self) -> None:
        """TestClass.test_foo with mock-only is detected."""
        code = """
class TestMyFeature:
    def test_foo(self):
        service = mock.Mock()
        handler(service)
        service.assert_called_with("x")
"""
        tree = ast.parse(code)
        detector = MockOnlyDetector(code.splitlines())
        detector.visit(tree)

        assert len(detector.violations) == 1
        assert "test_foo" in detector.violations[0].message
