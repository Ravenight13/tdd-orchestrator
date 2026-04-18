# Phase 2: Pipeline Extract + Metadata Execution

## Overview

| Attribute | Value |
|-----------|-------|
| **Goal** | Extract worker.py pipeline logic, then make `verify_command` and `done_criteria` useful |
| **Gaps addressed** | G1 (verify_command never executed), G2 (done_criteria never evaluated), G11 (worker.py structural debt) |
| **Dependencies** | None -- fully independent |
| **Estimated sessions** | 4 |
| **Risk level** | MEDIUM -- 2-Pre refactors the hot execution path |
| **Produces for downstream** | `pipeline.py` integration surface for Phase 3 gates; `done_criteria` results for Phase 3B run validation |

## Pre-existing State

- `worker_pool/worker.py` is at **782 lines** -- 18 lines from the 800-line hard limit
- `worker_pool/pool.py` is at 179 lines
- No pipeline extraction has been done
- `verify_command` and `done_criteria` are stored in DB but never read post-decomposition

## Task 2-Pre: Extract Pipeline Logic from Worker

### Problem

worker.py at 782 lines cannot accept ANY additions without violating the 800-line limit. Every subsequent phase in the roadmap needs integration points in the pipeline flow. Extraction is a prerequisite, not an optimization.

### Solution

Extract `_run_tdd_pipeline()` (lines 236-475, ~240 lines), `_run_green_with_retry()` (lines 611-731, ~121 lines), and `_consume_sdk_stream()` (lines 733-752, ~20 lines) into a new `worker_pool/pipeline.py` module. Total extracted: ~381 raw lines. With module overhead (imports, PipelineContext dataclass, docstring), pipeline.py will be ~400 lines. Worker drops from 782 to ~415 (782 - 381 + ~14 lines of import/call-site glue).

> **Note**: pipeline.py at ~400 lines sits right at the "start thinking about splitting" threshold (CLAUDE.md). This is acceptable because the extracted code is cohesive (single pipeline flow). If Phase 2A/2B additions push it past ~430, consider extracting `_run_green_with_retry` to a separate `green_retry.py` module.

**Worker keeps**: `process_task()`, `start()`, `stop()`, `_run_stage()`, `_verify_stage_result()`, `_heartbeat_loop()`

### Design Decisions

