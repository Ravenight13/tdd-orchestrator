"""Worker pool for parallel task execution.

Manages a pool of workers that process TDD tasks in parallel,
with database-backed task claiming and Git branch coordination.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .ast_checker import ASTCheckResult, ASTQualityChecker, ASTViolation
from .code_verifier import CodeVerifier
from .database import OrchestratorDB
from .git_coordinator import GitCoordinator
from .git_stash_guard import GitStashGuard
from .merge_coordinator import MergeCoordinator
from .models import Stage, StageResult
from .progress_writer import ProgressFileWriter
from .prompt_builder import PromptBuilder

# Stage-specific timeout limits (seconds)
# Prevents SDK calls from hanging indefinitely
STAGE_TIMEOUTS: dict[Stage, int] = {
    Stage.RED: 300,  # 5 min - writing failing tests
    Stage.RED_FIX: 300,  # 5 min - fixing static review issues
    Stage.GREEN: 600,  # 10 min - implementing code to pass tests
    Stage.VERIFY: 60,  # 1 min - running quality checks
    Stage.FIX: 300,  # 5 min - fixing issues
    Stage.RE_VERIFY: 60,  # 1 min - re-running quality checks
}

# Aggregate timeout for GREEN retry (all attempts combined)
# Default 30 minutes; can be overridden via config 'max_green_retry_time_seconds'
DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS = 1800

# Model selection based on task complexity (PLAN8)
# Set via ANTHROPIC_MODEL env var before SDK calls
MODEL_MAP: dict[str, str] = {
    "low": "claude-haiku-4-5-20251001",
    "medium": "claude-sonnet-4-5-20250929",
    "high": "claude-opus-4-5-20251101",
}

# Decomposition always uses Opus (needs full reasoning capability)
DECOMPOSITION_MODEL = "claude-opus-4-5-20251101"

# Escalation model for GREEN retries (when first attempt fails)
ESCALATION_MODEL = "claude-opus-4-5-20251101"

# RED stage always uses Opus (test accuracy is critical)
RED_STAGE_MODEL = "claude-opus-4-5-20251101"

# Maximum test output size to include in retry prompts (prevents context overflow)
MAX_TEST_OUTPUT_SIZE = 3000


def set_model_for_complexity(complexity: str) -> str:
    """Set ANTHROPIC_MODEL environment variable based on task complexity.

    Args:
        complexity: Task complexity level ("low", "medium", "high").

    Returns:
        The model that was set.
    """
    import os

    model = MODEL_MAP.get(complexity, MODEL_MAP["medium"])
    os.environ["ANTHROPIC_MODEL"] = model
    return model


if TYPE_CHECKING:
    from typing import Any

# Agent SDK (optional - graceful degradation if not installed)
# Define stub types first, then optionally override with real SDK
HAS_AGENT_SDK = False
ClaudeAgentOptions: Any = None


def sdk_query(*args: Any, **kwargs: Any) -> Any:
    """Stub for sdk_query when SDK is not available."""
    raise RuntimeError("claude_agent_sdk not installed")


class _StubAgentOptions:
    """Stub for ClaudeAgentOptions when SDK is not available."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("claude_agent_sdk not installed")


ClaudeAgentOptions = _StubAgentOptions

try:
    from claude_agent_sdk import (  # type: ignore[import-not-found]
        ClaudeAgentOptions as _SDKAgentOptions,
        query as _sdk_query,
    )

    ClaudeAgentOptions = _SDKAgentOptions
    sdk_query = _sdk_query
    HAS_AGENT_SDK = True
except ImportError:
    pass  # Keep the stubs defined above


logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Configuration for worker pool."""

    max_workers: int = 2
    max_invocations_per_session: int = 100
    budget_warning_threshold: int = 80
    heartbeat_interval_seconds: int = 30
    claim_timeout_seconds: int = 300
    worker_timeout_seconds: int = 600
    use_local_branches: bool = False
    single_branch_mode: bool = False
    git_stash_enabled: bool = True
    progress_file_enabled: bool = True
    progress_file_path: str = "tdd-progress.md"


@dataclass
class WorkerStats:
    """Statistics for a worker."""

    worker_id: int
    tasks_completed: int = 0
    tasks_failed: int = 0
    invocations: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since worker started."""
        return time.time() - self.start_time


