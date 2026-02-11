"""Stage result verification for TDD pipeline stages.

Extracted from Worker._verify_stage_result() to keep worker.py under
the 800-line limit. This module contains a pure function that verifies
stage completion based on stage type, with no Worker instance dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path
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
    base_dir: Path,
    skip_recording: bool = False,
) -> StageResult:
    """Verify stage completed successfully based on stage type.

    Args:
        stage: The TDD stage being verified.
        task: Task dictionary with id, test_file, impl_file etc.
        result_text: The output text from the stage execution.
        db: Database instance for recording attempts.
        verifier: Code verifier for running pytest/ruff/mypy.
        base_dir: Root directory for resolving relative file paths.
        skip_recording: If True, skip recording stage attempt (caller handles it).

    Returns:
        StageResult with success status and output.
    """
    if stage == Stage.RED:
        # RED succeeds if test file exists and pytest fails (expected)
        test_file = task.get("test_file", "")

        # Guard: test file must exist on disk before running pytest
        if not test_file or not (base_dir / test_file).exists():
            logger.error("RED verification failed: test file not found: %s", test_file)
            await db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=False,
                pytest_exit_code=4,  # pytest exit code 4 = no tests collected
            )
            return StageResult(
                stage=stage,
                success=False,
                output=f"Test file not found: {test_file}",
                error="Test file not created by RED stage",
            )

        passed, output = await verifier.run_pytest(test_file)

        if not passed:
            # Classic TDD: tests fail as expected -> RED success
            await db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=True,
                pytest_exit_code=1,
            )
            return StageResult(stage=stage, success=True, output=output)

        # Tests passed unexpectedly -- check if impl_file already exists
        impl_file = task.get("impl_file", "")
        task_key = task.get("task_key", "UNKNOWN")

        if impl_file and (base_dir / impl_file).exists():
            # Implementation file exists and tests pass against it.
            # This task's requirements are already satisfied by a dependency.
            logger.warning(
                "[%s] RED tests passed -- impl_file exists (%s), marking pre-implemented",
                task_key,
                impl_file,
            )
            await db.record_stage_attempt(
                task_id=task["id"],
                stage=stage.value,
                attempt_number=1,
                success=True,
                pytest_exit_code=0,
            )
            return StageResult(
                stage=stage, success=True, output=output, pre_implemented=True,
            )

        # Tests passed but no impl file exists -- genuine RED failure
        logger.error(
            "[%s] RED tests passed but no implementation file exists at %s",
            task_key,
            impl_file or "(no impl_file specified)",
        )
        await db.record_stage_attempt(
            task_id=task["id"],
            stage=stage.value,
            attempt_number=1,
            success=False,
            pytest_exit_code=0,
        )
        return StageResult(
            stage=stage,
            success=False,
            output=output,
            error="RED tests passed without implementation -- tests may not be asserting correctly",
        )

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

        # --- Sibling test regression check ---
        if verify_result.all_passed and impl_file:
            test_file_str = test_file or ""
            sibling_files = await db.get_sibling_test_files(impl_file, test_file_str)
            if sibling_files:
                sib_passed, sib_output = await verifier.run_pytest_on_files(sibling_files)
                verify_result.siblings_passed = sib_passed
                verify_result.siblings_output = sib_output
                if not sib_passed:
                    logger.warning(
                        "Sibling test regression for %s: %s",
                        task.get("task_key", "?"),
                        ", ".join(sibling_files),
                    )
                    return StageResult(
                        stage=stage,
                        success=False,
                        output=result_text,
                        error=f"Sibling test regression: {', '.join(sibling_files)}",
                        issues=[{"tool": "pytest-siblings", "output": sib_output}],
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
