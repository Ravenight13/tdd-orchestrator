"""Acceptance criteria validator for post-run validation.

Parses acceptance_criteria text from decomposition Pass 3 and validates
each criterion against code artifacts using AST-based heuristic matchers.
Results are informational (non-blocking), reported as coverage metrics.

Follows the done_criteria_checker.py pattern: module-level functions
with frozen dataclasses for results.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ACResult:
    """Result of validating a single acceptance criterion."""

    criterion: str
    status: str  # "satisfied", "not_satisfied", "unverifiable"
    matcher: str  # "error_handling", "export", "import", "endpoint", "given_when_then", "none"
    detail: str


@dataclass
class TaskACResult:
    """Aggregate AC validation for a single task."""

    task_key: str
    results: list[ACResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def verifiable(self) -> int:
        return sum(1 for r in self.results if r.status != "unverifiable")

    @property
    def satisfied(self) -> int:
        return sum(1 for r in self.results if r.status == "satisfied")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Regex for numbered list items: "1. text", "2) text"
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+")
# Regex for bullet list items: "- text", "* text"
_BULLET_RE = re.compile(r"^\s*[-*]\s+")
# GIVEN/WHEN/THEN start detection
_GWT_RE = re.compile(r"^\s*GIVEN\b", re.IGNORECASE)


def parse_acceptance_criteria(raw: str) -> list[str]:
    """Parse AC text into individual criteria.

    Handles: JSON arrays, numbered lists, bullet lists, newline-separated,
    GIVEN/WHEN/THEN blocks (kept as single criterion).
    """
    if not raw or not raw.strip():
        return []

    stripped = raw.strip()

    # Try JSON array first
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass

    lines = stripped.split("\n")

    # Detect GIVEN/WHEN/THEN block — keep as single criterion
    if _GWT_RE.match(lines[0]):
        joined = " ".join(line.strip() for line in lines if line.strip())
        return [joined] if joined else []

    criteria: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        # Strip numbered prefix
        text = _NUMBERED_RE.sub("", text).strip()
        # Strip bullet prefix
        text = _BULLET_RE.sub("", text).strip()
        if text:
            criteria.append(text)

    return criteria


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _safe_parse_file(file_path: Path) -> ast.Module | None:
    """Parse a Python file to AST, returning None on any error."""
    try:
        source = file_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return None


def _get_defined_names(tree: ast.Module) -> set[str]:
    """Extract top-level function and class names from an AST."""
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _has_raise(tree: ast.Module, exception_name: str) -> bool:
    """Check if the AST contains a `raise ExceptionName(...)` statement."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            # raise ExceptionName(...)
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                if exc.func.id == exception_name:
                    return True
            # raise ExceptionName
            if isinstance(exc, ast.Name) and exc.id == exception_name:
                return True
    return False


def _has_pytest_raises(tree: ast.Module, exception_name: str) -> bool:
    """Check if the AST contains a `pytest.raises(ExceptionName)` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # pytest.raises(ExceptionName)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "raises"
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
            and node.args
        ):
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Name) and first_arg.id == exception_name:
                return True
    return False


def _get_route_decorators(tree: ast.Module) -> list[tuple[str, str]]:
    """Extract route decorators as (method, path) tuples.

    Finds patterns like @app.get("/path") or @router.post("/path").
    """
    routes: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func if isinstance(dec, ast.Call) else None
            if not isinstance(func, ast.Attribute):
                continue
            method = func.attr.upper()
            if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    path = str(dec.args[0].value)
                    routes.append((method, path))
    return routes


def _get_test_function_names(tree: ast.Module) -> list[str]:
    """Extract all function names starting with 'test_' from the AST."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.append(node.name)
    return names


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------

# Error handling trigger words
_ERROR_RE = re.compile(
    r"\b(?:raises?|error|exception)\b.*\b([A-Z]\w*(?:Error|Exception))\b",
    re.IGNORECASE,
)

# Export/define trigger words
_EXPORT_RE = re.compile(
    r"\b(?:exports?|provides?|defines?|has\s+(?:function|class|method))\s+"
    r"(\w+)",
    re.IGNORECASE,
)

