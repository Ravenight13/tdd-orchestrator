"""Unit tests for verify_command_runner (parsing and execution)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.worker_pool.verify_command_runner import (
    ALLOWED_TOOLS,
    VerifyCommandResult,
    parse_verify_command,
    run_verify_command,
)


# ---------------------------------------------------------------------------
# parse_verify_command tests (pure, no I/O)
# ---------------------------------------------------------------------------


class TestParseVerifyCommand:
    """Parsing logic for verify_command strings."""

    def test_bare_pytest(self) -> None:
        tool, args, skip = parse_verify_command("pytest tests/test_foo.py -v")
        assert tool == "pytest"
        assert args == ("tests/test_foo.py", "-v")
        assert skip == ""

    def test_uv_run_prefix_stripped(self) -> None:
        tool, args, skip = parse_verify_command("uv run pytest tests/test_foo.py")
        assert tool == "pytest"
        assert args == ("tests/test_foo.py",)
        assert skip == ""

    def test_venv_bin_prefix_stripped(self) -> None:
        tool, args, skip = parse_verify_command(".venv/bin/pytest tests/test_foo.py")
        assert tool == "pytest"
        assert args == ("tests/test_foo.py",)
        assert skip == ""

    def test_absolute_venv_bin_stripped(self) -> None:
        tool, args, skip = parse_verify_command(
            "/home/user/project/.venv/bin/mypy src/ --strict"
        )
        assert tool == "mypy"
        assert args == ("src/", "--strict")
        assert skip == ""

    def test_python_with_args(self) -> None:
        tool, args, skip = parse_verify_command("python -c 'import tdd_orchestrator'")
        assert tool == "python"
        assert args == ("-c", "import tdd_orchestrator")
        assert skip == ""

    def test_pip_install(self) -> None:
        tool, args, skip = parse_verify_command(".venv/bin/pip install -e '.[dev]'")
        assert tool == "pip"
        assert args == ("install", "-e", ".[dev]")
        assert skip == ""

    def test_ruff_check(self) -> None:
        tool, args, skip = parse_verify_command("ruff check src/module.py")
        assert tool == "ruff"
        assert args == ("check", "src/module.py")
        assert skip == ""

    def test_disallowed_tool_skipped(self) -> None:
        tool, args, skip = parse_verify_command("node scripts/test.js")
        assert tool == ""
        assert args == ()
        assert "not in allowlist" in skip

    def test_empty_string_skipped(self) -> None:
        tool, args, skip = parse_verify_command("")
        assert tool == ""
        assert args == ()
        assert "empty" in skip.lower()

    def test_whitespace_only_skipped(self) -> None:
        tool, args, skip = parse_verify_command("   ")
        assert tool == ""
        assert args == ()
        assert "empty" in skip.lower()

    def test_malformed_quoting_skipped(self) -> None:
        tool, args, skip = parse_verify_command("pytest 'unclosed quote")
        assert tool == ""
        assert args == ()
        assert "parse" in skip.lower() or "malformed" in skip.lower()

    def test_allowlist_contains_expected_tools(self) -> None:
        assert ALLOWED_TOOLS == frozenset({"pytest", "python", "ruff", "mypy", "pip"})


# ---------------------------------------------------------------------------
# run_verify_command tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRunVerifyCommand:
    """Execution with mocked subprocess."""

    async def test_successful_run(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"OK\n", b""))
        mock_proc.returncode = 0

        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner._resolve_tool",
            return_value="pytest",
        ):
            result = await run_verify_command("pytest tests/test_foo.py", tmp_path)

        assert isinstance(result, VerifyCommandResult)
        assert result.exit_code == 0
        assert result.stdout == "OK\n"
        assert not result.skipped

    async def test_failed_run(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"FAILED\n"))
        mock_proc.returncode = 1

        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner._resolve_tool",
            return_value="pytest",
        ):
            result = await run_verify_command("pytest tests/test_foo.py", tmp_path)

        assert result.exit_code == 1
        assert result.stderr == "FAILED\n"
        assert not result.skipped

    async def test_timeout_handled(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner._resolve_tool",
            return_value="pytest",
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            result = await run_verify_command("pytest tests/test_foo.py", tmp_path)

        assert result.exit_code == -1
        assert "timeout" in result.stderr.lower()
        assert not result.skipped

    async def test_skipped_command_no_subprocess(self, tmp_path: Path) -> None:
        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as mock_exec:
            result = await run_verify_command("", tmp_path)

        assert result.skipped
        assert "empty" in result.skip_reason.lower()
        mock_exec.assert_not_called()

    async def test_file_not_found_handled(self, tmp_path: Path) -> None:
        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("pytest not found"),
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner._resolve_tool",
            return_value="pytest",
        ):
            result = await run_verify_command("pytest tests/test_foo.py", tmp_path)

        assert result.exit_code == -1
        assert "not found" in result.stderr.lower()
        assert not result.skipped

    async def test_summary_on_success(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch(
            "tdd_orchestrator.worker_pool.verify_command_runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "tdd_orchestrator.worker_pool.verify_command_runner._resolve_tool",
            return_value="pytest",
        ):
            result = await run_verify_command("pytest tests/", tmp_path)

        assert "passed" in result.summary.lower()

    async def test_summary_on_skip(self, tmp_path: Path) -> None:
        result = await run_verify_command("", tmp_path)
        assert "skipped" in result.summary.lower()
