"""Unit tests for PromptBuilder — REFACTOR stage, absolute paths, and contract visibility."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tdd_orchestrator.models import Stage
from tdd_orchestrator.prompt_builder import PromptBuilder


@pytest.fixture()
def task() -> dict[str, Any]:
    return {
        "task_key": "TDD-1",
        "title": "Test Task",
        "goal": "Test goal",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }


def test_refactor_prompt_includes_reasons(task: dict[str, Any]) -> None:
    """refactor() embeds each reason string in the output."""
    result = PromptBuilder.refactor(task, ["File too long"])
    assert "File too long" in result


def test_refactor_prompt_includes_impl_file(task: dict[str, Any]) -> None:
    """refactor() embeds the implementation file path."""
    result = PromptBuilder.refactor(task, ["cleanup"])
    assert task["impl_file"] in result


def test_refactor_prompt_includes_test_file(task: dict[str, Any]) -> None:
    """refactor() embeds the test file path."""
    result = PromptBuilder.refactor(task, ["cleanup"])
    assert task["test_file"] in result


def test_build_dispatches_refactor(task: dict[str, Any]) -> None:
    """build() dispatches Stage.REFACTOR and passes refactor_reasons through."""
    result = PromptBuilder.build(Stage.REFACTOR, task, refactor_reasons=["reason"])
    assert "reason" in result


def test_build_refactor_missing_reasons_raises(task: dict[str, Any]) -> None:
    """build(Stage.REFACTOR) without refactor_reasons raises ValueError."""
    with pytest.raises(ValueError, match="refactor_reasons"):
        PromptBuilder.build(Stage.REFACTOR, task)


# ---------------------------------------------------------------------------
# RED / GREEN absolute path tests
# ---------------------------------------------------------------------------

_BASE_DIR = Path("/Users/dev/Projects/tdd_orchestrator")


def test_red_prompt_includes_absolute_path_when_base_dir_provided(task: dict[str, Any]) -> None:
    """red() with base_dir embeds the absolute test file path."""
    result = PromptBuilder.red(task, base_dir=_BASE_DIR)
    expected = str(_BASE_DIR / task["test_file"])
    assert expected in result


def test_red_prompt_falls_back_to_relative_when_no_base_dir(task: dict[str, Any]) -> None:
    """red() without base_dir uses the relative test file path."""
    result = PromptBuilder.red(task)
    # The relative path should appear but not as an absolute path
    assert task["test_file"] in result
    assert str(_BASE_DIR) not in result


def test_green_prompt_includes_absolute_path_when_base_dir_provided(
    task: dict[str, Any],
) -> None:
    """green() with base_dir embeds the absolute impl file path."""
    result = PromptBuilder.green(task, "test output", base_dir=_BASE_DIR)
    expected = str(_BASE_DIR / task["impl_file"])
    assert expected in result


def test_green_prompt_falls_back_to_relative_when_no_base_dir(task: dict[str, Any]) -> None:
    """green() without base_dir uses the relative impl file path."""
    result = PromptBuilder.green(task, "test output")
    assert task["impl_file"] in result
    assert str(_BASE_DIR) not in result


def test_build_passes_base_dir_to_red(task: dict[str, Any]) -> None:
    """build(RED) forwards base_dir to red()."""
    result = PromptBuilder.build(Stage.RED, task, base_dir=_BASE_DIR)
    expected = str(_BASE_DIR / task["test_file"])
    assert expected in result


def test_build_passes_base_dir_to_green(task: dict[str, Any]) -> None:
    """build(GREEN) forwards base_dir to green()."""
    result = PromptBuilder.build(Stage.GREEN, task, test_output="failures", base_dir=_BASE_DIR)
    expected = str(_BASE_DIR / task["impl_file"])
    assert expected in result


# ---------------------------------------------------------------------------
# _to_import_path regression tests
# ---------------------------------------------------------------------------


def test_to_import_path_strips_src_prefix() -> None:
    """_to_import_path strips the src. prefix from src-layout paths."""
    assert (
        PromptBuilder._to_import_path("src/tdd_orchestrator/api/app.py")
        == "tdd_orchestrator.api.app"
    )


def test_to_import_path_no_src_prefix() -> None:
    """_to_import_path leaves paths without src/ prefix unchanged."""
    assert (
        PromptBuilder._to_import_path("tdd_orchestrator/api/app.py")
        == "tdd_orchestrator.api.app"
    )


# ---------------------------------------------------------------------------
# GREEN contract visibility tests
# ---------------------------------------------------------------------------


def test_green_prompt_includes_test_file_content(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() with base_dir reads test file content into the prompt."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_add():\n    assert add(1, 2) == 3\n")

    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "def test_add():" in result
    assert "assert add(1, 2) == 3" in result


def test_green_prompt_fallback_when_test_file_missing(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() shows fallback text when the test file doesn't exist on disk."""
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "test file not available" in result


