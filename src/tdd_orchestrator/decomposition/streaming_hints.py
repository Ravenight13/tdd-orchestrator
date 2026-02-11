"""Streaming-aware hint injection for decomposed tasks.

Detects tasks that involve SSE, WebSocket, or streaming endpoints and injects
domain-specific testing guidance into their implementation_hints. This prevents
common failure modes like hanging tests caused by awaiting streaming responses
without timeouts or sentinel-based termination.

This module is deterministic (zero LLM cost) — it enriches tasks post-Pass-4
via keyword matching.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .decomposer import DecomposedTask

logger = logging.getLogger(__name__)

STREAMING_KEYWORDS: list[str] = [
    "sse",
    "server-sent event",
    "eventsource",
    "event stream",
    "text/event-stream",
    "websocket",
    "streaming endpoint",
    "async generator",
    "event-stream",
]

STREAMING_TEST_HINTS: str = """\
### Streaming / SSE Testing Patterns

**CRITICAL: Streaming endpoints hang forever if tested incorrectly.**

1. **Never `await client.get()` on streaming endpoints** — the response never
   completes because the server keeps the connection open. This is the #1 cause
   of hanging tests.

2. **Use sentinel-based stream termination** — have the generator yield a final
   sentinel value (e.g., `None` in a queue, or a `data: [DONE]` event) so the
   consumer knows when to stop reading.

3. **Always wrap with `asyncio.wait_for(coro, timeout=...)`** — even with
   sentinels, add a timeout as a safety net:
   ```python
   result = await asyncio.wait_for(consume_stream(), timeout=5.0)
   ```

4. **Test the async generator directly** — instead of going through HTTP,
   call the generator function and iterate with `async for`:
   ```python
   events = []
   async for event in my_generator():
       events.append(event)
   assert len(events) > 0
   ```

5. **For HTTP-level tests, use `client.stream()` context manager** (httpx) or
   the equivalent streaming API of your test client:
   ```python
   async with client.stream("GET", "/events") as response:
       async for line in response.aiter_lines():
           ...
   ```

6. **Keep test data small** — use 2-3 events max to keep tests fast and
   deterministic.
"""


def detect_streaming_task(task: DecomposedTask) -> bool:
    """Check if a task involves streaming by keyword matching.

    Searches title, goal, acceptance_criteria, and components for any of the
    known streaming keywords (case-insensitive substring match).

    Args:
        task: A DecomposedTask to check.

    Returns:
        True if any streaming keyword is found.
    """
    searchable = " ".join([
        task.title or "",
        task.goal or "",
        " ".join(task.acceptance_criteria or []),
        " ".join(task.components or []),
    ]).lower()

    return any(keyword in searchable for keyword in STREAMING_KEYWORDS)


def enrich_streaming_hints(tasks: list[DecomposedTask]) -> list[DecomposedTask]:
    """Post-process tasks to inject streaming-specific testing hints.

    For each task that matches streaming keywords:
    - Prepends STREAMING_TEST_HINTS to existing implementation_hints
    - Forces complexity to "high" (ensures Opus model selection)

    Non-streaming tasks pass through unchanged.

    Args:
        tasks: List of DecomposedTask objects (typically after Pass 4).

    Returns:
        New list with streaming tasks enriched (uses dataclasses.replace
        for immutability).
    """
    result: list[DecomposedTask] = []
    for task in tasks:
        if detect_streaming_task(task):
            existing = task.implementation_hints or ""
            combined = STREAMING_TEST_HINTS + "\n" + existing if existing else STREAMING_TEST_HINTS
            enriched = replace(
                task,
                implementation_hints=combined,
                complexity="high",
            )
            logger.info("Streaming hints injected for %s", task.task_key)
            result.append(enriched)
        else:
            result.append(task)
    return result
