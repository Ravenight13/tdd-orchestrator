"""End-of-run validator for comprehensive post-run checks.

After all phases complete, runs full regression, lint, type check,
orphaned task detection, and non-blocking import/criteria checks.
Results are stored in the execution_runs table.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..subprocess_utils import resolve_tool

if TYPE_CHECKING:
    from ..database import OrchestratorDB

logger = logging.getLogger(__name__)

# Statuses that indicate a task is done and should not be orphaned
TERMINAL_STATUSES = ("complete", "passing")


@dataclass
class RunValidationResult:
    """Result of end-of-run validation checks."""

    passed: bool
    regression_passed: bool
    lint_passed: bool
    type_check_passed: bool
    import_check_passed: bool
    orphaned_tasks: list[str] = field(default_factory=list)
    done_criteria_summary: str = ""
    ac_validation_summary: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Human-readable summary of the validation result."""
        if self.passed:
            return "End-of-run validation PASSED"

        parts: list[str] = ["End-of-run validation FAILED:"]

        if not self.regression_passed:
            parts.append("regression failed")
        if not self.lint_passed:
            parts.append("lint failed")
        if not self.type_check_passed:
            parts.append("type check failed")
        if self.orphaned_tasks:
            parts.append(f"{len(self.orphaned_tasks)} orphaned task(s)")

        return " ".join(parts)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))


