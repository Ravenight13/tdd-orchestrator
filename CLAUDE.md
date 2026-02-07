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

## File Structure

```
src/tdd_orchestrator/
├── cli.py                  # Click CLI entry point
├── models.py               # Domain models
├── database.py             # SQLite persistence (aiosqlite)
├── worker_pool.py          # Parallel worker management
├── circuit_breaker.py      # 3-level circuit breakers
├── circuit_breaker_config.py
├── decomposition/          # 4-pass LLM decomposition pipeline
│   ├── decomposer.py       #   Pipeline orchestrator
│   ├── generator.py        #   LLM prompt generation
│   ├── parser.py           #   Response parsing
│   ├── validators.py       #   Output validation
│   └── ...
├── decompose_spec.py       # Spec decomposition entry point
├── prompt_builder.py       # LLM prompt construction
├── ast_checker.py          # AST-based code analysis
├── code_verifier.py        # Code verification
├── complexity_detector.py  # Complexity analysis
├── health.py               # Health checks
├── hooks.py                # Event hooks
├── mcp_tools.py            # MCP tool integration
├── metrics.py              # Prometheus-style metrics
├── notifications.py        # Slack notifications
├── git_coordinator.py      # Git operations
├── git_stash_guard.py      # Stash safety
├── merge_coordinator.py    # Branch merging
├── progress_writer.py      # Progress output
└── task_loader.py          # Task file loading
tests/
├── unit/                   # Fast, in-memory DB tests
├── integration/            # Full system tests
└── e2e/                    # End-to-end tests
```

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

## Environment Variables

```bash
# Optional — SDK integration
ANTHROPIC_API_KEY=               # For Claude SDK workers

# Optional — Notifications
SLACK_WEBHOOK_URL=               # Slack webhook for alerts

# Optional — Tuning
TDD_MAX_WORKERS=3                # Worker pool size
TDD_MAX_INVOCATIONS=100          # Max task invocations
TDD_CIRCUIT_STAGE_MAX_FAILURES=5
TDD_CIRCUIT_WORKER_MAX_CONSECUTIVE=5
```

## Quick Reference

- **TDD Pipeline**: RED → RED_FIX → GREEN → VERIFY → (FIX → RE_VERIFY)
- **Circuit Breakers**: Stage (per task:stage), Worker (per worker), System (global). States: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Worker Pool**: Claim-based distribution with optimistic locking. Single-branch or multi-branch modes.
- **Decomposition**: 4-pass LLM pipeline (extract cycles → atomize → acceptance criteria → implementation hints)
- **Model Selection**: RED/decomposition always Opus. Low=Haiku, Medium=Sonnet, High=Opus. GREEN retries escalate.
- **SDK is optional**: Always guard imports with try/except. Never assume it's installed.

## Code Organization (Mission Critical)

- Many small files over few large files
- 200-400 lines typical, **800 absolute max** per file
- High cohesion, low coupling — each module owns one responsibility
- Organize by feature/domain, not by type
- When a file grows past 400 lines, proactively split it before it hits the limit
- When adding new functionality, create a new module rather than appending to an existing one

**Splitting signals**: multiple classes, unrelated functions grouped together,
file requires scrolling to understand, imports span many unrelated domains.

## Testing Strategy

- **Unit tests** (`tests/unit/`): Fast, in-memory SQLite, no external deps
- **Integration tests** (`tests/integration/`): Full system, real DB
- **E2E tests** (`tests/e2e/`): End-to-end workflow validation
- Write tests first (TDD) — RED test before GREEN implementation
- All async tests use `asyncio_mode = "auto"` (no decorator needed)
- Coverage target: 80%+ on core modules

## Rules

@.claude/rules/security.md
@.claude/rules/dev-patterns.md

## Non-Negotiable Rules

- **NEVER** let a file exceed 800 lines — split by responsibility before reaching the limit
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
| `python-reviewer` | Code review: async patterns, mypy strict, Pythonic idioms |
| `build-error-resolver` | Minimal-diff fixes for mypy, ruff, and pytest failures |
| `refactor-cleaner` | Dead code removal, file splitting, 800-line enforcement |
| `e2e-runner` | Playwright E2E tests for frontend and CLI workflows |
