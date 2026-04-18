# Pipeline Integrity Roadmap: app_spec -> Working System

## Context

The TDD Orchestrator's 4-pass decomposition pipeline generates well-structured tasks, and the execution engine (RED -> GREEN -> VERIFY) runs each task independently. But the pipeline has systemic gaps between these two layers: decomposed metadata is generated but never enforced, phases advance without validation, and completed runs are never tested as integrated systems.

**Root cause (what we just fixed)**: Pass 2 classified route handler tasks as "unit" because the Phase name didn't contain "Integration". Mock-based tests passed VERIFY, tasks were marked COMPLETE, but real DB wiring was never done. We patched prompts and rewired circuits.py -- but the structural gaps that allowed it remain.

**This roadmap** closes every gap between "app_spec in" and "working system out," organized into 5 phases with clear dependencies.

> **Corrections applied** (2026-02-13 audit):
> - `cli.py` actual line count is **270** (not ~170 as originally stated). Projections updated accordingly.
> - `decompose_spec.py` is **635** lines (not 636).
> - `ast_checker/models.py` is **108** lines (not 109).
> - G6 prompt-level enforcement is already implemented (uncommitted) in `decomposition/prompts.py` with regression test in `tests/unit/decomposition/test_boundary_detection.py`. Phase 1A scope is validator-level hard enforcement only.
> - **worker.py extraction arithmetic** (post-review fix): Original roadmap showed -240 delta (only counting `_run_tdd_pipeline`). Corrected to -365 (all three extracted methods: `_run_tdd_pipeline` ~240 + `_run_green_with_retry` ~121 + `_consume_sdk_stream` ~20 = ~381 raw lines, minus ~16 lines of added glue code). worker.py: 782 -> ~415. pipeline.py: ~400 (not ~280).

---

## Pipeline Anatomy (current state)

```
app_spec.txt
  |
[DECOMPOSITION] -----------------------------------------------
  Pass 1: Extract TDD cycles                 (decomposer.py)
  Pass 2: Break cycles -> atomic tasks       (decomposer.py, prompts.py)
  Pass 3: Generate acceptance criteria        (decomposer.py, prompts.py)
  Pass 4: Generate implementation hints       (decomposer.py, prompts.py)
  Post:   Recursive validation                (validators.py)
  Post:   Dependency calculation              (generator.py)
  Post:   Overlap detection                   (overlap_detector.py)
  Post:   Spec conformance                    (spec_validator.py)
  |
tasks in DB (with verify_command, done_criteria, acceptance_criteria)
  |
[EXECUTION] ----------------------------------------------------
  Per-task TDD pipeline:
    RED -> RED_FIX -> GREEN (retry+escalate) -> VERIFY -> FIX -> RE_VERIFY
  Per-task verification:
    pytest + ruff + mypy + AST checks + sibling regression
  |
tasks marked "complete"
  |
[POST-EXECUTION] --- (nothing here) ----------------------------
  No phase gates
  No end-of-run validation
  No system-level smoke test
  Run marked "completed" -> done
```

## Gap Inventory

| # | Gap | Layer | Severity | Status |
|---|-----|-------|----------|--------|
| G1 | `verify_command` generated, never executed | Execution | CRITICAL | Open |
| G2 | `done_criteria` generated, never evaluated | Execution | HIGH | Open |
| G3 | `acceptance_criteria` never validated post-execution | Post-exec | HIGH | Open |
| G4 | No phase gates between execution phases | Post-exec | HIGH | Open |
| G5 | No end-of-run system validation | Post-exec | HIGH | Open |
| G6 | Integration boundary not enforced in validators | Decomp | HIGH | Prompt-only fix (soft); validator enforcement pending |
| G7 | Circular dependencies not detected | Decomp | HIGH | Open |
| G8 | Task key uniqueness not enforced | Decomp | MEDIUM | Open |
| G9 | No placeholder/stub detection | Execution | MEDIUM | Open |
| G10 | No mock-only test detection | Execution | MEDIUM | Open |
| G11 | worker.py at 782 lines, no room for new logic | Structural | MEDIUM | Open |
| G12 | pool.py has no multi-phase loop (`run_all_phases`) | Structural | HIGH | Open |
| G13 | No CLI entry point for manual run/phase validation | Usability | LOW | Open |

