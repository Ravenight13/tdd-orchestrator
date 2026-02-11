"""Unit tests for Prompt Builder Hardening Round 3.

Tests for bug fixes and enrichment consistency added during the hardening
round: format injection safety, sibling hint loop fix, path traversal
defense, empty goal handling, FIX conftest, RED_FIX enrichments,
GREEN_RETRY enrichments, and REFACTOR enrichments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tdd_orchestrator.models import Stage
from tdd_orchestrator.prompt_builder import PromptBuilder


def _setup_rich_sibling(tmp_path: Path) -> dict[str, Any]:
    """Helper: create a task with a sibling that has status codes, response assertions, imports."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_current.py").write_text("def test_current():\n    assert True\n")
    (test_dir / "test_sibling.py").write_text(
        "from tdd_orchestrator.api.app import create_app\n"
        "import pytest\n\n"
        "async def test_create():\n"
        "    response = await client.post('/items')\n"
        "    assert response.status_code == 400\n"
        "    assert response.json()['detail'] == 'invalid'\n"
    )
    return {
        "task_key": "TDD-2",
        "title": "Test Task",
        "goal": "Test goal",
        "test_file": "tests/test_current.py",
        "impl_file": "src/foo.py",
    }


# ---------------------------------------------------------------------------
# Phase 2a: FIX stage conftest (#2)
# ---------------------------------------------------------------------------

_FIX_ISSUES = [
    {"tool": "mypy", "output": "error: Missing type annotation"},
]


def test_fix_prompt_includes_conftest_when_present(tmp_path: Path) -> None:
    """fix() includes conftest.py when present in test directory."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text(
        "@pytest.fixture\ndef client():\n    return TestClient()\n"
    )

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "Fix it",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "SHARED FIXTURES (conftest.py)" in result
    assert "def client():" in result


def test_fix_prompt_omits_conftest_when_absent(tmp_path: Path) -> None:
    """fix() omits conftest section when no conftest.py exists."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "Fix it",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "SHARED FIXTURES" not in result


# ---------------------------------------------------------------------------
# Phase 2b: RED_FIX base_dir + enrichments (#3)
# ---------------------------------------------------------------------------


def test_red_fix_includes_conftest(tmp_path: Path) -> None:
    """red_fix() includes conftest when base_dir provided."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text("@pytest.fixture\ndef db(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "Fix tests",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    issues = [{"severity": "error", "line_number": 5, "message": "bad",
               "code_snippet": "x"}]
    result = PromptBuilder.red_fix(task, issues, base_dir=tmp_path)
    assert "SHARED FIXTURES" in result


def test_red_fix_includes_sibling_tests(tmp_path: Path) -> None:
    """red_fix() includes sibling tests when base_dir provided."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "test_bar.py").write_text("import os\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "Fix tests",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    issues = [{"severity": "error", "line_number": 5, "message": "bad",
               "code_snippet": "x"}]
    result = PromptBuilder.red_fix(task, issues, base_dir=tmp_path)
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


def test_build_passes_base_dir_to_red_fix(tmp_path: Path) -> None:
    """build(RED_FIX) forwards base_dir to red_fix()."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text("@pytest.fixture\ndef db(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "Fix tests",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    issues = [{"severity": "error", "line_number": 5, "message": "bad",
               "code_snippet": "x"}]
    result = PromptBuilder.build(Stage.RED_FIX, task, issues=issues, base_dir=tmp_path)
    assert "SHARED FIXTURES" in result


# ---------------------------------------------------------------------------
# Phase 2c: GREEN_RETRY module_exports + impl_content (#5)
# ---------------------------------------------------------------------------


def test_green_retry_includes_module_exports(tmp_path: Path) -> None:
    """build_green_retry() includes module exports when present."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
        "module_exports": '["Foo", "Bar"]',
    }
    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "REQUIRED MODULE EXPORTS" in result
    assert "Foo" in result
    assert "Bar" in result


def test_green_retry_includes_existing_impl(tmp_path: Path) -> None:
    """build_green_retry() includes existing impl when file exists."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.py").write_text("class Foo:\n    pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "EXISTING IMPLEMENTATION" in result
    assert "class Foo:" in result


def test_green_retry_omits_module_exports_when_absent(tmp_path: Path) -> None:
    """build_green_retry() omits exports section when no exports."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "REQUIRED MODULE EXPORTS" not in result


# ---------------------------------------------------------------------------
# Phase 3a: REFACTOR enrichments (#7) — test_content, criteria, module_exports
# ---------------------------------------------------------------------------


def test_refactor_includes_test_content(tmp_path: Path) -> None:
    """refactor() includes test content when test file exists."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_add():\n    assert add(1, 2) == 3\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "Refactor", "goal": "Clean up",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.refactor(task, ["cleanup"], base_dir=tmp_path)
    assert "TEST CONTRACT" in result
    assert "def test_add():" in result


def test_refactor_includes_acceptance_criteria(tmp_path: Path) -> None:
    """refactor() includes acceptance criteria when present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "Refactor", "goal": "Clean up",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
        "acceptance_criteria": '["must keep API stable", "must pass tests"]',
    }
    result = PromptBuilder.refactor(task, ["cleanup"], base_dir=tmp_path)
    assert "ACCEPTANCE CRITERIA" in result
    assert "must keep API stable" in result


