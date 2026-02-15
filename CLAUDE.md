# CLAUDE.md

TDD Orchestrator — parallel TDD task execution engine with circuit breakers and LLM decomposition. Solo project by Cliff Clarke. Standalone pip-installable library and CLI.

## Essential Commands

```bash
pip install -e ".[dev,sdk]"        # Install with all dependencies
ruff check src/                     # Linting
mypy src/ --strict                  # Type checking
pytest tests/ -v                    # All tests
pytest tests/unit/ -v               # Unit tests only (fast)
tdd-orchestrator init               # Initialize database
tdd-orchestrator health             # Check health
tdd-orchestrator run -p -w 2        # Run with 2 parallel workers
tdd-orchestrator serve              # Start API server
tdd-orchestrator run-prd <file>     # End-to-end PRD pipeline
```

## Things That Will Bite You

- **SDK imports**: Claude Agent SDK is optional. Always guard with `try/except ImportError` and `SDK_AVAILABLE` flag.
- **asyncio_mode**: Set to `"auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorator needed.
- **src-layout imports**: File paths start with `src/` but imports must NOT use `from src.tdd_orchestrator`. Never create `src/__init__.py`.
- **aiosqlite rows**: Row access returns `Any` — wrap with `str()`, `int()`, etc. for typed returns.
- **DB singleton in tests**: `get_db()` leaks connections between tests. Use `reset_db()` in fixtures.
- **`_run_with_cleanup()`**: Calls `os._exit(0)` — never test through it, test `main()` directly.

## Quick Reference

- **TDD Pipeline**: RED → RED_FIX → GREEN → VERIFY → (FIX → RE_VERIFY)
- **Circuit Breakers**: Stage (per task:stage), Worker (per worker), System (global). States: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Worker Pool**: Claim-based distribution with optimistic locking. Single-branch or multi-branch modes.
- **Decomposition**: 4-pass LLM pipeline (extract cycles → atomize → acceptance criteria → implementation hints)
- **Model Selection**: RED/decomposition always Opus. Low=Haiku, Medium=Sonnet, High=Opus. GREEN retries escalate.

## Code Organization (Mission Critical)

- Many small files over few large files
- 200-400 lines typical, **800 absolute max** per file
- High cohesion, low coupling — each module owns one responsibility
- When a file grows past 400 lines, proactively split it before it hits the limit
- When adding new functionality, create a new module rather than appending to an existing one

**Splitting signals**: multiple classes, unrelated functions grouped together, file requires scrolling to understand, imports span many unrelated domains.

## Non-Negotiable Rules

Security rules enforced in `.claude/rules/security.md` (auto-loaded).

- **NEVER** let a file exceed 800 lines — split by responsibility before reaching the limit
- **NEVER** assume Claude SDK is installed (it's optional)
- **ALWAYS** maintain mypy strict compliance
- **ALWAYS** run `ruff check` and `mypy --strict` before committing
- **ALWAYS** write tests for new functionality

## Commit Conventions

Conventional commits: `<type>(<scope>): <description>` — types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`. Title under 72 chars, imperative mood. Body explains **why**. Always include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`. Session handoffs: `chore(session): <session-slug>`.

## Compaction

When compacting, always preserve: the full list of modified files, active todo items, any test commands that were run, and the current session goal.

## Master Documents

Living project documents in `.claude/docs/master/`:
- `DECISIONS_ACTIVE.md` — Current decisions (read at session start)
- `WIP.md` — Work in progress across sessions
- `DEAD_ENDS.md` — Failed approaches (check before proposing solutions)
- `ASSUMPTIONS.md` — Foundational beliefs (flag if challenged)
- `KNOWLEDGE_DEBT.md` — Documentation gaps from corrections
- `DECISIONS_SUPERSEDED.md` — Historical decisions archive

## Key References

- Architecture: `docs/ARCHITECTURE.md`
- Database schema: `schema/schema.sql`
- Domain models: `src/tdd_orchestrator/models.py`
- Build config: `pyproject.toml`

## Session Workflow

Start: `/cc-ready` | End: `/cc-handoff` | Health: `/quick-test` | Verify: `/verify-implementation`
