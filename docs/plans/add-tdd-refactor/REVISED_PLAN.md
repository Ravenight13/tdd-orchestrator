# Add REFACTOR Stage to TDD Pipeline -- Revised Plan

**Status:** Proposed (Revised)
**Original Author:** Cliff Clarke
**Revision By:** Opus Architect Review
**Date:** 2026-02-07
**Prerequisite:** All 504 tests passing, mypy strict clean, ruff clean
**Goal:** Add a REFACTOR stage after VERIFY in the TDD pipeline to enforce file size limits, remove duplication, and ensure project conventions before marking tasks complete

---

## Architectural Review Summary

This revision addresses findings from a deep architectural review of the Sonnet-drafted plan at `polished-weaving-koala.md` and the original plan at `docs/plans/add-tdd-refactor/PLAN.md`. Below is each finding, its severity, and the corrective action taken.

### Critical Corrections

| # | Finding | Severity | Action |
|---|---------|----------|--------|
| 1 | **Test count is 504, not 324.** Both plans cite 324 tests. The actual count is 504. | HIGH | Corrected throughout. Regression scope is larger than estimated. |
| 2 | **PipelineExecutor extraction will break 50+ test call sites.** The grep reveals that integration and e2e tests directly call `worker._run_stage`, `worker._run_tdd_pipeline`, and `worker._run_green_with_retry` across 8 test files and 50+ call sites. A PipelineExecutor class with a `self.pipeline` delegation pattern would break all of them. | CRITICAL | Rejected PipelineExecutor extraction. Use targeted method extraction instead (see Phase 0 redesign below). |
| 3 | **prompt_templates.py at ~600 lines creates a new near-limit file.** Extracting all template strings from prompt_builder.py into a single file produces ~600 lines of constants. This exceeds the 400-line split threshold on day one. | HIGH | Extract templates per-stage instead of into a monolithic file (see Phase 0.1 redesign). |
| 4 | **`invocations.stage` column has no CHECK constraint** -- unlike `attempts.stage`, the `invocations` table uses a bare `TEXT NOT NULL` for stage. No schema change needed there. However, both plans missed that `attempts.stage` also needs `'refactor'` added. | MEDIUM | Schema task (Phase 1.3) now explicitly covers the `attempts` CHECK constraint. |
| 5 | **Schema uses `CREATE TABLE IF NOT EXISTS` but CHECK constraints are baked into CREATE.** Existing databases will NOT get the updated CHECK constraint because the table already exists. The plan says "users can delete and recreate" but does not mention that `record_stage_attempt` will silently fail with a CHECK constraint violation on existing databases. | MEDIUM | Added explicit migration note and a runtime guard in the REFACTOR stage handler. |

### Design Decision Verdicts

| Question | Original Answer | Revised Verdict | Rationale |
|----------|----------------|-----------------|-----------|
| REFACTOR retry? | No | **No -- Confirmed.** | Correct. REFACTOR is best-effort. If RE_VERIFY fails, the existing FIX -> RE_VERIFY loop handles recovery. Adding retry complexity for a code-quality stage is unnecessary. |
| PipelineExecutor composition? | Yes | **No -- Rejected.** | 50+ test call sites reference `worker._run_stage` etc. directly. The cost of updating all tests outweighs the benefit. Instead, extract only the new REFACTOR concern into a standalone function, keeping the Worker class structure intact. |
| Extract all prompt templates? | Yes, single file | **No -- Split by concern.** | A single 600-line file just moves the problem. Instead, add the REFACTOR prompt inline in prompt_builder.py (the file drops to ~180 after proper extraction) OR use the per-stage pattern already established in `decomposition/prompts.py`. See Phase 0 for the revised approach. |
| Skip DB migration? | Yes | **Yes -- Confirmed, with caveat.** | Correct for a dev tool. But the plan must document the failure mode (CHECK constraint violation) and provide a one-line ALTER TABLE command for users who want to preserve data. |

---

## Revised Implementation Phases

### Phase 0: File Size Reduction (Pre-Requisite)

The original plan proposed two aggressive file splits. The revised approach is more conservative: reduce prompt_builder.py below the 400-line threshold without creating a monolithic replacement, and leave worker.py as-is since the REFACTOR changes fit within the 800-line limit.

#### Why NOT Extract PipelineExecutor

The PipelineExecutor pattern (composition via `self.pipeline = PipelineExecutor(...)`) was the original plan's centerpiece. Rejecting it requires justification.

