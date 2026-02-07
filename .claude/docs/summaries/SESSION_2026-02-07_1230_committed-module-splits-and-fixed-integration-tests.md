---
session_date: 2026-02-07
session_time: 12:30:05
status: Committed module splits and fixed integration tests
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Committed module splits and fixed integration tests

**Date**: 2026-02-07 | **Time**: 12:30:05 CST

---

## Executive Summary

Committed the 4 oversized module splits (circuit_breaker, worker_pool, database, ast_checker) that were completed in a prior session but never committed. Then systematically diagnosed and fixed 5 distinct bugs introduced by the split, bringing integration/e2e tests from 120 failures + 31 errors down to 9 pre-existing failures unrelated to the refactoring. All 495 passing tests, mypy strict, and ruff are green.

---

## Key Decisions

- **MRO reorder for OrchestratorDB**: Changed from `(TaskMixin, WorkerMixin, RunsMixin, ConnectionMixin)` to `(ConnectionMixin, TaskMixin, WorkerMixin, RunsMixin)` so the real `_ensure_connected` implementation in ConnectionMixin takes precedence over no-op stubs in the other mixins. The stubs remain for mypy type-checking purposes.
- **Patch target convention**: After the package split, mock.patch targets must use `tdd_orchestrator.worker_pool.worker.*` (the module where names are imported and used) rather than `tdd_orchestrator.worker_pool.*` (the package `__init__.py`). This follows Python's standard patching rule: patch where the name is looked up, not where it's defined.

---

## Completed Work

### Accomplishments

- Committed 4 module splits: circuit_breaker (1866 lines), worker_pool (1459), database (1425), ast_checker (1085) -- all now under 800-line limit
- Fixed SCHEMA_PATH in `database/connection.py` to correctly traverse from new package depth to `schema/schema.sql`
- Fixed MRO ordering in `OrchestratorDB` so `_ensure_connected` resolves to `ConnectionMixin`'s real implementation instead of mixin stubs
- Exported `HAS_AGENT_SDK`, `sdk_query`, `ClaudeAgentOptions` from `worker_pool/__init__.py`
- Updated 50+ mock patch targets across integration/e2e tests to use `tdd_orchestrator.worker_pool.worker.*`
- Fixed `test_circuit_breaker_db.py` schema_path fixture (pointed to ancient `src/agents/orchestrator/` path)
- Cleared TO-DOS.md after all split tasks completed

### Files Modified

**Source (3 files):**
- `src/tdd_orchestrator/database/connection.py` -- SCHEMA_PATH fix
- `src/tdd_orchestrator/database/core.py` -- MRO reorder
- `src/tdd_orchestrator/worker_pool/__init__.py` -- added SDK re-exports

**Tests (8 files):**
- `tests/integration/conftest.py` -- monkeypatch targets
- `tests/integration/test_circuit_breaker_db.py` -- schema_path fixture
- `tests/integration/test_green_retry_edge_cases.py` -- patch targets
- `tests/integration/test_green_retry_integration.py` -- patch targets
- `tests/integration/test_worker_processing.py` -- patch targets
- `tests/integration/test_worker_sdk_failures.py` -- patch targets
- `tests/e2e/test_decomposition_to_execution.py` -- patch targets
- `tests/e2e/test_full_pipeline.py` -- patch targets

### Git State

- **Branch**: main
- **Recent commits**:
  - `3820d62` fix: resolve integration/e2e test failures after module split
  - `f9600a5` chore: clear TO-DOS.md after completing all file splits
  - `4a2508b` refactor: split 4 oversized modules into focused packages
- **Uncommitted changes**: `tdd-progress.md`, `.claude/rules/task-execution.md`, `uv.lock` (test artifacts, not session work)

---

## Known Issues

**9 pre-existing test failures (NOT from refactoring):**

1. **test_code_verifier.py (4 failures)** -- `ruff` and `mypy` not on system PATH. The code verifier runs these as subprocesses outside the venv. Fix: either add venv bin to PATH in test setup or make the verifier resolve tool paths from the venv.
   - `test_ruff_returns_pass_on_clean_code`
   - `test_ruff_returns_fail_on_lint_error`
   - `test_mypy_returns_pass_on_valid_types`
   - `test_verify_all_runs_parallel`

2. **test_green_retry_integration.py (4 failures)** -- Full pipeline tests hit `blocked-static-review` because AST checker references mock file paths that don't exist on disk. Fix: mock the AST checker or create temp files for the test.
   - `test_pipeline_with_green_retry`
   - `test_pipeline_green_success_no_retry`
   - `test_mark_task_failing_on_exhausted_attempts`
   - `test_git_commit_only_on_success`

3. **test_worker_budget.py (1 failure)** -- `git status --porcelain` fails because the test runs in a temp dir without a git repo. Fix: use the `git_repo` fixture from conftest.py.
   - `test_pool_stops_on_budget_exhaustion`

**Integration tests commit to real git repo** -- The Worker's `process_task` runs `git commit` during integration tests, polluting the real repo history with `wip(TDD-RETRY-01)` commits. This needs a test isolation fix (mock git operations or use temp git repos).

---

## Next Priorities

1. **Fix 9 pre-existing test failures** -- Must resolve all errors before beginning new work. See Known Issues above for root causes and fix strategies.
2. **Isolate integration tests from real git repo** -- Integration tests should not commit to the main repository during test runs.

---

*Session logged: 2026-02-07 12:30:05 CST*
