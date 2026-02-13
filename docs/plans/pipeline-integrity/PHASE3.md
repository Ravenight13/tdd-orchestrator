# Phase 3: Phase Gates + End-of-Run Validation

## Overview

| Attribute | Value |
|-----------|-------|
| **Goal** | Validate between phases and after complete runs |
| **Gaps addressed** | G4 (no phase gates), G5 (no end-of-run validation), G12 (no multi-phase loop), G13 (no CLI for manual validation) |
| **Dependencies** | **Phase 2 required** -- pipeline.py extraction provides stable surface; done_criteria results feed into run validation |
| **Estimated sessions** | 5 |
| **Risk level** | MEDIUM-HIGH -- 3A changes execution flow (phase gating) |
| **Produces for downstream** | `run_validator.py` integration surface for Phase 5 AC validation |

## Pre-existing State (after Phase 2)

- `worker_pool/pipeline.py` exists (~430 lines) with TDD pipeline flow, verify_command, and done_criteria hooks
- `worker_pool/worker.py` reduced to ~415 lines
- `done_criteria` results available from Phase 2B
- `verify_command` results available from Phase 2A
- `pool.py` at 179 lines with only `run_parallel_phase(phase)` -- no multi-phase loop
- `cli.py` at **270 lines** -- baseline for Phase 3 additions

## Task 3-Pre: Multi-Phase Loop in Pool

### Problem

`pool.py` has only `run_parallel_phase(phase)` which processes a single phase. There is no method that iterates through phases sequentially, inserting gates between them. Phase 3A (phase gates) requires this loop to exist.

**Current call chain**: `cli.py:run()` -> `pool.run_parallel_phase(phase=N)` -> processes tasks in phase N -> returns.

### Solution

Add `run_all_phases()` to `WorkerPool` that:
1. Queries distinct phases from the task table, sorted ascending
2. For each phase, calls `run_parallel_phase(phase)`
3. After each phase completes, runs the phase gate (Phase 3A -- initially a no-op placeholder)
4. If gate fails, stops execution and reports which gate failed
5. After all phases, runs end-of-run validation (Phase 3B -- initially a no-op placeholder)

### Design Decisions

- **`run_parallel_phase()` unchanged**: Backward compatible. Existing CLI path still works.
- **New CLI flag**: `--all-phases` triggers `run_all_phases()` instead of single-phase execution.
- **Phase list from DB**: `SELECT DISTINCT phase FROM tasks WHERE status = 'pending' ORDER BY phase`. Handles partial runs (resume from phase N).
- **Gate/validator placeholders**: 3-Pre creates the loop with hook points. 3A and 3B fill in the implementations.

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/pool.py`** (179 -> ~250 lines)

```python
async def run_all_phases(self) -> bool:
    """Execute all pending phases with gate validation between each."""
    phases = await self._get_pending_phases()
    if not phases:
        logger.info("No pending phases found")
        return True

    for phase in phases:
        logger.info("Starting phase %d", phase)
        success = await self.run_parallel_phase(phase)
        if not success:
            logger.error("Phase %d failed", phase)
            return False

        # Phase gate hook (filled in by 3A)
        gate_passed = await self._run_phase_gate(phase)
        if not gate_passed:
            logger.error("Phase gate failed for phase %d", phase)
            return False

    # End-of-run validation hook (filled in by 3B)
    return await self._run_end_of_run_validation()

async def _get_pending_phases(self) -> list[int]:
    """Query distinct pending phases, sorted ascending."""
    # SELECT DISTINCT phase FROM tasks WHERE status = 'pending' ORDER BY phase
    ...

async def _run_phase_gate(self, phase: int) -> bool:
    """Phase gate placeholder. Filled in by Task 3A."""
    return True  # No-op until 3A

async def _run_end_of_run_validation(self) -> bool:
    """End-of-run validation placeholder. Filled in by Task 3B."""
    return True  # No-op until 3B
```

**File: `src/tdd_orchestrator/cli.py`** (270 -> ~285 lines)

```python
# Add to run command:
@click.option("--all-phases", is_flag=True, help="Run all phases with gate validation")
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| `worker_pool/pool.py` | 179 | +71 | ~250 |
| `cli.py` | 270 | +15 | ~285 |

---

## Task 3A: Phase Gate Validator

### Problem