**Changes from original**: Added G11 (worker.py structural debt -- any roadmap phase that touches worker.py must reckon with this), G12 (pool.py architecture gap that Phase 3 depends on), and G13 (manual validation trigger). Downgraded G2 from CRITICAL to HIGH -- `done_criteria` is typically redundant with VERIFY ("tests pass and code is formatted") and has lower marginal value than `verify_command`.

---

## Phase 1: Decomposition Hardening (G6, G7, G8)

**Goal**: Prevent bad task graphs from being generated. Hard enforcement where only soft prompts exist today.

**Why first**: Cheapest to implement, prevents problems at the source, zero runtime risk.

### 1A: Integration Boundary Hard Validation

**Problem**: Prompts now say "route handlers should be integration tests" but LLM can ignore this. `validators.py` has no check for test_type vs impl_file consistency.

**Pre-existing work**: Prompt-level changes already in `decomposition/prompts.py` (uncommitted) with regression test in `tests/unit/decomposition/test_boundary_detection.py` (52 lines). Phase 1A adds the _validator-level_ enforcement that catches violations even when the LLM ignores the prompt rules.

**Solution**: Add `validate_integration_boundaries()` to `AtomicityValidator` in `validators.py`:
- If `impl_file` contains route/api/database keywords AND `test_file` starts with `tests/unit/` -> validation error
- Configurable keyword list + escape hatch flag in `DecompositionConfig`

**Files**:
- Edit: `src/tdd_orchestrator/decomposition/validators.py` (378 -> ~440 lines)
- Edit: `src/tdd_orchestrator/decomposition/config.py` (80 -> ~95 lines)
- Extend: `tests/unit/decomposition/test_validators.py`

### 1B: Circular Dependency Detection

**Problem**: `generator.py` calculates `depends_on` based on phase ordering but never validates the resulting graph for cycles. The current dependency rule (Phase N depends on ALL Phase N-1 tasks) cannot produce cycles by construction, but manually edited tasks, recursive validation splits, or future dependency rules could introduce them. This is defensive hardening.

**Solution**: New module with Kahn's algorithm (topological sort). If in-degree nodes remain after sort, cycles exist. Report the cycle members in the error.

**Files**:
- New: `src/tdd_orchestrator/decomposition/dependency_validator.py` (~80 lines)
- Edit: `src/tdd_orchestrator/decompose_spec.py` (+15 lines -- call after `_calculate_dependencies()` at line 417)
- New: `tests/unit/decomposition/test_dependency_validator.py` (~100 lines)

### 1C: Task Key Uniqueness

**Problem**: `TaskGenerator` assigns keys sequentially but never checks for duplicates (could occur with split tasks or multiple runs with same prefix).

**Solution**: Standalone function `validate_unique_task_keys()` in `validators.py`, called in `decompose_spec.py` alongside spec conformance. Also verify no duplicate `(impl_file, test_file)` pairs which would cause execution collisions.

**Files**:
- Edit: `src/tdd_orchestrator/decomposition/validators.py` (+30 lines)
- Edit: `src/tdd_orchestrator/decompose_spec.py` (+5 lines)
- Extend: `tests/unit/decomposition/test_validators.py`

### Phase 1 Verification
```bash
.venv/bin/pytest tests/unit/decomposition/ -v
.venv/bin/mypy src/tdd_orchestrator/decomposition/ --strict
.venv/bin/ruff check src/tdd_orchestrator/decomposition/
```

**Estimated effort**: 2 sessions

---

## Phase 2: Execute Decomposed Metadata (G1, G2, G11)

**Goal**: Make `verify_command` and `done_criteria` useful -- they are generated by the LLM with specific intent but currently decorative.

**Depends on**: Nothing (can run parallel with Phase 1)

**Prerequisite**: Before adding ANY call sites to worker.py (782 lines), extract `_run_tdd_pipeline` (lines 236-475, ~240 lines), `_run_green_with_retry` (lines 611-731, ~121 lines), and `_consume_sdk_stream` (lines 733-752, ~20 lines) into a new `src/tdd_orchestrator/worker_pool/pipeline.py` module. This is not optional -- worker.py is 18 lines from the 800-line hard limit. Total extracted: ~381 raw lines. The extraction produces a worker.py of ~415 lines and a pipeline.py of ~400 lines. All Phase 2 call sites go into pipeline.py, not worker.py.

### 2-Pre: Extract Pipeline Logic from Worker

