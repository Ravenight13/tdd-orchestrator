"""Verify-command runner for post-pipeline supplemental checks.

Parses verify_command strings from decomposition output, validates them
against an allowlist of safe tools, and executes them as subprocess calls.
Results are informational (log-only), not pipeline-blocking.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from ..subprocess_utils import resolve_tool

logger = logging.getLogger(__name__)

ALLOWED_TOOLS: frozenset[str] = frozenset({"pytest", "python", "ruff", "mypy", "pip"})

# Matches paths like .venv/bin/, /home/user/.venv/bin/, etc.
_VENV_BIN_RE = re.compile(r"^(?:.*/)?\.?venv/bin/")


@dataclass(frozen=True)
class VerifyCommandResult:
    """Result of a verify_command execution."""

    raw_command: str
    tool: str
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    skipped: bool
    skip_reason: str

    @property
    def summary(self) -> str:
        """Human-readable one-line summary."""
        if self.skipped:
            return f"skipped ({self.skip_reason})"
        if self.exit_code == 0:
            return f"passed (exit 0): {self.tool} {' '.join(self.args)}"
        return f"FAILED (exit {self.exit_code}): {self.tool} {' '.join(self.args)}"


def parse_verify_command(raw: str) -> tuple[str, tuple[str, ...], str]:
    """Parse a verify_command string into (tool, args, skip_reason).

    Returns:
        Tuple of (tool_name, args_tuple, skip_reason).
        If skip_reason is non-empty, tool will be "" and args will be ().
    """
    if not raw or not raw.strip():
        return "", (), "empty command"

    cleaned = raw.strip()

    # Strip "uv run " launcher prefix
    if cleaned.startswith("uv run "):
        cleaned = cleaned[len("uv run "):]

    # Strip venv bin path prefixes (e.g., .venv/bin/, /abs/path/.venv/bin/)
    cleaned = _VENV_BIN_RE.sub("", cleaned)

    try:
        parts = shlex.split(cleaned)
    except ValueError:
        return "", (), "malformed quoting"

    if not parts:
        return "", (), "empty after parsing"

    tool = parts[0]
    if tool not in ALLOWED_TOOLS:
        return "", (), f"{tool!r} not in allowlist"

    return tool, tuple(parts[1:]), ""


async def run_verify_command(
    raw: str,
    base_dir: str | Path,
    timeout: int = 60,
) -> VerifyCommandResult:
    """Parse and execute a verify_command, returning the result.

    This is non-blocking and informational. Failures are logged, not raised.
    Uses asyncio.create_subprocess_exec (not shell=True) for safety.
    The tool is validated against ALLOWED_TOOLS before execution.

    Args:
        raw: The raw verify_command string from decomposition.
        base_dir: Working directory for the subprocess.
        timeout: Maximum seconds to wait for completion.

    Returns:
        VerifyCommandResult with captured stdout/stderr.
    """
    tool, args, skip_reason = parse_verify_command(raw)

    if skip_reason:
        return VerifyCommandResult(
            raw_command=raw, tool="", args=(), exit_code=-1,
            stdout="", stderr="", skipped=True, skip_reason=skip_reason,
        )

    resolved = resolve_tool(tool)

    try:
        proc = await asyncio.create_subprocess_exec(
            resolved, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(base_dir),
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
        return VerifyCommandResult(
            raw_command=raw, tool=tool, args=args,
            exit_code=proc.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            skipped=False, skip_reason="",
        )
    except TimeoutError:
        logger.warning("verify_command timed out after %ds: %s", timeout, raw)
        return VerifyCommandResult(
            raw_command=raw, tool=tool, args=args, exit_code=-1,
            stdout="", stderr=f"Timeout after {timeout}s",
            skipped=False, skip_reason="",
        )
    except FileNotFoundError as e:
        logger.warning("verify_command tool not found: %s", e)
        return VerifyCommandResult(
            raw_command=raw, tool=tool, args=args, exit_code=-1,
            stdout="", stderr=f"Tool not found: {e}",
            skipped=False, skip_reason="",
        )