When Phase N tasks all complete, Phase N+1 starts with no validation. A broken phase can cascade failures into subsequent phases.

### Solution

New module `worker_pool/phase_gate.py`. After all tasks in a phase complete:
1. Batch-run pytest on ALL test files from this phase's tasks
2. Batch-run pytest on ALL test files from PRIOR phases (regression check)
3. Scan impl files for stubs/placeholders (if Phase 4 detectors available)
4. Verify all tasks in this phase have status='complete' (no partial phases)

### Design Decisions

- **Optional via config**: `enable_phase_gates: bool = True` in `WorkerConfig`
- **Blocking by default**: Phase gate failure prevents next phase from starting
- **Uses `CodeVerifier.run_pytest_on_files()`**: Already exists, already async, already handles subprocess safely
- **Fallback on batch failure**: If batch pytest fails, re-run each test file individually and report which specific files fail. This distinguishes test isolation issues from real implementation failures.
- **Phase 4 integration**: If stub_detector or mock_only_detector are available, phase gate runs them on impl/test files. If Phase 4 is not yet implemented, this check is silently skipped.

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/phase_gate.py`** (new, ~200 lines)

```python
"""Phase gate validation between execution phases."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PhaseGateResult:
    """Result of a phase gate check."""
    phase: int
    passed: bool
    test_results: list[TestFileResult] = field(default_factory=list)
    regression_results: list[TestFileResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return f"Phase {self.phase} gate: {status}"


@dataclass
class TestFileResult:
    """Result of running pytest on a single test file."""
    file: str
    passed: bool
    exit_code: int
    output: str


class PhaseGateValidator:
    """Validates phase completion before allowing next phase to start."""

    def __init__(self, db: Any, verifier: Any, base_dir: str) -> None:
        self._db = db
        self._verifier = verifier
        self._base_dir = base_dir

    async def validate_phase(self, phase: int) -> PhaseGateResult:
        """Run all phase gate checks for the given phase."""
        result = PhaseGateResult(phase=phase, passed=True)

        # 1. Check all tasks in phase are complete
        incomplete = await self._check_phase_completion(phase)
        if incomplete:
            result.passed = False
            result.errors.extend(incomplete)
            return result  # Don't run tests if tasks incomplete

        # 2. Batch pytest on this phase's test files
        phase_tests = await self._get_phase_test_files(phase)
        test_passed = await self._run_batch_tests(phase_tests, result.test_results)
        if not test_passed:
            result.passed = False

        # 3. Regression: batch pytest on prior phases' test files
        prior_tests = await self._get_prior_test_files(phase)
        if prior_tests:
            reg_passed = await self._run_batch_tests(prior_tests, result.regression_results)
            if not reg_passed:
                result.passed = False

        return result

    async def _run_batch_tests(
        self, test_files: list[str], results: list[TestFileResult]
    ) -> bool:
        """Run pytest on test files. On batch failure, re-run individually."""
        # Try batch first for speed
        # If batch fails, re-run individual files for diagnosis
        ...
```

**File: `src/tdd_orchestrator/worker_pool/pool.py`** (~250 -> ~280 lines)

Replace `_run_phase_gate` placeholder:

```python
async def _run_phase_gate(self, phase: int) -> bool:
    """Run phase gate validation."""
    if not self._config.enable_phase_gates:
        return True
    from tdd_orchestrator.worker_pool.phase_gate import PhaseGateValidator
    gate = PhaseGateValidator(self._db, self._verifier, self._base_dir)
    result = await gate.validate_phase(phase)
    logger.info(result.summary)
    return result.passed
```

### Test Cases

**File: `tests/unit/worker_pool/test_phase_gate.py`** (new, ~150 lines)

```python
# Test: all tasks complete + all tests pass -> gate passes
# Test: incomplete tasks -> gate fails immediately
# Test: batch test failure -> individual files re-run for diagnosis
# Test: regression test failure -> gate fails
# Test: enable_phase_gates=False -> always passes
# Test: no test files for phase -> gate passes (nothing to check)
# Test: no prior phases (phase 0) -> skip regression
# Test: PhaseGateResult summary format
```

**File: `tests/integration/test_phase_gate_flow.py`** (new, ~120 lines)

```python
# Test: multi-phase execution with gates (2 phases, both pass)
# Test: phase 1 gate failure stops phase 2 from starting
# Test: regression catches phase 1 breakage during phase 2 gate
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `worker_pool/phase_gate.py` | 0 | ~200 | ~200 |
| `worker_pool/pool.py` | ~250 | +30 | ~280 |
| NEW: `tests/unit/worker_pool/test_phase_gate.py` | 0 | ~150 | ~150 |
| NEW: `tests/integration/test_phase_gate_flow.py` | 0 | ~120 | ~120 |

---

## Task 3B: End-of-Run Validator

### Problem

Run marked "completed" means "no task failed." Does not mean the system works. There is no full regression test, no lint/type check across all files, no verification that all module exports are importable.

### Solution

New module `worker_pool/run_validator.py`. After final phase completes:
1. Run pytest on ALL test files from ALL tasks (full regression)
2. Run ruff + mypy on ALL impl files
3. Check no tasks left in 'blocked' or 'pending' status
4. Try importing all `module_exports` from all tasks
5. Aggregate done_criteria results (from Phase 2B)
6. Record results in `execution_runs.validation_details`

### Design Decisions

- **Separate from pool**: Called by `run_all_phases()` after final phase gate passes, before `complete_execution_run()`.
- **Schema change**: Add `validation_status TEXT` and `validation_details TEXT` to `execution_runs`. Migration: `ALTER TABLE` (additive only, no data loss).
- **Run status**: Validation failure -> run status 'failed'. Validation pass -> run status 'passed' (already in CHECK constraint).
- **Blocking vs non-blocking checks**: `regression_passed`, `lint_passed`, `type_check_passed`, and `orphaned_tasks` determine `result.passed` (blocking). `import_check_passed` is intentionally **non-blocking initially** -- import failures are logged and recorded in `validation_details` but do not fail the run. Promote to blocking after data collection shows reliability.
- **Timeout**: Full regression can be slow. Configurable timeout (default 10 minutes).
- **Phase 5 hook**: `run_validator` will call `ac_validator` (Phase 5A) when it becomes available. Initially, the AC check is a no-op (also non-blocking by design).

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/run_validator.py`** (new, ~200 lines)

```python
"""End-of-run validation for execution completeness."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RunValidationResult:
    """Aggregate result of end-of-run validation."""
    passed: bool = True
    regression_passed: bool = True
    lint_passed: bool = True
    type_check_passed: bool = True
    import_check_passed: bool = True
    orphaned_tasks: list[str] = field(default_factory=list)
    done_criteria_summary: str = ""
    ac_validation_summary: str = ""  # Filled by Phase 5A
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize to JSON for storage in validation_details."""
        return json.dumps({
            "passed": self.passed,
            "regression_passed": self.regression_passed,
            "lint_passed": self.lint_passed,
            "type_check_passed": self.type_check_passed,
            "import_check_passed": self.import_check_passed,
            "orphaned_tasks": self.orphaned_tasks,
            "done_criteria_summary": self.done_criteria_summary,
            "ac_validation_summary": self.ac_validation_summary,
            "errors": self.errors,
        })


class RunValidator:
    """Validates an execution run after all phases complete."""

    def __init__(self, db: Any, verifier: Any, base_dir: str) -> None:
        self._db = db
        self._verifier = verifier
        self._base_dir = base_dir

    async def validate_run(self, run_id: str) -> RunValidationResult:
        """Run all end-of-run validation checks."""
        result = RunValidationResult()

        # 1. Full regression (all test files)
        await self._run_full_regression(run_id, result)

        # 2. Lint + type check
        await self._run_lint_and_types(run_id, result)

        # 3. Orphaned tasks check
        await self._check_orphaned_tasks(run_id, result)

        # 4. Module import check
        await self._check_module_imports(run_id, result)

        # 5. Aggregate done_criteria results
        await self._aggregate_done_criteria(run_id, result)

        # 6. AC validation hook (Phase 5A -- no-op initially)
        await self._run_ac_validation(run_id, result)

        # Note: import_check_passed is intentionally NOT included here (non-blocking).
        # AC validation (Phase 5A) is also non-blocking.
        result.passed = (
            result.regression_passed
            and result.lint_passed
            and result.type_check_passed
            and not result.orphaned_tasks
        )
        return result
```

**File: `schema/schema.sql`** (748 -> ~753 lines)

```sql
-- Add to execution_runs table (or as ALTER TABLE migration):
-- validation_status TEXT,
-- validation_details TEXT
```

**File: `src/tdd_orchestrator/worker_pool/pool.py`** (~280 -> ~295 lines)

Replace `_run_end_of_run_validation` placeholder:

```python
async def _run_end_of_run_validation(self) -> bool:
    """Run end-of-run validation."""
    from tdd_orchestrator.worker_pool.run_validator import RunValidator
    validator = RunValidator(self._db, self._verifier, self._base_dir)
    result = await validator.validate_run(self._run_id)
    # Store results in DB
    await self._db.execute(
        "UPDATE execution_runs SET validation_status = ?, validation_details = ? WHERE id = ?",
        ("passed" if result.passed else "failed", result.to_json(), self._run_id),
    )
    return result.passed
```

### Test Cases

**File: `tests/unit/worker_pool/test_run_validator.py`** (new, ~150 lines)

```python
# Test: all checks pass -> RunValidationResult.passed = True
# Test: regression failure -> passed = False
# Test: lint failure -> passed = False
# Test: type check failure -> passed = False
# Test: orphaned tasks found -> passed = False, tasks listed
# Test: import check failure -> logged but non-blocking (initially)
# Test: done_criteria aggregation includes results from all tasks
# Test: RunValidationResult.to_json() produces valid JSON
# Test: validation results stored in execution_runs table
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `worker_pool/run_validator.py` | 0 | ~200 | ~200 |
| `worker_pool/pool.py` | ~280 | +15 | ~295 |
| `schema/schema.sql` | 748 | +5 | ~753 |
| NEW: `tests/unit/worker_pool/test_run_validator.py` | 0 | ~150 | ~150 |

---

## Task 3C: CLI Entry Point for Manual Validation

### Problem

No way to manually trigger phase gate or run validation outside of the execution pipeline. Useful for debugging, dry-run validation, and CI integration.

### Solution

New CLI command group `validate`:
- `tdd-orchestrator validate --phase N` -- run phase gate for phase N
- `tdd-orchestrator validate --run` -- run end-of-run validation on current state
- `tdd-orchestrator validate --all` -- run all phase gates + end-of-run

### Implementation Details

**File: `src/tdd_orchestrator/cli.py`** (~285 -> ~325 lines)

```python
@main.group()
def validate() -> None:
    """Run validation checks on execution state."""
    pass

@validate.command("phase")
@click.option("--phase", "-p", type=int, required=True, help="Phase number to validate")
def validate_phase(phase: int) -> None:
    """Run phase gate validation for a specific phase."""
    # ... create PhaseGateValidator, run, display results ...

@validate.command("run")
def validate_run() -> None:
    """Run end-of-run validation on current state."""
    # ... create RunValidator, run, display results ...

@validate.command("all")
def validate_all() -> None:
    """Run all phase gates + end-of-run validation."""
    # ... iterate phases, run gates, then run validation ...
```

### Test Cases

Test via CLI invocation:
```python
# Test: validate --phase 1 runs gate for phase 1
# Test: validate --run runs end-of-run validation
# Test: validate --all runs all gates then run validation
# Test: validation failure exits with non-zero code
# Test: validation results displayed to stdout
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| `cli.py` | ~285 | +40 | ~325 |

---

## Session Breakdown

### Session 1: Multi-Phase Loop + CLI Flag (3-Pre)

**Steps**:
1. Read `pool.py` and `cli.py`
2. Add `run_all_phases()`, `_get_pending_phases()`, placeholder gate/validation methods
3. Add `--all-phases` flag to CLI run command
4. Write tests for the loop logic
5. Verify existing single-phase path still works

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/ -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/pool.py --strict
.venv/bin/mypy src/tdd_orchestrator/cli.py --strict
```

### Session 2: Phase Gate (3A)

**Steps**:
1. Read `CodeVerifier` to understand `run_pytest_on_files()` API
2. Create `phase_gate.py` with `PhaseGateValidator`
3. Replace `_run_phase_gate` placeholder in `pool.py`
4. Write unit tests
5. Write integration test for multi-phase gate flow

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/test_phase_gate.py -v
.venv/bin/pytest tests/integration/test_phase_gate_flow.py -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
```

### Session 3: Run Validator (3B)

**Steps**:
1. Read schema.sql for `execution_runs` table structure
2. Add `validation_status` and `validation_details` columns
3. Create `run_validator.py` with `RunValidator`
4. Replace `_run_end_of_run_validation` placeholder in `pool.py`
5. Write unit tests
6. Verify schema migration is additive-only

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/test_run_validator.py -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
```

### Session 4: CLI Validate Commands (3C)

**Steps**:
1. Read cli.py current structure
2. Add `validate` command group with `phase`, `run`, `all` subcommands
3. Wire to PhaseGateValidator and RunValidator
4. Test CLI invocations
5. Verify cli.py stays under 400 lines

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/ -v
.venv/bin/mypy src/tdd_orchestrator/cli.py --strict
```

### Session 5: Integration Testing

**Steps**:
1. Run full test suite
2. Test multi-phase execution with real gates
3. Test run validation with real file checks
4. Test CLI validate commands end-to-end
5. Verify pool.py line count (should be ~295, under 400)

**Session boundary check**:
```bash
.venv/bin/pytest tests/ -v  # full suite
.venv/bin/mypy src/ --strict
.venv/bin/ruff check src/
```

---

## pool.py Growth Concern

| After Task | Projected Lines | Status |
|------------|----------------|--------|
| 3-Pre | ~250 | Well within limits |
| 3A | ~280 | Within limits |
| 3B | ~295 | Approaching 300 |

295 lines is within the 400-line "start thinking about splitting" threshold. However, if `run_all_phases()` grows complex in future work, consider extracting it to a separate `orchestration.py` module. Monitor during implementation.

---

## Verification Commands

```bash
# Unit tests for all worker pool modules
.venv/bin/pytest tests/unit/worker_pool/ -v

# Integration tests including phase gate flow
.venv/bin/pytest tests/integration/ -v

# Type checking
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
.venv/bin/mypy src/tdd_orchestrator/cli.py --strict

# Linting
.venv/bin/ruff check src/tdd_orchestrator/worker_pool/
.venv/bin/ruff check src/tdd_orchestrator/cli.py
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase gate too strict (false failures) | Execution blocked unnecessarily | Config flag `enable_phase_gates=True` to disable. Batch failure triggers individual re-runs for diagnosis. |
| Phase gate too lenient (misses real failures) | Broken phase cascades | Gate checks ALL test files (batch), not just the ones that changed. Regression check on prior phases catches cascading failures. |
| Multi-phase loop introduces new failure modes | Execution hangs or crashes | Existing single-phase path unchanged. New path opt-in via `--all-phases`. Timeout on gate checks. |
| Schema migration breaks existing data | DB errors | `ALTER TABLE ADD COLUMN` is additive only. No data loss. Existing rows get NULL for new columns. |
| CLI validate commands slow | Poor UX | Add `--timeout` option. Default 10 minutes for full regression. |

---

## Integration Checklist (Post-Phase 3)

- [ ] `run_all_phases()` processes all pending phases in order
- [ ] Phase gates run between phases and block on failure
- [ ] `enable_phase_gates` config flag can disable gates
- [ ] Phase gate re-runs individual test files on batch failure
- [ ] Regression check catches prior phase breakage
- [ ] End-of-run validation runs full regression + lint + type check
- [ ] Validation results stored in `execution_runs` table
- [ ] `validation_status` and `validation_details` columns exist
- [ ] CLI `validate --phase N` runs phase gate
- [ ] CLI `validate --run` runs end-of-run validation
- [ ] CLI `validate --all` runs all gates + run validation
- [ ] Existing single-phase execution path works unchanged
- [ ] pool.py is under 400 lines
- [ ] cli.py is under 400 lines
- [ ] mypy strict passes on all modified files

---

## Dependency Tracking

### What Phase 3 Produces

| Output | Consumer |
|--------|----------|
| `run_validator.py` -- end-of-run validation surface | Phase 5A hooks AC validation into run_validator |
| `phase_gate.py` -- phase gate infrastructure | Phase 4 detectors enhance gates when available |
| `validation_status`/`validation_details` columns | Phase 5A stores AC results in validation_details |
| CLI `validate` commands | Users can manually trigger validation |

### What Phase 3 Consumes

| Input | Source |
|-------|--------|
| `pipeline.py` -- stable integration surface | Phase 2 (2-Pre) |
| `done_criteria` results | Phase 2B |
| `verify_command` results | Phase 2A |
