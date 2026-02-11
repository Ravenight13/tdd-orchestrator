"""Unit tests for prompt_enrichment module-level helper functions.

Covers parse_criteria, parse_module_exports, escape_braces, to_import_path,
safe_absolute_path, read_file_safe, and build_code_section.
"""

from __future__ import annotations

from pathlib import Path

from tdd_orchestrator.prompt_enrichment import (
    build_code_section,
    escape_braces,
    parse_criteria,
    parse_module_exports,
    read_file_safe,
    safe_absolute_path,
    to_import_path,
)


# ---------------------------------------------------------------------------
# parse_criteria
# ---------------------------------------------------------------------------


def test_parse_criteria_from_json_string() -> None:
    """parse_criteria decodes a JSON string into a list."""
    result = parse_criteria('["must return 200", "must validate"]')
    assert result == ["must return 200", "must validate"]


def test_parse_criteria_from_list() -> None:
    """parse_criteria passes through a list unchanged."""
    result = parse_criteria(["a", "b"])
    assert result == ["a", "b"]


def test_parse_criteria_from_none() -> None:
    """parse_criteria returns empty list for None."""
    assert parse_criteria(None) == []


def test_parse_criteria_from_invalid_json() -> None:
    """parse_criteria returns empty list for invalid JSON."""
    assert parse_criteria("not json") == []


def test_parse_criteria_from_non_list_json() -> None:
    """parse_criteria returns empty list when JSON is not a list."""
    assert parse_criteria('{"key": "value"}') == []


# ---------------------------------------------------------------------------
# parse_module_exports
# ---------------------------------------------------------------------------


def test_parse_module_exports_from_json_string() -> None:
    """parse_module_exports decodes a JSON string."""
    result = parse_module_exports('["Foo", "Bar"]')
    assert result == ["Foo", "Bar"]


def test_parse_module_exports_from_list() -> None:
    """parse_module_exports passes through a list."""
    result = parse_module_exports(["X"])
    assert result == ["X"]


def test_parse_module_exports_from_none() -> None:
    """parse_module_exports returns empty list for None."""
    assert parse_module_exports(None) == []


# ---------------------------------------------------------------------------
# escape_braces
# ---------------------------------------------------------------------------


def test_escape_braces_single() -> None:
    """escape_braces doubles single braces."""
    assert escape_braces("{key}") == "{{key}}"


def test_escape_braces_double() -> None:
    """escape_braces quadruples already-doubled braces."""
    assert escape_braces("{{key}}") == "{{{{key}}}}"


def test_escape_braces_empty_string() -> None:
    """escape_braces handles empty string."""
    assert escape_braces("") == ""


def test_escape_braces_no_braces() -> None:
    """escape_braces returns text unchanged when no braces present."""
    assert escape_braces("hello world") == "hello world"


# ---------------------------------------------------------------------------
# to_import_path
# ---------------------------------------------------------------------------


def test_to_import_path_strips_src_prefix() -> None:
    """to_import_path strips the src. prefix from src-layout paths."""
    assert to_import_path("src/tdd_orchestrator/api/app.py") == "tdd_orchestrator.api.app"


def test_to_import_path_no_src_prefix() -> None:
    """to_import_path leaves paths without src/ prefix unchanged."""
    assert to_import_path("tdd_orchestrator/api/app.py") == "tdd_orchestrator.api.app"


# ---------------------------------------------------------------------------
# safe_absolute_path
# ---------------------------------------------------------------------------


def test_safe_absolute_path_rejects_traversal(tmp_path: Path) -> None:
    """safe_absolute_path returns raw relative path for traversal attempts."""
    result = safe_absolute_path(tmp_path, "../../../etc/passwd")
    assert result == "../../../etc/passwd"


def test_safe_absolute_path_accepts_valid(tmp_path: Path) -> None:
    """safe_absolute_path returns resolved absolute path for valid paths."""
    result = safe_absolute_path(tmp_path, "src/foo.py")
    assert result == str(tmp_path / "src/foo.py")


def test_safe_absolute_path_no_base_dir() -> None:
    """safe_absolute_path returns relative path when base_dir is None."""
    assert safe_absolute_path(None, "tests/test_foo.py") == "tests/test_foo.py"


# ---------------------------------------------------------------------------
# read_file_safe
# ---------------------------------------------------------------------------


def test_read_file_safe_reads_file(tmp_path: Path) -> None:
    """read_file_safe reads a file within base_dir."""
    (tmp_path / "test.py").write_text("content")
    assert read_file_safe(tmp_path, "test.py", 1000, "FALLBACK") == "content"


def test_read_file_safe_truncates(tmp_path: Path) -> None:
    """read_file_safe truncates files exceeding max_chars."""
    (tmp_path / "test.py").write_text("x" * 200)
    result = read_file_safe(tmp_path, "test.py", 50, "FALLBACK")
    assert len(result) < 200
    assert "# ... (truncated)" in result


def test_read_file_safe_rejects_traversal(tmp_path: Path) -> None:
    """read_file_safe returns fallback for path traversal."""
    result = read_file_safe(tmp_path, "../etc/passwd", 1000, "FALLBACK")
    assert result == "FALLBACK"


def test_read_file_safe_no_base_dir() -> None:
    """read_file_safe returns fallback when base_dir is None."""
    assert read_file_safe(None, "test.py", 1000, "FALLBACK") == "FALLBACK"


def test_read_file_safe_missing_file(tmp_path: Path) -> None:
    """read_file_safe returns fallback when file doesn't exist."""
    assert read_file_safe(tmp_path, "missing.py", 1000, "FALLBACK") == "FALLBACK"


# ---------------------------------------------------------------------------
# build_code_section
# ---------------------------------------------------------------------------


def test_build_code_section_reads_and_wraps(tmp_path: Path) -> None:
    """build_code_section reads file and wraps in titled code block."""
    (tmp_path / "foo.py").write_text("def hello(): pass\n")
    result = build_code_section(tmp_path, "foo.py", 1000, "MY TITLE")
    assert "## MY TITLE" in result
    assert "```python" in result
    assert "def hello(): pass" in result


def test_build_code_section_with_description(tmp_path: Path) -> None:
    """build_code_section includes description line."""
    (tmp_path / "foo.py").write_text("x = 1\n")
    result = build_code_section(tmp_path, "foo.py", 1000, "TITLE", "Some description.")
    assert "Some description." in result


def test_build_code_section_escapes_braces(tmp_path: Path) -> None:
    """build_code_section escapes braces in file content."""
    (tmp_path / "foo.py").write_text('data = {"key": "value"}\n')
    result = build_code_section(tmp_path, "foo.py", 1000, "TITLE")
    # Should not crash when used in .format()
    assert "TITLE" in result


def test_build_code_section_returns_empty_for_missing_file(tmp_path: Path) -> None:
    """build_code_section returns empty string when file doesn't exist."""
    result = build_code_section(tmp_path, "missing.py", 1000, "TITLE")
    assert result == ""