**Evidence against PipelineExecutor:**

1. **50+ test breakages.** Integration tests (`test_worker_processing.py`, `test_worker_sdk_failures.py`, `test_green_retry_unit.py`, `test_green_retry_edge_cases.py`, `test_green_retry_integration.py`) and e2e tests (`test_full_pipeline.py`, `test_decomposition_to_execution.py`) directly access `worker._run_stage`, `worker._run_tdd_pipeline`, and `worker._run_green_with_retry`. Changing these from Worker methods to `worker.pipeline.run_stage(...)` would require updating every call site plus all `patch.object(worker, "_run_stage", ...)` mocks.

2. **The split saves nothing right now.** worker.py is 767 lines. Adding REFACTOR integration (~35 lines to `_run_tdd_pipeline` + ~10 lines to `_verify_stage_result`) brings it to ~812 lines -- over the 800 limit. But extracting a PipelineExecutor creates TWO files: ~535 and ~240, and the 535-line file is ALSO over the 400-line threshold. We gain nothing.

3. **Simpler alternative exists.** We can reduce worker.py below 800 by extracting `_verify_stage_result` (110 lines) into a standalone module `worker_pool/stage_verifier.py`. This method is a pure dispatcher that takes `(stage, task, result_text)` and returns `StageResult`. It has no `self` dependencies beyond `self.db`, `self.verifier`, and `self.run_id` -- these can be passed as arguments. Tests that mock `_verify_stage_result` (rare -- most tests mock `_run_stage` which calls it internally) are easy to update.

**Alternative chosen:** Extract `_verify_stage_result` into a function-based module `stage_verifier.py`, and extract prompt template strings from `prompt_builder.py`.

#### Task 0.1: Extract prompt template strings from prompt_builder.py

**Problem:** prompt_builder.py is 725 lines. Adding a `refactor()` method (~50 lines) would push it to ~775.

**Solution:** The bulk of prompt_builder.py is long template strings inside each static method (RED: 80 lines of string, GREEN: 100 lines of string, etc.). Extract the template strings as module-level constants to a new file `prompt_templates.py`, keeping the formatting logic and `build()` dispatcher in `prompt_builder.py`.

**BUT** a single `prompt_templates.py` at ~600 lines exceeds the 400-line threshold. Instead, keep the templates inline but extract the verbose instructional sections (type annotation examples, static review examples) into reusable constants within prompt_builder.py itself. The repeated sections between `green()` and `build_green_retry()` can be deduplicated.

Revised approach:

- CREATE `src/tdd_orchestrator/prompt_templates.py` (~350 lines)
  - Move template string constants: `RED_PROMPT_TEMPLATE`, `GREEN_PROMPT_TEMPLATE`, `GREEN_RETRY_TEMPLATE`, `VERIFY_PROMPT_TEMPLATE`, `FIX_PROMPT_TEMPLATE`, `RED_FIX_PROMPT_TEMPLATE`
  - Move the shared instruction blocks (`TYPE_ANNOTATION_INSTRUCTIONS`, `STATIC_REVIEW_INSTRUCTIONS`, `FILE_STRUCTURE_CONSTRAINT`) into module-level constants that the templates reference
  - This deduplicates ~80 lines of repeated type annotation instructions between `green()` and `build_green_retry()`
- MODIFY `src/tdd_orchestrator/prompt_builder.py` (725 -> ~200 lines)
  - Import templates from `prompt_templates.py`
  - Keep `_parse_criteria()`, `_parse_module_exports()` (parsing logic)
  - Keep all static methods but they now do `.format()` on imported templates
  - Keep `build()` dispatcher
- Verify: `pytest tests/ -v --tb=short`, `mypy --strict`, `ruff check`

**Line count validation:**
- The RED prompt is ~80 lines of string + 20 lines of formatting logic
- GREEN prompt is ~100 lines of string + 25 lines of formatting
- build_green_retry is ~35 lines of string
- verify is ~25 lines
- fix is ~45 lines
- red_fix is ~60 lines
- Total template strings: ~345 lines -> prompt_templates.py
- Total formatting logic + parsers + build(): ~200 lines -> prompt_builder.py
- Both files are well under 400.

**Risk:** LOW. No test file imports `PromptBuilder` -- only `worker.py` imports it. The public API (`PromptBuilder.build()`, `PromptBuilder.red()`, etc.) does not change.

