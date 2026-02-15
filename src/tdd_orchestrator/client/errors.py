"""Custom exceptions for the TDD Orchestrator client."""

from __future__ import annotations


class ClientError(Exception):
    """Base error for client HTTP failures.

    Attributes:
        status_code: The HTTP status code returned by the server.
        message: A human-readable error description.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class NotFoundError(ClientError):
    """Raised when the server returns a 404 Not Found response."""

    def __init__(self, message: str = "Not found") -> None:
        super().__init__(status_code=404, message=message)


class ServerError(ClientError):
    """Raised when the server returns a 5xx response."""

    def __init__(self, status_code: int = 500, message: str = "Server error") -> None:
        super().__init__(status_code=status_code, message=message)
