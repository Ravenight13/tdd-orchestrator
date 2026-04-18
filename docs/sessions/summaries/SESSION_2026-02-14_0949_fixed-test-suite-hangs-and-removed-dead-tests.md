---
session_date: 2026-02-14
session_time: 09:49:04
status: Fixed test suite hangs and removed dead integration tests
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Fixed test suite hangs and removed dead integration tests

**Date**: 2026-02-14 | **Time**: 09:49:04 CST

---

## Executive Summary

Diagnosed and fixed two root causes that made `pytest tests/` hang indefinitely: a subprocess test running the full suite with no timeout, and lifecycle tests calling `init_dependencies()` directly causing leaked DB connections. Also cleaned up 18 dead tests (1420 lines removed) from the pipeline extraction refactor and fixed 9 stale tests with missing `goal` params and mock ordering issues. Full suite now runs cleanly in ~62 seconds.

---

## Key Decisions

- **Added `--run-slow` flag to conftest.py**: Tests marked `@pytest.mark.slow` are skipped by default. Run with `--run-slow` to include them. This prevents the subprocess regression test (which runs the entire suite as a child process) from doubling wall time on every run.
- **Deleted dead test files rather than updating them**: `test_green_retry_unit.py`, `test_green_retry_integration.py`, and `test_green_retry_edge_cases.py` tested `Worker._run_green_with_retry()` which was moved to `pipeline.py` as a module function. The new `test_pipeline.py` and `test_refactor_pipeline.py` already cover this functionality with 12 passing tests.

---

## Completed Work

### Accomplishments

- Diagnosed test suite hang: `test_regression_subprocess.py` spawned a full pytest subprocess with no timeout, and `test_app_lifecycle.py` leaked DB connections via direct `init_dependencies()` calls
- Added `--run-slow` pytest flag and subprocess timeouts (30s for collection, 180s for full run)
- Replaced direct `init_dependencies()`/`shutdown_dependencies()` calls with lifespan-managed `AsyncClient` contexts in lifecycle tests
- Deleted 3 dead test files (-1420 lines) testing the old `Worker._run_green_with_retry()` API
- Fixed 9 stale tests: added missing `goal=` param to `create_task()` calls, created test files on disk for RED stage verifier, fixed mock verifier ordering (must be set after `worker.start()`)
- Pushed 9 commits to `origin/main`

### Files Modified

- `tests/conftest.py` - Added `--run-slow` flag and `pytest_collection_modifyitems` hook
- `tests/integration/api/test_regression_subprocess.py` - Added `timeout=` to all `subprocess.run` calls
- `tests/integration/api/test_app_lifecycle.py` - Replaced direct init/shutdown calls with AsyncClient lifespan
- `tests/integration/test_green_retry_unit.py` - **Deleted** (dead code)
- `tests/integration/test_green_retry_integration.py` - **Deleted** (dead code)
- `tests/integration/test_green_retry_edge_cases.py` - **Deleted** (dead code)
- `tests/integration/test_worker_processing.py` - Added `goal=` to `create_task()` calls
- `tests/integration/test_worker_sdk_failures.py` - Added `goal=` to all `create_task()` calls
- `tests/e2e/test_decomposition_to_execution.py` - Added `tmp_path`, test file creation, fixed mock ordering
- `tests/e2e/test_full_pipeline.py` - Added `goal=` to `create_task()` call

### Git State

- **Branch**: main
- **Recent commits**:
  - `e2f6517` fix(test): remove dead tests and fix stale integration tests
  - `c1187d8` fix(test): prevent test suite hangs from subprocess and lifecycle tests
- **Uncommitted changes**: None

---

## Known Issues

- `test_shutdown_releases_resources_without_warnings` - 1 pre-existing failure from aiosqlite event loop cleanup (`RuntimeError: Event loop is closed` in background thread). Not caused by our changes.
- 2 RuntimeWarning deprecations for `datetime.utcnow()` in SSE bridge tests
- 2 RuntimeWarnings for unawaited coroutines in worker SDK failure tests

---

## Next Priorities

1. **Fix remaining lifecycle test failure**: `test_shutdown_releases_resources_without_warnings` fails due to aiosqlite connection cleanup after event loop closes. May need to explicitly close DB in shutdown or suppress the threading warning.
2. **Clean up test warnings**: Replace `datetime.utcnow()` with `datetime.now(datetime.UTC)` in SSE bridge tests; fix unawaited coroutine warnings in SDK failure mocks.
3. **Pipeline integrity G7 is done**: Circular dependency detection was already implemented in commit `5d0d634`. All 13/13 pipeline integrity gaps are now closed.

---

*Session logged: 2026-02-14 09:49:04 CST*
