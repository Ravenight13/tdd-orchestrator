# PLAN: Streaming-Aware Decomposition Pipeline

## Context

API-TDD-09-03 (SSE Events Endpoint) failed 3 GREEN attempts because the RED stage generated tests that hang forever. Root cause: the decomposition pipeline produces `implementation_hints: None` for SSE tasks, so the test writer has no awareness that streaming endpoints need special testing patterns (sentinels, timeouts, direct generator testing). This fix makes the pipeline detect streaming tasks and inject domain-specific testing guidance automatically.

## Approach

Three targeted layers, no over-engineering:

1. **Detect + inject** — New module detects streaming tasks by keyword and injects testing guidance into `implementation_hints` (deterministic, zero LLM cost)
2. **Surface hints in RED** — The RED stage prompt currently ignores `implementation_hints`; make it visible so the test writer uses them
3. **Complexity classification** — Ensure SSE/WebSocket keywords trigger "high" complexity (Opus model)

## Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/tdd_orchestrator/decomposition/streaming_hints.py` | **CREATE** | ~120 |
| `src/tdd_orchestrator/decomposition/decomposer.py` | Modify (5 lines at ~262) | 791→796 |
| `src/tdd_orchestrator/prompt_builder.py` | Modify (~10 lines in `red()`) | 548→558 |
| `src/tdd_orchestrator/prompt_templates.py` | Modify (add `{hints_section}` to RED) | 479→481 |
| `src/tdd_orchestrator/complexity_detector.py` | Modify (add keywords) | 124→128 |
| `tests/unit/test_streaming_hints.py` | **CREATE** | ~120 |
| `tests/unit/test_prompt_builder.py` | Modify (add hints tests) | +15 |

## Implementation Sequence

### Step 1: `streaming_hints.py` (new module)

Create `src/tdd_orchestrator/decomposition/streaming_hints.py`:

- `STREAMING_KEYWORDS` — list of detection keywords: `sse`, `server-sent event`, `eventsource`, `event stream`, `websocket`, `text/event-stream`, `streaming endpoint`, `async generator`
- `STREAMING_TEST_HINTS` — constant string with SSE/streaming testing patterns:
  - Never use `await client.get()` on streaming endpoints
  - Always use sentinel-based stream termination
  - Always wrap stream reads with `asyncio.wait_for`
  - Test generators directly, not through HTTP
  - For HTTP-level tests, use `client.stream()` context manager
- `detect_streaming_task(task) -> bool` — keyword match against title + goal + criteria + components
- `enrich_streaming_hints(tasks) -> list[DecomposedTask]` — post-process tasks after Pass 4, inject hints for streaming tasks, force `complexity="high"`

Design: deterministic (no LLM calls), uses `dataclasses.replace()` for immutability.

### Step 2: Wire into `decomposer.py`

At ~line 262, after Pass 4 completes, add:

```python
from .streaming_hints import enrich_streaming_hints
tasks = enrich_streaming_hints(tasks)
```

5 lines including a log message for visibility.

### Step 3: Surface hints in RED stage prompt

**`prompt_templates.py`**: Add `{hints_section}` placeholder to `RED_PROMPT_TEMPLATE` before the `## REQUIREMENTS` section.

**`prompt_builder.py`**: In `red()` method, read `implementation_hints` from the task dict, truncate to `MAX_HINTS_CONTENT` (4000 chars), escape braces, format into hints section. Pass to template.

### Step 4: Complexity detector keywords

In `complexity_detector.py`, add to the `data_processing.high` list:
`"sse"`, `"server-sent event"`, `"eventsource"`, `"websocket"`

### Step 5: Tests

**`tests/unit/test_streaming_hints.py`** (~120 lines):
- `detect_streaming_task()` identifies SSE/WebSocket/streaming tasks
- `detect_streaming_task()` returns False for normal tasks
- `enrich_streaming_hints()` injects hints for streaming tasks
- `enrich_streaming_hints()` preserves existing hints
- `enrich_streaming_hints()` forces complexity to "high"
- `enrich_streaming_hints()` leaves non-streaming tasks unchanged

**`tests/unit/test_prompt_builder.py`** (+15 lines):
- `red()` includes hints section when task has `implementation_hints`
- `red()` omits hints section when `implementation_hints` is None

## Verification

```bash
.venv/bin/pytest tests/unit/test_streaming_hints.py tests/unit/test_prompt_builder.py -v
.venv/bin/mypy src/ --strict
.venv/bin/ruff check src/
```

## What This Does NOT Do

- Does not change LLM prompts in Pass 4 — deterministic injection is more reliable
- Does not modify VERIFY timeout — hints prevent the hanging in the first place
- Does not affect non-streaming tasks — keyword detection is the gate
