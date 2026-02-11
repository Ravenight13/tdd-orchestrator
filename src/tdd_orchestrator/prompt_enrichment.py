"""Prompt enrichment helpers for the TDD pipeline.

Extracted from prompt_builder.py to keep that module focused on stage-level
prompt assembly. This module contains:

- Named constants for content truncation limits
- File I/O helpers (read, escape, path validation)
- Sibling test discovery and conftest reading
- Signature extraction from implementation files
- Parsing helpers for criteria and module exports
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

# =============================================================================
# Named constants (replaces magic numbers across stage methods)
# =============================================================================

MAX_TEST_FILE_CONTENT = 8000
MAX_IMPL_FILE_CONTENT = 6000
MAX_HINTS_CONTENT = 3000
MAX_SIBLING_FILES = 5
MAX_SIBLING_HINT_LINES = 10

# Previously class attributes on PromptBuilder
MAX_CONFTEST_CONTENT = 4000
MAX_IMPL_SIGNATURES = 30

# Previously hardcoded literals in stage methods
MAX_TEST_OUTPUT = 3000
MAX_FAILURE_OUTPUT = 3000
MAX_ISSUES_OUTPUT = 1000


# =============================================================================
# Parsing helpers
# =============================================================================


def parse_criteria(acceptance_criteria: str | list[str] | None) -> list[str]:
    """Parse acceptance criteria from string or list."""
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return acceptance_criteria
    try:
        parsed = json.loads(acceptance_criteria)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def parse_module_exports(module_exports_raw: str | list[str] | None) -> list[str]:
    """Parse module_exports from string or list."""
    if module_exports_raw is None:
        return []
    if isinstance(module_exports_raw, list):
        return module_exports_raw
    try:
        parsed = json.loads(module_exports_raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def to_import_path(file_path: str) -> str:
    """Convert a file path to a Python import path, stripping src layout prefix."""
    import_path = file_path.replace("/", ".").replace(".py", "")
    if import_path.startswith("src."):
        import_path = import_path[4:]
    return import_path


def escape_braces(text: str) -> str:
    """Escape curly braces for safe use in str.format() templates."""
    return text.replace("{", "{{").replace("}", "}}")


# =============================================================================
# File I/O helpers
# =============================================================================


def read_file_safe(
    base_dir: Path | None,
    relative_path: str,
    max_chars: int,
    fallback: str,
) -> str:
    """Read a file with truncation and fallback."""
    if not base_dir or not relative_path:
        return fallback
    try:
        file_path = (base_dir / relative_path).resolve()
        file_path.relative_to(base_dir.resolve())
    except (ValueError, OSError):
        return fallback
    if not file_path.exists():
        return fallback
    try:
        raw = file_path.read_text(encoding="utf-8")
        if len(raw) > max_chars:
            return raw[:max_chars] + "\n# ... (truncated)"
        return raw
    except OSError:
        return fallback


def safe_absolute_path(base_dir: Path | None, relative_path: str) -> str:
    """Resolve an absolute path, falling back to relative if traversal detected."""
    if not base_dir:
        return relative_path
    try:
        resolved = (base_dir / relative_path).resolve()
        resolved.relative_to(base_dir.resolve())
        return str(resolved)
    except (ValueError, OSError):
        return relative_path


def build_code_section(
    base_dir: Path | None,
    file_path: str,
    max_chars: int,
    title: str,
    description: str = "",
) -> str:
    """Read a file, escape braces, and wrap in a titled code section.

    DRY helper replacing the duplicated read→escape→wrap pattern in
    fix(), refactor(), and green() stage methods.

    Returns:
        Formatted prompt section string, or empty string if the file
        doesn't exist or can't be read.
    """
    raw = read_file_safe(base_dir, file_path, max_chars, "")
    if not raw:
        return ""
    escaped = escape_braces(raw)
    desc_line = f"{description}\n" if description else ""
    return f"\n## {title}\n{desc_line}```python\n{escaped}\n```\n"


# =============================================================================
# Sibling test discovery
# =============================================================================


def discover_sibling_tests(
    base_dir: Path | None,
    test_file: str,
    stage_hint: Literal["green", "red"] = "green",
) -> str:
    """Discover sibling test files and extract behavioral contract hints.

    Globs test_*.py in the test file's parent directory, reads each sibling
    for behavioral patterns (status codes, response assertions, await
    patterns, imports), and builds a prompt section warning the worker
    about existing contracts.

    Args:
        base_dir: Project root for resolving paths.
        test_file: The current task's test file (excluded from results).
        stage_hint: Controls header/description language.
            ``"green"`` (default) warns about not breaking siblings.
            ``"red"`` instructs matching existing contracts.

    Returns:
        Prompt section string (empty string if no siblings found).
    """
    if not base_dir or not test_file:
        return ""

    test_path = base_dir / test_file
    parent = test_path.parent
    if not parent.exists():
        return ""

    siblings = sorted(
        p for p in parent.glob("test_*.py")
        if p.name != test_path.name
    )
    if not siblings:
        return ""

    sections: list[str] = []
    for sib in siblings[:MAX_SIBLING_FILES]:
        try:
            rel = str(sib.relative_to(base_dir))
        except ValueError:
            continue
        hints: list[str] = []
        try:
            lines = sib.read_text(encoding="utf-8").splitlines()
            # Prioritized extraction: status codes > response assertions > await > imports
            status_lines: list[str] = []
            response_lines: list[str] = []
            await_lines: list[str] = []
            import_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if "status_code" in stripped and "==" in stripped:
                    status_lines.append(f"    {stripped}")
                elif stripped.startswith("assert") and "response." in stripped:
                    response_lines.append(f"    {stripped}")
                elif "await " in stripped:
                    await_lines.append(f"    {stripped}")
                elif stripped.startswith(("from ", "import ")):
                    import_lines.append(f"    {stripped}")
            # Merge in priority order, capped at MAX_SIBLING_HINT_LINES
            for bucket in (status_lines, response_lines, await_lines, import_lines):
                if len(hints) >= MAX_SIBLING_HINT_LINES:
                    break
                for item in bucket:
                    if len(hints) >= MAX_SIBLING_HINT_LINES:
                        break
                    hints.append(escape_braces(item))
        except OSError:
            continue

        if hints:
            hint_block = "\n".join(hints)
            sections.append(f"- `{escape_braces(rel)}` (behavioral contracts):\n{hint_block}")
        else:
            sections.append(f"- `{escape_braces(rel)}`")

    sibling_list = "\n".join(sections)

    if stage_hint == "red":
        return (
            "\n## SIBLING TESTS (MATCH EXISTING CONTRACTS)\n"
            "Other test files target the SAME implementation module. "
            "These tests have already established behavioral contracts "
            "(status codes, response shapes, async patterns, imports). "
            "Your tests MUST match these conventions.\n"
            "Key rules:\n"
            "- If a sibling asserts `status_code == 400`, use the SAME "
            "status code for similar errors\n"
            "- If a sibling uses `await`, your tests MUST also use "
            "`await` for that function\n"
            "- Match import paths from siblings exactly\n\n"
            f"{sibling_list}\n"
        )

    return (
        "\n## SIBLING TESTS (DO NOT BREAK)\n"
        "Other test files target the SAME implementation module. "
        "Your changes MUST NOT break these existing tests.\n"
        "Key contracts to preserve:\n"
        "- Status codes and response shapes asserted by siblings\n"
        "- Async/sync nature of functions (if a sibling uses "
        "`await`, keep it `async def`)\n"
        "- Import paths used by siblings\n\n"
        f"{sibling_list}\n"
    )


# =============================================================================
# Conftest reading
# =============================================================================


def read_conftest(base_dir: Path | None, test_file: str) -> str:
    """Read conftest.py from the test file's directory or one level up.

    Returns a formatted prompt section, or empty string if not found.
    """
    if not base_dir or not test_file:
        return ""

    test_path = base_dir / test_file
    parent = test_path.parent

    # Check same directory first, then one level up
    for candidate_dir in (parent, parent.parent):
        conftest = candidate_dir / "conftest.py"
        try:
            conftest.resolve().relative_to(base_dir.resolve())
        except (ValueError, OSError):
            continue
        if conftest.exists():
            try:
                content = conftest.read_text(encoding="utf-8")
                if len(content) > MAX_CONFTEST_CONTENT:
                    content = content[:MAX_CONFTEST_CONTENT] + "\n# ... (truncated)"
                escaped = escape_braces(content)
                return (
                    "\n## SHARED FIXTURES (conftest.py)\n"
                    "Reuse these fixtures rather than duplicating setup logic.\n"
                    f"```python\n{escaped}\n```\n"
                )
            except OSError:
                continue

    return ""


# =============================================================================
# Implementation signature extraction
# =============================================================================


def extract_impl_signatures(base_dir: Path | None, impl_file: str) -> str:
    """Extract function/class signatures from an existing implementation file.

    Reads the implementation file and extracts lines starting with ``def ``,
    ``async def ``, or ``class `` (plus preceding decorator lines).  The
    result is wrapped in a prompt section that instructs the LLM to match
    these exact signatures.

    Args:
        base_dir: Project root for resolving paths.
        impl_file: Relative path to the implementation file.

    Returns:
        Formatted prompt section, or empty string if file doesn't exist
        or contains no signatures.
    """
    raw = read_file_safe(base_dir, impl_file, MAX_IMPL_FILE_CONTENT, "")
    if not raw:
        return ""

    lines = raw.splitlines()
    signatures: list[str] = []
    decorator_buffer: list[str] = []
    in_decorator = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("@"):
            in_decorator = True
            decorator_buffer.append(line)
        elif in_decorator and stripped.startswith(("def ", "async def ", "class ")):
            signatures.extend(decorator_buffer)
            signatures.append(line)
            decorator_buffer = []
            in_decorator = False
            if len(signatures) >= MAX_IMPL_SIGNATURES:
                break
        elif in_decorator:
            decorator_buffer.append(line)  # multi-line decorator args
        else:
            decorator_buffer = []
            in_decorator = False
            if stripped.startswith(("def ", "async def ", "class ")):
                signatures.append(line)
                if len(signatures) >= MAX_IMPL_SIGNATURES:
                    break

    if not signatures:
        return ""

    sig_block = escape_braces("\n".join(signatures))
    return (
        "\n## EXISTING API SIGNATURES\n"
        "The implementation file already exists. Your tests MUST use "
        "these exact function signatures. Do NOT assume different "
        "parameter names, types, or sync/async.\n"
        f"```python\n{sig_block}\n```\n"
    )
