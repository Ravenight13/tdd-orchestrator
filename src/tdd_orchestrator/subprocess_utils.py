"""Shared subprocess utilities."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_tool(tool_name: str) -> str:
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
