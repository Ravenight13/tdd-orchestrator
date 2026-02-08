"""Individual worker that processes TDD tasks.

Contains the Worker class with all TDD pipeline execution logic,
stage running, verification, and SDK integration.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from ..code_verifier import CodeVerifier
from ..database import OrchestratorDB
from ..git_coordinator import GitCoordinator
from ..git_stash_guard import GitStashGuard
from ..models import Stage, StageResult
from ..prompt_builder import PromptBuilder
from ..refactor_checker import check_needs_refactor
from .circuit_breakers import RedFixAttemptTracker, StaticReviewCircuitBreaker
from .config import (
    DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS,
    ESCALATION_MODEL,
    HAS_AGENT_SDK,
    MAX_TEST_OUTPUT_SIZE,
    RED_STAGE_MODEL,
    REFACTOR_MODEL,
    STAGE_MAX_TURNS,
    STAGE_TIMEOUTS,
    ClaudeAgentOptions,
    WorkerConfig,
    WorkerStats,
    get_model_for_complexity,
    sdk_query,
)
from .file_discovery import discover_test_file
from .git_ops import commit_stage, run_ruff_fix, squash_wip_commits
from .review import run_static_review
from .stage_verifier import verify_stage_result

logger = logging.getLogger(__name__)


class Worker:
    """Individual worker that processes tasks."""

    def __init__(
        self,
        worker_id: int,
        db: OrchestratorDB,
        git: GitCoordinator,
        config: WorkerConfig,
        run_id: int,
        base_dir: Path,
    ) -> None:
        """Initialize worker.

        Args:
            worker_id: Unique worker identifier.
            db: Database instance.
            git: Git coordinator instance.
            config: Worker configuration.
            run_id: Current execution run ID.
            base_dir: Root directory for file path resolution.
        """
        self.worker_id = worker_id
        self.db = db
        self.git = git
        self.config = config
        self.run_id = run_id
        self.base_dir = base_dir
        self.stats = WorkerStats(worker_id=worker_id)
        self.current_branch: str | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self.prompt_builder = PromptBuilder()
        self.verifier = CodeVerifier(base_dir)
        self.static_review_circuit_breaker = StaticReviewCircuitBreaker()

    async def start(self) -> None:
        """Register worker and start heartbeat."""
        await self.db.register_worker(self.worker_id)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Worker %d started", self.worker_id)

    async def stop(self) -> None:
        """Stop worker and cleanup."""
        self._stop_event.set()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        await self.db.unregister_worker(self.worker_id)
        logger.info(
            "Worker %d stopped: %d completed, %d failed",
            self.worker_id,
            self.stats.tasks_completed,
            self.stats.tasks_failed,
        )

    async def process_task(self, task: dict[str, Any]) -> bool:
        """Process a single task through TDD pipeline.

        Args:
            task: Task dict from database.

        Returns:
            True if task completed successfully.
        """
        task_id = task["id"]
        task_key = task["task_key"]

        # Claim task
        claimed = await self.db.claim_task(
            task_id, self.worker_id, self.config.claim_timeout_seconds
        )
        if not claimed:
            logger.warning("Worker %d failed to claim task %s", self.worker_id, task_key)
            return False

        try:
            # Create worker branch (skip in single branch mode)
            if not self.config.single_branch_mode:
                self.current_branch = await self.git.create_worker_branch(
                    self.worker_id, task_key, use_local=self.config.use_local_branches
                )

            # Update heartbeat with current task
            await self.db.update_worker_heartbeat(self.worker_id, task_id)

            # Process task via Agent SDK (with optional git stash protection)
            if self.config.git_stash_enabled:
                guard = GitStashGuard(task_key, self.base_dir, preserve_on_failure=True)
                async with guard:
                    success = await self._run_tdd_pipeline(task)
                    guard.mark_result(success)
                    # Log stash operations for audit
                    for op in guard.get_operations():
                        logger.debug(
                            "GitStashGuard operation: task=%s op=%s success=%s",
                            op.task_key,
                            op.operation,
                            op.success,
                        )
                # Persist audit log AFTER context exits (guard still in scope)
                await guard.persist_operations(self.db, task_id)
                # Handle failure AFTER context manager exits (files preserved)
                if not success:
                    logger.error(
                        "TDD pipeline failed for task %s - files preserved for inspection",
                        task_key,
                    )
            else:
                success = await self._run_tdd_pipeline(task)

            if success:
                # Squash WIP commits in single-branch mode
                if self.config.single_branch_mode:
                    await squash_wip_commits(task_key, self.base_dir)
                else:
                    # Commit any remaining changes (TDD stages already commit incrementally,
                    # so this may have nothing to commit - that's OK)
                    try:
                        await self.git.commit_changes(
                            f"feat({task_key}): implement {task['title']}\n\n"
                            "Co-Authored-By: Claude <noreply@anthropic.com>"
                        )
                    except ValueError as e:
                        if "No changes to commit" in str(e):
                            logger.debug(
                                "[%s] No additional changes to commit (stages committed incrementally)",
                                task_key,
                            )
                        else:
                            raise

                # Mark task complete
                await self.db.update_task_status(task_key, "complete")
                await self.db.release_task(task_id, self.worker_id, "completed")

                # Push branch for merge (skip in single branch mode)
                if not self.config.single_branch_mode and self.current_branch:
                    assert self.current_branch is not None  # Type narrowing for mypy
                    try:
                        await self.git.push_branch(self.current_branch)
                    except Exception as push_error:
                        logger.warning(
                            "Worker %d failed to push branch %s: %s (task %s already complete)",
                            self.worker_id,
                            self.current_branch,
                            push_error,
                            task_key,
                        )

                self.stats.tasks_completed += 1
                logger.info("Worker %d completed task %s", self.worker_id, task_key)
                return True
            else:
                # Mark task as failed
                await self.db.update_task_status(task_key, "blocked")
                await self.db.release_task(task_id, self.worker_id, "failed")

                # Rollback branch (skip in single branch mode)
                if not self.config.single_branch_mode and self.current_branch:
                    await self.git.rollback_to_main(self.current_branch)
                    self.current_branch = None

                self.stats.tasks_failed += 1
                logger.warning("Worker %d failed task %s", self.worker_id, task_key)
                return False

        except Exception as e:
            logger.exception("Worker %d error on task %s: %s", self.worker_id, task_key, e)

            # Release task as failed
            await self.db.release_task(task_id, self.worker_id, "failed")
            await self.db.update_task_status(task_key, "blocked")

            # Rollback branch (skip in single branch mode)
            if not self.config.single_branch_mode and self.current_branch:
                await self.git.rollback_to_main(self.current_branch)
                self.current_branch = None

            self.stats.tasks_failed += 1
            return False

    async def _run_tdd_pipeline(self, task: dict[str, Any]) -> bool:
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

        # Resume capability: Check if test file exists from prior run
        test_file_path = Path(test_file) if test_file else None
        skip_red = False

        if test_file_path and test_file_path.exists():
            prior_red = await self.db.get_successful_attempt(task_key, "red")
            if prior_red:
                logger.info("[%s] Resuming from GREEN (test file exists from prior RED)", task_key)
                skip_red = True
                # Use empty output since we don't have the original test output
                result = StageResult(stage=Stage.RED, success=True, output="", error=None)

        if not skip_red:
            # Stage 1: RED - Write failing tests
            result = await self._run_stage(Stage.RED, task)
            if not result.success:
                return False
            await commit_stage(
                task_key, "RED", f"wip({task_key}): RED stage - failing tests", self.base_dir
            )

            # Post-RED: verify test file exists at expected path, reconcile if needed
            if test_file:
                actual = await discover_test_file(test_file, self.base_dir)
                if actual is None:
                    logger.error("[%s] Test file not found after RED: %s", task_key, test_file)
                    return False
                if actual != test_file:
                    logger.info(
                        "[%s] Test file relocated: %s -> %s", task_key, test_file, actual
                    )
                    task["test_file"] = actual
                    test_file = actual
                    await self.db.update_task_test_file(task["id"], actual)

            # Stage 1.5: Static RED Review (PLAN12)
            fix_tracker = RedFixAttemptTracker()
            review_result = await run_static_review(
                task, self.base_dir, self.static_review_circuit_breaker, self.db, self.run_id
            )

            while review_result.is_blocking:
                can_fix, reason = fix_tracker.can_attempt()
                if not can_fix:
                    logger.error("[%s] Cannot attempt RED_FIX: %s", task_key, reason)
                    await self.db.update_task_status(task_key, "blocked-static-review")
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
                fix_result = await self._run_stage(Stage.RED_FIX, task, issues=issues)
                if not fix_result.success:
                    logger.error("[%s] RED_FIX stage failed", task_key)
                    return False
                await commit_stage(
                    task_key,
                    "RED_FIX",
                    f"wip({task_key}): RED_FIX - static review fixes",
                    self.base_dir,
                )

                # Re-run static review
                review_result = await run_static_review(
                    task,
                    self.base_dir,
                    self.static_review_circuit_breaker,
                    self.db,
                    self.run_id,
                )

            logger.info("[%s] Static review passed", task_key)

        # Stage 2: GREEN - Write implementation (WITH RETRY)
        result = await self._run_green_with_retry(task, test_output=result.output)
        if not result.success:
            # Record final failure (individual attempts already logged)
            await self.db.mark_task_failing(
                task_key,
                f"GREEN failed after max attempts. Last error: {result.error}",
            )
            return False
        await commit_stage(
            task_key, "GREEN", f"wip({task_key}): GREEN stage - implementation", self.base_dir
        )

        # Auto-fix unused imports before VERIFY
        impl_file = task.get("impl_file", "")
        if impl_file:
            await run_ruff_fix(impl_file, task_key, self.base_dir)

        # Stage 3: VERIFY - Run quality checks
        result = await self._run_stage(Stage.VERIFY, task)
        if not result.success:
            # Stage 4: FIX - Address issues (conditional)
            if not result.issues:
                logger.error("VERIFY failed but no issues provided")
                return False

            result = await self._run_stage(Stage.FIX, task, issues=result.issues)
            if not result.success:
                return False
            await commit_stage(
                task_key, "FIX", f"wip({task_key}): FIX stage - issue fixes", self.base_dir
            )

            # Stage 5: RE_VERIFY - Final verification (conditional)
            result = await self._run_stage(Stage.RE_VERIFY, task)
            if result.success:
                await commit_stage(
                    task_key,
                    "RE_VERIFY",
                    f"feat({task_key}): complete - all checks pass",
                    self.base_dir,
                )
            return result.success

        # Stage 3.5: REFACTOR (only if VERIFY passed)
        impl_file = task.get("impl_file", "")
        refactor_check = await check_needs_refactor(impl_file, self.base_dir)

        if not refactor_check.needs_refactor:
            # No refactoring needed - commit VERIFY and return success
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
            # REFACTOR failed - still commit VERIFY and return success
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

        # REFACTOR broke something - enter FIX flow
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

    async def _run_stage(
        self,
        stage: Stage,
        task: dict[str, Any],
        *,
        skip_recording: bool = False,
        model_override: str | None = None,
        **kwargs: Any,
    ) -> StageResult:
        """Run a single TDD stage via Agent SDK.

        Records ONE invocation per stage (not per streamed message).

        Args:
            stage: The TDD stage to run.
            task: Task dictionary with acceptance criteria, test/impl files.
            skip_recording: If True, skip recording stage attempt in _verify_stage_result.
                           Used by _run_green_with_retry() to handle recording itself.
            model_override: If provided, use this model instead of complexity-based selection.
                           Used by _run_green_with_retry() for Opus escalation.
            **kwargs: Additional arguments passed to PromptBuilder.build().

        Returns:
            StageResult with success status and output.
        """
        # Build prompt for this stage
        prompt = PromptBuilder.build(stage, task, **kwargs)

        # Verify SDK is available
        if not HAS_AGENT_SDK or sdk_query is None or ClaudeAgentOptions is None:
            logger.error("Agent SDK not available - cannot run stage %s", stage.value)
            return StageResult(
                stage=stage, success=False, output="", error="Agent SDK not available"
            )

        # Check budget before starting
        count, limit, _ = await self.db.check_invocation_budget(self.run_id)
        if count >= limit:
            logger.error("Invocation limit reached at stage %s", stage.value)
            return StageResult(stage=stage, success=False, output="", error="Budget exceeded")

        # Select model: stage overrides > caller override > complexity-based
        complexity = task.get("complexity", "medium")

        if stage == Stage.RED:
            model = RED_STAGE_MODEL
        elif model_override:
            model = model_override
        else:
            model = get_model_for_complexity(complexity)

        logger.info(
            "Worker %d: using model %s for stage %s (complexity=%s)",
            self.worker_id,
            model,
            stage.value,
            complexity,
        )

        # Configure Agent SDK
        options = ClaudeAgentOptions(
            allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
            max_turns=STAGE_MAX_TURNS.get(stage, 15),
            permission_mode="bypassPermissions",
            cwd=str(self.base_dir),
            model=model,
        )

        # Get stage-specific timeout (default 5 min)
        timeout_seconds = STAGE_TIMEOUTS.get(stage, 300)

        logger.info(
            "Worker %d running stage %s for %s (timeout: %ds)",
            self.worker_id,
            stage.value,
            task["task_key"],
            timeout_seconds,
        )

        # Track duration of SDK call
        start_time = time.time()
        duration_ms: int = 0

        try:
            # Wrap SDK call with timeout to prevent indefinite hangs
            result_text = await asyncio.wait_for(
                self._consume_sdk_stream(prompt, options),
                timeout=timeout_seconds,
            )

            # Calculate duration after SDK call completes
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            # Verify stage succeeded based on stage type
            return await self._verify_stage_result(
                stage, task, result_text, skip_recording=skip_recording
            )

        except asyncio.TimeoutError:
            # Calculate duration on timeout
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            logger.error(
                "Stage %s timed out after %ds for task %s",
                stage.value,
                timeout_seconds,
                task["task_key"],
            )
            return StageResult(
                stage=stage,
                success=False,
                output="",
                error=f"Stage timed out after {timeout_seconds}s",
            )

        except Exception as e:
            # Calculate duration even on error
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            logger.exception("Stage %s error: %s", stage.value, e)
            return StageResult(stage=stage, success=False, output="", error=str(e))

        finally:
            # Record invocation AFTER the SDK call with duration
            await self.db.record_invocation(
                run_id=self.run_id,
                stage=stage.value,
                worker_id=self.worker_id,
                task_id=task["id"],
                duration_ms=duration_ms,
            )
            self.stats.invocations += 1

    async def _run_green_with_retry(
        self,
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
            task: Task dictionary with acceptance criteria, test/impl files.
            test_output: Output from RED stage (failing tests).

        Returns:
            StageResult with success=True if any attempt passes tests.
        """
        max_attempts = await self.db.get_config_int("max_green_attempts", 2)
        delay_ms = await self.db.get_config_int("green_retry_delay_ms", 1000)
        aggregate_timeout = await self.db.get_config_int(
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
                    self.worker_id,
                    aggregate_timeout,
                    task_key,
                )
                break

            logger.info(
                "Worker %d: GREEN attempt %d/%d for %s",
                self.worker_id,
                attempt,
                max_attempts,
                task_key,
            )

            # Build kwargs for _run_stage
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
                    self.worker_id,
                    ESCALATION_MODEL,
                    attempt,
                )

            # Run the stage (with skip_recording since we handle it)
            result = await self._run_stage(
                Stage.GREEN,
                task,
                skip_recording=True,
                model_override=model_override,
                **stage_kwargs,
            )

            # Record this attempt with actual attempt number
            await self.db.record_stage_attempt(
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
                    self.worker_id,
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
            self.worker_id,
            max_attempts,
            task_key,
        )

        return last_result or StageResult(
            stage=Stage.GREEN,
            success=False,
            output="",
            error=f"All {max_attempts} GREEN attempts failed",
        )

    async def _consume_sdk_stream(self, prompt: str, options: Any) -> str:
        """Consume SDK streaming response and return final text.

        This helper enables timeout wrapping around the async generator
        returned by sdk_query(), since asyncio.wait_for() only works
        with coroutines.

        Args:
            prompt: The prompt to send to the SDK.
            options: ClaudeAgentOptions for the SDK call.

        Returns:
            The final text from the SDK response.
        """
        result_text = ""
        async for message in sdk_query(prompt=prompt, options=options):
            # Just capture output, don't count messages
            if hasattr(message, "text"):
                result_text = message.text
        return result_text

    async def _verify_stage_result(
        self,
        stage: Stage,
        task: dict[str, Any],
        result_text: str,
        *,
        skip_recording: bool = False,
    ) -> StageResult:
        """Verify stage completed successfully based on stage type.

        Delegates to the standalone verify_stage_result() function in
        stage_verifier.py, passing self.db and self.verifier as arguments.
        """
        return await verify_stage_result(
            stage, task, result_text, self.db, self.verifier,
            base_dir=self.base_dir,
            skip_recording=skip_recording,
        )

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while not self._stop_event.is_set():
            try:
                await self.db.update_worker_heartbeat(self.worker_id)
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker %d heartbeat error: %s", self.worker_id, e)
