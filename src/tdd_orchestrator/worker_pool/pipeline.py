"""TDD pipeline execution logic.

Contains the main pipeline orchestrator (run_tdd_pipeline) and GREEN
retry logic, extracted from Worker to keep worker.py under the 800-line limit.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..database import OrchestratorDB
from ..models import Stage, StageResult
from ..refactor_checker import check_needs_refactor
from .circuit_breakers import RedFixAttemptTracker, StaticReviewCircuitBreaker
from .config import (
    DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS,
    ESCALATION_MODEL,
    HAS_AGENT_SDK,
    MAX_TEST_OUTPUT_SIZE,
    REFACTOR_MODEL,
    RunStageFunc,
)
from .file_discovery import discover_test_file
from .git_ops import commit_stage, run_ruff_fix
from .review import run_static_review
from .verify_only import run_verify_only_pipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineContext:
    """Immutable context for pipeline execution.

    Bundles all dependencies that pipeline functions need from Worker,
    avoiding the need to pass ``self`` across module boundaries.
    """

    db: OrchestratorDB
    base_dir: Path
    worker_id: int
    run_id: int
    static_review_circuit_breaker: StaticReviewCircuitBreaker
    run_stage: RunStageFunc


async def run_tdd_pipeline(ctx: PipelineContext, task: dict[str, Any]) -> bool:
    """Run TDD pipeline via discrete stage prompts.

    Pipeline: RED -> Static Review -> GREEN -> VERIFY -> REFACTOR (if needed)
              -> RE_VERIFY -> (FIX -> RE_VERIFY if needed)
    Returns True if all stages pass.

    Each successful stage is committed incrementally to preserve work,
    preventing loss of progress if later stages fail.
    """
    if not HAS_AGENT_SDK:
        logger.error("Agent SDK not installed - cannot process tasks")
        return False

    task_key = task.get("task_key", "UNKNOWN")
    test_file = task.get("test_file", "")

    # Check for verify-only tasks (overlap detection marked this task)
    task_type = task.get("task_type", "implement")
    if task_type == "verify-only":
        logger.info("[%s] Task type: verify-only -- skipping RED+GREEN", task_key)
        return await run_verify_only_pipeline(
            task=task,
            run_stage=ctx.run_stage,
            base_dir=ctx.base_dir,
        )

    # Resume capability: Check if test file exists from prior run
    test_file_path = Path(test_file) if test_file else None
    skip_red = False

    if test_file_path and test_file_path.exists():
        prior_red = await ctx.db.get_successful_attempt(task_key, "red")
        if prior_red:
            logger.info("[%s] Resuming from GREEN (test file exists from prior RED)", task_key)
            skip_red = True
            # Use empty output since we don't have the original test output
            result = StageResult(stage=Stage.RED, success=True, output="", error=None)

    if not skip_red:
        # Stage 1: RED - Write failing tests
        result = await ctx.run_stage(Stage.RED, task)
        if not result.success:
            return False
        await commit_stage(
            task_key, "RED", f"wip({task_key}): RED stage - failing tests", ctx.base_dir
        )

    # Check if task is pre-implemented (RED tests passed because impl exists)
    skip_green = False
    if result.pre_implemented:
        logger.info(
            "[%s] Pre-implemented -- skipping RED review + GREEN, proceeding to VERIFY",
            task_key,
        )
        skip_green = True

    if not skip_red and not skip_green:
        # Post-RED: verify test file exists at expected path, reconcile if needed
        if test_file:
            actual = await discover_test_file(test_file, ctx.base_dir)
            if actual is None:
                logger.error("[%s] Test file not found after RED: %s", task_key, test_file)
                return False
            if actual != test_file:
                logger.info(
                    "[%s] Test file relocated: %s -> %s", task_key, test_file, actual
                )
                task["test_file"] = actual
                test_file = actual
                await ctx.db.update_task_test_file(task["id"], actual)

        # Stage 1.5: Static RED Review (PLAN12)
        fix_tracker = RedFixAttemptTracker()
        review_result = await run_static_review(
            task, ctx.base_dir, ctx.static_review_circuit_breaker, ctx.db, ctx.run_id
        )

        while review_result.is_blocking:
            can_fix, reason = fix_tracker.can_attempt()
            if not can_fix:
                logger.error("[%s] Cannot attempt RED_FIX: %s", task_key, reason)
                await ctx.db.update_task_status(task_key, "blocked-static-review")
                return False

            # Convert violations to issue dicts for prompt
            issues = [
                {
                    "pattern": v.pattern,
                    "line_number": v.line_number,
                    "message": v.message,
                    "severity": v.severity,
                    "code_snippet": v.code_snippet,
                }
                for v in review_result.violations
                if v.severity == "error"  # Only fix errors, not warnings
            ]
            fix_tracker.record_attempt(review_result.violations)

            # Attempt LLM fix
            fix_result = await ctx.run_stage(Stage.RED_FIX, task, issues=issues)
            if not fix_result.success:
                logger.error("[%s] RED_FIX stage failed", task_key)
                return False
            await commit_stage(
                task_key,
                "RED_FIX",
                f"wip({task_key}): RED_FIX - static review fixes",
                ctx.base_dir,
            )

            # Re-run static review
            review_result = await run_static_review(
                task,
                ctx.base_dir,
                ctx.static_review_circuit_breaker,
                ctx.db,
                ctx.run_id,
            )

        logger.info("[%s] Static review passed", task_key)

    if not skip_green:
        # Stage 2: GREEN - Write implementation (WITH RETRY)
        result = await _run_green_with_retry(ctx, task, test_output=result.output)
        if not result.success:
            # Record final failure (individual attempts already logged)
            await ctx.db.mark_task_failing(
                task_key,
                f"GREEN failed after max attempts. Last error: {result.error}",
            )
            return False
        await commit_stage(
            task_key, "GREEN", f"wip({task_key}): GREEN stage - implementation", ctx.base_dir
        )

    # Auto-fix unused imports before VERIFY
    impl_file = task.get("impl_file", "")
    if impl_file:
        await run_ruff_fix(impl_file, task_key, ctx.base_dir)

    # Stage 3: VERIFY - Run quality checks
    result = await ctx.run_stage(Stage.VERIFY, task)
    if not result.success:
        # Stage 4: FIX - Address issues (conditional)
        if not result.issues:
            logger.error("VERIFY failed but no issues provided")
            return False

        result = await ctx.run_stage(Stage.FIX, task, issues=result.issues)
        if not result.success:
            return False
        await commit_stage(
            task_key, "FIX", f"wip({task_key}): FIX stage - issue fixes", ctx.base_dir
        )

        # Stage 5: RE_VERIFY - Final verification (conditional)
        result = await ctx.run_stage(Stage.RE_VERIFY, task)
        if result.success:
            await commit_stage(
                task_key,
                "RE_VERIFY",
                f"feat({task_key}): complete - all checks pass",
                ctx.base_dir,
            )
        return result.success

    # Stage 3.5: REFACTOR (only if VERIFY passed)
    impl_file = task.get("impl_file", "")
    refactor_check = await check_needs_refactor(impl_file, ctx.base_dir)

    if not refactor_check.needs_refactor:
        # No refactoring needed - commit VERIFY and return success
        await commit_stage(
            task_key, "VERIFY",
            f"feat({task_key}): complete - all checks pass",
            ctx.base_dir,
        )
        return True

    # REFACTOR needed
    logger.info(
        "[%s] REFACTOR triggered: %s",
        task_key,
        "; ".join(refactor_check.reasons),
    )
    result = await ctx.run_stage(
        Stage.REFACTOR, task,
        refactor_reasons=refactor_check.reasons,
        model_override=REFACTOR_MODEL,
    )
    if not result.success:
        # REFACTOR failed - still commit VERIFY and return success
        # (REFACTOR is best-effort, not a gate)
        logger.warning("[%s] REFACTOR stage failed, proceeding anyway", task_key)
        await commit_stage(
            task_key, "VERIFY",
            f"feat({task_key}): complete - all checks pass",
            ctx.base_dir,
        )
        return True

    await commit_stage(
        task_key, "REFACTOR",
        f"wip({task_key}): REFACTOR - code cleanup",
        ctx.base_dir,
    )

    # RE_VERIFY after REFACTOR
    result = await ctx.run_stage(Stage.RE_VERIFY, task)
    if result.success:
        await commit_stage(
            task_key, "RE_VERIFY",
            f"feat({task_key}): complete - all checks pass",
            ctx.base_dir,
        )
        return True

    # REFACTOR broke something - enter FIX flow
    if result.issues:
        result = await ctx.run_stage(Stage.FIX, task, issues=result.issues)
        if not result.success:
            return False
        await commit_stage(
            task_key, "FIX",
            f"wip({task_key}): FIX - post-refactor fixes",
            ctx.base_dir,
        )
        result = await ctx.run_stage(Stage.RE_VERIFY, task)
        if result.success:
            await commit_stage(
                task_key, "RE_VERIFY",
                f"feat({task_key}): complete - all checks pass",
                ctx.base_dir,
            )
        return result.success

    return False


async def _run_green_with_retry(
    ctx: PipelineContext,
    task: dict[str, Any],
    test_output: str,
) -> StageResult:
    """Run GREEN stage with iterative retry on test failure.

    Implements Ralph Wiggum-inspired iteration:
    1. Attempt implementation
    2. If tests fail, pass failure details to new LLM call
    3. LLM sees its previous code + test failures
    4. Repeat until success or max_attempts reached

    Args:
        ctx: Pipeline context with dependencies.
        task: Task dictionary with acceptance criteria, test/impl files.
        test_output: Output from RED stage (failing tests).

    Returns:
        StageResult with success=True if any attempt passes tests.
    """
    max_attempts = await ctx.db.get_config_int("max_green_attempts", 2)
    delay_ms = await ctx.db.get_config_int("green_retry_delay_ms", 1000)
    aggregate_timeout = await ctx.db.get_config_int(
        "max_green_retry_time_seconds", DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS
    )

    task_key = task.get("task_key", "UNKNOWN")
    start_time = asyncio.get_event_loop().time()
    last_result: StageResult | None = None
    last_failure_output: str = ""

    for attempt in range(1, max_attempts + 1):
        # Check aggregate timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > aggregate_timeout:
            logger.warning(
                "Worker %d: GREEN aggregate timeout (%ds) exceeded for %s",
                ctx.worker_id,
                aggregate_timeout,
                task_key,
            )
            break

        logger.info(
            "Worker %d: GREEN attempt %d/%d for %s",
            ctx.worker_id,
            attempt,
            max_attempts,
            task_key,
        )

        # Build kwargs for run_stage
        stage_kwargs: dict[str, Any] = {"test_output": test_output}
        if attempt > 1:
            # Include failure context for retry attempts
            stage_kwargs["attempt"] = attempt
            stage_kwargs["previous_failure"] = last_failure_output[:MAX_TEST_OUTPUT_SIZE]

        # Determine model override for escalation
        model_override = ESCALATION_MODEL if attempt > 1 else None
        if model_override:
            logger.info(
                "Worker %d: escalating to %s for GREEN retry attempt %d",
                ctx.worker_id,
                ESCALATION_MODEL,
                attempt,
            )

        # Run the stage (with skip_recording since we handle it)
        result = await ctx.run_stage(
            Stage.GREEN,
            task,
            skip_recording=True,
            model_override=model_override,
            **stage_kwargs,
        )

        # Record this attempt with actual attempt number
        await ctx.db.record_stage_attempt(
            task_id=task["id"],
            stage="green",
            attempt_number=attempt,
            success=result.success,
            pytest_exit_code=0 if result.success else 1,
            error_message=result.error if not result.success else None,
        )

        if result.success:
            escalation_note = " (with Opus escalation)" if attempt > 1 else ""
            logger.info(
                "Worker %d: GREEN succeeded on attempt %d/%d for %s%s",
                ctx.worker_id,
                attempt,
                max_attempts,
                task_key,
                escalation_note,
            )
            return result

        # Capture failure output for next iteration
        last_result = result
        last_failure_output = result.output or ""

        # Delay between attempts (except after last attempt)
        if delay_ms > 0 and attempt < max_attempts:
            await asyncio.sleep(delay_ms / 1000)

    # All attempts exhausted
    logger.warning(
        "Worker %d: GREEN failed after %d attempts for %s",
        ctx.worker_id,
        max_attempts,
        task_key,
    )

    return last_result or StageResult(
        stage=Stage.GREEN,
        success=False,
        output="",
        error=f"All {max_attempts} GREEN attempts failed",
    )