- **PipelineContext dataclass**: Pipeline functions receive a `PipelineContext` with db, verifier, prompt_builder, base_dir, worker_id, run_id, config, and static_review_circuit_breaker. This keeps the pipeline testable without constructing a full Worker.
- **Single call site replacement**: `Worker.process_task()` creates a `PipelineContext` and calls `pipeline.run_tdd_pipeline(context, task)`. No behavior change.
- **`_run_stage()` stays on Worker**: The roadmap approach -- pipeline.py receives a callable `run_stage` via context. This avoids moving too much at once and keeps Worker responsible for stage execution mechanics.

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/pipeline.py`** (new, ~400 lines)

```python
"""TDD pipeline execution logic extracted from Worker.

This module contains the core RED -> GREEN -> VERIFY pipeline flow,
including retry/escalation logic and SDK stream consumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from tdd_orchestrator.database import OrchestratorDB
    # ... other type imports

@dataclass
class PipelineContext:
    """Immutable context for pipeline execution."""
    db: OrchestratorDB
    verifier: Any  # CodeVerifier
    prompt_builder: Any  # PromptBuilder
    base_dir: str
    worker_id: str
    run_id: str
    config: Any  # WorkerConfig
    static_review_circuit_breaker: Any
    run_stage: Callable[..., Awaitable[Any]]  # Worker._run_stage bound method


async def run_tdd_pipeline(ctx: PipelineContext, task: dict[str, Any]) -> bool:
    """Execute the full TDD pipeline for a single task.

    RED -> RED_FIX -> GREEN (retry+escalate) -> VERIFY -> FIX -> RE_VERIFY
    """
    # ... extracted from Worker._run_tdd_pipeline() ...


async def _run_green_with_retry(ctx: PipelineContext, task: dict[str, Any]) -> bool:
    """Execute GREEN stage with retry and model escalation."""
    # ... extracted from Worker._run_green_with_retry() ...


async def _consume_sdk_stream(stream: Any) -> str:
    """Consume an SDK stream and return the accumulated text."""
    # ... extracted from Worker._consume_sdk_stream() ...
```

**File: `src/tdd_orchestrator/worker_pool/worker.py`** (782 -> ~415 lines)

Changes:
- Remove `_run_tdd_pipeline()`, `_run_green_with_retry()`, `_consume_sdk_stream()` (~381 lines)
- Import `PipelineContext`, `run_tdd_pipeline` from `pipeline`
- In `process_task()`, construct `PipelineContext` and call `run_tdd_pipeline(ctx, task)`

### Test Cases

**File: `tests/unit/worker_pool/test_pipeline.py`** (new, ~80 lines)

```python
# Test: PipelineContext creation with all required fields
# Test: run_tdd_pipeline calls run_stage in correct order (RED, GREEN, VERIFY)
# Test: _run_green_with_retry retries on failure with model escalation
# Test: _consume_sdk_stream accumulates text correctly
# Test: pipeline returns True on success, False on stage failure
```

**Regression**: All existing `tests/unit/worker_pool/` and `tests/integration/` tests must pass unchanged. The extraction should be invisible to callers.

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `worker_pool/pipeline.py` | 0 | ~400 | ~400 |
| `worker_pool/worker.py` | 782 | -365 | ~415 |
| NEW: `tests/unit/worker_pool/test_pipeline.py` | 0 | ~80 | ~80 |

---

## Task 2A: verify_command Execution

### Problem

The decomposer generates per-task shell commands like `"pytest tests/unit/config/test_loader.py -v"` and stores them in the `verify_command` DB column. The execution engine ignores them, running standardized VERIFY instead. The decomposer's specific intent (e.g., "run _this_ test file") is lost.

### Solution

New module `worker_pool/verify_command_runner.py` that:
1. Parses `verify_command` string into safe components (tool + target + flags)
2. Validates tool against allowlist (pytest, python, ruff, mypy)
3. Executes via `asyncio.create_subprocess_exec` (list-form, no shell=True)
4. Records result for later analysis

### Design Decisions

- **Parse, don't execute raw**: Security rule prohibits `shell=True`. Parser handles `uv run pytest ...` (strip prefix), `.venv/bin/pytest ...` (strip path), and bare `pytest ...`.
- **Supplemental, not replacement**: Main VERIFY still runs first. verify_command adds the decomposer's specific intent.
- **Non-blocking initially**: If parsing fails or command fails, log warning and continue. Collect data to decide when to promote to blocking.
- **Allowlisted tools only**: `pytest`, `python`, `ruff`, `mypy`. Anything else -> skip with warning.
- **Call site**: In `pipeline.py` after main VERIFY passes (not in `stage_verifier.py`).

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/verify_command_runner.py`** (new, ~130 lines)

```python
"""Parse and execute decomposer-generated verify_command strings safely."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ALLOWED_TOOLS: frozenset[str] = frozenset({"pytest", "python", "ruff", "mypy"})
STRIP_PREFIXES: tuple[str, ...] = ("uv run ", ".venv/bin/", "python -m ")


@dataclass
class VerifyCommandResult:
    """Result of running a verify_command."""
    command: str
    parsed_tool: str | None
    parsed_args: list[str]
    exit_code: int | None  # None if not executed
    stdout: str
    stderr: str
    skipped: bool
    skip_reason: str


def parse_verify_command(raw: str) -> tuple[str | None, list[str], str]:
    """Parse a verify_command string into (tool, args, skip_reason).

    Returns (tool, args, "") on success, (None, [], reason) if unparseable.
    """
    # ... strip prefixes, extract tool, validate against allowlist ...


async def run_verify_command(
    raw: str,
    base_dir: str,
    timeout: int = 60,
) -> VerifyCommandResult:
    """Parse and execute a verify_command safely."""
    # ... parse, validate, execute with create_subprocess_exec ...