#### Task 0.2: Extract stage verification from worker.py

**Problem:** worker.py is 767 lines. Adding REFACTOR integration will push it over 800.

**Solution:** Extract `_verify_stage_result()` (lines 646-756, 110 lines) into a standalone async function in `worker_pool/stage_verifier.py`.

- CREATE `src/tdd_orchestrator/worker_pool/stage_verifier.py` (~140 lines)
  - `async def verify_stage_result(stage, task, result_text, db, verifier, *, skip_recording=False) -> StageResult`
  - Pure function -- receives db and verifier as arguments instead of using `self`
  - Contains all the stage-specific verification logic (RED, GREEN, VERIFY/RE_VERIFY, FIX, RED_FIX, and later REFACTOR)
- MODIFY `src/tdd_orchestrator/worker_pool/worker.py` (767 -> ~660 lines)
  - Replace `_verify_stage_result()` with a call to `from .stage_verifier import verify_stage_result`
  - Update `_run_stage()` to call `verify_stage_result(stage, task, result_text, self.db, self.verifier, ...)`
- MODIFY `src/tdd_orchestrator/worker_pool/__init__.py`
  - No changes needed -- `stage_verifier` is an internal module, not part of the public API
- Verify: all 504 tests pass, `mypy --strict`, `ruff check`, `wc -l` on both files

**Test impact analysis:**
- Tests that mock `_run_stage` (the vast majority): **UNAFFECTED**. `_run_stage` still exists on Worker and still calls verify_stage_result internally.
- Tests that mock `_verify_stage_result` directly: grep shows **ZERO** tests do this. All tests mock at the `_run_stage` level or at `verifier.run_pytest` / `verifier.verify_all` level.
- Tests that mock `_run_tdd_pipeline`: **UNAFFECTED**. The pipeline method still exists on Worker.

**Risk:** LOW. The extraction is purely internal. No test patches `_verify_stage_result` directly.

### Phase 1: Domain Models, Config, and Schema

#### Task 1.1: Add REFACTOR to Stage enum + RefactorResult

**Files:** `src/tdd_orchestrator/models.py` (101 -> ~130 lines)

**Action:**
1. Add `REFACTOR = "refactor"` to Stage enum between VERIFY and FIX
2. Update the module and Stage docstrings with the new pipeline flow:
   ```
   RED -> RED_FIX -> GREEN -> VERIFY -> [REFACTOR -> RE_VERIFY] -> (FIX -> RE_VERIFY)
   ```
3. Add `RefactorResult` dataclass:
   ```python
   @dataclass
   class RefactorResult:
       """Result from pre-REFACTOR analysis."""
       files_checked: int
       files_refactored: int
       issues_found: list[str]
       lines_before: int
       lines_after: int

       @property
       def had_changes(self) -> bool:
           return self.files_refactored > 0
   ```

**Note on `issues_found` type:** The original plan used `list[dict[str, Any]]` but the actual usage only needs string reasons (e.g., "File exceeds 400-line split threshold (523 lines)"). Using `list[str]` is simpler, more type-safe, and matches how `refactor_reasons` flows through the pipeline. If structured data is needed later, a dataclass can replace the strings.

**Verify:** `mypy src/tdd_orchestrator/models.py --strict`, existing tests pass.

#### Task 1.2: Add REFACTOR timeout + model constant

**Files:** `src/tdd_orchestrator/worker_pool/config.py` (145 -> ~152 lines)

**Action:**
1. Add `Stage.REFACTOR: 300` to `STAGE_TIMEOUTS` (5 min -- refactoring is similar to FIX in scope)
2. Add `REFACTOR_MODEL = "claude-opus-4-5-20251101"` constant (refactoring needs strong reasoning about code structure and split boundaries)

**Verify:** `mypy src/tdd_orchestrator/worker_pool/config.py --strict`

#### Task 1.3: Update schema CHECK constraints

**Files:** `schema/schema.sql`

**Action:**
1. Line 100: Add `'refactor'` to the `attempts.stage` CHECK list:
   ```sql
   CHECK(stage IN ('red', 'red_fix', 'green', 'review', 'fix', 'verify', 're_verify', 'refactor', 'commit'))
   ```
2. The `invocations.stage` column has no CHECK constraint (just `TEXT NOT NULL`), so no change needed there.