# Import trigger words
_IMPORT_TRIGGER_RE = re.compile(
    r"\b(?:importable|can\s+import|can\s+be\s+imported)\b",
    re.IGNORECASE,
)

# Endpoint trigger: "responds to GET /path" or "endpoint GET /path"
_ENDPOINT_RE = re.compile(
    r"\b(?:responds?\s+to|endpoint|route)\s+"
    r"(GET|POST|PUT|DELETE|PATCH)\s+"
    r"(/\S+)",
    re.IGNORECASE,
)

# GIVEN/WHEN/THEN detection in criterion text
_GWT_CRITERION_RE = re.compile(r"\bGIVEN\b.*\bWHEN\b.*\bTHEN\b", re.IGNORECASE | re.DOTALL)
_WHEN_CLAUSE_RE = re.compile(r"\bWHEN\b\s+(.+?)(?:\s+THEN\b)", re.IGNORECASE | re.DOTALL)


def _match_error_handling(
    criterion: str,
    impl_tree: ast.Module | None,
    test_tree: ast.Module | None,
) -> ACResult | None:
    """Match error handling criteria: raise X in impl + pytest.raises(X) in test."""
    match = _ERROR_RE.search(criterion)
    if not match:
        return None

    exc_name = match.group(1)

    impl_has = impl_tree is not None and _has_raise(impl_tree, exc_name)
    test_has = test_tree is not None and _has_pytest_raises(test_tree, exc_name)

    if impl_has and test_has:
        return ACResult(criterion, "satisfied", "error_handling", f"raise {exc_name} verified")

    parts: list[str] = []
    if not impl_has:
        parts.append(f"raise {exc_name} not found in impl")
    if not test_has:
        parts.append(f"pytest.raises({exc_name}) not found in test")

    return ACResult(criterion, "not_satisfied", "error_handling", "; ".join(parts))


def _match_export(
    criterion: str,
    impl_tree: ast.Module | None,
) -> ACResult | None:
    """Match export/define criteria: function/class definition in impl."""
    match = _EXPORT_RE.search(criterion)
    if not match:
        return None

    symbol = match.group(1)
    if impl_tree is None:
        return ACResult(criterion, "not_satisfied", "export", "impl file not parseable")

    names = _get_defined_names(impl_tree)
    if symbol in names:
        return ACResult(criterion, "satisfied", "export", f"{symbol} defined in impl")

    return ACResult(criterion, "not_satisfied", "export", f"{symbol} not found in impl")


def _match_import(
    criterion: str,
    impl_path: Path,
    impl_tree: ast.Module | None,
) -> ACResult | None:
    """Match import/importable criteria: file exists and parses."""
    if not _IMPORT_TRIGGER_RE.search(criterion):
        return None

    if not impl_path.exists():
        return ACResult(criterion, "not_satisfied", "import", "impl file does not exist")

    if impl_tree is not None:
        return ACResult(criterion, "satisfied", "import", "file exists and parses")

    return ACResult(criterion, "not_satisfied", "import", "file exists but cannot be parsed")


def _match_endpoint(
    criterion: str,
    impl_tree: ast.Module | None,
) -> ACResult | None:
    """Match endpoint/route criteria: decorator pattern in impl."""
    match = _ENDPOINT_RE.search(criterion)
    if not match:
        return None

    method = match.group(1).upper()
    path = match.group(2)

    if impl_tree is None:
        return ACResult(criterion, "not_satisfied", "endpoint", "impl file not parseable")

    routes = _get_route_decorators(impl_tree)
    for route_method, route_path in routes:
        if route_method == method and route_path == path:
            return ACResult(
                criterion, "satisfied", "endpoint", f"{method} {path} route found"
            )

    return ACResult(criterion, "not_satisfied", "endpoint", f"{method} {path} route not found")


