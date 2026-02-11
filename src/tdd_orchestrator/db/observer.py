"""Observer pattern for task status change callbacks.

Provides a simple callback registry that dispatches task status change
events to registered observers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
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


class DBObserver:
    """Database observer that polls for task status changes.

    Monitors the tasks table for status changes and dispatches events to
    registered callbacks via the dispatch_task_callbacks mechanism.
    """

    def __init__(
        self,
        db: Any,  # OrchestratorDB, avoid circular import
        poll_interval: float = 1.0,
    ) -> None:
        """Initialize the DB observer.

        Args:
            db: The OrchestratorDB instance to observe.
            poll_interval: How frequently to poll for changes (seconds).
        """
        self._db = db
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._task_states: dict[str, str] = {}  # task_key -> status

    @property
    def is_running(self) -> bool:
        """Return whether the observer is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the observer polling loop."""
        if self._running:
            return

        self._running = True
        # Initialize task states from current database state
        await self._refresh_task_states()
        # Start the polling task
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the observer polling loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            # Cancel the polling task
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _refresh_task_states(self) -> None:
        """Refresh the internal cache of task states from the database."""
        # Query all tasks and their current status
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        async with self._db._conn.execute(
            "SELECT task_key, status FROM tasks"
        ) as cursor:
            rows = await cursor.fetchall()
            self._task_states = {str(row[0]): str(row[1]) for row in rows}

    async def _poll_loop(self) -> None:
        """Main polling loop that checks for status changes."""
        while self._running:
            try:
                await self._poll()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                # Clean shutdown
                break
            except Exception as e:
                logger.error("Error in DB observer poll loop: %s", e, exc_info=True)
                # Continue polling despite errors
                await asyncio.sleep(self._poll_interval)

    async def _poll(self) -> None:
        """Single poll cycle - check for task status changes and dispatch events."""
        # Get current state from database
        await self._db._ensure_connected()
        if not self._db._conn:
            return

        async with self._db._conn.execute(
            "SELECT task_key, status FROM tasks"
        ) as cursor:
            rows = await cursor.fetchall()
            current_states = {str(row[0]): str(row[1]) for row in rows}

        # Detect changes
        for task_key, new_status in current_states.items():
            old_status = self._task_states.get(task_key)

            # If status changed, dispatch event
            if old_status is not None and old_status != new_status:
                event = {
                    "task_id": task_key,
                    "old_status": old_status,
                    "new_status": new_status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                dispatch_task_callbacks(event)

        # Update our cached state
        self._task_states = current_states