def test_green_prompt_truncates_large_test_files(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() truncates test files exceeding MAX_TEST_FILE_CONTENT."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("x" * 10000)

    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "# ... (truncated)" in result


def test_green_prompt_escapes_braces_in_test_content(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() doesn't crash when test file contains curly braces."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text('data = {"key": "value"}\nassert data["key"] == "value"\n')

    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    # Content should be present (braces rendered back by .format())
    assert '"key": "value"' in result


def test_green_prompt_includes_acceptance_criteria(
    task: dict[str, Any],
) -> None:
    """green() includes acceptance criteria section when task has criteria."""
    task["acceptance_criteria"] = '["must serialize to JSON", "must handle None"]'
    result = PromptBuilder.green(task, "ImportError")
    assert "ACCEPTANCE CRITERIA" in result
    assert "must serialize to JSON" in result
    assert "must handle None" in result


def test_green_prompt_omits_hints_when_none(
    task: dict[str, Any],
) -> None:
    """green() omits IMPLEMENTATION HINTS section when hints are None."""
    task["implementation_hints"] = None
    result = PromptBuilder.green(task, "ImportError")
    assert "IMPLEMENTATION HINTS" not in result


def test_green_prompt_includes_existing_impl(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() includes existing implementation section when impl file exists."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    impl_file = src_dir / "foo.py"
    impl_file.write_text("class Foo:\n    pass\n")

    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "EXISTING IMPLEMENTATION (from prior task)" in result
    assert "class Foo:" in result


def test_green_prompt_no_existing_impl_when_absent(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() omits existing impl section when impl file doesn't exist."""
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "EXISTING IMPLEMENTATION" not in result


def test_green_retry_includes_test_file_content(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """build_green_retry() includes test file content when base_dir provided."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_subtract():\n    assert subtract(5, 3) == 2\n")

    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="AssertionError",
        base_dir=tmp_path,
    )
    assert "def test_subtract():" in result
    assert "Test File Content (the contract)" in result


def test_build_dispatcher_forwards_base_dir_to_retry(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """build(GREEN, attempt=2) forwards base_dir to build_green_retry()."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_multiply():\n    assert multiply(2, 3) == 6\n")

    result = PromptBuilder.build(
        Stage.GREEN, task,
        test_output="failures", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "def test_multiply():" in result


def test_red_prompt_includes_name_adherence_requirement(
    task: dict[str, Any],
) -> None:
    """red() prompt includes the name adherence requirement (rule #7)."""
    result = PromptBuilder.red(task)
    assert "Method and property names MUST match the acceptance criteria exactly" in result
    assert "Do NOT invent alternative names" in result


# ---------------------------------------------------------------------------
# Sibling test discovery in GREEN prompt
# ---------------------------------------------------------------------------


def _setup_sibling_tests(tmp_path: Path) -> dict[str, Any]:
    """Helper: create a task with a test file and a sibling test file."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    # Current task's test file
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert True\n")
    # Sibling test file with await patterns
    sibling = test_dir / "test_bar.py"
    sibling.write_text(
        "import pytest\n\nasync def test_bar():\n"
        "    result = await some_func()\n"
        "    assert result is not None\n"
    )
    return {
        "task_key": "TDD-1",
        "title": "Test Task",
        "goal": "Test goal",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }


def test_green_prompt_includes_sibling_tests_section(tmp_path: Path) -> None:
    """green() includes SIBLING TESTS section when siblings exist."""
    task = _setup_sibling_tests(tmp_path)
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


def test_green_prompt_omits_sibling_section_when_no_siblings(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """green() omits sibling section when no sibling test files exist."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert True\n")

    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SIBLING TESTS" not in result


def test_green_prompt_sibling_section_includes_await_hints(tmp_path: Path) -> None:
    """green() sibling section extracts await patterns as contract hints."""
    task = _setup_sibling_tests(tmp_path)
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "await some_func()" in result
    assert "async contracts" in result


def test_green_retry_includes_sibling_tests_section(tmp_path: Path) -> None:
    """build_green_retry() includes SIBLING TESTS section when siblings exist."""
    task = _setup_sibling_tests(tmp_path)
    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


# ---------------------------------------------------------------------------
# RED stage sibling awareness and impl signature tests
# ---------------------------------------------------------------------------


def test_red_prompt_includes_sibling_tests_section(tmp_path: Path) -> None:
    """red() includes SIBLING TESTS section when siblings exist."""
    task = _setup_sibling_tests(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


def test_red_prompt_omits_sibling_section_when_no_siblings(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """red() omits sibling section when no sibling test files exist."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert True\n")

    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "SIBLING TESTS" not in result


def test_red_prompt_sibling_uses_match_language(tmp_path: Path) -> None:
    """red() sibling section uses MATCH language, not DO NOT BREAK."""
    task = _setup_sibling_tests(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "MATCH EXISTING CONTRACTS" in result
    assert "DO NOT BREAK" not in result


def test_red_prompt_includes_existing_api_signatures(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """red() includes API signatures when impl file exists."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    impl_file = src_dir / "foo.py"
    impl_file.write_text(
        "def init_dependencies(db: object, broadcaster: object) -> None:\n"
        "    pass\n\n"
        "class FooService:\n"
        "    pass\n"
    )

    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "EXISTING API SIGNATURES" in result
    assert "def init_dependencies(db: object, broadcaster: object) -> None:" in result
    assert "class FooService:" in result


def test_red_prompt_omits_api_signatures_when_no_impl_file(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """red() omits API signatures section when impl file doesn't exist."""
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "EXISTING API SIGNATURES" not in result


def test_red_prompt_api_signatures_escapes_braces(
    task: dict[str, Any], tmp_path: Path,
) -> None:
    """red() doesn't crash when impl file has type hints with braces."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    impl_file = src_dir / "foo.py"
    impl_file.write_text(
        "def get_config() -> dict[str, Any]:\n"
        "    return {}\n"
    )

    # Should not raise KeyError from .format()
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "EXISTING API SIGNATURES" in result
    assert "dict[str, Any]" in result


def test_extract_impl_signatures_captures_async_def(tmp_path: Path) -> None:
    """_extract_impl_signatures() captures async def distinctly from def."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    impl_file = src_dir / "foo.py"
    impl_file.write_text(
        "def sync_func() -> None:\n"
        "    pass\n\n"
        "async def async_func() -> str:\n"
        "    return 'ok'\n"
    )

    result = PromptBuilder._extract_impl_signatures(tmp_path, "src/foo.py")
    assert "def sync_func() -> None:" in result
    assert "async def async_func() -> str:" in result


def test_read_file_safe_rejects_path_traversal(tmp_path: Path) -> None:
    """_read_file_safe rejects paths that escape base_dir."""
    sensitive_dir = tmp_path / "sensitive"
    sensitive_dir.mkdir()
    secret = sensitive_dir / "secret.txt"
    secret.write_text("SECRET_DATA")

    base_dir = tmp_path / "project"
    base_dir.mkdir()

    result = PromptBuilder._read_file_safe(
        base_dir, "../sensitive/secret.txt", 1000, "FALLBACK",
    )
    assert result == "FALLBACK"
