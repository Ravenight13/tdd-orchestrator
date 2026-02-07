# Add REFACTOR Stage to TDD Pipeline

**Status:** Proposed
**Author:** Cliff Clarke
**Date:** 2026-02-07
**Prerequisite:** All 324+ tests passing, mypy strict clean, ruff clean
**Goal:** Add a REFACTOR stage after VERIFY in the TDD pipeline to enforce file size limits, remove duplication, and ensure project conventions before marking tasks complete

---

## Context

The current TDD pipeline is:

```
RED -> RED_FIX -> GREEN -> VERIFY -> (FIX -> RE_VERIFY)
```

After this change:

```
RED -> RED_FIX -> GREEN -> VERIFY -> REFACTOR -> RE_VERIFY -> (FIX -> RE_VERIFY)
```

The REFACTOR stage runs **after VERIFY passes** (all tests pass, mypy clean, ruff clean). It is an LLM-driven stage that reads the implementation file, checks for quality issues, and refactors if needed. After REFACTOR, RE_VERIFY confirms nothing broke.

**Why:** The GREEN stage produces minimal code to pass tests. It does not enforce project conventions like the 400-line split threshold, naming patterns, or duplication removal. Without REFACTOR, these quality issues accumulate and require manual cleanup.

**Key files to understand:**
- @src/tdd_orchestrator/models.py (Stage enum, StageResult, VerifyResult)
- @src/tdd_orchestrator/worker_pool/worker.py (_run_tdd_pipeline, _verify_stage_result)
- @src/tdd_orchestrator/worker_pool/config.py (STAGE_TIMEOUTS, model config)
- @src/tdd_orchestrator/prompt_builder.py (stage prompts, build() dispatcher)
- @src/tdd_orchestrator/code_verifier.py (verification tools)

---

## Build Sequence

### Plan 1: Stage Enum and Models (2 tasks)

#### Task 1: Add REFACTOR to Stage enum and update docstrings

**Files:** `src/tdd_orchestrator/models.py`

**Action:**
1. Add `REFACTOR = "refactor"` to the `Stage` enum (between VERIFY and FIX)
2. Update the docstring to document the new pipeline flow:
   ```
   RED -> RED_FIX -> GREEN -> VERIFY -> REFACTOR -> RE_VERIFY -> (FIX -> RE_VERIFY)
   ```
3. Add a `RefactorResult` dataclass to capture refactor-specific output:
   ```python
   @dataclass
   class RefactorResult:
       """Result from the REFACTOR stage analysis."""
       files_checked: int
       files_refactored: int
       issues_found: list[dict[str, Any]]
       lines_before: int
       lines_after: int

       @property
       def had_changes(self) -> bool:
           return self.files_refactored > 0
   ```

**Verify:** `mypy src/tdd_orchestrator/models.py --strict` passes. Existing tests still pass.

**Done:** Stage enum has REFACTOR value. RefactorResult dataclass exists with typed fields.

#### Task 2: Add REFACTOR timeout and config

**Files:** `src/tdd_orchestrator/worker_pool/config.py`

**Action:**
1. Add `Stage.REFACTOR: 300` (5 min) to `STAGE_TIMEOUTS`
2. Add `REFACTOR_MODEL` constant set to Opus (refactoring needs strong reasoning):
   ```python
   REFACTOR_MODEL = "claude-opus-4-5-20251101"
   ```

**Verify:** `mypy src/tdd_orchestrator/worker_pool/config.py --strict` passes.

**Done:** REFACTOR stage has timeout config and model constant.

---

### Plan 2: Refactor Prompt and Checker (2 tasks)

#### Task 3: Create refactor_checker.py for file size and quality analysis

**Files:** `src/tdd_orchestrator/refactor_checker.py` (NEW)

**Action:** Create a module that analyzes implementation files for refactoring needs. This runs BEFORE the LLM prompt to determine if refactoring is even needed (skip LLM call if code is already clean).