def _match_given_when_then(
    criterion: str,
    test_tree: ast.Module | None,
) -> ACResult | None:
    """Match GIVEN/WHEN/THEN criteria: WHEN keywords in test function names."""
    if not _GWT_CRITERION_RE.search(criterion):
        return None

    when_match = _WHEN_CLAUSE_RE.search(criterion)
    if not when_match:
        return ACResult(criterion, "unverifiable", "given_when_then", "could not parse WHEN clause")

    when_text = when_match.group(1).lower()
    # Extract meaningful words from WHEN clause (skip stop words)
    stop_words = {"they", "the", "a", "an", "is", "are", "it", "to", "in", "on"}
    keywords = [w for w in re.findall(r"\w+", when_text) if w not in stop_words]

    if not keywords or test_tree is None:
        return ACResult(
            criterion, "not_satisfied", "given_when_then", "no test functions to match"
        )

    test_names = _get_test_function_names(test_tree)
    for test_name in test_names:
        name_lower = test_name.lower()
        if any(kw in name_lower for kw in keywords):
            return ACResult(
                criterion, "satisfied", "given_when_then",
                f"keyword matched in {test_name}",
            )

    return ACResult(
        criterion, "not_satisfied", "given_when_then",
        f"WHEN keywords {keywords} not found in test names",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def validate_task_ac(
    task_key: str,
    acceptance_criteria: str,
    impl_file: str,
    test_file: str,
    base_dir: Path,
) -> TaskACResult:
    """Validate all AC for a single task against its code artifacts."""
    criteria = parse_acceptance_criteria(acceptance_criteria)
    result = TaskACResult(task_key=task_key)

    if not criteria:
        return result

    impl_path = base_dir / impl_file
    test_path = base_dir / test_file

    # Parse files once, reuse across matchers
    impl_tree = _safe_parse_file(impl_path) if impl_path.exists() else None
    test_tree = _safe_parse_file(test_path) if test_path.exists() else None

    for criterion in criteria:
        ac_result = _match_criterion(criterion, impl_tree, test_tree, impl_path)
        result.results.append(ac_result)

    return result


def _match_criterion(
    criterion: str,
    impl_tree: ast.Module | None,
    test_tree: ast.Module | None,
    impl_path: Path,
) -> ACResult:
    """Run matchers in priority order, return first match or fallback."""
    # Priority 1: Error handling
    r = _match_error_handling(criterion, impl_tree, test_tree)
    if r is not None:
        return r

    # Priority 2: Export/define
    r = _match_export(criterion, impl_tree)
    if r is not None:
        return r

    # Priority 3: Import
    r = _match_import(criterion, impl_path, impl_tree)
    if r is not None:
        return r

    # Priority 4: Endpoint
    r = _match_endpoint(criterion, impl_tree)
    if r is not None:
        return r

    # Priority 5: GIVEN/WHEN/THEN
    r = _match_given_when_then(criterion, test_tree)
    if r is not None:
        return r

    # Fallback: unverifiable
    return ACResult(criterion, "unverifiable", "none", "no heuristic matcher available")


async def validate_run_ac(
    tasks: list[dict[str, Any]],
    base_dir: Path,
) -> str:
    """Validate AC for all tasks. Returns summary string for RunValidationResult."""
    total_verifiable = 0
    total_satisfied = 0
    total_criteria = 0

    for task in tasks:
        ac_raw = task.get("acceptance_criteria")
        if not ac_raw:
            continue

        task_key = str(task.get("task_key", "?"))
        impl_file = str(task.get("impl_file", ""))
        test_file = str(task.get("test_file", ""))

        if not impl_file or not test_file:
            continue

        task_result = await validate_task_ac(
            task_key=task_key,
            acceptance_criteria=str(ac_raw),
            impl_file=impl_file,
            test_file=test_file,
            base_dir=base_dir,
        )

        total_criteria += task_result.total
        total_verifiable += task_result.verifiable
        total_satisfied += task_result.satisfied

        if task_result.total > 0:
            logger.info(
                "AC validation for %s: %d/%d verifiable, %d satisfied",
                task_key,
                task_result.verifiable,
                task_result.total,
                task_result.satisfied,
            )

    if total_verifiable == 0:
        return f"0/{total_criteria} criteria verifiable"

    return (
        f"{total_verifiable}/{total_criteria} criteria verifiable, "
        f"{total_satisfied}/{total_verifiable} verified as satisfied"
    )
