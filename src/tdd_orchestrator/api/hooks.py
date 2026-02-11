"""Global state management for SSE broadcaster instances.

Provides a simple module-level singleton pattern for accessing the SSE
broadcaster instance across the application.
"""

from __future__ import annotations

from typing import Any

# Module-level global state
_sse_broadcaster: Any | None = None


def get_sse_broadcaster() -> Any | None:
    """Get the current SSE broadcaster instance.

    Returns:
        The current broadcaster instance, or None if not set.
    """
    return _sse_broadcaster


def set_sse_broadcaster(broadcaster: Any | None) -> None:
    """Set the global SSE broadcaster instance.

    Args:
        broadcaster: The broadcaster instance to set, or None to clear.
    """
    global _sse_broadcaster
    _sse_broadcaster = broadcaster


def reset_sse_broadcaster() -> None:
    """Reset the global SSE broadcaster state to None."""
    global _sse_broadcaster
    _sse_broadcaster = None