```python
"""Pre-REFACTOR analysis for file size, duplication, and convention checks.

Runs static analysis on implementation files to determine if the REFACTOR
stage LLM prompt should be invoked. Avoids unnecessary LLM calls when
the GREEN stage already produced clean code.
"""

@dataclass
class RefactorCheck:
    """Result of pre-refactor analysis."""
    needs_refactor: bool
    reasons: list[str]
    file_lines: int

@dataclass
class RefactorCheckConfig:
    """Thresholds for refactor triggers."""
    split_threshold: int = 400    # Warn and suggest split
    hard_limit: int = 800         # Must split
    max_function_length: int = 50 # Lines per function
    max_class_methods: int = 15   # Methods per class

async def check_needs_refactor(
    impl_file: str,
    base_dir: Path,
    config: RefactorCheckConfig | None = None,
) -> RefactorCheck:
    """Check if an implementation file needs refactoring.

    Checks:
    1. File line count vs thresholds (400 warn, 800 block)
    2. Function/method length
    3. Class method count
    4. Duplicate code patterns (simple AST-based detection)

    Returns RefactorCheck with needs_refactor=False if all clean.
    """
```

Key design decisions:
- This is a **synchronous analysis** (reads files, counts lines, parses AST) — no LLM needed
- If `needs_refactor` is False, the REFACTOR stage is **skipped entirely** (no LLM invocation)
- Uses the existing `ast` stdlib module, not the project's `ast_checker` (different purpose)
- Keeps the module under 200 lines

**Verify:** `mypy src/tdd_orchestrator/refactor_checker.py --strict` passes. Unit tests for all check functions pass.

**Done:** `check_needs_refactor()` can analyze a Python file and return whether refactoring is needed with specific reasons.

#### Task 4: Add PromptBuilder.refactor() method

**Files:** `src/tdd_orchestrator/prompt_builder.py`

**Action:**
1. Add a `refactor()` static method to `PromptBuilder`:
   ```python
   @staticmethod
   def refactor(task: dict[str, Any], refactor_reasons: list[str]) -> str:
       """Generate prompt for REFACTOR phase (clean up implementation).

       This prompt instructs the LLM to refactor the implementation file
       based on specific issues identified by the pre-refactor checker.
       The focus is on code quality without changing behavior.
       """
   ```

   The prompt must instruct the LLM to:
   - Read the implementation file and test file
   - Address ONLY the specific reasons provided (file too long, function too long, etc.)
   - Split files if over 400 lines (creating new module + updating imports)
   - Remove duplication
   - Ensure all tests still pass after refactoring
   - NOT add new functionality
   - NOT change public API (same exports, same function signatures)

2. Update the `build()` dispatcher to handle `Stage.REFACTOR`:
   ```python
   if stage == StageEnum.REFACTOR:
       refactor_reasons = kwargs.get("refactor_reasons")
       if refactor_reasons is None:
           msg = "REFACTOR stage requires 'refactor_reasons' argument"
           raise ValueError(msg)
       return PromptBuilder.refactor(task, refactor_reasons)
   ```

**Verify:** `mypy src/tdd_orchestrator/prompt_builder.py --strict` passes. Unit tests for `PromptBuilder.build(Stage.REFACTOR, ...)` pass.

**Done:** `PromptBuilder.refactor()` produces a focused refactoring prompt. `build()` dispatcher routes REFACTOR stage correctly.

---

### Plan 3: Pipeline Integration (2 tasks)

#### Task 5: Wire REFACTOR into _run_tdd_pipeline

**Files:** `src/tdd_orchestrator/worker_pool/worker.py`

**Action:** Modify `_run_tdd_pipeline()` to insert the REFACTOR stage after VERIFY passes but before marking the task complete.

