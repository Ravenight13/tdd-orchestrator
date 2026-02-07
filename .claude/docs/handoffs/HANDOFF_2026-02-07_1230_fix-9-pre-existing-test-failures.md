---
session_date: 2026-02-07
session_time: 12:30:05
status: Fix 9 pre-existing test failures
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Handoff: Fix 9 pre-existing test failures

**Date**: 2026-02-07 | **Time**: 12:30:05 CST

---

## Resume Checklist

Before starting, review:
1. This handoff document
2. Recent git log: `git log --oneline -10`
3. Run health check: `/cc-ready`

```bash
# Quick health check
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m pytest tests/unit/ --tb=no -q
python -m ruff check src/
python -m mypy src/ --strict
```

---

## Executive Summary

The 4 oversized module splits are committed and all post-split bugs are fixed (495 tests passing, mypy/ruff clean). 9 pre-existing test failures remain that must be resolved before new work begins. These fall into 3 categories: tool PATH resolution (4), missing test file mocks (4), and missing git repo in test fixture (1). An additional concern is that integration tests commit to the real git repo during runs.

---

## Current State

- **Branch**: main
- **Known issues**: 9 pre-existing test failures (see priorities below)
- **Uncommitted changes**: `tdd-progress.md`, `.claude/rules/task-execution.md`, `uv.lock` (test artifacts from prior session, safe to ignore or clean up)

---

## Next Priorities

1. **Fix test_code_verifier.py (4 failures)** -- `ruff` and `mypy` not on system PATH when run as subprocesses. The code verifier spawns these tools but doesn't resolve them from the venv. **Root cause**: `code_verifier.py` uses bare `ruff`/`mypy` commands. **Fix**: Resolve tool paths from `sys.executable` parent or accept a configurable tool path. **Files**: `src/tdd_orchestrator/code_verifier.py`, `tests/integration/test_code_verifier.py`.

2. **Fix test_green_retry_integration.py (4 failures)** -- Full pipeline tests hit `blocked-static-review` because AST checker tries to read mock file paths that don't exist. **Root cause**: `worker.py` runs static review which calls AST checker on `tests/test_retry.py` (doesn't exist). **Fix**: Mock the `StaticReviewCircuitBreaker` or `CodeVerifier.check_ast()` in these tests, or create the expected temp files. **Files**: `tests/integration/test_green_retry_integration.py`.

3. **Fix test_worker_budget.py (1 failure)** -- `test_pool_stops_on_budget_exhaustion` fails because `GitStashGuard` runs `git status` in a temp dir that isn't a git repo. **Root cause**: Test creates `WorkerPool` without providing a git repo path. **Fix**: Use the `git_repo` fixture from `tests/integration/conftest.py` or mock `GitStashGuard`. **Files**: `tests/integration/test_worker_budget.py`.

4. **(Bonus) Isolate integration tests from real git** -- The Worker's `process_task` commits to the REAL repository during test runs, creating `wip(TDD-RETRY-01)` commits that pollute history. This caused issues during this session where test commits swept up uncommitted work. **Fix**: Ensure all integration tests that exercise the Worker use a temp git repo fixture.

---

## Key Context

- **Full session log**: `.claude/docs/summaries/SESSION_2026-02-07_1230_committed-module-splits-and-fixed-integration-tests.md`
- **CLAUDE.md**: Project conventions and rules
- **Architecture**: `docs/ARCHITECTURE.md`
- **Error details**: Run `pytest tests/integration/test_code_verifier.py tests/integration/test_green_retry_integration.py tests/integration/test_worker_budget.py -v --tb=short` to see all 9 failures with tracebacks

---

*Handoff created: 2026-02-07 12:30:05 CST*