**Problem**: worker.py is at 782 lines. Adding even 15 lines of call sites for done_criteria evaluation (Phase 2B) would put it at 797 -- one import away from violating the 800-line limit. Future phases (3, 4, 5) also need integration points in the pipeline flow.

**Solution**: Extract `_run_tdd_pipeline()`, `_run_green_with_retry()`, and `_consume_sdk_stream()` into a new `pipeline.py` module. Worker keeps `process_task()`, `start()`, `stop()`, `_heartbeat_loop()`, and `_verify_stage_result()` (delegation to stage_verifier.py). The new module receives worker context (db, verifier, config, etc.) via a pipeline context dataclass or direct arguments.

**Design decisions**:
- **Dataclass for context, not the Worker instance**: Pipeline functions should not take `self: Worker`. Pass a `PipelineContext` dataclass with db, verifier, prompt_builder, base_dir, worker_id, run_id, config, and static_review_circuit_breaker. This keeps the pipeline testable without constructing a full Worker.
- **Worker.process_task() calls pipeline.run_tdd_pipeline()**: Single call site replacement, no behavior change.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/pipeline.py` (~400 lines)
- Edit: `src/tdd_orchestrator/worker_pool/worker.py` (782 -> ~415 lines)
- New: `tests/unit/worker_pool/test_pipeline.py` (~80 lines -- verify extraction didn't change behavior)

### 2A: verify_command Execution

**Problem**: Decomposer generates per-task shell commands like `"pytest tests/unit/config/test_loader.py -v"`. Stored in DB, never run. The execution engine uses standardized VERIFY instead.

**Solution**: Parse `verify_command` into safe components (tool + target + flags). Execute as supplemental check after main VERIFY passes. Route through `CodeVerifier._run_command()` (which already uses `asyncio.create_subprocess_exec`, no `shell=True`).

**Design decisions**:
- **Parse, don't execute raw**: Security rule prohibits `shell=True`. Parse to extract tool/file/flags. The parser must handle `uv run pytest ...` (strip `uv run` prefix), `.venv/bin/pytest ...`, and bare `pytest ...`.
- **Supplemental, not replacement**: Main VERIFY still runs. verify_command adds the decomposer's specific intent (e.g., running only the specific test file the decomposer targeted).
- **Non-blocking initially**: If parsing fails (malformed LLM output), log warning and continue. Promote to blocking after data collection shows reliability.
- **Allowlisted tools only**: pytest, python, ruff, mypy. Anything else -> skip with warning.
- **Record results**: Store verify_command outcome in a new `verify_command_result` column on the attempts table, or as JSON in an existing field. This data informs the promotion-to-blocking decision.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/verify_command_runner.py` (~130 lines)
- Edit: `src/tdd_orchestrator/worker_pool/pipeline.py` (+20 lines -- call after main VERIFY passes)
- New: `tests/unit/worker_pool/test_verify_command_runner.py` (~130 lines)

**Note**: The original plan placed the call site in `stage_verifier.py`. This is incorrect -- stage_verifier verifies the result of a single stage execution (RED produced a test file, GREEN made tests pass). The verify_command is a post-VERIFY supplemental check that belongs in the pipeline flow after VERIFY succeeds, not inside the stage result verification logic.

### 2B: done_criteria Heuristic Evaluation

**Problem**: done_criteria like "All tests pass and code is formatted with ruff" exists as text. Never checked.

**Solution**: Parse done_criteria with heuristic matchers:
- "tests pass" -> already covered by VERIFY (mark satisfied)
- "importable" / "exports X" -> `python -c 'import X'`
- "file exists" -> `Path(x).exists()`
- Everything else -> "unverifiable" (logged, not blocking)