@dataclass
class RedFixAttemptTracker:
    """Track RED_FIX attempts to prevent infinite loops.

    Implements PLAN12 loop safeguards:
    - Max 2 fix attempts (hard-coded)
    - Oscillation detection (A->B->A pattern)
    - 5-minute aggregate timeout
    """

    max_attempts: int = 2
    attempts: int = 0
    issue_fingerprints: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    aggregate_timeout_seconds: int = 300  # 5 minutes

    def can_attempt(self) -> tuple[bool, str]:
        """Check if another fix attempt is allowed.

        Returns:
            Tuple of (can_attempt, reason_if_not).
        """
        # Check max attempts
        if self.attempts >= self.max_attempts:
            return False, f"Max fix attempts ({self.max_attempts}) reached"

        # Check aggregate timeout
        elapsed = time.time() - self.start_time
        if elapsed > self.aggregate_timeout_seconds:
            return False, f"Aggregate timeout ({self.aggregate_timeout_seconds}s) exceeded"

        # Check for oscillation (A->B->A pattern)
        if len(self.issue_fingerprints) >= 3:
            if self.issue_fingerprints[-1] == self.issue_fingerprints[-3]:
                return False, "Oscillation detected (same issue reappeared)"

        return True, ""

    def record_attempt(self, issues: list[ASTViolation]) -> None:
        """Record a fix attempt with issue fingerprint.

        Args:
            issues: List of AST violations from static review.
        """
        self.attempts += 1
        # Create fingerprint: sorted list of (pattern:line)
        fingerprint = "|".join(sorted(f"{i.pattern}:{i.line_number}" for i in issues))
        self.issue_fingerprints.append(fingerprint)


@dataclass
class StaticReviewCircuitBreaker:
    """Circuit breaker to auto-disable static review after consecutive failures.

    If the static review system itself fails (not the checks finding issues,
    but the system crashing), this circuit breaker will temporarily disable
    static review to prevent blocking all tasks.

    Implements a simple circuit breaker pattern:
    - After max_consecutive_failures, circuit opens (disabled)
    - After cooldown_seconds, circuit closes (re-enabled)
    - Success resets the failure counter
    """

    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    disabled_until: float | None = None
    cooldown_seconds: float = 300.0  # 5 minutes

    def record_success(self) -> None:
        """Reset failure count on success."""
        self.consecutive_failures = 0
        self.disabled_until = None

    def record_failure(self) -> bool:
        """Record failure, return True if circuit is now open (disabled).

        Returns:
            True if the circuit breaker just opened (static review now disabled).
        """
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.disabled_until = time.time() + self.cooldown_seconds
            return True
        return False

    def is_enabled(self) -> bool:
        """Check if static review should run.

        Returns:
            True if static review is enabled and should run.
        """
        if self.disabled_until is None:
            return True
        if time.time() >= self.disabled_until:
            # Cooldown expired, reset and re-enable
            self.disabled_until = None
            self.consecutive_failures = 0
            return True
        return False