**Existing database handling:**
- `CREATE TABLE IF NOT EXISTS` means existing databases will NOT get the updated CHECK constraint
- Attempting to `record_stage_attempt` with `stage='refactor'` on an existing database will raise a CHECK constraint violation
- This is acceptable for a dev tool -- document the fix: `DELETE orchestrator.db && tdd-orchestrator init`
- For users who want to preserve data, provide:
  ```sql
  -- Run manually on existing databases:
  -- SQLite does not support ALTER TABLE to modify CHECK constraints.
  -- The only option is to recreate the table. For dev use, just delete the DB.
  ```

**Verify:** Schema still loads cleanly in tests (`:memory:` databases always get fresh schema).

### Phase 2: Refactor Checker and Prompt

#### Task 2.1: Create refactor_checker.py

**Files:** `src/tdd_orchestrator/refactor_checker.py` (NEW, ~160 lines)

**Action:** Create a module that analyzes implementation files for refactoring needs. This runs BEFORE the LLM prompt to determine if refactoring is needed (skip LLM call if code is already clean).

```python
"""Pre-REFACTOR static analysis for file quality checks.

Analyzes implementation files to determine if the REFACTOR stage
LLM prompt should be invoked. Avoids unnecessary LLM calls when
the GREEN stage already produced clean code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class RefactorCheckConfig:
    """Configurable thresholds for refactor triggers."""
    split_threshold: int = 400    # Lines: suggest split
    hard_limit: int = 800         # Lines: must split
    max_function_length: int = 50 # Max lines per function/method
    max_class_methods: int = 15   # Max methods per class

@dataclass
class RefactorCheck:
    """Result of pre-refactor analysis."""
    needs_refactor: bool
    reasons: list[str] = field(default_factory=list)
    file_lines: int = 0

async def check_needs_refactor(
    impl_file: str,
    base_dir: Path,
    config: RefactorCheckConfig | None = None,
) -> RefactorCheck:
    """Check if an implementation file needs refactoring."""
```

Key design decisions:
- **Async signature** even though the work is synchronous (file reads + AST parsing). This maintains consistency with the async pipeline and allows future extension (e.g., checking multiple files).
- Uses stdlib `ast` module for parsing -- NOT the project's `ast_checker.py` (which is specifically for AST quality violations like missing assertions, different purpose and different output type).
- Returns `needs_refactor=False` for missing files (graceful degradation -- file might not exist yet in dry-run scenarios).
- Returns `needs_refactor=False` for files with syntax errors (let VERIFY catch those).
- The `reasons` list contains human-readable strings that flow directly into the LLM prompt.

**Checks performed:**
1. File line count vs `split_threshold` (400) and `hard_limit` (800)
2. Individual function/method body length vs `max_function_length` (50)
3. Class method count vs `max_class_methods` (15)

**NOT included (intentional):** Duplicate code detection. AST-based duplication detection is unreliable for small files and adds complexity without clear value. The LLM can identify duplication on its own from the prompt context.

**Verify:** `mypy src/tdd_orchestrator/refactor_checker.py --strict`

#### Task 2.2: Add REFACTOR prompt template and PromptBuilder.refactor()

**Files:**
- `src/tdd_orchestrator/prompt_templates.py` -- add `REFACTOR_PROMPT_TEMPLATE` (~40 lines)
- `src/tdd_orchestrator/prompt_builder.py` -- add `refactor()` method + update `build()`

**Action:**

1. Add `REFACTOR_PROMPT_TEMPLATE` to `prompt_templates.py`:
   - Instructions: read implementation file + test file
   - Address ONLY the specified issues (reasons from checker)
   - Split files if over threshold (create new module + update imports in calling code)
   - Preserve public API (same exports, same function signatures)
   - Do NOT add new functionality
   - Do NOT modify test files
   - Run tests after changes to verify nothing broke

2. Add `PromptBuilder.refactor()` static method to `prompt_builder.py`:
   ```python
   @staticmethod
   def refactor(task: dict[str, Any], refactor_reasons: list[str]) -> str:
       """Generate prompt for REFACTOR phase (code quality cleanup)."""
   ```

3. Update `build()` dispatcher to handle `Stage.REFACTOR`:
   ```python
   if stage == StageEnum.REFACTOR:
       refactor_reasons = kwargs.get("refactor_reasons")
       if refactor_reasons is None:
           msg = "REFACTOR stage requires 'refactor_reasons' argument"
           raise ValueError(msg)
       return PromptBuilder.refactor(task, refactor_reasons)
   ```

