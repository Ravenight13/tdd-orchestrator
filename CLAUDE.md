# CLAUDE.md

TDD Orchestrator — parallel TDD task engine. Circuit breakers + LLM decomposition. Solo project Cliff Clarke. Standalone pip lib + CLI.

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
tdd-orchestrator init-prd --name X  # Scaffold PRD template
tdd-orchestrator run-prd <file>     # End-to-end PRD pipeline
```

## Things That Will Bite You

- **SDK imports**: Claude Agent SDK optional. Guard with `try/except ImportError` + `SDK_AVAILABLE` flag.
- **asyncio_mode**: Set `"auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorator needed.
- **src-layout imports**: Paths start `src/` but imports must NOT use `from src.tdd_orchestrator`. Never create `src/__init__.py`.
- **aiosqlite rows**: Row access returns `Any` — wrap `str()`, `int()` for typed returns.
- **DB singleton in tests**: `get_db()` leaks connections. Use `reset_db()` in fixtures.
- **`_run_with_cleanup()`**: Calls `os._exit(0)` — never test through it, test `main()` directly.

## Quick Reference

- **TDD Pipeline**: RED → RED_FIX → GREEN → VERIFY → (FIX → RE_VERIFY)
- **Circuit Breakers**: Stage (per task:stage), Worker (per worker), System (global). States: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Worker Pool**: Claim-based distribution, optimistic locking. Single-branch or multi-branch modes.
- **Decomposition**: 4-pass LLM pipeline (extract cycles → atomize → acceptance criteria → implementation hints)
- **Model Selection**: RED/decomposition always Opus. Low=Haiku, Medium=Sonnet, High=Opus. GREEN retries escalate.

## Code Organization (Mission Critical)

- Many small files over few large
- 200-400 lines typical, **800 absolute max** per file
- High cohesion, low coupling — each module one responsibility
- File past 400 lines → split before hits limit
- New functionality → new module, not append to existing

**Splitting signals**: multiple classes, unrelated functions grouped, file needs scrolling to grok, imports span many unrelated domains.

## Non-Negotiable Rules

Security rules in `.claude/rules/security.md` (auto-loaded).

- **NEVER** let file exceed 800 lines — split by responsibility before limit
- **NEVER** assume Claude SDK installed (optional)
- **ALWAYS** keep mypy strict compliance
- **ALWAYS** run `ruff check` + `mypy --strict` before commit
- **ALWAYS** write tests for new functionality

## Commit Conventions

Conventional commits: `<type>(<scope>): <description>` — types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`. Title under 72 chars, imperative. Body = **why**. Always include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`. Session handoffs: `chore(session): <session-slug>`.

## Compaction

When compacting, preserve: full list modified files, active todos, test commands run, current session goal.

## Master Documents

Living docs in `.claude/docs/master/`:
- `DECISIONS_ACTIVE.md` — Current decisions (read at session start)
- `WIP.md` — Work in progress across sessions
- `DEAD_ENDS.md` — Failed approaches (check before proposing solutions)
- `ASSUMPTIONS.md` — Foundational beliefs (flag if challenged)
- `KNOWLEDGE_DEBT.md` — Doc gaps from corrections
- `DECISIONS_SUPERSEDED.md` — Historical decisions archive

## Key References

- Architecture: `docs/ARCHITECTURE.md`
- Database schema: `schema/schema.sql`
- Domain models: `src/tdd_orchestrator/models.py`
- Build config: `pyproject.toml`

## Session Workflow

Start: `/cc-ready` | End: `/cc-handoff` | Health: `/quick-test` | Verify: `/verify-implementation`