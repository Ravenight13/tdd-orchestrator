# Development Patterns - TDD Orchestrator

## Async Everything

All database and worker operations MUST be async. Use `async def` and `await` consistently.

```python
async with OrchestratorDB("tasks.db") as db:
    tasks = await db.get_ready_tasks()
```

## Parameterized SQL Only

NEVER use f-strings for SQL. ALWAYS use `?` placeholders.

```python
# CORRECT
await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))

# WRONG - SQL injection risk
await db.execute(f"SELECT * FROM tasks WHERE id = '{task_id}'")
```

## Optional SDK Pattern

The Claude Agent SDK is optional. Always check availability:

```python
try:
    from claude_agent_sdk import ...
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
```

## Test Patterns

Tests use pytest-asyncio with `asyncio_mode = "auto"`. No decorator needed.

```python
async def test_something():
    async with OrchestratorDB(":memory:") as db:
        await db.initialize()
        # test logic here
```

## Decision Documentation

Architectural decisions should include:
- **Confidence**: LOW / MEDIUM / HIGH
- **Options**: What alternatives were considered
- **Trade-offs**: Pros/cons of chosen approach
- **"Would Change If..."**: Conditions that would trigger revisiting

Store in `.claude/docs/scratchpads/` or as ADRs in `docs/`.
