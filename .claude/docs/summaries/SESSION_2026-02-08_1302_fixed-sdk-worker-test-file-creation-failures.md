---
session_date: 2026-02-08
session_time: 13:02:57
status: Fixed SDK worker intermittent test file creation failures
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Fixed SDK worker intermittent test file creation failures

**Date**: 2026-02-08 | **Time**: 13:02:57 CST

---

## Executive Summary

Diagnosed and fixed five root causes behind SDK workers intermittently failing to create test files during the RED stage. The fixes addressed missing `permission_mode` (SDK subprocess couldn't answer Write prompts), missing `cwd` (paths resolved from wrong directory), `max_turns=10` being too low for exploration-heavy stages, an `os.environ["ANTHROPIC_MODEL"]` race condition between concurrent workers, and a bare `Path(test_file).exists()` that didn't resolve against `base_dir`. After applying fixes, API-TDD-01-03 (which had failed 3x previously) completed on the first run.

---

## Key Decisions

- **`permission_mode="bypassPermissions"`**: Required because SDK subprocess uses JSON streaming and cannot answer interactive Write permission prompts. Intermittency depended on project-level auto-allow settings.
- **Model passed via `ClaudeAgentOptions.model`** instead of `os.environ["ANTHROPIC_MODEL"]`: Eliminates race condition when concurrent workers share process env.
- **Stage-specific `max_turns`**: RED/GREEN get 25 turns (exploration + file creation), VERIFY/RE_VERIFY get 10 (command-only). Previous flat value of 10 was insufficient.
- **Deferred `_consume_sdk_stream` fix**: The `hasattr(message, "text")` bug always returns `""`, but pipeline correctness relies on filesystem verification (pytest, file existence), not SDK text output. Separate follow-up.

---

## Completed Work

### Accomplishments

- Fixed `ClaudeAgentOptions` constructor: added `permission_mode`, `cwd`, `model`, stage-specific `max_turns`
- Removed `os.environ["ANTHROPIC_MODEL"]` race condition from `worker.py` — model now passed directly to SDK options
- Renamed `set_model_for_complexity` to `get_model_for_complexity` (pure function, no env var side-effect)
- Added `STAGE_MAX_TURNS` config dict with per-stage turn limits
- Fixed `stage_verifier.py` path resolution: `Path(test_file).exists()` -> `(base_dir / test_file).exists()`
- Fixed 11 pre-existing integration test failures (tests missing file creation in `tmp_path`)
- Verified API-TDD-01-03 completes successfully through full TDD pipeline (RED -> GREEN retry -> VERIFY)

### Files Modified

- `src/tdd_orchestrator/worker_pool/config.py` — Added `STAGE_MAX_TURNS`, pure `get_model_for_complexity`
- `src/tdd_orchestrator/worker_pool/worker.py` — Fixed `ClaudeAgentOptions`, removed env var hack, pass `base_dir`
- `src/tdd_orchestrator/worker_pool/stage_verifier.py` — Added `base_dir` param, fixed path resolution
- `src/tdd_orchestrator/worker_pool/__init__.py` — Added `STAGE_MAX_TURNS` export
- `tests/integration/test_worker_processing.py` — Created test file in `tmp_path` for RED verification
- `tests/integration/test_green_retry_integration.py` — Created test files in `tmp_path` (4 tests)
- `tests/integration/test_refactor_pipeline.py` — Added `discover_test_file` mock to `_PipelineHarness`

### Git State

- **Branch**: main
- **Recent commits**:
  - `5f97746` feat(API-TDD-01-03): complete (squashed from 2 WIP commits)
  - `f3c99f9` fix(worker): fix SDK worker intermittent test file creation failures
- **Uncommitted changes**: None

---

## Known Issues

- **API-TDD-01-04 status is `blocked`** but its dependencies (API-TDD-0A-01, API-TDD-0A-02) are both complete. Status needs manual reset to `pending`.
- **`_consume_sdk_stream` always returns `""`**: `hasattr(message, "text")` is always False for SDK types. Not a correctness bug (pipeline uses filesystem verification), but an observability gap. Deferred to follow-up.
- **2 pre-existing e2e test failures**: `test_decomposition_to_execution` and `test_full_pipeline` — unrelated to this session's work.
- **Local/remote divergence**: Branch has 3 local commits ahead, 2 remote commits — needs pull/merge before push.

---

## Next Priorities

1. **Reset API-TDD-01-04 and continue API task execution** — Reset blocked status, run orchestrator to progress through remaining Phase 1 tasks (01-04), then Phases 2-12.
2. **Run orchestrator in multi-task mode** — With fixes in place, run with `-w 2` or more workers to parallelize remaining ~42 pending API tasks.
3. **Fix `_consume_sdk_stream` observability** — Extract to `sdk_stream.py`, handle `ResultMessage`, `AssistantMessage.error`, `ToolResultBlock.is_error`, and cost tracking.

---

*Session logged: 2026-02-08 13:02:57 CST*