```

**File: `src/tdd_orchestrator/worker_pool/pipeline.py`** (~400 -> ~420 lines)

Add call after VERIFY succeeds:

```python
# After VERIFY passes
if task.get("verify_command"):
    from tdd_orchestrator.worker_pool.verify_command_runner import run_verify_command
    result = await run_verify_command(task["verify_command"], ctx.base_dir)
    if not result.skipped and result.exit_code != 0:
        logger.warning(
            "verify_command failed for %s (non-blocking): %s",
            task.get("key", "?"), result.stderr[:200]
        )
    # Store result for analysis (Phase 3B can aggregate these)
```

### Test Cases

**File: `tests/unit/worker_pool/test_verify_command_runner.py`** (new, ~130 lines)

```python
# Parsing tests:
# Test: "pytest tests/test_foo.py -v" -> tool=pytest, args=["tests/test_foo.py", "-v"]
# Test: "uv run pytest tests/test_foo.py" -> tool=pytest, args=["tests/test_foo.py"]
# Test: ".venv/bin/pytest tests/test_foo.py" -> tool=pytest, args=["tests/test_foo.py"]
# Test: "ruff check src/module.py" -> tool=ruff, args=["check", "src/module.py"]
# Test: "node scripts/test.js" -> tool=None, skipped=True (not in allowlist)
# Test: "rm -rf /" -> tool=None, skipped=True
# Test: empty string -> tool=None, skipped=True
# Test: "python -m pytest ..." -> tool=pytest, args=[...]

# Execution tests (mocked subprocess):
# Test: successful execution -> exit_code=0
# Test: failed execution -> exit_code=1, stderr captured
# Test: timeout -> handled gracefully
# Test: skipped command -> no subprocess call
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `worker_pool/verify_command_runner.py` | 0 | ~130 | ~130 |
| `worker_pool/pipeline.py` | ~400 | +20 | ~420 |
| NEW: `tests/unit/worker_pool/test_verify_command_runner.py` | 0 | ~130 | ~130 |

---

## Task 2B: done_criteria Heuristic Evaluation

### Problem

`done_criteria` like "All tests pass and code is formatted with ruff" exists as text in the DB. Never checked. The decomposer generates specific intent, but the execution engine ignores it.

### Solution

New module `worker_pool/done_criteria_checker.py` with heuristic matchers:
- `"tests pass"` / `"all tests pass"` -> already covered by VERIFY (mark satisfied)
- `"importable"` / `"exports X"` -> `python -c 'from module import X'`
- `"file exists"` -> `Path(x).exists()`
- Everything else -> `"unverifiable"` (logged, not blocking)

### Design Decisions

- **Non-blocking**: Logs results, does not fail tasks. Informational layer.
- **Called at task completion**: In `pipeline.py`, after VERIFY passes, before returning success.
- **Results recorded**: JSON blob for later aggregation by Phase 3B run validator.
- **No LLM calls**: Pure heuristic. Zero cost, deterministic.

### Implementation Details

**File: `src/tdd_orchestrator/worker_pool/done_criteria_checker.py`** (new, ~140 lines)

```python
"""Heuristic evaluation of done_criteria strings."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CriterionResult:
    """Result of evaluating a single done criterion."""
    criterion: str
    status: str  # "satisfied", "failed", "unverifiable"
    detail: str


@dataclass
class DoneCriteriaResult:
    """Aggregate result for all done_criteria of a task."""
    task_key: str
    results: list[CriterionResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        satisfied = sum(1 for r in self.results if r.status == "satisfied")
        total = len(self.results)
        return f"{satisfied}/{total} criteria satisfied"


def parse_criteria(raw: str) -> list[str]:
    """Split done_criteria text into individual criteria."""
    # Split on newlines, semicolons, "and" conjunctions
    # ... implementation ...


async def evaluate_criteria(
    raw: str,
    task_key: str,
    base_dir: str,
) -> DoneCriteriaResult:
    """Evaluate all done_criteria for a task."""
    criteria = parse_criteria(raw)
    result = DoneCriteriaResult(task_key=task_key)
    for criterion in criteria:
        result.results.append(await _evaluate_single(criterion, base_dir))
    return result


async def _evaluate_single(criterion: str, base_dir: str) -> CriterionResult:
    """Evaluate a single criterion string."""
    lower = criterion.lower().strip()
    if _matches_test_pass(lower):
        return CriterionResult(criterion, "satisfied", "Covered by VERIFY stage")
    if match := _matches_importable(lower):
        return await _check_importable(criterion, match, base_dir)
    if match := _matches_file_exists(lower):
        return _check_file_exists(criterion, match, base_dir)
    return CriterionResult(criterion, "unverifiable", "No heuristic matcher")
```

