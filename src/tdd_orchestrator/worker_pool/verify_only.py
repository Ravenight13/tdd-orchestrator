"""Verify-only pipeline for pre-implemented tasks.

Tasks marked as verify-only skip RED and GREEN stages, proceeding
directly to VERIFY. Used when the overlap detector determines that
a dependency task has already implemented the required code.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..models import Stage
from .config import RunStageFunc
from .done_criteria_checker import evaluate_criteria
from .git_ops import commit_stage, run_ruff_fix
from .verify_command_runner import run_verify_command

logger = logging.getLogger(__name__)


async def _run_post_verify_checks(task: dict[str, Any], base_dir: str) -> None:
    """Run verify_command and done_criteria checks (log-only, non-blocking)."""
    task_key = str(task.get("key", task.get("task_key", "")))
    if verify_cmd := task.get("verify_command"):
        result = await run_verify_command(str(verify_cmd), base_dir)
        logger.info("verify-only post-check verify_command: %s", result.summary)
    if criteria := task.get("done_criteria"):
        result_dc = await evaluate_criteria(str(criteria), task_key, base_dir)
        logger.info("verify-only post-check done_criteria: %s", result_dc.summary)


async def run_verify_only_pipeline(
    task: dict[str, Any],
    run_stage: RunStageFunc,
    base_dir: Path,
) -> bool:
    """Execute verify-only pipeline: VERIFY -> (FIX -> RE_VERIFY if needed).

    Args:
        task: Task dictionary from database.
        run_stage: Bound method Worker._run_stage for executing stages.
        base_dir: Project root directory.

    Returns:
        True if verification passes (with or without fixes).
    """
    task_key = task.get("task_key", "UNKNOWN")
    impl_file = task.get("impl_file", "")

    logger.info("[%s] Running verify-only pipeline (RED+GREEN skipped)", task_key)

    # Auto-fix imports before VERIFY
    if impl_file:
        await run_ruff_fix(impl_file, task_key, base_dir)

    # VERIFY
    result = await run_stage(Stage.VERIFY, task)
    if result.success:
        await commit_stage(
            task_key, "VERIFY",
            f"feat({task_key}): complete (verify-only) - all checks pass",
            base_dir,
        )
        await _run_post_verify_checks(task, str(base_dir))
        return True

    # VERIFY failed -- attempt FIX
    if not result.issues:
        logger.error("[%s] VERIFY failed but no issues provided", task_key)
        return False

    result = await run_stage(Stage.FIX, task, issues=result.issues)
    if not result.success:
        return False
    await commit_stage(
        task_key, "FIX",
        f"wip({task_key}): FIX stage - verify-only fixes",
        base_dir,
    )

    # RE_VERIFY
    result = await run_stage(Stage.RE_VERIFY, task)
    if result.success:
        await commit_stage(
            task_key, "RE_VERIFY",
            f"feat({task_key}): complete (verify-only) - all checks pass",
            base_dir,
        )
        await _run_post_verify_checks(task, str(base_dir))
    return result.success