**Design decisions**:
- **Non-blocking**: Logs results, does not fail tasks. Informational layer.
- **Called at task completion**: In pipeline.py, after VERIFY passes, before returning True.
- **Results recorded**: JSON blob stored in a new `done_criteria_result TEXT` column on `tasks`, or appended to the existing task record. This avoids schema complexity while preserving audit trail.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/done_criteria_checker.py` (~140 lines)
- Edit: `src/tdd_orchestrator/worker_pool/pipeline.py` (+10 lines -- call at completion)
- New: `tests/unit/worker_pool/test_done_criteria_checker.py` (~100 lines)

### Phase 2 Verification
```bash
.venv/bin/pytest tests/unit/worker_pool/ -v
.venv/bin/pytest tests/integration/ -v  # regression
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
```

**Estimated effort**: 4 sessions (1 for extraction, 1 for 2A, 1 for 2B, 1 for integration/regression testing)

---

## Phase 3: Phase Gates and End-of-Run Validation (G4, G5, G12, G13)

**Goal**: Validate between phases and after the complete run. Currently, phase transitions and run completion have zero checks.

**Depends on**: Phase 2 (done_criteria results feed into run validation; pipeline.py extraction provides stable integration surface)

### 3-Pre: Multi-Phase Loop in Pool

**Problem**: `pool.py` has only `run_parallel_phase(phase)` which processes a single phase. The CLI calls `pool.run_parallel_phase(phase)` with a single phase number. There is no multi-phase orchestration loop -- no method iterates through phases sequentially, inserting gates between them. Phase 3A (phase gates) requires this loop to exist.

**Current call chain**: `cli.py:run()` -> `pool.run_parallel_phase(phase=N)` -> processes tasks in phase N -> returns.

**Solution**: Add `run_all_phases()` to `WorkerPool` that:
1. Queries distinct phases from the task table, sorted ascending
2. For each phase, calls `run_parallel_phase(phase)`
3. After each phase completes, runs the phase gate (Phase 3A)
4. If gate fails, stops execution and reports which gate failed
5. After all phases, runs end-of-run validation (Phase 3B)

**Design decisions**:
- **`run_parallel_phase()` unchanged**: Backward compatible. Existing CLI path still works.
- **New CLI flag**: `--all-phases` triggers `run_all_phases()` instead of single-phase execution.
- **Phase list from DB**: Query `SELECT DISTINCT phase FROM tasks WHERE status = 'pending' ORDER BY phase`. This handles partial runs (resume from phase N).

**Files**:
- Edit: `src/tdd_orchestrator/worker_pool/pool.py` (179 -> ~250 lines)
- Edit: `src/tdd_orchestrator/cli.py` (270 -> ~285 lines, +15 lines for `--all-phases` flag)

### 3A: Phase Gate Validator

**Problem**: When Phase N tasks all complete, Phase N+1 starts with no validation. A broken phase can cascade.

**Solution**: New module `phase_gate.py`. After all tasks in a phase complete:
1. Batch-run pytest on ALL test files from this phase's tasks
2. Batch-run pytest on ALL test files from PRIOR phases (regression check)
3. Scan impl files for stubs/placeholders (if Phase 4 detectors available)
4. Verify all tasks in this phase have status='complete' (no partial phases)

**Design decisions**:
- **Optional via config**: `enable_phase_gates: bool = True` in `WorkerConfig`
- **Blocking by default**: Phase gate failure prevents next phase from starting
- **Uses `CodeVerifier.run_pytest_on_files()`**: Already exists, already async, already handles subprocess safely
- **Test isolation concern**: Batch pytest across all phase test files could surface cross-test interference (shared fixtures, database state, etc.) that per-task pytest did not catch. This is a FEATURE, not a bug -- it's exactly the kind of integration failure the gate should catch. However, the gate must handle the case where batch pytest fails due to test isolation issues vs. real implementation failures. Strategy: if batch fails, re-run each test file individually and report which specific files fail.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/phase_gate.py` (~200 lines)
- Edit: `src/tdd_orchestrator/worker_pool/pool.py` (+30 lines -- call in `run_all_phases()`)
- New: `tests/unit/worker_pool/test_phase_gate.py` (~150 lines)
- New: `tests/integration/test_phase_gate_flow.py` (~120 lines)

### 3B: End-of-Run Validator

**Problem**: Run marked "completed" means "no task failed." Does not mean the system works.

**Solution**: New module `run_validator.py`. After final phase completes:
1. Run pytest on ALL test files from ALL tasks (full regression)
2. Run ruff + mypy on ALL impl files
3. Check no tasks left in 'blocked' or 'pending' status
4. Try importing all `module_exports` from all tasks (uses existing `module_exports` column)
5. Aggregate done_criteria results (from Phase 2B)
6. Record results in `execution_runs.validation_details`

