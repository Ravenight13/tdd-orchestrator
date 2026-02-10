"""Tests for SSEEvent dataclass that formats events into SSE wire protocol."""

import pytest

from tdd_orchestrator.api.sse import SSEEvent


class TestSSEEventDataOnly:
    """Tests for SSEEvent with only data field."""

    def test_serialize_returns_data_field_with_trailing_blank_line_when_data_only(self) -> None:
        """SSEEvent with only data formats to 'data: <value>\n\n'."""
        event = SSEEvent(data="hello")
        result = event.serialize()
        assert result == "data: hello\n\n"

    def test_serialize_returns_valid_wire_format_when_simple_data(self) -> None:
        """SSEEvent data field produces valid SSE wire protocol message."""
        event = SSEEvent(data="test message")
        result = event.serialize()
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        assert result == "data: test message\n\n"


class TestSSEEventMultilineData:
    """Tests for SSEEvent with multi-line data."""

    def test_serialize_splits_multiline_data_into_separate_data_fields(self) -> None:
        """Multi-line data splits each line into a separate 'data:' field."""
        event = SSEEvent(data="line1\nline2")
        result = event.serialize()
        assert result == "data: line1\ndata: line2\n\n"

    def test_serialize_handles_three_lines_when_multiline_data(self) -> None:
        """Multi-line data with three lines produces three data fields."""
        event = SSEEvent(data="first\nsecond\nthird")
        result = event.serialize()
        assert result == "data: first\ndata: second\ndata: third\n\n"

    def test_serialize_handles_trailing_newline_in_data(self) -> None:
        """Data with trailing newline is handled correctly."""
        event = SSEEvent(data="line1\nline2\n")
        result = event.serialize()
        # Trailing newline creates an empty line that should also be a data field
        assert "data: line1\n" in result
        assert "data: line2\n" in result
        assert result.endswith("\n\n")


class TestSSEEventWithAllFields:
    """Tests for SSEEvent with event, id, and data fields."""

    def test_serialize_formats_id_event_data_in_correct_order(self) -> None:
        """SSEEvent with event, id, and data formats them in order 'id: <id>\nevent: <event>\ndata: <data>\n\n'."""
        event = SSEEvent(data="payload", event="message", id="123")
        result = event.serialize()
        assert result == "id: 123\nevent: message\ndata: payload\n\n"

    def test_serialize_returns_complete_wire_format_string(self) -> None:
        """The serialize method returns the complete wire-format string."""
        event = SSEEvent(data="test", event="update", id="abc")
        result = event.serialize()
        assert isinstance(result, str)
        assert "id: abc\n" in result
        assert "event: update\n" in result
        assert "data: test\n" in result
        assert result.endswith("\n\n")

    def test_serialize_with_id_and_data_only(self) -> None:
        """SSEEvent with id and data (no event) formats correctly."""
        event = SSEEvent(data="content", id="456")
        result = event.serialize()
        assert "id: 456\n" in result
        assert "data: content\n" in result
        assert result.endswith("\n\n")

    def test_serialize_with_event_and_data_only(self) -> None:
        """SSEEvent with event and data (no id) formats correctly."""
        event = SSEEvent(data="content", event="notify")
        result = event.serialize()
        assert "event: notify\n" in result
        assert "data: content\n" in result
        assert result.endswith("\n\n")


class TestSSEEventWithRetry:
    """Tests for SSEEvent with retry field."""

    def test_serialize_includes_retry_field_in_milliseconds(self) -> None:
        """SSEEvent with retry field includes 'retry: <milliseconds>\n' in output."""
        event = SSEEvent(data="test", retry=5000)
        result = event.serialize()
        assert "retry: 5000\n" in result
        assert "data: test\n" in result
        assert result.endswith("\n\n")

    def test_serialize_renders_retry_as_integer(self) -> None:
        """Retry value is rendered as an integer of milliseconds."""
        event = SSEEvent(data="test", retry=1500)
        result = event.serialize()
        # Ensure retry is an integer (no decimal point)
        assert "retry: 1500\n" in result
        assert "retry: 1500.0" not in result

    def test_serialize_with_all_fields_including_retry(self) -> None:
        """SSEEvent with all fields (id, event, data, retry) formats correctly."""
        event = SSEEvent(data="payload", event="message", id="789", retry=3000)
        result = event.serialize()
        assert "id: 789\n" in result
        assert "event: message\n" in result
        assert "retry: 3000\n" in result
        assert "data: payload\n" in result
        assert result.endswith("\n\n")


class TestSSEEventEmptyData:
    """Tests for SSEEvent with empty-string data."""

    def test_serialize_formats_empty_data_as_data_field_with_no_payload(self) -> None:
        """SSEEvent with empty-string data formats to 'data: \n\n'."""
        event = SSEEvent(data="")
        result = event.serialize()
        assert result == "data: \n\n"

    def test_serialize_does_not_raise_error_when_data_is_empty(self) -> None:
        """Empty payloads do not raise errors."""
        event = SSEEvent(data="")
        # Should not raise
        result = event.serialize()
        assert result is not None
        assert isinstance(result, str)

    def test_serialize_does_not_drop_empty_data_silently(self) -> None:
        """Empty payloads are not silently dropped."""
        event = SSEEvent(data="")
        result = event.serialize()
        # The data field must be present even when empty
        assert "data:" in result
        assert result.startswith("data: ")


class TestSSEEventEdgeCases:
    """Edge case tests for SSEEvent."""

    def test_serialize_handles_data_with_colon(self) -> None:
        """Data containing colons is handled correctly."""
        event = SSEEvent(data="key: value")
        result = event.serialize()
        assert result == "data: key: value\n\n"

    def test_serialize_handles_data_with_special_characters(self) -> None:
        """Data with special characters is preserved."""
        event = SSEEvent(data="hello <world> & \"friends\"")
        result = event.serialize()
        assert "data: hello <world> & \"friends\"\n" in result

    def test_serialize_handles_unicode_data(self) -> None:
        """Unicode data is handled correctly."""
        event = SSEEvent(data="héllo wörld 你好")
        result = event.serialize()
        assert "data: héllo wörld 你好\n" in result

    def test_serialize_handles_numeric_id(self) -> None:
        """Numeric-like id string is handled correctly."""
        event = SSEEvent(data="test", id="12345")
        result = event.serialize()
        assert "id: 12345\n" in result

    def test_serialize_handles_zero_retry(self) -> None:
        """Zero retry value is valid and formatted correctly."""
        event = SSEEvent(data="test", retry=0)
        result = event.serialize()
        assert "retry: 0\n" in result