**File: `src/tdd_orchestrator/worker_pool/pipeline.py`** (~420 -> ~430 lines)

Add call at task completion:

```python
# After VERIFY passes, before returning success
if task.get("done_criteria"):
    from tdd_orchestrator.worker_pool.done_criteria_checker import evaluate_criteria
    dc_result = await evaluate_criteria(
        task["done_criteria"], task.get("key", "?"), ctx.base_dir
    )
    logger.info("Done criteria for %s: %s", task.get("key", "?"), dc_result.summary)
    # Store result for Phase 3B aggregation
```

### Test Cases

**File: `tests/unit/worker_pool/test_done_criteria_checker.py`** (new, ~100 lines)

```python
# Parsing:
# Test: "All tests pass" -> ["All tests pass"]
# Test: "Tests pass and code formatted" -> ["Tests pass", "code formatted"]
# Test: "Tests pass; module importable" -> ["Tests pass", "module importable"]
# Test: empty string -> []

# Evaluation:
# Test: "All tests pass" -> satisfied (covered by VERIFY)
# Test: "tests pass" -> satisfied
# Test: "module X is importable" -> calls subprocess, checks exit code
# Test: "file src/foo.py exists" -> checks Path.exists()
# Test: "performance is acceptable" -> unverifiable
# Test: multiple criteria, mixed results -> correct summary
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `worker_pool/done_criteria_checker.py` | 0 | ~140 | ~140 |
| `worker_pool/pipeline.py` | ~420 | +10 | ~430 |
| NEW: `tests/unit/worker_pool/test_done_criteria_checker.py` | 0 | ~100 | ~100 |

---

## Session Breakdown

### Session 1: Pipeline Extraction (2-Pre)

**This is the highest-risk task in Phase 2.** Refactoring the hot execution path. Zero tolerance for behavior change.

**Steps**:
1. Read `worker_pool/worker.py` thoroughly -- understand all method boundaries and state dependencies
2. Identify all `self.*` references in extracted methods -- these become `PipelineContext` fields
3. Create `pipeline.py` with `PipelineContext` dataclass
4. Move `_run_tdd_pipeline()`, `_run_green_with_retry()`, `_consume_sdk_stream()`
5. Update `Worker.process_task()` to create context and call `pipeline.run_tdd_pipeline()`
6. Run ALL existing tests -- extraction must be invisible to callers
7. Write `test_pipeline.py` for the new module

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/ -v
.venv/bin/pytest tests/integration/ -v  # CRITICAL: regression
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
.venv/bin/ruff check src/tdd_orchestrator/worker_pool/
```

### Session 2: verify_command Execution (2A)

**Steps**:
1. Read existing `CodeVerifier._run_command()` for subprocess pattern
2. Create `verify_command_runner.py` with parser and executor
3. Add call site in `pipeline.py` after VERIFY
4. Write comprehensive tests (parsing + execution)
5. Verify with mocked subprocess

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/ -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
```

### Session 3: done_criteria Evaluation (2B)

**Steps**:
1. Query DB for sample done_criteria values to understand real-world patterns
2. Create `done_criteria_checker.py` with parser and matchers
3. Add call site in `pipeline.py` at task completion
4. Write tests for all matcher types
5. Verify with mocked filesystem and subprocess

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/worker_pool/ -v
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict
```

