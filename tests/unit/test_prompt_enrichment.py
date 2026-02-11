"""Unit tests for PromptBuilder — pipeline context enrichment (Phases 1-3).

Covers richer sibling extraction, conftest.py visibility, RED_FIX enrichment,
REFACTOR enrichment, FIX full enrichment, and path traversal safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tdd_orchestrator.models import Stage
from tdd_orchestrator.prompt_builder import PromptBuilder


# ---------------------------------------------------------------------------
# Phase 1: Richer sibling extraction (behavioral contracts)
# ---------------------------------------------------------------------------


def _setup_rich_sibling(tmp_path: Path) -> dict[str, Any]:
    """Helper: create a task with a sibling that has status codes, response assertions, imports."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    # Current task's test file
    (test_dir / "test_current.py").write_text("def test_current():\n    assert True\n")
    # Rich sibling with multiple pattern types
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


def test_red_sibling_extracts_status_codes(tmp_path: Path) -> None:
    """Sibling with status_code == 400 appears in behavioral contract hints."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "status_code == 400" in result


def test_red_sibling_extracts_response_assertions(tmp_path: Path) -> None:
    """Sibling with assert response.json() appears in hints."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "response.json()" in result


def test_red_sibling_extracts_imports(tmp_path: Path) -> None:
    """Sibling import lines appear in hints."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "from tdd_orchestrator.api.app import create_app" in result


def test_sibling_hint_label_says_behavioral_contracts(tmp_path: Path) -> None:
    """Hint label uses 'behavioral contracts' instead of 'async contracts'."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "behavioral contracts" in result


def test_sibling_hints_respect_max_lines(tmp_path: Path) -> None:
    """Even with many patterns, hints stay within MAX_SIBLING_HINT_LINES limit."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_current.py").write_text("def test_x():\n    pass\n")
    # Sibling with 20+ hint-worthy lines
    lines = ["import mod_%d" % i for i in range(15)]
    lines += ["    assert response.status_code == %d" % (400 + i) for i in range(5)]
    (test_dir / "test_big.py").write_text("\n".join(lines) + "\n")

    section = PromptBuilder._discover_sibling_tests(tmp_path, "tests/test_current.py", "red")
    # Count indented hint lines (4-space prefix)
    hint_lines = [l for l in section.splitlines() if l.startswith("    ")]
    assert len(hint_lines) <= 10


# ---------------------------------------------------------------------------
# Phase 2a: conftest.py visibility in GREEN stage
# ---------------------------------------------------------------------------


def test_green_prompt_includes_conftest_when_present(tmp_path: Path) -> None:
    """green() includes conftest.py content when present in test directory."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text(
        "@pytest.fixture\ndef client(app):\n    return app.test_client()\n"
    )

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SHARED FIXTURES (conftest.py)" in result
    assert "def client(app):" in result


def test_green_prompt_finds_parent_conftest(tmp_path: Path) -> None:
    """green() finds conftest.py one level up from test directory."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (tmp_path / "conftest.py").write_text(
        "@pytest.fixture\ndef db():\n    return InMemoryDB()\n"
    )

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SHARED FIXTURES (conftest.py)" in result
    assert "def db():" in result


def test_green_prompt_omits_conftest_when_absent(tmp_path: Path) -> None:
    """green() omits conftest section when no conftest.py exists."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "SHARED FIXTURES" not in result


def test_green_retry_includes_conftest(tmp_path: Path) -> None:
    """build_green_retry() also gets conftest content."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text("@pytest.fixture\ndef session(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.build_green_retry(
        task, "test output", attempt=2, previous_failure="error",
        base_dir=tmp_path,
    )
    assert "SHARED FIXTURES (conftest.py)" in result
    assert "def session():" in result


# ---------------------------------------------------------------------------
# Phase 2b: RED_FIX context enrichment
# ---------------------------------------------------------------------------

_RED_FIX_ISSUES = [
    {
        "severity": "error",
        "line_number": 10,
        "message": "missing assertion",
        "code_snippet": "result = foo()",
    },
]


def test_red_fix_includes_goal() -> None:
    """red_fix() includes the task goal in the prompt."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Validate user registration",
        "test_file": "tests/test_reg.py",
        "impl_file": "src/reg.py",
    }
    result = PromptBuilder.red_fix(task, _RED_FIX_ISSUES)
    assert "Validate user registration" in result