**Design decisions**:
- **Separate from pool**: Called by `run_all_phases()` after final phase gate passes, before `complete_execution_run()`.
- **Schema change**: Add `validation_status TEXT` and `validation_details TEXT` to `execution_runs`. Migration: `ALTER TABLE execution_runs ADD COLUMN validation_status TEXT; ALTER TABLE execution_runs ADD COLUMN validation_details TEXT;`
- **Run status**: If validation fails, run status is 'failed' with reason in validation_details. If validation passes, status is 'passed' (new status, already in the CHECK constraint).
- **Timeout**: Full regression can be slow. Use configurable timeout (default 10 minutes) for the full pytest run.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/run_validator.py` (~200 lines)
- Edit: `src/tdd_orchestrator/worker_pool/pool.py` (+15 lines -- call after final phase)
- Edit: `schema/schema.sql` (+2 columns on `execution_runs`)
- New: `tests/unit/worker_pool/test_run_validator.py` (~150 lines)

### 3C: CLI Entry Point for Manual Validation

**Problem**: No way to manually trigger phase gate or run validation outside of the execution pipeline. Useful for debugging, dry-run validation, and CI integration.

**Solution**: New CLI commands:
- `tdd-orchestrator validate --phase N` -- run phase gate for phase N
- `tdd-orchestrator validate --run` -- run end-of-run validation on current state
- `tdd-orchestrator validate --all` -- run all phase gates + end-of-run

**Files**:
- Edit: `src/tdd_orchestrator/cli.py` (285 -> ~325 lines, +40 lines for `validate` command group)

### Phase 3 Verification
```bash
.venv/bin/pytest tests/unit/worker_pool/ tests/integration/ -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
.venv/bin/mypy src/tdd_orchestrator/cli.py --strict
```

**Estimated effort**: 5 sessions (1 for pool.py loop + CLI, 1 for phase gate, 1 for run validator, 1 for CLI validate commands, 1 for integration testing)

---

## Phase 4: Execution Quality Detectors (G9, G10)

**Goal**: Detect placeholder code and mock-only tests that pass VERIFY but prove nothing.

**Depends on**: Nothing (can run parallel with Phase 3). Enhances Phase 3 gates when both are present.

### 4A: Placeholder/Stub Detection

**Problem**: A GREEN stage could produce `def process(): pass` or `raise NotImplementedError()`. VERIFY passes if tests don't call that function. Task marked complete with stub code.

**Solution**: New AST detector in the ast_checker framework. Detects:
- `pass` as sole function body (excluding `__init__` with only `self` param, abstract methods, and protocol stubs)
- `raise NotImplementedError()` / `raise NotImplementedError`
- `...` (Ellipsis) as sole function body (excluding type stubs and Protocol classes)
- Functions with only a docstring and no implementation
- Return of hardcoded sentinel values (`return None`, `return {}`, `return []`) as sole body

**Design decisions**:
- **Blocking**: `severity="error"` -- stubs in "complete" tasks are real failures
- **Plugs into existing framework**: `checker.py` (209 lines) dispatches to detector classes. Adding a new detector follows the established pattern (see `quality_detectors.py`, `test_detectors.py`). The detector is an `ast.NodeVisitor` subclass with a `violations` list.
- **Runs during VERIFY**: Automatically via AST check pipeline in `CodeVerifier.verify_all()` -> `ASTQualityChecker.check_file()`
- **Configuration**: New `check_stubs: bool = True` in `ASTCheckConfig`
- **Exclusions**: Protocol methods, abstract methods (decorated with `@abstractmethod`), `__init__` with no logic needed, and `.pyi` stub files are all excluded from detection.

**Files**:
- New: `src/tdd_orchestrator/ast_checker/stub_detector.py` (~160 lines)
- Edit: `src/tdd_orchestrator/ast_checker/checker.py` (209 -> ~224 lines, +15 lines to register new detector)
- Edit: `src/tdd_orchestrator/ast_checker/models.py` (108 -> ~110 lines, +1 config field)
- New: `tests/unit/ast_checks/test_stub_detector.py` (~120 lines)

### 4B: Mock-Only Test Detection

**Problem**: A test that only asserts against mocks (`mock.assert_called_with(...)`) proves nothing about real behavior. It passes VERIFY but doesn't test actual code.

**Solution**: AST analysis of test functions. If ALL assertions in a test function only check mock behavior (`.assert_called_with`, `.call_count`, `assert_called_once_with`, return values from `Mock()`/`MagicMock()`) with zero assertions on real function returns -> flag it.

**Design decisions**:
- **Warning initially (shadow mode)**: `severity="warning"` with new config field `check_mock_only_tests: bool = True`. Collect data via `static_review_metrics` table (already exists for exactly this purpose -- PLAN12 shadow mode pattern) before promoting to error.
- **Heuristic**: Will have false positives for legitimate mock-heavy unit tests. That is acceptable -- the goal is catching integration-boundary tasks that should test real behavior but only test mocks.
- **Scope**: Only flags test functions where 100% of assertions are mock-only. A test with even one real assertion passes.
- **Test file only**: Only runs on files matching `test_*.py` or `*_test.py` pattern (consistent with existing `is_test_file` check in checker.py).

**Files**:
- New: `src/tdd_orchestrator/ast_checker/mock_only_detector.py` (~180 lines)
- Edit: `src/tdd_orchestrator/ast_checker/checker.py` (~224 -> ~239 lines, +15 lines to register new detector)
- Edit: `src/tdd_orchestrator/ast_checker/models.py` (~110 -> ~112 lines, +1 config field)
- New: `tests/unit/ast_checks/test_mock_only_detector.py` (~120 lines)

### Phase 4 Verification
```bash
.venv/bin/pytest tests/unit/ast_checks/ -v
.venv/bin/mypy src/tdd_orchestrator/ast_checker/ --strict
.venv/bin/ruff check src/tdd_orchestrator/ast_checker/
```

**Estimated effort**: 3 sessions

---

## Phase 5: Acceptance Criteria Post-Execution Validation (G3)

**Goal**: Validate that acceptance criteria are actually met by the implementation, not just used as prompt context.

**Depends on**: Phase 3B (runs as part of end-of-run validation, uses run_validator integration surface)

### 5A: Heuristic AC Validator

**Problem**: Acceptance criteria like "Loading a non-existent file raises ConfigNotFoundError" is generated in Pass 3, fed to RED/GREEN prompts, but never verified against actual code after execution.

**Solution**: Parse structured AC and match against code artifacts:
- **Error handling AC** ("raises X"): Check for `pytest.raises(X)` in tests + `raise X` in impl (AST)
- **Export AC** ("exports X"): Check if export exists in impl AST (function/class definition)
- **Import AC** ("X importable"): Try `python -c 'from module import X'`
- **Endpoint AC** ("responds to GET /path"): Check for route decorator in impl (AST)
- **GIVEN/WHEN/THEN**: Match WHEN clause keywords against test function names/docstrings
- **Unverifiable**: Everything else logged as unverifiable with the literal AC text

**Design decisions**:
- **Non-blocking**: Results are informational. Stored in run validation details.
- **Called during end-of-run validation** (Phase 3B) as one of the checks. The run_validator calls ac_validator for each completed task and aggregates results.
- **No LLM calls**: Pure heuristic. Keeps cost at zero and makes it deterministic.
- **Coverage metric**: Report "X of Y acceptance criteria verifiable, Z verified as satisfied." This gives a confidence signal even when many AC are unverifiable.

**Files**:
- New: `src/tdd_orchestrator/worker_pool/ac_validator.py` (~200 lines)
- Edit: `src/tdd_orchestrator/worker_pool/run_validator.py` (+15 lines -- integrate AC checks)
- New: `tests/unit/worker_pool/test_ac_validator.py` (~120 lines)

### Phase 5 Verification
```bash
.venv/bin/pytest tests/unit/worker_pool/test_ac_validator.py -v
.venv/bin/pytest tests/ -v  # full regression
.venv/bin/mypy src/ --strict
```

**Estimated effort**: 2 sessions

---

## Dependency Graph

```
Phase 1 (Decomposition)     Phase 2 (Metadata)          Phase 4 (Detectors)
  | 1A: Boundary valid.       | 2-Pre: Extract pipeline    | 4A: Stub detection
  | 1B: Cycle detection       | 2A: verify_cmd             | 4B: Mock-only detect
  | 1C: Key uniqueness        | 2B: done_criteria
                               |
                        Phase 3 (Gates)
                          | 3-Pre: Pool multi-phase loop
                          | 3A: Phase gates <-- (enhanced by 4A/4B)
                          | 3B: Run validator <-- (uses 2B results)
                          | 3C: CLI validate commands
                          |
                        Phase 5 (AC Validation)
                          | 5A: AC heuristic validator