**Verify:** `mypy --strict`, `ruff check`

### Phase 3: Pipeline Integration

#### Task 3.1: Wire REFACTOR into _run_tdd_pipeline

**Files:** `src/tdd_orchestrator/worker_pool/worker.py`

**Action:** Modify `_run_tdd_pipeline()` to insert the REFACTOR stage after VERIFY succeeds.

Current flow (lines 333-362):
```python
# Stage 3: VERIFY
result = await self._run_stage(Stage.VERIFY, task)
if result.success:
    await commit_stage(...)
    return True

# Stage 4: FIX (if VERIFY failed)
# Stage 5: RE_VERIFY
```

New flow:
```python
# Stage 3: VERIFY
result = await self._run_stage(Stage.VERIFY, task)
if not result.success:
    # ... existing FIX -> RE_VERIFY flow (UNCHANGED) ...

# Stage 3.5: REFACTOR (only if VERIFY passed)
impl_file = task.get("impl_file", "")
refactor_check = await check_needs_refactor(impl_file, self.base_dir)

if not refactor_check.needs_refactor:
    # No refactoring needed -- same as current behavior
    await commit_stage(
        task_key, "VERIFY",
        f"feat({task_key}): complete - all checks pass",
        self.base_dir,
    )
    return True

# REFACTOR needed
logger.info(
    "[%s] REFACTOR triggered: %s",
    task_key,
    "; ".join(refactor_check.reasons),
)
result = await self._run_stage(
    Stage.REFACTOR, task,
    refactor_reasons=refactor_check.reasons,
    model_override=REFACTOR_MODEL,
)
if not result.success:
    # REFACTOR failed -- still commit VERIFY and return success
    # (REFACTOR is best-effort, not a gate)
    logger.warning("[%s] REFACTOR stage failed, proceeding anyway", task_key)
    await commit_stage(
        task_key, "VERIFY",
        f"feat({task_key}): complete - all checks pass",
        self.base_dir,
    )
    return True

await commit_stage(
    task_key, "REFACTOR",
    f"wip({task_key}): REFACTOR - code cleanup",
    self.base_dir,
)

# RE_VERIFY after REFACTOR
result = await self._run_stage(Stage.RE_VERIFY, task)
if result.success:
    await commit_stage(
        task_key, "RE_VERIFY",
        f"feat({task_key}): complete - all checks pass",
        self.base_dir,
    )
    return True

# REFACTOR broke something -- enter FIX flow
if result.issues:
    result = await self._run_stage(Stage.FIX, task, issues=result.issues)
    if not result.success:
        return False
    await commit_stage(
        task_key, "FIX",
        f"wip({task_key}): FIX - post-refactor fixes",
        self.base_dir,
    )
    result = await self._run_stage(Stage.RE_VERIFY, task)
    if result.success:
        await commit_stage(
            task_key, "RE_VERIFY",
            f"feat({task_key}): complete - all checks pass",
            self.base_dir,
        )
    return result.success

return False
```

**Key design decisions:**

1. **REFACTOR failure is NOT fatal.** If the LLM errors or times out during REFACTOR, we log a warning and return success anyway (VERIFY already passed). This is different from the original plan where `result.success == False` returned False. The rationale: REFACTOR is a quality improvement, not a correctness gate. VERIFY already confirmed the code works.

2. **REFACTOR is conditional** -- only runs when `check_needs_refactor()` returns `needs_refactor=True`. Most tasks will skip it entirely (short, clean files).

3. **Uses Opus model** (refactoring needs strong reasoning about code structure and module boundaries).

4. **Separate commit for REFACTOR** -- preserves audit trail and enables `git revert` if REFACTOR introduced problems.

5. **Post-REFACTOR RE_VERIFY** -- if RE_VERIFY fails, enters the existing FIX -> RE_VERIFY recovery loop.

**Line impact:** ~35 lines added to `_run_tdd_pipeline()`. After Phase 0.2 extraction of `_verify_stage_result`, worker.py will be at ~660 + 35 = ~695 lines -- safely under 800.

**Verify:** `mypy src/tdd_orchestrator/worker_pool/worker.py --strict`, existing tests pass.

#### Task 3.2: Add REFACTOR handler to stage_verifier.py

**Files:** `src/tdd_orchestrator/worker_pool/stage_verifier.py` (from Phase 0.2)

