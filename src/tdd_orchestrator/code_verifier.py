"""Code verification tools for TDD pipeline.

This module provides the CodeVerifier class that runs external verification
tools (pytest, ruff, mypy) and captures their output for the TDD orchestrator
pipeline. All subprocess calls are async using asyncio.create_subprocess_exec.

Usage:
    verifier = CodeVerifier()
    result = await verifier.verify_all("tests/test_foo.py", "src/foo.py")
    if result.all_passed:
        print("All checks passed!")
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from .ast_checker import ASTCheckConfig, ASTCheckResult, ASTQualityChecker, ASTViolation
from .models import VerifyResult

logger = logging.getLogger(__name__)

# Default timeout for subprocess execution (30 seconds)
DEFAULT_TIMEOUT_SECONDS = 30

_PYTHON_EXTENSIONS = (".py", ".pyi")


def _is_python_file(path: str) -> bool:
    """Check if a file path has a Python extension.

    Args:
        path: File path string.

    Returns:
        True if the file ends with .py or .pyi.
    """
    return path.endswith(_PYTHON_EXTENSIONS)


class CodeVerifier:
    """Run external verification tools and capture output.

    This class executes pytest, ruff, and mypy as async subprocesses,
    capturing stdout/stderr and exit codes. It's designed to be used
    by the TDD orchestrator during VERIFY and RE_VERIFY stages.

    Attributes:
        base_dir: Base directory for resolving relative file paths.
        timeout: Timeout in seconds for each subprocess call.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        ast_config: ASTCheckConfig | None = None,
    ) -> None:
        """Initialize with optional base directory, timeout, and AST config.

        Args:
            base_dir: Base directory for file paths. Defaults to cwd.
            timeout: Timeout in seconds for subprocess calls. Defaults to 30.
            ast_config: Configuration for AST quality checks. Uses defaults if not provided.
        """
        self.base_dir = base_dir or Path.cwd()
        self.timeout = timeout
        self.ast_checker = ASTQualityChecker(ast_config or ASTCheckConfig())

    async def run_pytest(self, test_file: str) -> tuple[bool, str]:
        """Run pytest on a test file.

        Args:
            test_file: Path to the test file (relative or absolute).

        Returns:
            Tuple of (passed, output) where passed is True if exit code is 0.
        """
        test_path = self._resolve_path(test_file)
        logger.debug("Running pytest on %s", test_path)

        return await self._run_command(self._resolve_tool("pytest"), str(test_path), "-v", "--tb=short")

    async def run_ruff(self, impl_file: str) -> tuple[bool, str]:
        """Run ruff check on an implementation file.

        Args:
            impl_file: Path to the implementation file (relative or absolute).

        Returns:
            Tuple of (passed, output) where passed is True if exit code is 0.
        """
        if not _is_python_file(impl_file):
            return True, "Skipped: non-Python file"

        impl_path = self._resolve_path(impl_file)
        logger.debug("Running ruff check on %s", impl_path)

        return await self._run_command(self._resolve_tool("ruff"), "check", str(impl_path))

    async def run_mypy(self, impl_file: str) -> tuple[bool, str]:
        """Run mypy on an implementation file.

        Args:
            impl_file: Path to the implementation file (relative or absolute).

        Returns:
            Tuple of (passed, output) where passed is True if exit code is 0.
        """
        if not _is_python_file(impl_file):
            return True, "Skipped: non-Python file"

        impl_path = self._resolve_path(impl_file)
        logger.debug("Running mypy on %s", impl_path)

        return await self._run_command(self._resolve_tool("mypy"), str(impl_path))

    async def run_ast_checks(self, impl_file: str) -> ASTCheckResult:
        """Run AST quality checks on implementation file.

        Args:
            impl_file: Path to the implementation file (relative or absolute).

        Returns:
            ASTCheckResult containing all violations found.
        """
        if not _is_python_file(impl_file):
            return ASTCheckResult(violations=[], file_path=impl_file)

        impl_path = self._resolve_path(impl_file)
        logger.debug("Running AST checks on %s", impl_path)

        return await self.ast_checker.check_file(impl_path)

    async def verify_all(self, test_file: str, impl_file: str) -> VerifyResult:
        """Run all verification tools in parallel.

        Executes pytest, ruff, mypy, and AST checks concurrently using asyncio.gather
        and aggregates results into a VerifyResult.

        Args:
            test_file: Path to the test file.
            impl_file: Path to the implementation file.

        Returns:
            VerifyResult containing results from all four verification tools.
        """
        logger.info("Running all verification tools for test=%s, impl=%s", test_file, impl_file)

        is_python = _is_python_file(impl_file)

        if is_python:
            # Run all tools in parallel
            results = await asyncio.gather(
                self.run_pytest(test_file),
                self.run_ruff(impl_file),
                self.run_mypy(impl_file),
                self.run_ast_checks(impl_file),
                return_exceptions=True,
            )
            pytest_result = self._handle_result(results[0], "pytest")
            ruff_result = self._handle_result(results[1], "ruff")
            mypy_result = self._handle_result(results[2], "mypy")
            ast_result = self._handle_ast_result(results[3], impl_file)
        else:
            # Non-Python impl: only run pytest on the test file
            pytest_raw = await self.run_pytest(test_file)
            pytest_result = pytest_raw
            ruff_result = (True, "Skipped: non-Python file")
            mypy_result = (True, "Skipped: non-Python file")
            ast_result = ASTCheckResult(violations=[], file_path=impl_file)

        verify_result = VerifyResult(
            pytest_passed=pytest_result[0],
            pytest_output=pytest_result[1],
            ruff_passed=ruff_result[0],
            ruff_output=ruff_result[1],
            mypy_passed=mypy_result[0],
            mypy_output=mypy_result[1],
            ast_result=ast_result,
        )

        logger.info(
            "Verification complete: pytest=%s, ruff=%s, mypy=%s, ast_blocking=%s, all_passed=%s",
            pytest_result[0],
            ruff_result[0],
            mypy_result[0],
            ast_result.is_blocking if ast_result else False,
            verify_result.all_passed,
        )

        return verify_result

    async def _run_command(self, *args: str) -> tuple[bool, str]:
        """Run a command as an async subprocess.

        Args:
            *args: Command and arguments to execute.

        Returns:
            Tuple of (success, output) where success is True if exit code is 0.

        Raises:
            asyncio.TimeoutError: If command exceeds timeout.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.base_dir,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)

            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                error_output = stderr.decode("utf-8", errors="replace")
                output = f"{output}\n{error_output}".strip()

            passed = process.returncode == 0
            logger.debug("Command %s completed with exit code %d", args[0], process.returncode)

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
    def _resolve_tool(tool_name: str) -> str:
        """Resolve tool path from the Python interpreter's directory.

        Looks for the tool in the same directory as sys.executable (venv bin),
        falling back to the bare tool name for PATH resolution.

        Args:
            tool_name: Name of the tool (e.g., "ruff", "mypy", "pytest").

        Returns:
            Absolute path to the tool if found in venv, otherwise the bare name.
        """
        venv_bin = Path(sys.executable).parent
        tool_path = venv_bin / tool_name
        if tool_path.exists():
            return str(tool_path)
        return tool_name

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a file path relative to base_dir.

        Args:
            file_path: Path string (relative or absolute).

        Returns:
            Resolved Path object.
        """
        path = Path(file_path)
        if path.is_absolute():
            return path
        return self.base_dir / path

    def _handle_result(
        self, result: tuple[bool, str] | BaseException, tool_name: str
    ) -> tuple[bool, str]:
        """Handle a result from asyncio.gather, converting exceptions.

        Args:
            result: Either a (passed, output) tuple or an exception.
            tool_name: Name of the tool for error messages.

        Returns:
            Tuple of (passed, output).
        """
        if isinstance(result, BaseException):
            logger.error("%s raised exception: %s", tool_name, result)
            return False, f"{tool_name} raised exception: {result}"
        return result

    def _handle_ast_result(
        self, result: ASTCheckResult | BaseException, impl_file: str
    ) -> ASTCheckResult:
        """Handle AST check result from asyncio.gather, converting exceptions.

        Args:
            result: Either an ASTCheckResult or an exception.
            impl_file: Path to the implementation file for error context.

        Returns:
            ASTCheckResult (may contain error violation if exception occurred).
        """
        if isinstance(result, BaseException):
            logger.error("AST checker raised exception: %s", result)
            return ASTCheckResult(
                violations=[
                    ASTViolation(
                        pattern="checker_error",
                        line_number=0,
                        message=f"AST checker raised exception: {result}",
                        severity="error",
                    )
                ],
                file_path=impl_file,
            )
        return result
