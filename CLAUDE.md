# CLAUDE.md

## Project Overview

TDD Orchestrator is a parallel task execution engine for Test-Driven Development workflows. It manages multiple Claude AI workers executing TDD tasks concurrently, with three-level circuit breakers for resilience and a 4-pass LLM decomposition pipeline for breaking PRDs into atomic TDD tasks.

**Focus**: Standalone pip-installable library and CLI tool.
**Team**: Cliff Clarke (Owner/Architect) - Solo project

## Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.11+ | Strict mypy, asyncio throughout |
| Database | SQLite via aiosqlite | Optimistic locking, WAL mode |
| CLI | Click | `tdd-orchestrator` command |
| Build | hatchling | `pip install -e ".[dev,sdk]"` |
| Testing | pytest + pytest-asyncio | `asyncio_mode = "auto"` |
| Linting | ruff | line-length=100, target=py311 |
| Type checking | mypy | strict=true |
| SDK | claude-agent-sdk | Optional dependency, graceful degradation |

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
```

## Quick Reference

- **TDD Pipeline**: RED → RED_FIX → GREEN → VERIFY → (FIX → RE_VERIFY)
- **Circuit Breakers**: Stage (per task:stage), Worker (per worker), System (global). States: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Worker Pool**: Claim-based distribution with optimistic locking. Single-branch or multi-branch modes.
- **Decomposition**: 4-pass LLM pipeline (extract cycles → atomize → acceptance criteria → implementation hints)
- **Model Selection**: RED/decomposition always Opus. Low=Haiku, Medium=Sonnet, High=Opus. GREEN retries escalate.
- **SDK is optional**: Always guard imports with try/except. Never assume it's installed.

## Rules

@.claude/rules/security.md
@.claude/rules/dev-patterns.md

## Non-Negotiable Rules

- **NEVER** use f-strings or string formatting for SQL queries
- **NEVER** use `shell=True` in subprocess calls
- **NEVER** hardcode API keys or credentials
- **NEVER** assume Claude SDK is installed (it's optional)
- **ALWAYS** use parameterized queries with `?` placeholders
- **ALWAYS** maintain mypy strict compliance
- **ALWAYS** run `ruff check` and `mypy --strict` before committing
- **ALWAYS** write tests for new functionality

## Commit Conventions

Use conventional commits: `<type>(<scope>): <description>`

- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`
- Keep title under 72 characters, imperative mood
- Body explains **why**, not just what
- Always include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Session handoffs use: `chore(session): <session-slug>`

## Compaction

When compacting, always preserve: the full list of modified files, active todo items, any test commands that were run, and the current session goal.

## Key References

- Architecture: @docs/ARCHITECTURE.md
- Database schema: `schema/schema.sql`
- Domain models: `src/tdd_orchestrator/models.py`
- Build config: @pyproject.toml

## Session Workflow

Start: `/cc-ready` | End: `/cc-handoff` | Health: `/quick-test` | Verify: `/verify-implementation`

## Agents

| Agent | Purpose |
|-------|---------|
| `architect` | System architecture, circuit breaker design, concurrency patterns |
| `planner` | Feature implementation planning, phase breakdown |
| `docs-writer` | Library API docs, CLI reference, architecture docs |
| `security-auditor` | SQL injection, subprocess safety, dependency CVEs |
