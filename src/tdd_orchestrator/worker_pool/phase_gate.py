"""Phase gate validator for multi-phase sequential execution.

Validates that prior phases are complete and their tests pass
before allowing the next phase to start. Provides batch regression
testing with individual re-run on failure for diagnosis.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..subprocess_utils import resolve_tool

if TYPE_CHECKING:
    from ..database import OrchestratorDB

logger = logging.getLogger(__name__)

# Statuses that indicate a task is done and should not block the gate
TERMINAL_STATUSES = ("complete", "passing")


@dataclass(frozen=True)
class TestFileResult:
    """Result of running pytest on a single test file."""

    file: str
    passed: bool
    exit_code: int
    output: str


@dataclass
class PhaseGateResult:
    """Result of a phase gate validation check."""

    phase: int
    passed: bool
    incomplete_tasks: list[str] = field(default_factory=list)
    regression_results: list[TestFileResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Human-readable summary of the gate result."""
        if self.passed:
            return f"Phase {self.phase} gate PASSED"

        parts: list[str] = [f"Phase {self.phase} gate FAILED:"]

        if self.incomplete_tasks:
            parts.append(
                f"{len(self.incomplete_tasks)} incomplete task(s) in prior phases"
            )

        failed_tests = [r for r in self.regression_results if not r.passed]
        if failed_tests:
            parts.append(
                f"{len(failed_tests)} regression test(s) failed"
            )

        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")

        return " ".join(parts)


class PhaseGateValidator:
    """Validates phase gates before starting new phases.

    Checks that all tasks in prior phases have terminal status
    and runs regression tests on prior phase test files.

    Args:
        db: Database instance for querying task state.
        base_dir: Root directory for subprocess cwd.
        timeout: Timeout in seconds for subprocess calls.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        base_dir: Path,
        timeout: int = 90,
    ) -> None:
        self.db = db
        self.base_dir = base_dir
        self.timeout = timeout

    async def validate_phase(self, phase: int) -> PhaseGateResult:
        """Validate whether it is safe to start the given phase.

        Checks:
        1. All tasks in phases < phase have terminal status
        2. Regression tests from prior phases pass

        Args:
            phase: The phase about to start.

        Returns:
            PhaseGateResult with pass/fail status and details.
        """
        prior_tasks: list[dict[str, Any]] = await self.db.get_tasks_in_phases_before(phase)

        # No prior work -> pass immediately
        if not prior_tasks:
            return PhaseGateResult(phase=phase, passed=True)

        # Check all prior tasks have terminal status
        incomplete = self._check_prior_phases_complete(prior_tasks)
        if incomplete:
            return PhaseGateResult(
                phase=phase,
                passed=False,
                incomplete_tasks=incomplete,
            )

        # Get test files from prior phases
        test_files: list[str] = await self.db.get_test_files_from_phases_before(phase)
        if not test_files:
            return PhaseGateResult(phase=phase, passed=True)

        # Run regression tests
        batch_passed, regression_results = await self._run_batch_regression(test_files)

        return PhaseGateResult(
            phase=phase,
            passed=batch_passed,
            regression_results=regression_results,
        )

    def _check_prior_phases_complete(
        self, prior_tasks: list[dict[str, Any]]
    ) -> list[str]:
        """Filter tasks from prior phases that are not in terminal status.

        Args:
            prior_tasks: Task dicts from phases before the target phase.

        Returns:
            List of task_keys that are NOT complete/passing.
        """
        return [
            str(task["task_key"])
            for task in prior_tasks
            if task["status"] not in TERMINAL_STATUSES
        ]

    async def _run_batch_regression(
        self, test_files: list[str]
    ) -> tuple[bool, list[TestFileResult]]:
        """Run regression tests, batch first then individual on failure.

        Args:
            test_files: List of test file paths to run.

        Returns:
            Tuple of (all_passed, individual_results).
        """
        # Try batch first
        pytest_path = resolve_tool("pytest")
        file_args = [str(self.base_dir / f) for f in test_files]
        batch_passed, batch_output = await self._run_command(
            pytest_path, *file_args, "-v", "--tb=short"
        )

        if batch_passed:
            results = [
                TestFileResult(file=f, passed=True, exit_code=0, output=batch_output)
                for f in test_files
            ]
            return True, results

        # Batch failed -> re-run individually for diagnosis
        logger.warning("Batch regression failed, re-running individually for diagnosis")
        individual_tasks = [
            self._run_pytest_single(f) for f in test_files
        ]
        results = await asyncio.gather(*individual_tasks)
        all_passed = all(r.passed for r in results)

        for r in results:
            if not r.passed:
                logger.warning("Regression failure: %s (exit %d)", r.file, r.exit_code)

        return all_passed, list(results)

    async def _run_pytest_single(self, test_file: str) -> TestFileResult:
        """Run pytest on a single test file.

        Args:
            test_file: Relative path to the test file.

        Returns:
            TestFileResult with pass/fail and output.
        """
        pytest_path = resolve_tool("pytest")
        file_path = str(self.base_dir / test_file)
        passed, output = await self._run_command(
            pytest_path, file_path, "-v", "--tb=short"
        )
        return TestFileResult(
            file=test_file,
            passed=passed,
            exit_code=0 if passed else 1,
            output=output,
        )

    async def _run_command(self, *args: str) -> tuple[bool, str]:
        """Run a command as an async subprocess.

        Uses asyncio.create_subprocess_exec (no shell) for safety.

        Args:
            *args: Command and arguments to execute.

        Returns:
            Tuple of (success, output) where success is True if exit code is 0.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.base_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )

            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                error_output = stderr.decode("utf-8", errors="replace")
                output = f"{output}\n{error_output}".strip()

            passed = process.returncode == 0
            return passed, output

        except asyncio.TimeoutError:
            logger.warning("Command %s timed out after %ds", args[0], self.timeout)
            return False, f"Command timed out after {self.timeout} seconds"

        except FileNotFoundError:
            logger.error("Command not found: %s", args[0])
            return False, f"Command not found: {args[0]}"

        except Exception as e:
            logger.exception("Unexpected error running command %s", args[0])
            return False, f"Unexpected error: {e}"