**Action:** Add REFACTOR case to the `verify_stage_result()` function:

```python
if stage == Stage.REFACTOR:
    # REFACTOR always "succeeds" if no exceptions.
    # Actual quality verification happens in the subsequent RE_VERIFY.
    await db.record_stage_attempt(
        task_id=task["id"],
        stage=stage.value,
        attempt_number=1,
        success=True,
    )
    return StageResult(stage=stage, success=True, output=result_text)
```

This follows the exact same pattern as FIX and RED_FIX -- the stage itself always "succeeds" if the LLM didn't error, and RE_VERIFY does the actual verification.

**Verify:** `mypy --strict`

### Phase 4: Tests

#### Task 4.1: Unit tests for refactor_checker.py

**Files:** `tests/unit/test_refactor_checker.py` (NEW, ~180 lines)

**Tests:**
1. `test_short_file_no_refactor` -- file under 400 lines returns `needs_refactor=False`
2. `test_file_over_split_threshold` -- 401+ lines triggers with reason string containing "400"
3. `test_file_over_hard_limit` -- 801+ lines triggers with reason string containing "800" and "MUST"
4. `test_long_function_triggers_refactor` -- function >50 lines triggers with reason
5. `test_many_methods_triggers_refactor` -- class with 16+ methods triggers with reason
6. `test_clean_file_no_refactor` -- well-structured 100-line file passes all checks
7. `test_custom_config_thresholds` -- custom `RefactorCheckConfig(split_threshold=200)` is respected
8. `test_nonexistent_file` -- returns `needs_refactor=False` (graceful degradation)
9. `test_syntax_error_file` -- returns `needs_refactor=False` (let VERIFY handle it)
10. `test_multiple_reasons_accumulated` -- file with both long functions AND high line count reports all reasons

**Pattern:** Use `tmp_path` to create real Python files with known characteristics. Parse with the checker and assert on the result.

**Verify:** `.venv/bin/pytest tests/unit/test_refactor_checker.py -v`

#### Task 4.2: Unit tests for REFACTOR prompt

**Files:** `tests/unit/test_prompt_builder.py` (NEW, ~80 lines)

**Tests:**
1. `test_refactor_prompt_includes_reasons` -- `PromptBuilder.refactor(task, ["File too long"])` includes "File too long" in output
2. `test_refactor_prompt_includes_impl_file` -- prompt includes `task["impl_file"]`
3. `test_refactor_prompt_includes_test_file` -- prompt includes `task["test_file"]`
4. `test_build_dispatches_refactor` -- `PromptBuilder.build(Stage.REFACTOR, task, refactor_reasons=[...])` calls `refactor()`
5. `test_build_refactor_missing_reasons_raises` -- `PromptBuilder.build(Stage.REFACTOR, task)` raises `ValueError`

**Verify:** `.venv/bin/pytest tests/unit/test_prompt_builder.py -v`

#### Task 4.3: Integration tests for REFACTOR in pipeline

**Files:** `tests/integration/test_refactor_pipeline.py` (NEW, ~220 lines)

**Tests:**
1. `test_pipeline_skips_refactor_when_clean` -- mock `check_needs_refactor` returning `needs_refactor=False`, verify REFACTOR stage never called
2. `test_pipeline_runs_refactor_when_triggered` -- mock `check_needs_refactor` returning `needs_refactor=True`, verify `_run_stage(Stage.REFACTOR, ...)` called
3. `test_pipeline_reverify_after_refactor` -- after REFACTOR succeeds, RE_VERIFY is called
4. `test_pipeline_refactor_failure_still_succeeds` -- if REFACTOR stage fails, pipeline still returns True (best-effort)
5. `test_pipeline_fix_after_failed_reverify` -- if RE_VERIFY fails after REFACTOR, enters FIX -> RE_VERIFY
6. `test_refactor_uses_opus_model` -- verify `model_override=REFACTOR_MODEL` passed to `_run_stage`

**Pattern:** Mock `_run_stage` at the Worker level (matching existing test patterns from `test_green_retry_unit.py`). Mock `check_needs_refactor` to control conditional flow. Do NOT mock deep internals.

**Verify:** `.venv/bin/pytest tests/integration/test_refactor_pipeline.py -v`

### Phase 5: Final Verification