def test_refactor_includes_module_exports(tmp_path: Path) -> None:
    """refactor() includes module exports when present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "Refactor", "goal": "Clean up",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
        "module_exports": '["FooService", "create_foo"]',
    }
    result = PromptBuilder.refactor(task, ["cleanup"], base_dir=tmp_path)
    assert "MODULE EXPORTS" in result
    assert "FooService" in result


def test_refactor_omits_optional_sections_when_absent(tmp_path: Path) -> None:
    """refactor() omits test_content, criteria, exports when data absent."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "Refactor", "goal": "Clean up",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.refactor(task, ["cleanup"], base_dir=tmp_path)
    assert "ACCEPTANCE CRITERIA" not in result
    assert "MODULE EXPORTS" not in result
    assert "TEST CONTRACT" not in result


# ---------------------------------------------------------------------------
# Phase 1a: str.format() injection (#1) — braces in task values
# ---------------------------------------------------------------------------


def test_red_prompt_survives_braces_in_goal() -> None:
    """red() doesn't crash when goal contains curly braces."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T",
        "goal": "handle {dangerous} input",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task)
    assert "dangerous" in result
    assert "handle" in result


def test_green_prompt_survives_braces_in_test_output(tmp_path: Path) -> None:
    """green() doesn't crash when test_output contains curly braces."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.green(task, 'assert result == {"x": 1}', base_dir=tmp_path)
    assert "x" in result


def test_verify_prompt_survives_braces_in_title() -> None:
    """verify() doesn't crash when title contains curly braces."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "title": "handle {item} processing",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.verify(task)
    assert "item" in result
    assert "processing" in result


def test_fix_prompt_survives_braces_in_issues() -> None:
    """fix() doesn't crash when issues contain curly braces."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    issues = [{"tool": "mypy", "output": "dict[str, {T}] is invalid"}]
    result = PromptBuilder.fix(task, issues)
    assert "MYPY" in result
    assert "invalid" in result


def test_sibling_with_braces_doesnt_crash_format(tmp_path: Path) -> None:
    """Sibling file with {braces} in content doesn't crash .format()."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_current.py").write_text("def test_x(): pass\n")
    (test_dir / "test_sib.py").write_text(
        'assert response.json() == {"key": "val"}\n'
    )

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_current.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SIBLING TESTS" in result


def test_red_fix_survives_braces_in_goal() -> None:
    """red_fix() doesn't crash when goal contains curly braces."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "handle {items} in request",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    issues = [{"severity": "error", "line_number": 5, "message": "missing assert",
               "code_snippet": "result = foo()"}]
    result = PromptBuilder.red_fix(task, issues)
    assert "items" in result
    assert "TASK GOAL" in result


# ---------------------------------------------------------------------------
# Phase 1b: Sibling hint outer loop (#4)
# ---------------------------------------------------------------------------


def test_sibling_hints_outer_loop_stops_at_max(tmp_path: Path) -> None:
    """With status+response+await lines totaling 15, hints are capped at 10."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_current.py").write_text("def test_x(): pass\n")

    lines: list[str] = []
    for i in range(5):
        lines.append(f"    assert response.status_code == {400 + i}")
    for i in range(5):
        lines.append(f"    assert response.json()['key_{i}'] == 'val'")
    for i in range(5):
        lines.append(f"    result = await func_{i}()")
    (test_dir / "test_sib.py").write_text("\n".join(lines) + "\n")

    from tdd_orchestrator.prompt_enrichment import discover_sibling_tests

    section = discover_sibling_tests(tmp_path, "tests/test_current.py", "green")
    hint_lines = [ln for ln in section.splitlines() if ln.startswith("    ")]
    assert len(hint_lines) == 10


# ---------------------------------------------------------------------------
# Phase 1c: Path traversal in prompt abs paths (#6)
# ---------------------------------------------------------------------------


def test_red_prompt_abs_path_rejects_traversal(tmp_path: Path) -> None:
    """RED prompt with traversal test_file doesn't produce path outside base_dir."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "Test goal",
        "test_file": "../../../etc/passwd",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "/etc/passwd" not in result or "../../../etc/passwd" in result


# ---------------------------------------------------------------------------
# Phase 1d: Empty / whitespace goal (#11)
# ---------------------------------------------------------------------------


def test_red_prompt_handles_whitespace_only_goal() -> None:
    """red() doesn't crash when goal is whitespace only."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T",
        "goal": "   ",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task)
    assert "function" in result


def test_red_prompt_handles_empty_goal() -> None:
    """red() doesn't crash when goal is empty string."""
    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T",
        "goal": "",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task)
    assert "function" in result
