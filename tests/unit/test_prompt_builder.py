"""Unit tests for PromptBuilder — REFACTOR stage and absolute path prompts."""

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