def test_red_fix_includes_acceptance_criteria() -> None:
    """red_fix() includes acceptance criteria when present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Register users",
        "test_file": "tests/test_reg.py",
        "impl_file": "src/reg.py",
        "acceptance_criteria": '["must return 201 on success", "must validate email"]',
    }
    result = PromptBuilder.red_fix(task, _RED_FIX_ISSUES)
    assert "ACCEPTANCE CRITERIA" in result
    assert "must return 201 on success" in result


def test_red_fix_omits_criteria_when_none() -> None:
    """red_fix() omits criteria section when no criteria present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Register users",
        "test_file": "tests/test_reg.py",
        "impl_file": "src/reg.py",
    }
    result = PromptBuilder.red_fix(task, _RED_FIX_ISSUES)
    assert "ACCEPTANCE CRITERIA" not in result


def test_red_fix_includes_import_hint() -> None:
    """red_fix() includes the correct import path."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Register users",
        "test_file": "tests/test_reg.py",
        "impl_file": "src/tdd_orchestrator/api/registration.py",
    }
    result = PromptBuilder.red_fix(task, _RED_FIX_ISSUES)
    assert "tdd_orchestrator.api.registration" in result


# ---------------------------------------------------------------------------
# Phase 2c: REFACTOR context enrichment
# ---------------------------------------------------------------------------


def test_refactor_prompt_includes_impl_content(tmp_path: Path) -> None:
    """refactor() includes current impl file content when present."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.py").write_text("class Foo:\n    def bar(self) -> str:\n        return 'baz'\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "title": "Refactor Foo",
        "goal": "Improve Foo",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.refactor(task, ["File too long"], base_dir=tmp_path)
    assert "CURRENT IMPLEMENTATION" in result
    assert "class Foo:" in result


def test_refactor_prompt_omits_impl_when_missing(tmp_path: Path) -> None:
    """refactor() omits impl section when file doesn't exist."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "title": "Refactor Foo",
        "goal": "Improve Foo",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.refactor(task, ["File too long"], base_dir=tmp_path)
    assert "CURRENT IMPLEMENTATION" not in result


def test_refactor_prompt_includes_sibling_tests(tmp_path: Path) -> None:
    """refactor() includes sibling tests section when siblings exist."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "test_bar.py").write_text("async def test_y():\n    await func()\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "title": "Refactor Foo",
        "goal": "Improve Foo",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.refactor(task, ["cleanup"], base_dir=tmp_path)
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


def test_build_passes_base_dir_to_refactor(tmp_path: Path) -> None:
    """build(REFACTOR) forwards base_dir to refactor()."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.py").write_text("def hello() -> None: pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "title": "Refactor",
        "goal": "Improve",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.build(
        Stage.REFACTOR, task, refactor_reasons=["cleanup"], base_dir=tmp_path,
    )
    assert "CURRENT IMPLEMENTATION" in result
    assert "def hello()" in result


# ---------------------------------------------------------------------------
# Phase 3: FIX stage full enrichment (Gaps 2+4)
# ---------------------------------------------------------------------------

_FIX_ISSUES = [
    {"tool": "mypy", "output": "error: Missing type annotation"},
]


def test_fix_prompt_includes_test_content(tmp_path: Path) -> None:
    """fix() includes test file content in prompt."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_add():\n    assert add(1, 2) == 3\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Add function",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "TEST CONTRACT" in result
    assert "def test_add():" in result


def test_fix_prompt_includes_impl_content(tmp_path: Path) -> None:
    """fix() includes impl file content in prompt."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Add function",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "CURRENT IMPLEMENTATION" in result
    assert "def add(a: int, b: int)" in result


def test_fix_prompt_includes_acceptance_criteria(tmp_path: Path) -> None:
    """fix() includes acceptance criteria when present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Add function",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
        "acceptance_criteria": '["must return int", "must handle negatives"]',
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "ACCEPTANCE CRITERIA" in result
    assert "must return int" in result


def test_fix_prompt_includes_module_exports(tmp_path: Path) -> None:
    """fix() includes module exports when present."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Add function",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
        "module_exports": '["add", "subtract"]',
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "MODULE EXPORTS" in result
    assert "add" in result


def test_fix_prompt_includes_sibling_tests(tmp_path: Path) -> None:
    """fix() includes sibling tests section."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "test_bar.py").write_text("async def test_y():\n    await func()\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Add function",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES, base_dir=tmp_path)
    assert "SIBLING TESTS" in result
    assert "test_bar.py" in result


def test_fix_prompt_omits_optional_sections_when_absent() -> None:
    """fix() gracefully omits optional sections when data absent."""
    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Fix it",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.fix(task, _FIX_ISSUES)
    assert "ACCEPTANCE CRITERIA" not in result
    assert "MODULE EXPORTS" not in result
    assert "SIBLING TESTS" not in result


def test_build_passes_base_dir_to_fix(tmp_path: Path) -> None:
    """build(FIX) forwards base_dir to fix()."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.py").write_text("def hello() -> None: pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1",
        "goal": "Fix it",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
    }
    result = PromptBuilder.build(
        Stage.FIX, task, issues=_FIX_ISSUES, base_dir=tmp_path,
    )
    assert "CURRENT IMPLEMENTATION" in result
    assert "def hello()" in result


# ---------------------------------------------------------------------------
# Security: path traversal safety
# ---------------------------------------------------------------------------


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


def test_read_conftest_rejects_path_traversal(tmp_path: Path) -> None:
    """_read_conftest rejects conftest.py that escapes base_dir via parent.parent."""
    (tmp_path / "conftest.py").write_text("SENSITIVE_FIXTURE = True\n")

    base_dir = tmp_path / "project"
    base_dir.mkdir()

    result = PromptBuilder._read_conftest(base_dir, "test_foo.py")
    assert result == ""


# ---------------------------------------------------------------------------
# Sibling header text
# ---------------------------------------------------------------------------


def test_red_sibling_header_mentions_status_codes(tmp_path: Path) -> None:
    """RED sibling header includes guidance about status codes."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "status code" in result.lower()


def test_green_sibling_header_mentions_status_codes(tmp_path: Path) -> None:
    """GREEN sibling header includes guidance about preserving status codes."""
    task = _setup_rich_sibling(tmp_path)
    result = PromptBuilder.green(task, "ImportError", base_dir=tmp_path)
    assert "Status codes" in result or "status code" in result


# ---------------------------------------------------------------------------
# Fix 1: _discover_sibling_tests guards .relative_to() ValueError
# ---------------------------------------------------------------------------


def test_discover_sibling_tests_skips_escaped_paths(tmp_path: Path) -> None:
    """Siblings that raise ValueError on .relative_to() are silently skipped."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_current.py").write_text("def test_x(): pass\n")
    (test_dir / "test_good.py").write_text("import os\n")
    (test_dir / "test_bad.py").write_text("import sys\n")

    original_relative_to = Path.relative_to

    def patched_relative_to(self: Path, other: Path) -> Path:  # type: ignore[override]
        if self.name == "test_bad.py":
            raise ValueError("escaped")
        return original_relative_to(self, other)

    import unittest.mock
    with unittest.mock.patch.object(Path, "relative_to", patched_relative_to):
        section = PromptBuilder._discover_sibling_tests(
            tmp_path, "tests/test_current.py", "green",
        )

    assert "test_good.py" in section
    assert "test_bad.py" not in section


# ---------------------------------------------------------------------------
# Fix 2: _read_conftest catches OSError
# ---------------------------------------------------------------------------


def test_read_conftest_handles_broken_symlink(tmp_path: Path) -> None:
    """_read_conftest returns '' when .resolve() raises OSError."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    broken_link = test_dir / "conftest.py"
    broken_link.symlink_to(tmp_path / "nonexistent_target")

    result = PromptBuilder._read_conftest(tmp_path, "tests/test_foo.py")
    assert result == ""


def test_read_file_safe_handles_broken_symlink(tmp_path: Path) -> None:
    """_read_file_safe returns fallback when .resolve() raises OSError."""
    broken_link = tmp_path / "broken.py"
    broken_link.symlink_to(tmp_path / "nonexistent_target")

    result = PromptBuilder._read_file_safe(tmp_path, "broken.py", 1000, "FALLBACK")
    assert result == "FALLBACK"


# ---------------------------------------------------------------------------
# Fix 3: RED conftest + truncation
# ---------------------------------------------------------------------------


def test_red_prompt_includes_conftest_when_present(tmp_path: Path) -> None:
    """red() includes conftest.py content when present."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")
    (test_dir / "conftest.py").write_text(
        "@pytest.fixture\ndef client(app):\n    return app.test_client()\n"
    )

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "SHARED FIXTURES" in result


def test_red_prompt_omits_conftest_when_absent(tmp_path: Path) -> None:
    """red() omits conftest section when no conftest.py exists."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_foo.py").write_text("def test_x(): pass\n")

    task: dict[str, Any] = {
        "task_key": "TDD-1", "title": "T", "goal": "G",
        "test_file": "tests/test_foo.py", "impl_file": "src/foo.py",
    }
    result = PromptBuilder.red(task, base_dir=tmp_path)
    assert "SHARED FIXTURES" not in result


def test_read_conftest_truncates_large_content(tmp_path: Path) -> None:
    """_read_conftest truncates content exceeding MAX_CONFTEST_CONTENT."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "conftest.py").write_text("x" * 5000)

    result = PromptBuilder._read_conftest(tmp_path, "tests/test_foo.py")
    assert "# ... (truncated)" in result


def test_extract_impl_signatures_rejects_path_traversal(tmp_path: Path) -> None:
    """_extract_impl_signatures returns '' for paths that escape base_dir."""
    result = PromptBuilder._extract_impl_signatures(tmp_path, "../etc/passwd")
    assert result == ""