class RunValidator:
    """Validates a completed run with comprehensive checks.

    Blocking checks (affect passed):
    - Full regression (pytest on all test_files)
    - Lint (ruff on all impl_files)
    - Type check (mypy on all impl_files)
    - Orphaned task detection

    Non-blocking checks (logged only):
    - Module import verification
    - Done criteria aggregation
    - AC validation (Phase 5 placeholder)

    Args:
        db: Database instance for querying tasks.
        base_dir: Root directory for subprocess cwd.
        timeout: Timeout in seconds for subprocess calls.
    """

    def __init__(
        self,
        db: OrchestratorDB,
        base_dir: Path,
        timeout: int = 600,
    ) -> None:
        self.db = db
        self.base_dir = base_dir
        self.timeout = timeout

    async def validate_run(self, run_id: int) -> RunValidationResult:
        """Run all validation checks for an execution run.

        Args:
            run_id: The execution run ID to validate.

        Returns:
            RunValidationResult with all check outcomes.
        """
        tasks: list[dict[str, Any]] = await self.db.get_all_tasks()

        if not tasks:
            logger.info("No tasks in run %d — validation passes by default", run_id)
            return RunValidationResult(
                passed=True,
                regression_passed=True,
                lint_passed=True,
                type_check_passed=True,
                import_check_passed=True,
            )

        result = RunValidationResult(
            passed=True,
            regression_passed=True,
            lint_passed=True,
            type_check_passed=True,
            import_check_passed=True,
        )

        # Blocking checks
        await self._run_full_regression(result, tasks)
        await self._run_lint(result, tasks)
        await self._run_type_check(result, tasks)
        self._check_orphaned_tasks(result, tasks)

        # Non-blocking checks
        await self._check_module_imports(result, tasks)
        await self._aggregate_done_criteria(result, tasks)
        self._run_ac_validation(result)

        # Compute final passed status from blocking checks
        result.passed = (
            result.regression_passed
            and result.lint_passed
            and result.type_check_passed
            and len(result.orphaned_tasks) == 0
        )

        return result

    async def _run_full_regression(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Run pytest on all test_files from tasks."""
        test_files = self._collect_files(tasks, "test_file")
        if not test_files:
            logger.info("No test files to regress — skipping regression")
            return

        pytest_path = resolve_tool("pytest")
        file_args = [str(self.base_dir / f) for f in test_files]
        passed, output = await self._run_command(
            pytest_path, *file_args, "-v", "--tb=short"
        )

        result.regression_passed = passed
        if not passed:
            result.errors.append(f"Regression failed: {output[:500]}")
            logger.warning("Regression test failure in end-of-run validation")

    async def _run_lint(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Run ruff check on all impl_files from tasks."""
        impl_files = self._collect_files(tasks, "impl_file")
        if not impl_files:
            logger.info("No impl files to lint — skipping lint check")
            return

        ruff_path = resolve_tool("ruff")
        file_args = [str(self.base_dir / f) for f in impl_files]
        passed, output = await self._run_command(ruff_path, "check", *file_args)

        result.lint_passed = passed
        if not passed:
            result.errors.append(f"Lint failed: {output[:500]}")
            logger.warning("Lint failure in end-of-run validation")

    async def _run_type_check(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Run mypy --strict on all impl_files from tasks."""
        impl_files = self._collect_files(tasks, "impl_file")
        if not impl_files:
            logger.info("No impl files for type check — skipping")
            return

        mypy_path = resolve_tool("mypy")
        file_args = [str(self.base_dir / f) for f in impl_files]
        passed, output = await self._run_command(mypy_path, *file_args, "--strict")

        result.type_check_passed = passed
        if not passed:
            result.errors.append(f"Type check failed: {output[:500]}")
            logger.warning("Type check failure in end-of-run validation")

    def _check_orphaned_tasks(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Identify tasks not in terminal status."""
        result.orphaned_tasks = [
            str(task["task_key"])
            for task in tasks
            if task["status"] not in TERMINAL_STATUSES
        ]

        if result.orphaned_tasks:
            logger.warning(
                "Orphaned tasks detected: %s", ", ".join(result.orphaned_tasks)
            )

    async def _check_module_imports(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Try importing module_exports from tasks (non-blocking)."""
        for task in tasks:
            exports_raw = task.get("module_exports", "[]")
            impl_file = task.get("impl_file")
            if not exports_raw or exports_raw == "[]" or not impl_file:
                continue

            try:
                exports: list[str] = json.loads(str(exports_raw))
            except (json.JSONDecodeError, TypeError):
                continue

            if not exports:
                continue

            # Convert impl_file path to module path
            module_path = self._file_to_module(str(impl_file))
            if not module_path:
                continue

            import_stmt = f"from {module_path} import {', '.join(exports)}"
            python_path = resolve_tool("python")
            passed, output = await self._run_command(
                python_path, "-c", import_stmt
            )

            if not passed:
                result.import_check_passed = False
                logger.info(
                    "Import check failed for %s: %s",
                    task.get("task_key", "?"),
                    output[:200],
                )

    async def _aggregate_done_criteria(
        self, result: RunValidationResult, tasks: list[dict[str, Any]]
    ) -> None:
        """Re-evaluate done_criteria for all tasks (non-blocking)."""
        from ..worker_pool.done_criteria_checker import evaluate_criteria

        satisfied = 0
        total = 0

        for task in tasks:
            raw = task.get("done_criteria")
            if not raw:
                continue

            task_key = str(task.get("task_key", "?"))
            dc_result = await evaluate_criteria(str(raw), task_key, self.base_dir)

            for cr in dc_result.results:
                total += 1
                if cr.status == "satisfied":
                    satisfied += 1

        result.done_criteria_summary = f"{satisfied}/{total} criteria satisfied"

    def _run_ac_validation(self, result: RunValidationResult) -> None:
        """Placeholder for Phase 5A acceptance criteria validation."""
        result.ac_validation_summary = ""

    async def _run_command(self, *args: str) -> tuple[bool, str]:
        """Run a command as an async subprocess.

        Uses asyncio.create_subprocess_exec (no shell=True) for safety.

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

    @staticmethod
    def _collect_files(tasks: list[dict[str, Any]], key: str) -> list[str]:
        """Collect unique non-null file paths from tasks.

        Args:
            tasks: List of task dicts.
            key: Key to extract ('test_file' or 'impl_file').

        Returns:
            Deduplicated list of file paths.
        """
        seen: set[str] = set()
        files: list[str] = []
        for task in tasks:
            value = task.get(key)
            if value and str(value) not in seen:
                seen.add(str(value))
                files.append(str(value))
        return files

    @staticmethod
    def _file_to_module(file_path: str) -> str | None:
        """Convert a file path to a Python module path.

        'src/tdd_orchestrator/foo/bar.py' -> 'tdd_orchestrator.foo.bar'

        Returns None if the path doesn't look like a Python file.
        """
        if not file_path.endswith(".py"):
            return None

        # Strip src/ prefix if present
        path = file_path
        if path.startswith("src/"):
            path = path[4:]

        # Remove .py suffix and convert / to .
        path = path[:-3].replace("/", ".")
        return path