Current flow (lines 333-362):
```python
# Stage 3: VERIFY
result = await self._run_stage(Stage.VERIFY, task)
if result.success:
    await commit_stage(...)
    return True

# Stage 4: FIX (if VERIFY failed)
...
# Stage 5: RE_VERIFY
...
```

New flow:
```python
# Stage 3: VERIFY
result = await self._run_stage(Stage.VERIFY, task)
if not result.success:
    # ... existing FIX -> RE_VERIFY flow (unchanged) ...

# Stage 3.5: REFACTOR (only if VERIFY passed)
refactor_check = await check_needs_refactor(
    task.get("impl_file", ""), self.base_dir
)
if refactor_check.needs_refactor:
    result = await self._run_stage(
        Stage.REFACTOR, task,
        refactor_reasons=refactor_check.reasons,
        model_override=REFACTOR_MODEL,
    )
    if not result.success:
        return False
    await commit_stage(
        task_key, "REFACTOR",
        f"wip({task_key}): REFACTOR - code cleanup",
        self.base_dir,
    )

    # RE_VERIFY after refactor to confirm nothing broke
    result = await self._run_stage(Stage.RE_VERIFY, task)
    if not result.success:
        # Refactor broke something — enter FIX flow
        if result.issues:
            result = await self._run_stage(Stage.FIX, task, issues=result.issues)
            if not result.success:
                return False
            result = await self._run_stage(Stage.RE_VERIFY, task)
            if not result.success:
                return False
        else:
            return False
    await commit_stage(
        task_key, "RE_VERIFY",
        f"feat({task_key}): complete - all checks pass",
        self.base_dir,
    )
else:
    # No refactoring needed — commit VERIFY and done
    await commit_stage(
        task_key, "VERIFY",
        f"feat({task_key}): complete - all checks pass",
        self.base_dir,
    )

return True
```

Key decisions:
- REFACTOR is **conditional** — only runs if `check_needs_refactor()` says so
- Uses Opus model (refactoring needs strong reasoning about code structure)
- If REFACTOR breaks tests, enters FIX -> RE_VERIFY recovery (same pattern as existing)
- REFACTOR is committed separately (preserves audit trail)
- If no refactoring needed, pipeline behavior is identical to current

**Verify:** `mypy src/tdd_orchestrator/worker_pool/worker.py --strict`. Existing tests pass. New integration test confirms REFACTOR stage runs when file exceeds 400 lines.

**Done:** Pipeline executes REFACTOR conditionally after VERIFY, with RE_VERIFY confirmation.

#### Task 6: Add _verify_stage_result handler for REFACTOR

**Files:** `src/tdd_orchestrator/worker_pool/worker.py`

**Action:** Add REFACTOR case to `_verify_stage_result()`:

```python
if stage == Stage.REFACTOR:
    # REFACTOR succeeds if no exceptions (actual verification in RE_VERIFY)
    await self.db.record_stage_attempt(
        task_id=task["id"],
        stage=stage.value,
        attempt_number=1,
        success=True,
    )
    return StageResult(stage=stage, success=True, output=result_text)
```

This follows the same pattern as FIX and RED_FIX — the stage itself always "succeeds" if no exceptions, and the RE_VERIFY stage does the actual verification.

**Verify:** `mypy src/tdd_orchestrator/worker_pool/worker.py --strict`.

**Done:** REFACTOR stage result is properly verified and recorded.

---

### Plan 4: Tests and Verification (2 tasks)

#### Task 7: Unit tests for refactor_checker.py

**Files:** `tests/unit/test_refactor_checker.py` (NEW)

**Action:** Write comprehensive tests:
1. `test_short_file_no_refactor` — File under 400 lines returns needs_refactor=False
2. `test_file_over_split_threshold` — File at 401+ lines triggers refactor with reason
3. `test_file_over_hard_limit` — File at 801+ lines triggers refactor with blocking reason
4. `test_long_function_triggers_refactor` — Function over 50 lines triggers refactor
5. `test_many_methods_triggers_refactor` — Class with 16+ methods triggers refactor
6. `test_clean_file_no_refactor` — Well-structured file passes all checks
7. `test_custom_config_thresholds` — Custom RefactorCheckConfig values are respected
8. `test_nonexistent_file` — Missing file returns needs_refactor=False with warning

