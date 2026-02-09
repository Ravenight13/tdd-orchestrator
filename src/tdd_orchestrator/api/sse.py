"""SSE (Server-Sent Events) event formatting."""

from dataclasses import dataclass


@dataclass
class SSEEvent:
    """Represents a Server-Sent Event with proper wire protocol formatting."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def serialize(self) -> str:
        """Serialize the event to SSE wire protocol format.

        Returns:
            Formatted SSE event string ending with double newline.
        """
        lines: list[str] = []

        # Add fields in correct order: id, event, retry, data
        if self.id is not None:
            lines.append(f"id: {self.id}")

        if self.event is not None:
            lines.append(f"event: {self.event}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # Handle multi-line data by splitting on newlines
        data_lines = self.data.split("\n")
        for data_line in data_lines:
            lines.append(f"data: {data_line}")

        # Join all lines with newline and add trailing double newline
        return "\n".join(lines) + "\n\n"
