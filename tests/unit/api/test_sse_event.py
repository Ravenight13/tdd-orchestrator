"""Tests for SSEEvent dataclass that formats events into SSE wire protocol."""

import pytest

from tdd_orchestrator.api.sse import SSEEvent


class TestSSEEventDataOnly:
    """Tests for SSEEvent with only data field."""

    def test_serialize_returns_data_field_with_trailing_blank_line_when_only_data_provided(
        self,
    ) -> None:
        """SSEEvent with only data formats to 'data: <value>\n\n'."""
        event = SSEEvent(data="hello")
        result = event.serialize()
        assert result == "data: hello\n\n"

    def test_serialize_handles_single_word_data(self) -> None:
        """Single word data is properly formatted."""
        event = SSEEvent(data="test")
        result = event.serialize()
        assert result == "data: test\n\n"

    def test_serialize_handles_data_with_spaces(self) -> None:
        """Data containing spaces is preserved."""
        event = SSEEvent(data="hello world")
        result = event.serialize()
        assert result == "data: hello world\n\n"


class TestSSEEventMultiLineData:
    """Tests for SSEEvent with multi-line data."""

    def test_serialize_splits_multiline_data_into_separate_data_fields(self) -> None:
        """Multi-line data splits each line into separate 'data:' field."""
        event = SSEEvent(data="line1\nline2")
        result = event.serialize()
        assert result == "data: line1\ndata: line2\n\n"

    def test_serialize_handles_three_lines_of_data(self) -> None:
        """Three lines of data produce three data fields."""
        event = SSEEvent(data="first\nsecond\nthird")
        result = event.serialize()
        assert result == "data: first\ndata: second\ndata: third\n\n"

    def test_serialize_handles_data_with_empty_line_in_middle(self) -> None:
        """Empty line in middle of data is preserved as empty data field."""
        event = SSEEvent(data="before\n\nafter")
        result = event.serialize()
        assert result == "data: before\ndata: \ndata: after\n\n"

    def test_serialize_handles_data_ending_with_newline(self) -> None:
        """Data ending with newline produces trailing empty data field."""
        event = SSEEvent(data="content\n")
        result = event.serialize()
        assert result == "data: content\ndata: \n\n"


class TestSSEEventWithEventAndId:
    """Tests for SSEEvent with event, id, and data fields."""

    def test_serialize_formats_id_event_data_in_correct_order(self) -> None:
        """Fields are ordered: id, event, data."""
        event = SSEEvent(data="payload", event="message", id="123")
        result = event.serialize()
        assert result == "id: 123\nevent: message\ndata: payload\n\n"

    def test_serialize_with_only_event_and_data(self) -> None:
        """Event and data without id are formatted correctly."""
        event = SSEEvent(data="payload", event="update")
        result = event.serialize()
        assert "event: update\n" in result
        assert "data: payload\n" in result
        assert result.endswith("\n\n")

    def test_serialize_with_only_id_and_data(self) -> None:
        """Id and data without event are formatted correctly."""
        event = SSEEvent(data="payload", id="456")
        result = event.serialize()
        assert "id: 456\n" in result
        assert "data: payload\n" in result
        assert result.endswith("\n\n")

    def test_serialize_id_appears_before_event(self) -> None:
        """Id field appears before event field in output."""
        event = SSEEvent(data="test", event="myevent", id="789")
        result = event.serialize()
        id_pos = result.find("id:")
        event_pos = result.find("event:")
        assert id_pos < event_pos, "id should appear before event"

    def test_serialize_event_appears_before_data(self) -> None:
        """Event field appears before data field in output."""
        event = SSEEvent(data="test", event="myevent", id="789")
        result = event.serialize()
        event_pos = result.find("event:")
        data_pos = result.find("data:")
        assert event_pos < data_pos, "event should appear before data"


class TestSSEEventWithRetry:
    """Tests for SSEEvent with retry field."""

    def test_serialize_includes_retry_in_milliseconds(self) -> None:
        """Retry field is included as integer milliseconds."""
        event = SSEEvent(data="payload", retry=5000)
        result = event.serialize()
        assert "retry: 5000\n" in result

    def test_serialize_retry_value_is_integer(self) -> None:
        """Retry value is rendered as integer, not float."""
        event = SSEEvent(data="payload", retry=1000)
        result = event.serialize()
        assert "retry: 1000\n" in result
        assert "retry: 1000.0" not in result

    def test_serialize_with_all_fields_including_retry(self) -> None:
        """All fields including retry are formatted correctly."""
        event = SSEEvent(data="payload", event="test", id="1", retry=3000)
        result = event.serialize()
        assert "id: 1\n" in result
        assert "event: test\n" in result
        assert "retry: 3000\n" in result
        assert "data: payload\n" in result
        assert result.endswith("\n\n")

    def test_serialize_retry_zero_is_valid(self) -> None:
        """Retry value of zero is valid and included."""
        event = SSEEvent(data="test", retry=0)
        result = event.serialize()
        assert "retry: 0\n" in result


class TestSSEEventEmptyData:
    """Tests for SSEEvent with empty string data."""

    def test_serialize_empty_string_data_produces_empty_data_field(self) -> None:
        """Empty string data formats to 'data: \\n\\n'."""
        event = SSEEvent(data="")
        result = event.serialize()
        assert result == "data: \n\n"

    def test_serialize_empty_data_does_not_raise_error(self) -> None:
        """Empty data does not raise an error."""
        event = SSEEvent(data="")
        result = event.serialize()
        assert result is not None
        assert isinstance(result, str)

    def test_serialize_empty_data_is_not_silently_dropped(self) -> None:
        """Empty data still produces a data field, not dropped."""
        event = SSEEvent(data="")
        result = event.serialize()
        assert "data:" in result


class TestSSEEventEdgeCases:
    """Edge case tests for SSEEvent."""

    def test_serialize_data_with_special_characters(self) -> None:
        """Data with special characters is preserved."""
        event = SSEEvent(data="hello: world")
        result = event.serialize()
        assert result == "data: hello: world\n\n"

    def test_serialize_data_with_unicode(self) -> None:
        """Unicode data is properly handled."""
        event = SSEEvent(data="Hello \u4e16\u754c")
        result = event.serialize()
        assert result == "data: Hello \u4e16\u754c\n\n"

    def test_serialize_numeric_id(self) -> None:
        """Numeric string id is handled correctly."""
        event = SSEEvent(data="test", id="12345")
        result = event.serialize()
        assert "id: 12345\n" in result

    def test_serialize_event_name_with_hyphen(self) -> None:
        """Event name with hyphen is preserved."""
        event = SSEEvent(data="test", event="my-event")
        result = event.serialize()
        assert "event: my-event\n" in result

    def test_serialize_returns_string_type(self) -> None:
        """Serialize method returns a string."""
        event = SSEEvent(data="test")
        result = event.serialize()
        assert isinstance(result, str)

    def test_serialize_whitespace_only_data(self) -> None:
        """Whitespace-only data is preserved."""
        event = SSEEvent(data="   ")
        result = event.serialize()
        assert result == "data:    \n\n"

    def test_serialize_data_with_carriage_return_newline(self) -> None:
        """Data with CRLF line endings is handled."""
        event = SSEEvent(data="line1\r\nline2")
        result = event.serialize()
        assert "data:" in result
        assert result.endswith("\n\n")