### Session 4: Integration Regression

**Steps**:
1. Run full test suite
2. Run a sample decomposition + execution to verify end-to-end
3. Verify verify_command and done_criteria results are logged
4. Check pipeline.py line count is within bounds
5. Clean up any TODO items from Sessions 1-3

**Session boundary check**:
```bash
.venv/bin/pytest tests/ -v  # full suite
.venv/bin/mypy src/ --strict
.venv/bin/ruff check src/
```

---

## Verification Commands

```bash
# Unit tests
.venv/bin/pytest tests/unit/worker_pool/ -v

# Integration regression (CRITICAL after extraction)
.venv/bin/pytest tests/integration/ -v

# Type checking
.venv/bin/mypy src/tdd_orchestrator/worker_pool/ --strict

# Linting
.venv/bin/ruff check src/tdd_orchestrator/worker_pool/
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pipeline extraction breaks execution flow | Tasks fail to execute | Extract-only refactor, no behavior change. Full integration suite must pass before/after. Rollback: revert extraction commit. |
| PipelineContext missing a required field | AttributeError at runtime | List all `self.*` references in extracted methods before creating dataclass. Tests catch missing fields. |
| verify_command parser mishandles LLM output | Warning logged, execution continues | Non-blocking initially. Parser is conservative (skip unknown patterns). Data collection informs promotion. |
| done_criteria matcher false positives | "satisfied" when not actually met | Low risk -- most criteria are "tests pass" which IS covered by VERIFY. Matcher is conservative. |
| pipeline.py grows past 430 lines | File size concern | Projected at ~430 after Phase 2 complete. Already above the 400-line threshold. If Phase 3 integration points push it further, extract `_run_green_with_retry` (~121 lines) to a separate `green_retry.py` module, bringing pipeline.py back to ~310. |

---

## Integration Checklist (Post-Phase 2)

- [ ] `worker_pool/worker.py` is under 500 lines (~415 expected)
- [ ] `worker_pool/pipeline.py` exists and handles full TDD pipeline
- [ ] All existing worker pool tests pass unchanged (regression)
- [ ] `PipelineContext` contains all required fields
- [ ] `verify_command_runner` parses common patterns (bare, uv run, .venv/bin/)
- [ ] `verify_command_runner` rejects non-allowlisted tools
- [ ] `done_criteria_checker` satisfies "tests pass" criteria
- [ ] `done_criteria_checker` marks unrecognized criteria as "unverifiable"
- [ ] Results are logged for both verify_command and done_criteria
- [ ] mypy strict passes on all worker_pool files
- [ ] ruff check passes on all worker_pool files

---

## Dependency Tracking

### What Phase 2 Produces

| Output | Consumer |
|--------|----------|
| `pipeline.py` -- stable integration surface | Phase 3 gates hook into pipeline flow |
| `PipelineContext` dataclass | Phase 3A, 3B use context for test discovery |
| `done_criteria` results | Phase 3B aggregates in run validation |
| `verify_command` results | Phase 3B includes in validation details |
| worker.py headroom (~415 lines) | All future phases can safely add to worker |

### What Phase 2 Consumes

Nothing -- Phase 2 is fully independent and can start immediately.

### Design Note: Extraction Boundary

The plan extracts `_run_tdd_pipeline`, `_run_green_with_retry`, and `_consume_sdk_stream` (~381 raw lines) but leaves `_run_stage()` (~132 lines) on Worker. pipeline.py starts at ~400 lines and reaches ~430 after Tasks 2A/2B.

**Mitigation options if pipeline.py exceeds 430 lines:**
1. Extract `_run_green_with_retry` (~121 lines) to `green_retry.py`, reducing pipeline.py to ~310.
2. Alternatively, move `_run_stage` from Worker to pipeline.py (makes pipeline fully self-contained at ~560, but then split pipeline into `pipeline.py` + `stage_runner.py`).

**Recommendation**: Accept ~430 for Phase 2 since the code is cohesive. If Phase 3 adds more integration points, apply option 1.
