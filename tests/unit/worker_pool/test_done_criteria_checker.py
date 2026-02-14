"""Unit tests for done_criteria_checker (parsing and evaluation)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.worker_pool.done_criteria_checker import (
    CriterionResult,
    DoneCriteriaResult,
    evaluate_criteria,
    parse_criteria,
)


# ---------------------------------------------------------------------------
# parse_criteria tests
# ---------------------------------------------------------------------------


class TestParseCriteria:
    """Parsing raw done_criteria strings into individual criteria."""

    def test_single_criterion(self) -> None:
        assert parse_criteria("All tests pass") == ["All tests pass"]

    def test_semicolon_separated(self) -> None:
        result = parse_criteria("Tests pass; module importable")
        assert result == ["Tests pass", "module importable"]

    def test_newline_separated(self) -> None:
        result = parse_criteria("Tests pass\nModule importable")
        assert result == ["Tests pass", "Module importable"]

    def test_comma_and_conjunction(self) -> None:
        result = parse_criteria("Tests pass, and module importable")
        assert result == ["Tests pass", "module importable"]

    def test_empty_string(self) -> None:
        assert parse_criteria("") == []

    def test_whitespace_only(self) -> None:
        assert parse_criteria("   ") == []

    def test_strips_whitespace_from_items(self) -> None:
        result = parse_criteria("  Tests pass ;  module importable  ")
        assert result == ["Tests pass", "module importable"]

    def test_filters_empty_items(self) -> None:
        result = parse_criteria("Tests pass;;module importable")
        assert result == ["Tests pass", "module importable"]


# ---------------------------------------------------------------------------
# evaluate_criteria tests
# ---------------------------------------------------------------------------


class TestEvaluateCriteria:
    """Evaluation of individual criteria via heuristic matchers."""

    async def test_tests_pass_satisfied(self, tmp_path: Path) -> None:
        result = await evaluate_criteria("All tests pass", "TDD-01", tmp_path)
        assert len(result.results) == 1
        assert result.results[0].status == "satisfied"

    async def test_tests_pass_variants(self, tmp_path: Path) -> None:
        for text in ["tests pass", "All tests pass", "Tests pass"]:
            result = await evaluate_criteria(text, "TDD-01", tmp_path)
            assert result.results[0].status == "satisfied", f"Failed for: {text!r}"

    async def test_importable_success(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "tdd_orchestrator.worker_pool.done_criteria_checker.asyncio"
            ".create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            result = await evaluate_criteria(
                "module tdd_orchestrator is importable", "TDD-01", tmp_path
            )

        assert result.results[0].status == "satisfied"

    async def test_importable_failure(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"ModuleNotFoundError"))
        mock_proc.returncode = 1

        with patch(
            "tdd_orchestrator.worker_pool.done_criteria_checker.asyncio"
            ".create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            result = await evaluate_criteria(
                "Package tdd_orchestrator importable", "TDD-01", tmp_path
            )

        assert result.results[0].status == "failed"

    async def test_file_exists_satisfied(self, tmp_path: Path) -> None:
        # Create the file so it exists
        target = tmp_path / "src" / "foo.py"
        target.parent.mkdir(parents=True)
        target.touch()

        result = await evaluate_criteria(
            "file src/foo.py exists", "TDD-01", tmp_path
        )
        assert result.results[0].status == "satisfied"

    async def test_file_exists_failed(self, tmp_path: Path) -> None:
        result = await evaluate_criteria(
            "file src/missing.py exists", "TDD-01", tmp_path
        )
        assert result.results[0].status == "failed"

    async def test_unverifiable_criterion(self, tmp_path: Path) -> None:
        result = await evaluate_criteria(
            "performance is acceptable", "TDD-01", tmp_path
        )
        assert result.results[0].status == "unverifiable"

    async def test_multiple_criteria_mixed(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "foo.py"
        target.parent.mkdir(parents=True)
        target.touch()

        result = await evaluate_criteria(
            "All tests pass; file src/foo.py exists; performance is good",
            "TDD-01",
            tmp_path,
        )
        assert len(result.results) == 3
        assert result.results[0].status == "satisfied"
        assert result.results[1].status == "satisfied"
        assert result.results[2].status == "unverifiable"
        assert "2/3" in result.summary

    async def test_empty_criteria(self, tmp_path: Path) -> None:
        result = await evaluate_criteria("", "TDD-01", tmp_path)
        assert len(result.results) == 0
        assert "0/0" in result.summary

    async def test_summary_format(self, tmp_path: Path) -> None:
        result = await evaluate_criteria("All tests pass", "TDD-01", tmp_path)
        assert "1/1" in result.summary
        assert "satisfied" in result.summary