```bash
# Full regression (504+ existing + ~21 new)
.venv/bin/pytest tests/ -v --tb=short

# Type checking
.venv/bin/mypy src/ --strict

# Linting
.venv/bin/ruff check src/

# File size verification
wc -l src/tdd_orchestrator/prompt_builder.py          # ~200 (was 725)
wc -l src/tdd_orchestrator/prompt_templates.py        # ~390 (new)
wc -l src/tdd_orchestrator/worker_pool/worker.py      # ~695 (was 767)
wc -l src/tdd_orchestrator/worker_pool/stage_verifier.py  # ~150 (new)
wc -l src/tdd_orchestrator/refactor_checker.py        # ~160 (new)
```

---

## Appendix A: Rejected Alternatives

### A1: PipelineExecutor Composition Pattern (Rejected)

The Sonnet plan proposed extracting `_run_tdd_pipeline`, `_run_stage`, `_run_green_with_retry`, `_consume_sdk_stream`, and `_verify_stage_result` into a `PipelineExecutor` class, with Worker delegating via `self.pipeline`.

**Why rejected:**
- **50+ test call sites break.** Tests across 8 files directly call `worker._run_stage(...)`, `worker._run_tdd_pipeline(...)`, etc. Every `patch.object(worker, "_run_stage", ...)` would need to become `patch.object(worker.pipeline, "run_stage", ...)`.
- **Net zero file size benefit.** The extraction produces a 535-line file (over 400 threshold) and a 240-line file. We still need further splitting.
- **Constructor coupling.** PipelineExecutor needs 7+ constructor arguments (`worker_id, db, base_dir, verifier, prompt_builder, static_review_circuit_breaker, run_id`), creating a complex dependency injection surface.
- **The simpler alternative works.** Extracting only `_verify_stage_result` (110 lines) into a standalone function achieves the file size goal with zero test breakage.

### A2: Mixin-Based Split (Rejected)

An alternative to PipelineExecutor was using a mixin: `class PipelineMixin` with the pipeline methods, and `class Worker(PipelineMixin)` inheriting them.

**Why rejected:**
- Mixins are fragile with `self` dependencies -- every mixin method still accesses `self.db`, `self.verifier`, etc., creating implicit coupling.
- mypy strict mode makes mixins painful -- type narrowing through multiple inheritance requires Protocol classes.
- Gains are marginal: the mixin still needs to be in a separate file, but the methods conceptually belong to Worker.

### A3: Monolithic prompt_templates.py (Rejected)

The Sonnet plan proposed extracting ALL template strings into a single `prompt_templates.py` at ~600 lines.

**Why rejected:**
- 600 lines exceeds the 400-line split threshold on creation day.
- A file of nothing but string constants is hard to navigate.
- Better to keep it under 400 by deduplicating shared instruction blocks (type annotation guidance appears in both GREEN and GREEN_RETRY templates).

---

## Appendix B: Edge Cases

### B1: REFACTOR on Files That Don't Exist

If `task["impl_file"]` doesn't exist (e.g., GREEN failed to create it), `check_needs_refactor` returns `needs_refactor=False`. The pipeline skips REFACTOR and proceeds normally.

### B2: REFACTOR on Non-Python Files

The checker uses `ast.parse()` which only works on Python files. For non-Python impl files, `ast.parse()` will raise `SyntaxError`, and the checker returns `needs_refactor=False`. This is correct behavior -- the REFACTOR stage's AST checks only apply to Python.

### B3: REFACTOR Breaks Tests But FIX Also Fails

If REFACTOR produces code that fails RE_VERIFY, and the FIX stage also fails, the pipeline returns `False` and the task is marked as blocked. This is the same behavior as the existing VERIFY -> FIX -> RE_VERIFY failure path. The REFACTOR commit is preserved in git history, so a human can `git revert` if needed.

### B4: Existing Database With Old CHECK Constraint

If a user has an existing database without `'refactor'` in the `attempts.stage` CHECK constraint:
- `record_stage_attempt(stage='refactor', ...)` will raise an `aiosqlite.IntegrityError`
- This error propagates up and the REFACTOR stage will fail
- Per the revised design (REFACTOR failure is not fatal), the pipeline will log a warning and return success
- **Fix:** Delete `orchestrator.db` and run `tdd-orchestrator init`

### B5: Multiple Refactor Reasons

The checker may return multiple reasons (e.g., "File exceeds 400 lines" AND "Function `process_data` is 67 lines"). All reasons are passed to the LLM prompt so it can address them all in a single pass.

