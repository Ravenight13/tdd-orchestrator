"""Pre-REFACTOR static analysis for file quality checks.

Analyzes implementation files to determine if the REFACTOR stage
LLM prompt should be invoked. Avoids unnecessary LLM calls when
the GREEN stage already produced clean code.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RefactorCheckConfig:
    """Configurable thresholds for refactor triggers."""

    split_threshold: int = 400    # Lines: suggest split
    hard_limit: int = 800         # Lines: must split
    max_function_length: int = 50  # Max lines per function/method
    max_class_methods: int = 15    # Max methods per class


@dataclass
class RefactorCheck:
    """Result of pre-refactor analysis."""

    needs_refactor: bool
    reasons: list[str] = field(default_factory=list)
    file_lines: int = 0


async def check_needs_refactor(
    impl_file: str,
    base_dir: Path,
    config: RefactorCheckConfig | None = None,
) -> RefactorCheck:
    """Check if an implementation file needs refactoring.

    Uses stdlib ast module to analyze file structure. Returns
    needs_refactor=False for missing or unparseable files.

    Args:
        impl_file: Relative path to the implementation file.
        base_dir: Root directory for resolving the file path.
        config: Optional custom thresholds. Uses defaults if None.

    Returns:
        RefactorCheck with needs_refactor flag and list of reasons.
    """
    cfg = config or RefactorCheckConfig()
    file_path = base_dir / impl_file

    # Graceful degradation for missing files
    if not file_path.exists():
        return RefactorCheck(needs_refactor=False)

    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return RefactorCheck(needs_refactor=False)

    lines = source.splitlines()
    line_count = len(lines)
    reasons: list[str] = []

    # Check 1: File line count
    if line_count > cfg.hard_limit:
        reasons.append(
            f"File exceeds {cfg.hard_limit}-line hard limit ({line_count} lines) - MUST split"
        )
    elif line_count > cfg.split_threshold:
        reasons.append(
            f"File exceeds {cfg.split_threshold}-line split threshold ({line_count} lines)"
        )

    # Parse AST for structural checks
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Let VERIFY catch syntax errors
        return RefactorCheck(needs_refactor=False, file_lines=line_count)

    # Check 2: Function/method length
    _check_function_lengths(tree, cfg, reasons)

    # Check 3: Class method count
    _check_class_methods(tree, cfg, reasons)

    return RefactorCheck(
        needs_refactor=len(reasons) > 0,
        reasons=reasons,
        file_lines=line_count,
    )


def _check_function_lengths(
    tree: ast.Module,
    cfg: RefactorCheckConfig,
    reasons: list[str],
) -> None:
    """Check for functions/methods exceeding the max length threshold."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno is not None and node.lineno is not None:
                func_length = node.end_lineno - node.lineno + 1
                if func_length > cfg.max_function_length:
                    reasons.append(
                        f"Function '{node.name}' is {func_length} lines "
                        f"(max {cfg.max_function_length})"
                    )


def _check_class_methods(
    tree: ast.Module,
    cfg: RefactorCheckConfig,
    reasons: list[str],
) -> None:
    """Check for classes with too many methods."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_count = sum(
                1 for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            if method_count > cfg.max_class_methods:
                reasons.append(
                    f"Class '{node.name}' has {method_count} methods "
                    f"(max {cfg.max_class_methods})"
                )