**Verify:** `pytest tests/unit/test_refactor_checker.py -v` all pass.

**Done:** All refactor checker edge cases covered.

#### Task 8: Integration test for REFACTOR in pipeline

**Files:** `tests/unit/test_refactor_pipeline.py` (NEW)

**Action:** Test the REFACTOR stage integration without SDK (mock `_run_stage`):
1. `test_pipeline_skips_refactor_when_clean` — Short clean file skips REFACTOR entirely
2. `test_pipeline_runs_refactor_when_file_too_long` — 500-line file triggers REFACTOR stage
3. `test_pipeline_reverify_after_refactor` — RE_VERIFY runs after REFACTOR
4. `test_pipeline_fix_after_failed_refactor_reverify` — FIX -> RE_VERIFY if REFACTOR broke tests
5. `test_refactor_prompt_includes_reasons` — PromptBuilder.refactor() includes check reasons
6. `test_refactor_uses_opus_model` — REFACTOR stage uses REFACTOR_MODEL override

These tests mock the SDK and file system to test the pipeline flow logic.

**Verify:** `pytest tests/unit/test_refactor_pipeline.py -v` all pass. Full suite `pytest tests/unit/ -v` still passes.

**Done:** Pipeline flow with REFACTOR stage is tested. All existing tests unbroken.

---

### Final Verification

```bash
# All existing tests pass (regression)
.venv/bin/pytest tests/unit/ --tb=short -q

# New tests pass
.venv/bin/pytest tests/unit/test_refactor_checker.py tests/unit/test_refactor_pipeline.py -v

# Type checking clean
.venv/bin/mypy src/ --strict

# Linting clean
.venv/bin/ruff check src/

# File size check (no file over 400 lines)
wc -l src/tdd_orchestrator/refactor_checker.py
wc -l src/tdd_orchestrator/worker_pool/worker.py
```

---

## Success Criteria

1. `Stage.REFACTOR` exists in the enum and is documented
2. `PromptBuilder.refactor()` generates a focused refactoring prompt
3. `check_needs_refactor()` detects file size violations and quality issues
4. Pipeline runs REFACTOR conditionally (only when needed — no wasted LLM calls)
5. RE_VERIFY confirms refactoring didn't break anything
6. All 324+ existing tests still pass
7. New tests cover checker logic and pipeline integration
8. mypy strict and ruff clean on all modified/new files
9. No file exceeds 400 lines

---

## Files Created

| File | Lines (est) | Purpose |
|------|-------------|---------|
| `src/tdd_orchestrator/refactor_checker.py` | ~180 | Pre-refactor static analysis |
| `tests/unit/test_refactor_checker.py` | ~200 | Checker unit tests |
| `tests/unit/test_refactor_pipeline.py` | ~250 | Pipeline integration tests |

## Files Modified

| File | Change | Lines Added (est) |
|------|--------|-------------------|
| `src/tdd_orchestrator/models.py` | Add REFACTOR enum + RefactorResult | ~25 |
| `src/tdd_orchestrator/worker_pool/config.py` | Add timeout + model constant | ~5 |
| `src/tdd_orchestrator/prompt_builder.py` | Add refactor() + update build() | ~80 |
| `src/tdd_orchestrator/worker_pool/worker.py` | Wire REFACTOR into pipeline + verify handler | ~50 |

## Total Estimated Impact

- **New files:** 3 (1 production, 2 test)
- **Modified files:** 4
- **New lines:** ~790
- **New tests:** ~14
- **LLM invocations per task:** 0-1 additional (only when refactoring needed)