### B6: REFACTOR After FIX

The current pipeline flow is:
```
VERIFY (fail) -> FIX -> RE_VERIFY (pass) -> done
```

REFACTOR only triggers after the initial VERIFY pass. If VERIFY fails and the task goes through FIX -> RE_VERIFY, REFACTOR does NOT run on that path. This is intentional: the FIX path is already a recovery mechanism, and adding REFACTOR there would increase complexity and LLM invocations for already-struggling tasks.

If REFACTOR is desired after FIX-based recovery, it can be added in a future iteration.

---

## File Summary

### Created (5 files)

| File | Est Lines | Purpose |
|------|-----------|---------|
| `src/tdd_orchestrator/prompt_templates.py` | ~390 | Extracted prompt template constants |
| `src/tdd_orchestrator/worker_pool/stage_verifier.py` | ~150 | Extracted stage verification logic |
| `src/tdd_orchestrator/refactor_checker.py` | ~160 | Pre-refactor static analysis |
| `tests/unit/test_refactor_checker.py` | ~180 | Checker unit tests |
| `tests/unit/test_prompt_builder.py` | ~80 | Prompt builder unit tests |

### Created (1 integration test)

| File | Est Lines | Purpose |
|------|-----------|---------|
| `tests/integration/test_refactor_pipeline.py` | ~220 | Pipeline integration tests |

### Modified (5 files)

| File | Before | After | Change |
|------|--------|-------|--------|
| `src/tdd_orchestrator/models.py` | 102 | ~130 | +REFACTOR enum, +RefactorResult |
| `src/tdd_orchestrator/worker_pool/config.py` | 145 | ~152 | +timeout, +model constant |
| `src/tdd_orchestrator/prompt_builder.py` | 725 | ~200 | Extract templates, +refactor() |
| `src/tdd_orchestrator/worker_pool/worker.py` | 767 | ~695 | Extract verifier, +REFACTOR wiring |
| `schema/schema.sql` | 744 | ~745 | +'refactor' in CHECK constraint |

### Dependency Order

```
Phase 0: 0.1 (prompt split) and 0.2 (verifier extract) [parallel -- independent]
Phase 1: 1.1 (enum) -> 1.2 (config) and 1.3 (schema) [1.2 and 1.3 parallel]
Phase 2: 2.1 (checker) and 2.2 (prompt) [parallel -- independent]
Phase 3: 3.1 (pipeline wiring) -> 3.2 (verify handler)
Phase 4: 4.1, 4.2, 4.3 [all parallel]
Phase 5: Full regression
```

### Validation Gates Between Phases

| Gate | Criteria |
|------|----------|
| Phase 0 -> Phase 1 | All 504 tests pass, mypy clean, ruff clean, no file over 400 lines |
| Phase 1 -> Phase 2 | `Stage.REFACTOR` exists, config constants defined, schema updated |
| Phase 2 -> Phase 3 | `check_needs_refactor()` works, `PromptBuilder.refactor()` returns valid prompt |
| Phase 3 -> Phase 4 | Pipeline integrates REFACTOR conditionally, stage verifier handles REFACTOR |
| Phase 4 -> Phase 5 | All new tests pass individually |
| Phase 5 -> Done | Full suite passes (504 + ~21 new), mypy clean, ruff clean, no file over 800 |

---

## Success Criteria

1. `Stage.REFACTOR` exists in the enum and is documented
2. `PromptBuilder.refactor()` generates a focused refactoring prompt with specific reasons
3. `check_needs_refactor()` detects file size violations and structural quality issues
4. Pipeline runs REFACTOR conditionally (only when needed -- no wasted LLM calls)
5. REFACTOR failure does NOT block task completion (best-effort quality improvement)
6. RE_VERIFY confirms refactoring didn't break anything
7. All 504+ existing tests still pass (zero regression)
8. ~21 new tests cover checker logic, prompt building, and pipeline integration
9. mypy strict and ruff clean on all modified/new files
10. No file exceeds 800 lines; no new file exceeds 400 lines

## Total Estimated Impact

- **New files:** 6 (3 production, 3 test)
- **Modified files:** 5
- **New production lines:** ~700
- **New test lines:** ~480
- **New tests:** ~21
- **LLM invocations per task:** 0-1 additional (only when refactoring needed)
- **Risk to existing tests:** LOW (Phase 0 extractions do not change Worker's public or private API surface that tests depend on)
