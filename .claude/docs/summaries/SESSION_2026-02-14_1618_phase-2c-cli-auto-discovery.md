---
session_date: 2026-02-14
session_time: 16:18:36
status: Wired all CLI commands to project config auto-discovery (Phase 2C)
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Wired all CLI commands to project config auto-discovery (Phase 2C)

**Date**: 2026-02-14 | **Time**: 16:18:36 CST

---

## Executive Summary

Implemented Phase 2C of the production roadmap: added a shared `resolve_db_for_cli()` helper and wired all 9 remaining CLI commands (`run`, `status`, `serve`, `circuits status/health/reset`, `validate phase/run/all`) to auto-discover `.tdd/orchestrator.db` when `--db` is omitted. The `run` command also resolves `--workers` from project config. All 1587 unit tests pass, mypy strict and ruff clean.

---

## Key Decisions

- **D1: Shared helper in domain module** -- `resolve_db_for_cli()` lives in `project_config.py` (no Click import), callers handle errors
- **D3: `--workers` default changed to `None`** -- Resolution chain: explicit `--workers` > `config.tdd.max_workers` > fallback `2`
- **D5: No singleton pattern needed** -- Unlike `ingest`, these commands create `OrchestratorDB(path)` directly
- **D7: Resolution in sync Click handlers** -- Matching the `ingest` pattern: resolve in sync handler, pass resolved `Path` to async functions
- **D8: No legacy fallback** -- Commands without `--db` and without `.tdd/` error with a helpful message suggesting `init` or `--db`

---

## Completed Work

### Accomplishments

- Added `resolve_db_for_cli()` shared helper to `project_config.py` returning `tuple[Path, ProjectConfig | None]`
- Wired `run`, `status`, `serve` commands in `cli.py` with auto-discovery and config-based worker resolution
- Wired `circuits status/health/reset` commands in `cli_circuits.py` with auto-discovery
- Wired `validate phase/run/all` commands in `cli_validate.py` with auto-discovery
- Updated all async function signatures from `str | None` to `Path`
- Fixed 12 pre-existing serve CLI tests that needed `resolve_db_for_cli` mock
- Added 23 new tests across 4 test files (5 helper tests, 10 cli tests, 5 circuits tests, 3+5 validate tests)
- Created new `tests/unit/test_cli_circuits.py` test file

### Files Modified

**Source (4 files):**
- `src/tdd_orchestrator/project_config.py` -- Added `resolve_db_for_cli()` (~25 lines)
- `src/tdd_orchestrator/cli.py` -- Wired run/status/serve + workers config resolution
- `src/tdd_orchestrator/cli_circuits.py` -- Wired 3 circuit commands + added `sys`/`Path` imports
- `src/tdd_orchestrator/cli_validate.py` -- Wired 3 validate commands

**Tests (5 files):**
- `tests/unit/test_project_config.py` -- Added `TestResolveDbForCli` class (5 tests)
- `tests/unit/test_cli.py` -- Added auto-discovery test classes (10 tests)
- `tests/unit/test_cli_circuits.py` -- NEW file (5 tests)
- `tests/unit/test_cli_validate.py` -- Updated existing + added auto-discovery tests
- `tests/unit/api/test_serve_cli.py` -- Fixed 12 tests for auto-discovery compatibility

### Git State

- **Branch**: main
- **Recent commits**: `40ad6bb feat(cli): wire all commands to project config auto-discovery (Phase 2C)`
- **Uncommitted changes**: None

---

## Known Issues

- `cli_circuits.py` at ~450 lines -- above 400-line soft limit but under 800 hard limit. Acceptable for cohesive subcommand group. Flag for future if more commands added.
- Phase 1 API layer is substantially built (20 source files, 33 test files) -- the `run_server` in `cli.py` is a stub but `api/serve.py` has the real implementation. Need to wire `serve` CLI command to the real API server.

---

## Next Priorities

1. **Plan remaining Phase 2 work** -- Assess what's left: PRD-to-PR pipeline (`run-prd`), checkpoint & resume, PRD template system
2. **Wire `serve` command to real API server** -- `cli.py:run_server()` is a stub but `api/serve.py` exists with full FastAPI app
3. **Phase 3: Web Dashboard** -- React + Vite + Tailwind setup, task board, worker health panel

---

*Session logged: 2026-02-14 16:18:36 CST*
