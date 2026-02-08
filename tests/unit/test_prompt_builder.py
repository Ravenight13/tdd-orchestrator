"""Unit tests for PromptBuilder — REFACTOR stage prompts."""

from __future__ import annotations

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