@dataclass
class PoolResult:
    """Result of running the worker pool."""

    tasks_completed: int
    tasks_failed: int
    total_invocations: int
    worker_stats: list[WorkerStats]
    stopped_reason: str | None = None


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
                    await self._squash_wip_commits(task_key)
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

        Pipeline: RED -> Static Review -> GREEN -> VERIFY -> (FIX -> RE_VERIFY if needed)
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
            await self._commit_stage(task_key, "RED", f"wip({task_key}): RED stage - failing tests")

            # Stage 1.5: Static RED Review (PLAN12)
            fix_tracker = RedFixAttemptTracker()
            review_result = await self._run_static_review(task)

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
                await self._commit_stage(
                    task_key, "RED_FIX", f"wip({task_key}): RED_FIX - static review fixes"
                )

                # Re-run static review
                review_result = await self._run_static_review(task)

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
        await self._commit_stage(
            task_key, "GREEN", f"wip({task_key}): GREEN stage - implementation"
        )

        # Auto-fix unused imports before VERIFY
        impl_file = task.get("impl_file", "")
        if impl_file:
            await self._run_ruff_fix(impl_file, task_key)

        # Stage 3: VERIFY - Run quality checks
        result = await self._run_stage(Stage.VERIFY, task)
        if result.success:
            await self._commit_stage(
                task_key, "VERIFY", f"feat({task_key}): complete - all checks pass"
            )
            return True

        # Stage 4: FIX - Address issues (conditional)
        if not result.issues:
            logger.error("VERIFY failed but no issues provided")
            return False

        result = await self._run_stage(Stage.FIX, task, issues=result.issues)
        if not result.success:
            return False
        await self._commit_stage(task_key, "FIX", f"wip({task_key}): FIX stage - issue fixes")

        # Stage 5: RE_VERIFY - Final verification (conditional)
        result = await self._run_stage(Stage.RE_VERIFY, task)
        if result.success:
            await self._commit_stage(
                task_key, "RE_VERIFY", f"feat({task_key}): complete - all checks pass"
            )
        return result.success

    async def _run_ruff_fix(self, impl_file: str, task_key: str) -> bool:
        """Run ruff --fix on implementation file to auto-fix lint issues.

        Args:
            impl_file: Path to implementation file.
            task_key: Task key for logging.

        Returns:
            True if ruff ran successfully, False otherwise.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "ruff",
                "check",
                "--fix",
                impl_file,
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            logger.info("[%s] Ran ruff --fix on %s", task_key, impl_file)
            return True
        except Exception as e:
            logger.warning("[%s] ruff --fix failed: %s", task_key, e)
            return False

    async def _squash_wip_commits(self, task_key: str) -> bool:
        """Squash all WIP commits for this task into a single commit.

        Finds all commits with 'wip({task_key}):' prefix and squashes them
        into a single feat commit.

        Args:
            task_key: Task key to match WIP commits (e.g., 'HTMX-TDD-02-04').

        Returns:
            True if squash succeeded, False otherwise.
        """
        try:
            # Count WIP commits for this task
            proc = await asyncio.create_subprocess_exec(
                "git",
                "log",
                "--oneline",
                "--grep",
                f"wip({task_key}):",
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            wip_commits = stdout.decode().strip().split("\n")
            wip_count = len([c for c in wip_commits if c])

            if wip_count < 2:
                logger.debug("[%s] Only %d WIP commits, skipping squash", task_key, wip_count)
                return True

            # Soft reset to before first WIP commit
            proc = await asyncio.create_subprocess_exec(
                "git",
                "reset",
                "--soft",
                f"HEAD~{wip_count}",
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            if proc.returncode != 0:
                logger.warning("[%s] git reset failed, aborting squash", task_key)
                return False

            # Create single squashed commit
            message = f"feat({task_key}): complete (squashed from {wip_count} WIP commits)\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
            proc = await asyncio.create_subprocess_exec(
                "git",
                "commit",
                "--no-verify",
                "-m",
                message,
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            if proc.returncode == 0:
                logger.info("[%s] Squashed %d WIP commits into one", task_key, wip_count)
                return True
            else:
                logger.warning("[%s] squash commit failed", task_key)
                return False

        except Exception as e:
            logger.warning("[%s] WIP squash failed: %s", task_key, e)
            return False

    async def _commit_stage(self, task_key: str, stage: str, message: str) -> bool:
        """Commit current changes for a TDD stage.

        Creates a WIP commit after each successful stage to preserve work
        incrementally, preventing loss of progress if later stages fail.

        Args:
            task_key: JIRA task key (e.g., 'VEA-123').
            stage: Stage name for logging (e.g., 'RED', 'GREEN').
            message: Commit message.

        Returns:
            True if commit succeeded, False otherwise.
        """
        try:
            # Stage all changes
            proc = await asyncio.create_subprocess_exec(
                "git",
                "add",
                "-A",
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            # Commit with message and co-author
            # Use --no-verify for TDD WIP commits since:
            # 1. Partial code intentionally doesn't pass all checks
            # 2. RED stage has failing tests by design
            # 3. Actual verification happens in VERIFY stage
            full_message = f"{message}\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
            proc = await asyncio.create_subprocess_exec(
                "git",
                "commit",
                "--no-verify",
                "-m",
                full_message,
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            if proc.returncode == 0:
                logger.info("[%s] Committed %s stage", task_key, stage)
                return True
            else:
                # Non-zero return may mean no changes to commit (not an error)
                stderr = await proc.stderr.read() if proc.stderr else b""
                if b"nothing to commit" in stderr:
                    logger.debug("[%s] No changes to commit for %s stage", task_key, stage)
                    return True
                logger.warning(
                    "[%s] Git commit returned %d for %s stage",
                    task_key,
                    proc.returncode,
                    stage,
                )
                return False
        except Exception as e:
            logger.warning("[%s] Failed to commit %s stage: %s", task_key, stage, e)
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

        # Set model based on task complexity (PLAN8) or use override
        complexity = task.get("complexity", "medium")

        # Always use Opus for RED stage (tests are specifications, must be accurate)
        if stage == Stage.RED:
            model_override = RED_STAGE_MODEL

        if model_override:
            import os

            os.environ["ANTHROPIC_MODEL"] = model_override
            model = model_override
            logger.info(
                "Worker %d: using model %s (override)",
                self.worker_id,
                model,
            )
        else:
            model = set_model_for_complexity(complexity)
            logger.info(
                "Worker %d: using model %s for complexity %s",
                self.worker_id,
                model,
                complexity,
            )

        # Configure Agent SDK
        options = ClaudeAgentOptions(
            allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
            max_turns=10,  # Fewer turns per stage (focused prompt)
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

    async def _run_static_review(self, task: dict[str, Any]) -> ASTCheckResult:
        """Run static review on RED stage test file.

        Implements PLAN12 Static RED Review gate using:
        - AST-based checks (missing assertions, empty assertions)
        - Subprocess pytest collection verification
        - Circuit breaker to auto-disable after consecutive failures

        Graceful degradation: parse failures, timeouts, or exceptions
        don't block pipeline - they pass through with warning.

        Args:
            task: Task dict with test_file path.

        Returns:
            ASTCheckResult with violations found.
        """
        test_file = task.get("test_file", "")
        task_key = task.get("task_key", "UNKNOWN")

        # Check circuit breaker - skip static review if disabled
        if not self.static_review_circuit_breaker.is_enabled():
            remaining = 0.0
            if self.static_review_circuit_breaker.disabled_until is not None:
                remaining = self.static_review_circuit_breaker.disabled_until - time.time()
            logger.warning(
                "[%s] Static review circuit breaker OPEN - skipping (re-enables in %.0fs)",
                task_key,
                max(0.0, remaining),
            )
            return ASTCheckResult(violations=[], file_path=test_file)

        # Check if circuit breaker just re-enabled after cooldown
        if self.static_review_circuit_breaker.consecutive_failures == 0:
            # May have just reset - log if we had failures before
            pass  # Normal operation, no special logging needed

        try:
            # Timeout wrapper (500ms max for all checks)
            async with asyncio.timeout(0.5):
                # AST checks
                checker = ASTQualityChecker()
                test_path = self.base_dir / test_file
                result = await checker.check_file(test_path)

                # Subprocess verification: pytest --collect-only
                collection_ok, stderr = await self._verify_pytest_collection(test_file)
                if not collection_ok:
                    result.violations.append(
                        ASTViolation(
                            pattern="pytest_collection",
                            line_number=0,
                            message="Pytest collection failed",
                            severity="warning",
                            code_snippet=stderr[:200] if stderr else "",
                        )
                    )
                    # Recalculate is_blocking since we added a violation
                    result.is_blocking = any(v.severity == "error" for v in result.violations)

                # Log Phase 1B shadow mode metrics (warnings only)
                for violation in result.violations:
                    if violation.severity == "warning":
                        try:
                            await self.db.log_static_review_metric(
                                task_id=task.get("id", 0),
                                task_key=task_key,
                                check_name=violation.pattern,
                                severity=violation.severity,
                                line_number=violation.line_number,
                                message=violation.message,
                                code_snippet=violation.code_snippet or None,
                                fix_guidance=None,  # ASTViolation doesn't have fix_guidance
                                run_id=self.run_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "[%s] Failed to log shadow mode metric: %s",
                                task_key,
                                e,
                            )

                logger.info(
                    "[%s] Static review: %d violations, blocking=%s",
                    task_key,
                    len(result.violations),
                    result.is_blocking,
                )

                # Record success - reset circuit breaker
                self.static_review_circuit_breaker.record_success()
                return result

        except asyncio.TimeoutError:
            logger.warning("[%s] Static review timeout - passing through", task_key)
            return ASTCheckResult(violations=[], file_path=test_file)

        except Exception as e:
            # Record failure in circuit breaker
            circuit_opened = self.static_review_circuit_breaker.record_failure()
            if circuit_opened:
                logger.error(
                    "[%s] Static review circuit breaker OPEN - disabled for %.0fs after %d failures",
                    task_key,
                    self.static_review_circuit_breaker.cooldown_seconds,
                    self.static_review_circuit_breaker.max_consecutive_failures,
                )
            else:
                logger.error(
                    "[%s] Static review exception: %s - passing through (failure %d/%d)",
                    task_key,
                    e,
                    self.static_review_circuit_breaker.consecutive_failures,
                    self.static_review_circuit_breaker.max_consecutive_failures,
                )
            return ASTCheckResult(violations=[], file_path=test_file)

    async def _verify_pytest_collection(self, test_file: str) -> tuple[bool, str]:
        """Run pytest --collect-only to catch import/fixture errors.

        Args:
            test_file: Path to test file.

        Returns:
            Tuple of (success, stderr).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "pytest",
                "--collect-only",
                "-q",
                test_file,
                cwd=str(self.base_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                return proc.returncode == 0, stderr.decode()
            except asyncio.TimeoutError:
                proc.kill()
                return False, "Pytest collection timed out (5s)"
        except Exception as e:
            logger.warning("Pytest collection error: %s", e)
            return True, ""  # Graceful degradation

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

        Args:
            stage: The TDD stage being verified.
            task: Task dictionary with id, test_file, impl_file etc.
            result_text: The output text from the stage execution.
            skip_recording: If True, skip recording stage attempt (caller handles it).
                           Used by _run_green_with_retry() to avoid duplicate recording.

        Returns:
            StageResult with success status and output.
        """
        if stage == Stage.RED:
            # RED succeeds if test file exists and pytest fails (expected)
            test_file = task.get("test_file", "")
            passed, output = await self.verifier.run_pytest(test_file)
            # RED should FAIL (tests fail because no implementation)
            success = not passed  # Inverted: pytest failing = RED success

            # Record stage attempt
            await self.db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=success,
                pytest_exit_code=0 if passed else 1,
            )

            return StageResult(stage=stage, success=success, output=output)

        if stage == Stage.GREEN:
            # GREEN succeeds if pytest passes
            test_file = task.get("test_file", "")
            passed, output = await self.verifier.run_pytest(test_file)

            # Record stage attempt (unless caller handles it)
            if not skip_recording:
                await self.db.record_stage_attempt(
                    task_id=task["id"],
                    stage=stage.value,
                    attempt_number=1,  # Will be dynamic in Phase 1
                    success=passed,
                    pytest_exit_code=0 if passed else 1,
                )

            return StageResult(stage=stage, success=passed, output=output)

        if stage in (Stage.VERIFY, Stage.RE_VERIFY):
            # VERIFY/RE_VERIFY succeeds if all tools pass
            test_file = task.get("test_file", "")
            impl_file = task.get("impl_file", "")
            verify_result = await self.verifier.verify_all(test_file, impl_file)

            issues: list[dict[str, Any]] = []
            if not verify_result.pytest_passed:
                issues.append({"tool": "pytest", "output": verify_result.pytest_output})
            if not verify_result.ruff_passed:
                issues.append({"tool": "ruff", "output": verify_result.ruff_output})
            if not verify_result.mypy_passed:
                issues.append({"tool": "mypy", "output": verify_result.mypy_output})

            # Record stage attempt with all exit codes
            await self.db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=verify_result.all_passed,
                pytest_exit_code=0 if verify_result.pytest_passed else 1,
                ruff_exit_code=0 if verify_result.ruff_passed else 1,
                mypy_exit_code=0 if verify_result.mypy_passed else 1,
            )

            return StageResult(
                stage=stage,
                success=verify_result.all_passed,
                output=result_text,
                issues=issues if issues else None,
            )

        if stage == Stage.FIX:
            # FIX succeeds if no exceptions (actual verification in RE_VERIFY)

            # Record stage attempt (no exit codes for FIX stage)
            await self.db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=True,
            )

            return StageResult(stage=stage, success=True, output=result_text)

        if stage == Stage.RED_FIX:
            # RED_FIX succeeds if no exceptions (actual verification in re-run of static review)
            await self.db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=True,
            )
            return StageResult(stage=stage, success=True, output=result_text)

        return StageResult(stage=stage, success=False, output="", error="Unknown stage")

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


class WorkerPool:
    """Manages parallel worker execution."""

    def __init__(
        self,
        db: OrchestratorDB,
        base_dir: Path,
        config: WorkerConfig | None = None,
        slack_webhook_url: str | None = None,
    ) -> None:
        """Initialize worker pool.

        Args:
            db: Database instance.
            base_dir: Root directory of the Git repository.
            config: Worker configuration.
            slack_webhook_url: Slack webhook for notifications.
        """
        self.db = db
        self.base_dir = base_dir
        self.config = config or WorkerConfig()
        self.git = GitCoordinator(base_dir)
        self.merge = MergeCoordinator(base_dir, slack_webhook_url)
        self.workers: list[Worker] = []
        self.run_id: int = 0
        self.progress_writer: ProgressFileWriter | None = None
        if self.config.progress_file_enabled:
            self.progress_writer = ProgressFileWriter(
                db=db, output_path=Path(self.config.progress_file_path)
            )

    async def run_parallel_phase(self, phase: int | None = None) -> PoolResult:
        """Run all tasks in a phase in parallel.

        Only Phase 0 tasks (no dependencies) are processed in parallel.

        Args:
            phase: Phase number to process.

        Returns:
            PoolResult with completion statistics.
        """
        # Start execution run
        self.run_id = await self.db.start_execution_run(self.config.max_workers)

        result = PoolResult(
            tasks_completed=0,
            tasks_failed=0,
            total_invocations=0,
            worker_stats=[],
        )

        try:
            # Initialize progress writer with run_id
            if self.progress_writer:
                self.progress_writer.run_id = self.run_id
                self.progress_writer.start_time = datetime.now()

            # Get claimable tasks for this phase
            tasks = await self.db.get_claimable_tasks(phase)
            if not tasks:
                logger.info(
                    "No tasks available for phase %s", phase if phase is not None else "all"
                )
                result.stopped_reason = "no_tasks"
                return result

            logger.info(
                "Found %d tasks for phase %s", len(tasks), phase if phase is not None else "all"
            )

            # Create and start workers
            self.workers = [
                Worker(i, self.db, self.git, self.config, self.run_id, self.base_dir)
                for i in range(1, self.config.max_workers + 1)
            ]

            for worker in self.workers:
                await worker.start()

            # Process tasks with worker pool
            task_queue = list(tasks)

            while task_queue:
                # Check budget
                count, limit, is_warning = await self.db.check_invocation_budget(self.run_id)

                if count >= limit:
                    logger.warning("Invocation limit reached (%d/%d)", count, limit)
                    result.stopped_reason = "invocation_limit"
                    break

                if is_warning:
                    logger.warning(
                        "Budget warning: %d/%d invocations (%.0f%%)",
                        count,
                        limit,
                        count / limit * 100,
                    )

                # Assign tasks to workers
                worker_tasks: list[tuple[Worker, dict[str, Any]]] = []

                for worker in self.workers:
                    if task_queue:
                        task = task_queue.pop(0)
                        worker_tasks.append((worker, task))

                if not worker_tasks:
                    break

                # Process tasks in parallel
                results = await asyncio.gather(
                    *[worker.process_task(task) for worker, task in worker_tasks],
                    return_exceptions=True,
                )

                # Check for failures (100% success required)
                for i, (worker, _) in enumerate(worker_tasks):
                    if isinstance(results[i], Exception):
                        logger.error("Worker %d exception: %s", worker.worker_id, results[i])
                        result.tasks_failed += 1
                    elif results[i] is True:
                        result.tasks_completed += 1
                    else:
                        result.tasks_failed += 1

                # Update progress file after each batch of tasks
                if self.progress_writer:
                    await self.progress_writer.update()

                # Stop on any failure (100% success required)
                if result.tasks_failed > 0:
                    logger.error("Task failure detected - stopping (100%% success required)")
                    result.stopped_reason = "task_failure"
                    break

            # Cleanup stale claims
            await self.db.cleanup_stale_claims()

            # Merge completed branches (skip in single branch mode - already on main)
            if result.tasks_completed > 0 and not self.config.single_branch_mode:
                completed_tasks = [t for t in tasks[: result.tasks_completed]]
                branches = [
                    (
                        f"worker-{(i % self.config.max_workers) + 1}/{t['task_key']}",
                        t["task_key"],
                    )
                    for i, t in enumerate(completed_tasks)
                ]

                merge_results = await self.merge.merge_phase_branches(phase, branches)

                for mr in merge_results:
                    if not mr.success:
                        logger.error("Merge failed for %s: %s", mr.branch, mr.error_message)
                        result.stopped_reason = "merge_failure"

        finally:
            # Stop all workers
            for worker in self.workers:
                await worker.stop()
                result.worker_stats.append(worker.stats)

            # Complete execution run
            status = "completed" if result.stopped_reason is None else "failed"
            await self.db.complete_execution_run(self.run_id, status)

            result.total_invocations = await self.db.get_invocation_count(self.run_id)

        return result
