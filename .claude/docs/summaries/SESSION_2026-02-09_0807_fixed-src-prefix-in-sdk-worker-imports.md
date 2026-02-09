---
session_date: 2026-02-09
session_time: 08:07:10
status: Fixed src. prefix in SDK worker import paths
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Fixed src. prefix in SDK worker import paths

**Date**: 2026-02-09 | **Time**: 08:07:10 CST

---

## Executive Summary

Fixed a critical bug where SDK workers generated broken imports like `from src.tdd_orchestrator.api.app import create_app` instead of `from tdd_orchestrator.api.app import create_app`. This caused API-TDD-04-03 to fail all 3 GREEN attempts. The root cause was `prompt_builder.py` performing naive `replace("/", ".")` on file paths without stripping the `src.` layout prefix. Added a helper method, prompt guardrails, and fixed 14 test files plus production code that had the same wrong import pattern.

---

## Key Decisions

- **Kept `tests/conftest.py` sys.path manipulation**: Initially removed it, but discovered the API conftest.py relies on `import tests.unit.api...` for monkeypatch paths, which requires project root on sys.path. Updated the docstring to reflect the actual purpose.
- **Added IMPORT_CONVENTION to three prompt templates**: Injected into RED, GREEN, and GREEN_RETRY templates as a guardrail so SDK workers never generate `src.` imports, even if a file path slips through.
- **Deleted `src/__init__.py`**: This file existed solely to enable the wrong `from src.tdd_orchestrator` import pattern. Removing it prevents regression.

---

## Completed Work

### Accomplishments

- Added `PromptBuilder._to_import_path()` static helper that strips `src.` prefix from import paths, used at both RED and GREEN prompt generation sites
- Added `IMPORT_CONVENTION` constant to `prompt_templates.py` and injected into RED, GREEN, and GREEN_RETRY templates
- Fixed the same `src.` prefix bug in `decomposition/prerequisites.py` for package path generation
- Fixed production code in `api/app.py` (2 occurrences of `from src.tdd_orchestrator`)
- Fixed imports and patch strings across 14 test files (9 API, 5 database)
- Deleted `src/__init__.py` that enabled the wrong import pattern
- Added regression tests for `_to_import_path` in `test_prompt_builder.py`
- Reset `API-TDD-04-03` task from `blocked` to `pending` in orchestrator.db
- Updated auto memory with src-layout import path patterns

### Files Modified

**Source (4 files):**
- `src/__init__.py` (deleted)
- `src/tdd_orchestrator/api/app.py` (fixed imports)
- `src/tdd_orchestrator/decomposition/prerequisites.py` (added src. stripping)
- `src/tdd_orchestrator/prompt_builder.py` (added `_to_import_path`, used at 2 sites)
- `src/tdd_orchestrator/prompt_templates.py` (added `IMPORT_CONVENTION`, injected into 3 templates)

**Tests (15 files):**
- `tests/conftest.py` (updated docstring)
- `tests/unit/test_prompt_builder.py` (added 2 regression tests)
- `tests/unit/api/test_dependencies_deps.py`
- `tests/unit/api/test_dependencies_init.py`
- `tests/unit/api/test_dependencies_lifespan.py` (imports + 22 patch strings)
- `tests/unit/api/test_sse_broadcaster_fanout.py`
- `tests/unit/api/test_sse_broadcaster_shutdown.py`
- `tests/unit/api/test_sse_broadcaster_slow_consumer.py`
- `tests/unit/api/test_sse_event.py`
- `tests/unit/api/models/test_requests.py`
- `tests/unit/api/models/test_status_responses.py`
- `tests/unit/database/conftest.py`
- `tests/unit/database/test_get_all_workers.py`
- `tests/unit/database/test_get_tasks_by_status.py`
- `tests/unit/database/test_get_tasks_filtered.py`
- `tests/unit/database/test_runs_queries.py`

### Git State

- **Branch**: main
- **Recent commits**: `e42de44 fix(imports): strip src. prefix from SDK worker import paths`
- **Uncommitted changes**: None

---

## Known Issues

- 55 pre-existing RED-stage test failures across 5 API test files (tests written ahead of implementation):
  - `test_dependencies_lifespan.py` — lifespan tests use sync ASGITransport but impl is async
  - `test_sse_broadcaster_fanout.py` — calls `subscribe()` sync but impl is async
  - `test_sse_broadcaster_slow_consumer.py` — same subscribe API mismatch
  - `test_sse_event.py` — SSE event serialize tests (impl behavior differs)
  - `test_dependencies_init.py` — calls `await shutdown_dependencies()` but impl is sync

---

## Next Priorities

1. **Re-run API-TDD-04-03 GREEN stage**: Task reset to `pending`. Run `tdd-orchestrator run -p -w 2` — should now succeed with correct import paths.
2. **Continue API feature implementation**: Check remaining API-TDD-04-xx tasks and proceed through the TDD pipeline.
3. **Address pre-existing RED-stage test mismatches**: The 55 failing API tests have API mismatches (sync vs async) that need reconciliation between tests and implementation.

---

*Session logged: 2026-02-09 08:07:10 CST*
