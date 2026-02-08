"""Stage result verification for TDD pipeline stages.

Extracted from Worker._verify_stage_result() to keep worker.py under
the 800-line limit. This module contains a pure function that verifies
stage completion based on stage type, with no Worker instance dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from ..code_verifier import CodeVerifier
from ..database import OrchestratorDB
from ..models import Stage, StageResult

logger = logging.getLogger(__name__)


async def verify_stage_result(
    stage: Stage,
    task: dict[str, Any],
    result_text: str,
    db: OrchestratorDB,
    verifier: CodeVerifier,
    *,
    skip_recording: bool = False,
) -> StageResult:
    """Verify stage completed successfully based on stage type.

    Args:
        stage: The TDD stage being verified.
        task: Task dictionary with id, test_file, impl_file etc.
        result_text: The output text from the stage execution.
        db: Database instance for recording attempts.
        verifier: Code verifier for running pytest/ruff/mypy.
        skip_recording: If True, skip recording stage attempt (caller handles it).

    Returns:
        StageResult with success status and output.
    """
    if stage == Stage.RED:
        # RED succeeds if test file exists and pytest fails (expected)
        test_file = task.get("test_file", "")
        passed, output = await verifier.run_pytest(test_file)
        # RED should FAIL (tests fail because no implementation)
        success = not passed  # Inverted: pytest failing = RED success

        # Record stage attempt
        await db.record_stage_attempt(
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
        passed, output = await verifier.run_pytest(test_file)

        # Record stage attempt (unless caller handles it)
        if not skip_recording:
            await db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=passed,
                pytest_exit_code=0 if passed else 1,
            )

        return StageResult(stage=stage, success=passed, output=output)

    if stage in (Stage.VERIFY, Stage.RE_VERIFY):
        # VERIFY/RE_VERIFY succeeds if all tools pass
        test_file = task.get("test_file", "")
        impl_file = task.get("impl_file", "")
        verify_result = await verifier.verify_all(test_file, impl_file)

        issues: list[dict[str, Any]] = []
        if not verify_result.pytest_passed:
            issues.append({"tool": "pytest", "output": verify_result.pytest_output})
        if not verify_result.ruff_passed:
            issues.append({"tool": "ruff", "output": verify_result.ruff_output})
        if not verify_result.mypy_passed:
            issues.append({"tool": "mypy", "output": verify_result.mypy_output})

        # Record stage attempt with all exit codes
        await db.record_stage_attempt(
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

    if stage == Stage.FIX:
        # FIX succeeds if no exceptions (actual verification in RE_VERIFY)
        await db.record_stage_attempt(
            task_id=task["id"],
            stage=stage.value,
            attempt_number=1,
            success=True,
        )

        return StageResult(stage=stage, success=True, output=result_text)

    if stage == Stage.RED_FIX:
        # RED_FIX succeeds if no exceptions (actual verification in re-run of static review)
        await db.record_stage_attempt(
            task_id=task["id"],
            stage=stage.value,
            attempt_number=1,
            success=True,
        )
        return StageResult(stage=stage, success=True, output=result_text)

    return StageResult(stage=stage, success=False, output="", error="Unknown stage")