```

**Parallelism**: Phases 1, 2, and 4 are independent. Phase 3 depends on 2. Phase 5 depends on 3.

**Critical path**: Phase 2 (4 sessions) -> Phase 3 (5 sessions) -> Phase 5 (2 sessions) = 11 sessions sequential minimum.

---

## File Impact Summary

### New Files (10 source + 9 test = 19)

| File | Phase | Lines |
|------|-------|-------|
| `src/.../decomposition/dependency_validator.py` | 1B | ~80 |
| `src/.../worker_pool/pipeline.py` | 2-Pre | ~400 |
| `src/.../worker_pool/verify_command_runner.py` | 2A | ~130 |
| `src/.../worker_pool/done_criteria_checker.py` | 2B | ~140 |
| `src/.../worker_pool/phase_gate.py` | 3A | ~200 |
| `src/.../worker_pool/run_validator.py` | 3B | ~200 |
| `src/.../ast_checker/stub_detector.py` | 4A | ~160 |
| `src/.../ast_checker/mock_only_detector.py` | 4B | ~180 |
| `src/.../worker_pool/ac_validator.py` | 5A | ~200 |
| `tests/unit/decomposition/test_dependency_validator.py` | 1B | ~100 |
| `tests/unit/worker_pool/test_pipeline.py` | 2-Pre | ~80 |
| `tests/unit/worker_pool/test_verify_command_runner.py` | 2A | ~130 |
| `tests/unit/worker_pool/test_done_criteria_checker.py` | 2B | ~100 |
| `tests/unit/worker_pool/test_phase_gate.py` | 3A | ~150 |
| `tests/unit/worker_pool/test_run_validator.py` | 3B | ~150 |
| `tests/integration/test_phase_gate_flow.py` | 3A | ~120 |
| `tests/unit/ast_checks/test_stub_detector.py` | 4A | ~120 |
| `tests/unit/ast_checks/test_mock_only_detector.py` | 4B | ~120 |
| `tests/unit/worker_pool/test_ac_validator.py` | 5A | ~120 |

### Modified Files (9)

| File | Current | Change | Projected | Phase |
|------|---------|--------|-----------|-------|
| `decomposition/validators.py` | 378 | +62 | ~440 | 1A, 1C |
| `decomposition/config.py` | 80 | +15 | ~95 | 1A |
| `decompose_spec.py` | 635 | +20 | ~655 | 1B, 1C |
| `worker_pool/worker.py` | 782 | -365 | ~415 | 2-Pre (extraction) |
| `worker_pool/pool.py` | 179 | +116 | ~295 | 3-Pre, 3A, 3B |
| `ast_checker/checker.py` | 209 | +30 | ~239 | 4A, 4B |
| `ast_checker/models.py` | 108 | +4 | ~112 | 4A, 4B |
| `schema/schema.sql` | 748 | +5 | ~753 | 3B |
| `cli.py` | 270 | +55 | ~325 | 3-Pre, 3C |

All within 800-line limit. worker.py SHRINKS from 782 to ~415 via pipeline extraction (Phase 2-Pre), creating permanent headroom. pipeline.py starts at ~400 (at the "start thinking about splitting" threshold) and reaches ~430 after Phase 2 -- acceptable because the code is cohesive. See PHASE2.md Design Note for mitigation options if it grows further.

---

## Risk Assessment

| Phase | Risk | Impact | Mitigation |
|-------|------|--------|------------|
| 1 | LOW | Pure validation, no runtime changes | Test-driven, decomp-only |
| 2-Pre | MEDIUM | Refactoring hot path (pipeline execution) | Extract-only refactor, no behavior change. Full integration test suite must pass before/after. |
| 2A | MEDIUM | Parsing LLM-generated shell commands | Allowlist + parse-don't-execute. Non-blocking initially. |
| 2B | LOW | Informational only, non-blocking | Heuristic-only, logs results |
| 3-Pre | MEDIUM | New execution path (multi-phase loop) | Existing single-phase path unchanged. New path opt-in via `--all-phases`. |
| 3A | HIGH | Changes execution flow (phase gating) | Config flag to disable. Fallback: re-run individual test files on batch failure. |
| 3B | MEDIUM | Schema migration required | ALTER TABLE (additive only), no data loss. |
| 3C | LOW | Read-only CLI commands | No execution side effects |
| 4 | LOW | AST analysis only, pluggable | 4B starts in shadow mode (warning-only) |
| 5 | LOW | Non-blocking, informational | Heuristic-only, no LLM cost |

---

## Design Decision Rationale

### Why parse-don't-execute for verify_command (2A)?
The security rule "NEVER use `shell=True`" is non-negotiable. LLM-generated commands like `uv run pytest tests/test_foo.py -v` cannot be passed to a shell. Parsing extracts the tool name and arguments, which are then passed to `asyncio.create_subprocess_exec` (list-form). The parser handles common patterns (`uv run`, `.venv/bin/`, bare tool names) and rejects anything unrecognized. This is more restrictive than needed but safe by default.

### Why heuristic-only for done_criteria (2B)?
Most done_criteria text is "All tests pass and code is formatted" -- literally what VERIFY already checks. An LLM-based evaluator would cost money to tell us what we already know. Heuristic matchers cover the 80% case. The 20% that are unverifiable are logged honestly. If the data shows a pattern of unverifiable criteria that matter, we can add matchers or escalate to LLM evaluation later.

### Why non-blocking for AC validation (5A)?
Acceptance criteria are written in natural language by an LLM. Heuristic matching will miss valid implementations (false negatives) and flag correct code (false positives). Making this blocking would create friction without high enough accuracy. The value is in the coverage metric: "We could verify 14 of 20 AC, 14 satisfied" vs "We could verify 3 of 20 AC." The former gives confidence; the latter signals weak AC generation that should be improved at the decomposition layer.

### Why extract pipeline before adding features (2-Pre)?
worker.py at 782 lines is a time bomb. Every phase in this roadmap needs to touch the pipeline flow. Without extraction, Phase 2B puts it at 797, and any subsequent phase (3, 4, 5) breaks the 800-line limit. Extracting first creates ~240 lines of headroom and makes the pipeline independently testable.

### Why add a multi-phase loop (3-Pre) instead of external scripting?
Phase gates are meaningless if the orchestrator does not control the phase-to-phase transition. If the CLI just calls `run_parallel_phase(0)`, then `run_parallel_phase(1)`, etc., the gate has no authority to stop execution. The loop must own the transition to enforce the gate.

---

## After Full Roadmap: What Changes

```
app_spec.txt
  |
