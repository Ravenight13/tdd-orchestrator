"""Done-criteria checker for post-pipeline supplemental evaluation.

Parses done_criteria strings from decomposition output and evaluates
each criterion using heuristic matchers. Results are informational
(log-only), not pipeline-blocking.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns for heuristic matching
_TESTS_PASS_RE = re.compile(r"(?:all\s+)?tests?\s+pass", re.IGNORECASE)
_IMPORTABLE_RE = re.compile(
    r"(?:package|module)\s+([\w.]+)\s+(?:is\s+)?importable", re.IGNORECASE
)
_IMPORT_RE = re.compile(r"import\s+([\w.]+)", re.IGNORECASE)
_FILE_EXISTS_RE = re.compile(r"file\s+(\S+)\s+exists", re.IGNORECASE)

# Separator for ", and " conjunction
_COMMA_AND_RE = re.compile(r",\s+and\s+", re.IGNORECASE)


@dataclass(frozen=True)
class CriterionResult:
    """Result of evaluating a single criterion."""

    criterion: str
    status: str  # "satisfied", "failed", "unverifiable"
    detail: str


@dataclass
class DoneCriteriaResult:
    """Aggregated result of evaluating all done_criteria."""

    task_key: str
    results: list[CriterionResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Human-readable summary, e.g. '3/4 criteria satisfied'."""
        satisfied = sum(1 for r in self.results if r.status == "satisfied")
        total = len(self.results)
        return f"{satisfied}/{total} criteria satisfied"


def parse_criteria(raw: str) -> list[str]:
    """Split a raw done_criteria string into individual criteria.

    Splits on newlines, semicolons, and ', and ' conjunction.
    Strips whitespace and filters empty items.
    """
    if not raw or not raw.strip():
        return []

    # First split on ", and " conjunction
    text = _COMMA_AND_RE.sub(";", raw)

    # Split on newlines and semicolons
    parts: list[str] = []
    for line in text.split("\n"):
        for item in line.split(";"):
            stripped = item.strip()
            if stripped:
                parts.append(stripped)

    return parts


async def evaluate_criteria(
    raw: str,
    task_key: str,
    base_dir: str | Path,
) -> DoneCriteriaResult:
    """Parse and evaluate all done_criteria for a task.

    Args:
        raw: The raw done_criteria string from decomposition.
        task_key: Task identifier for logging.
        base_dir: Project root directory for file checks.

    Returns:
        DoneCriteriaResult with per-criterion statuses.
    """
    criteria = parse_criteria(raw)
    result = DoneCriteriaResult(task_key=task_key)

    for criterion in criteria:
        cr = await _evaluate_single(criterion, Path(base_dir))
        result.results.append(cr)

    return result


async def _evaluate_single(criterion: str, base_dir: Path) -> CriterionResult:
    """Evaluate a single criterion using heuristic matchers.

    Matchers:
    - "tests pass" / "all tests pass" -> satisfied (covered by VERIFY stage)
    - "importable" / "import X" -> subprocess check via python -c
    - "file X exists" -> Path.exists() check
    - Everything else -> unverifiable
    """
    # "tests pass" family -- already covered by the VERIFY stage
    if _TESTS_PASS_RE.search(criterion):
        return CriterionResult(
            criterion=criterion, status="satisfied",
            detail="Covered by VERIFY stage",
        )

    # "module/package X importable"
    match = _IMPORTABLE_RE.search(criterion) or _IMPORT_RE.search(criterion)
    if match:
        module_name = match.group(1)
        return await _check_importable(criterion, module_name, base_dir)

    # "file X exists"
    match = _FILE_EXISTS_RE.search(criterion)
    if match:
        file_path = match.group(1)
        full_path = base_dir / file_path
        if full_path.exists():
            return CriterionResult(
                criterion=criterion, status="satisfied",
                detail=f"{file_path} exists",
            )
        return CriterionResult(
            criterion=criterion, status="failed",
            detail=f"{file_path} not found",
        )

    # Fallback: unverifiable
    return CriterionResult(
        criterion=criterion, status="unverifiable",
        detail="No heuristic matcher available",
    )


async def _check_importable(
    criterion: str, module_name: str, base_dir: Path,
) -> CriterionResult:
    """Check if a Python module is importable via subprocess.

    Uses create_subprocess_exec (not shell=True) for safety.
    The module_name is passed as a single argument to 'python -c'.
    """
    python = str(Path(sys.executable))
    try:
        proc = await asyncio.create_subprocess_exec(
            python, "-c", f"import {module_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(base_dir),
        )
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            return CriterionResult(
                criterion=criterion, status="satisfied",
                detail=f"import {module_name} succeeded",
            )
        return CriterionResult(
            criterion=criterion, status="failed",
            detail=stderr_bytes.decode(errors="replace").strip()[:200],
        )
    except (TimeoutError, FileNotFoundError) as e:
        return CriterionResult(
            criterion=criterion, status="unverifiable",
            detail=f"Could not check: {e}",
        )
