"""Observer pattern for task status change callbacks.

Provides a simple callback registry that dispatches task status change
events to registered observers.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Module-level callback registry
_callbacks: list[Callable[[dict[str, Any]], None]] = []


def register_task_callback(callback: Callable[[dict[str, Any]], None]) -> bool | None:
    """Register a callback to be invoked on task status changes.

    Args:
        callback: A callable that accepts a dict with keys:
            - task_id: str
            - old_status: str
            - new_status: str
            - timestamp: str

    Returns:
        True on success, or None.
    """
    _callbacks.append(callback)
    return True


def unregister_task_callback(callback: Callable[[dict[str, Any]], None]) -> bool | None:
    """Unregister a previously registered callback.

    Args:
        callback: The callback to remove.

    Returns:
        True if callback was found and removed, False or None otherwise.
    """
    try:
        _callbacks.remove(callback)
        return True
    except ValueError:
        # Callback not in list
        return False


def dispatch_task_callbacks(event: dict[str, Any]) -> None:
    """Dispatch a task status change event to all registered callbacks.

    Invokes each callback in registration order. If a callback raises an
    exception, the exception is logged and remaining callbacks continue
    to execute.

    Args:
        event: A dict containing task status change information with keys:
            - task_id: str
            - old_status: str
            - new_status: str
            - timestamp: str
    """
    # Iterate over a copy to handle callbacks that modify the list during dispatch
    for callback in _callbacks[:]:
        try:
            callback(event)
        except Exception as e:
            logger.error(
                "Callback %s raised exception: %s",
                callback,
                e,
                exc_info=True,
            )