[DECOMPOSITION] --- Phase 1 hardening --------------------------
  Pass 1-4: (unchanged)
  Post: Recursive validation
  Post: Dependency calculation
  NEW: Circular dependency detection          (1B)
  Post: Overlap detection
  Post: Spec conformance
  NEW: Integration boundary enforcement       (1A)
  NEW: Task key uniqueness check              (1C)
  |
tasks in DB
  |
[EXECUTION] --- Phases 2 + 4 -----------------------------------
  Per-task TDD pipeline:
    RED -> RED_FIX -> GREEN -> VERIFY
    NEW: verify_command supplemental check    (2A)
    NEW: Stub/placeholder detection in AST    (4A)
    NEW: Mock-only test detection in AST      (4B)
    -> FIX -> RE_VERIFY
    NEW: done_criteria evaluation             (2B)
  |
tasks marked "complete"
  |
[PHASE GATE] --- Phase 3A --------------------------------------
  NEW: Batch pytest on all phase test files
  NEW: Regression check on prior phases
  NEW: Placeholder scan across phase
  NEW: All-tasks-complete check
  | (gate passes -> next phase)
  |
[END-OF-RUN] --- Phases 3B + 5 ---------------------------------
  NEW: Full regression (ALL test files)
  NEW: Full lint + type check (ALL impl files)
  NEW: Module export import check
  NEW: Done-criteria aggregation
  NEW: Acceptance criteria heuristic check    (5A)
  NEW: Final run status with validation details
```

## Estimated Total Effort

~16 sessions across all 5 phases. Phases 1 + 4 can run in parallel. Phase 2 -> 3 -> 5 are sequential.

| Phase | Sessions | Can Parallel With |
|-------|----------|-------------------|
| 1: Decomposition Hardening | 2 | Phase 2, Phase 4 |
| 2: Pipeline Extract + Metadata | 4 | Phase 1, Phase 4 |
| 3: Phase Gates + Run Validation | 5 | -- (depends on 2) |
| 4: Quality Detectors | 3 | Phase 1, Phase 2 |
| 5: AC Validation | 2 | -- (depends on 3) |

**Total**: 16 sessions (11 on critical path)
