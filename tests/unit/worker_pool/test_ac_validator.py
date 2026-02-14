"""Tests for acceptance criteria validator.

Validates parsing of AC text (JSON arrays, bullets, numbered lists,
GIVEN/WHEN/THEN) and heuristic matchers (error handling, export,
import, endpoint, GWT, fallback).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tdd_orchestrator.worker_pool.ac_validator import (
    ACResult,
    TaskACResult,
    parse_acceptance_criteria,
    validate_run_ac,
    validate_task_ac,
)


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseAcceptanceCriteria:
    """Tests for parse_acceptance_criteria."""

    def test_parse_json_array(self) -> None:
        raw = '["criterion 1", "criterion 2"]'
        result = parse_acceptance_criteria(raw)
        assert result == ["criterion 1", "criterion 2"]

    def test_parse_newline_separated(self) -> None:
        raw = "line 1\nline 2"
        result = parse_acceptance_criteria(raw)
        assert result == ["line 1", "line 2"]

    def test_parse_numbered_list(self) -> None:
        raw = "1. first\n2. second"
        result = parse_acceptance_criteria(raw)
        assert result == ["first", "second"]

    def test_parse_bullet_list(self) -> None:
        raw = "- first\n- second"
        result = parse_acceptance_criteria(raw)
        assert result == ["first", "second"]

    def test_parse_given_when_then(self) -> None:
        raw = "GIVEN a user exists\nWHEN they log in\nTHEN they see dashboard"
        result = parse_acceptance_criteria(raw)
        # GWT block should be kept as a single criterion
        assert len(result) == 1
        assert "GIVEN" in result[0]
        assert "THEN" in result[0]

    def test_parse_empty(self) -> None:
        assert parse_acceptance_criteria("") == []

    def test_parse_single(self) -> None:
        result = parse_acceptance_criteria("one criterion")
        assert result == ["one criterion"]

    def test_parse_json_array_single(self) -> None:
        raw = '["only one"]'
        result = parse_acceptance_criteria(raw)
        assert result == ["only one"]

    def test_parse_mixed_whitespace(self) -> None:
        raw = "  \n  criterion 1  \n\n  criterion 2  \n  "
        result = parse_acceptance_criteria(raw)
        assert result == ["criterion 1", "criterion 2"]


# ---------------------------------------------------------------------------
# Fixture helpers: create temp Python files for AST matching
# ---------------------------------------------------------------------------


def _write_file(tmp_path: Path, rel_path: str, content: str) -> Path:
    """Write content to a file under tmp_path and return the full path."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(textwrap.dedent(content))
    return full


# ---------------------------------------------------------------------------
# Error handling matcher
# ---------------------------------------------------------------------------


class TestErrorHandlingMatcher:
    """Tests for the error_handling matcher."""

    async def test_error_handling_satisfied(self, tmp_path: Path) -> None:
        """Both raise in impl and pytest.raises in test -> satisfied."""
        _write_file(
            tmp_path,
            "src/impl.py",
            """\
            def validate(x):
                if x < 0:
                    raise ValueError("negative")
            """,
        )
        _write_file(
            tmp_path,
            "tests/test_impl.py",
            """\
            import pytest
            def test_validate():
                with pytest.raises(ValueError):
                    validate(-1)
            """,
        )
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["raises ValueError on negative input"]',
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "error_handling"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_error_handling_missing_impl(self, tmp_path: Path) -> None:
        """Impl missing raise -> not_satisfied."""
        _write_file(
            tmp_path,
            "src/impl.py",
            """\
            def validate(x):
                return x
            """,
        )
        _write_file(
            tmp_path,
            "tests/test_impl.py",
            """\
            import pytest
            def test_validate():
                with pytest.raises(ValueError):
                    validate(-1)
            """,
        )
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["raises ValueError on negative input"]',
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "error_handling"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"

    async def test_error_handling_missing_test(self, tmp_path: Path) -> None:
        """Test missing pytest.raises -> not_satisfied."""
        _write_file(
            tmp_path,
            "src/impl.py",
            """\
            def validate(x):
                if x < 0:
                    raise ValueError("negative")
            """,
        )
        _write_file(
            tmp_path,
            "tests/test_impl.py",
            """\
            def test_validate():
                assert validate(1) == 1
            """,
        )
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["raises ValueError on negative input"]',
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "error_handling"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"


# ---------------------------------------------------------------------------
# Export matcher
# ---------------------------------------------------------------------------


class TestExportMatcher:
    """Tests for the export/define matcher."""

    async def test_export_function_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/config.py",
            """\
            def load_config():
                return {}
            """,
        )
        _write_file(tmp_path, "tests/test_config.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["exports load_config function"]',
            impl_file="src/config.py",
            test_file="tests/test_config.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "export"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_export_class_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/config.py",
            """\
            class ConfigLoader:
                pass
            """,
        )
        _write_file(tmp_path, "tests/test_config.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["provides ConfigLoader class"]',
            impl_file="src/config.py",
            test_file="tests/test_config.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "export"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_export_missing(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/config.py",
            """\
            def other_func():
                pass
            """,
        )
        _write_file(tmp_path, "tests/test_config.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["exports nonexistent_func"]',
            impl_file="src/config.py",
            test_file="tests/test_config.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "export"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"


# ---------------------------------------------------------------------------
# Import matcher
# ---------------------------------------------------------------------------


class TestImportMatcher:
    """Tests for the import/importable matcher."""

    async def test_import_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/mod.py",
            """\
            x = 1
            """,
        )
        _write_file(tmp_path, "tests/test_mod.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["module is importable"]',
            impl_file="src/mod.py",
            test_file="tests/test_mod.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "import"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_import_missing_file(self, tmp_path: Path) -> None:
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["module is importable"]',
            impl_file="src/nonexistent.py",
            test_file="tests/test_nonexistent.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "import"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"


# ---------------------------------------------------------------------------
# Endpoint matcher
# ---------------------------------------------------------------------------


class TestEndpointMatcher:
    """Tests for the endpoint/route matcher."""

    async def test_endpoint_get_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/app.py",
            """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/health")
            def health():
                return {"status": "ok"}
            """,
        )
        _write_file(tmp_path, "tests/test_app.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["responds to GET /health"]',
            impl_file="src/app.py",
            test_file="tests/test_app.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "endpoint"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_endpoint_post_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/app.py",
            """\
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/tasks")
            def create_task():
                return {"id": 1}
            """,
        )
        _write_file(tmp_path, "tests/test_app.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["responds to POST /tasks"]',
            impl_file="src/app.py",
            test_file="tests/test_app.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "endpoint"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_endpoint_not_found(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/app.py",
            """\
            def health():
                return {"status": "ok"}
            """,
        )
        _write_file(tmp_path, "tests/test_app.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["responds to GET /health"]',
            impl_file="src/app.py",
            test_file="tests/test_app.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "endpoint"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"


# ---------------------------------------------------------------------------
# GIVEN/WHEN/THEN matcher
# ---------------------------------------------------------------------------


class TestGivenWhenThenMatcher:
    """Tests for the GIVEN/WHEN/THEN matcher."""

    async def test_gwt_satisfied(self, tmp_path: Path) -> None:
        _write_file(
            tmp_path,
            "src/impl.py",
            """\
            def process():
                pass
            """,
        )
        _write_file(
            tmp_path,
            "tests/test_impl.py",
            """\
            def test_user_logs_in_and_sees_dashboard():
                pass
            """,
        )
        ac = "GIVEN a user exists WHEN they log in THEN they see dashboard"
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria=json.dumps([ac]),
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "given_when_then"]
        assert len(matched) == 1
        assert matched[0].status == "satisfied"

    async def test_gwt_not_found(self, tmp_path: Path) -> None:
        _write_file(tmp_path, "src/impl.py", "def process(): pass\n")
        _write_file(
            tmp_path,
            "tests/test_impl.py",
            """\
            def test_something_unrelated():
                pass
            """,
        )
        ac = "GIVEN a user exists WHEN they log in THEN they see dashboard"
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria=json.dumps([ac]),
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        matched = [r for r in result.results if r.matcher == "given_when_then"]
        assert len(matched) == 1
        assert matched[0].status == "not_satisfied"


# ---------------------------------------------------------------------------
# Unverifiable / fallback
# ---------------------------------------------------------------------------


class TestUnverifiable:
    """Tests for unverifiable (no matcher) criteria."""

    async def test_unverifiable_vague(self, tmp_path: Path) -> None:
        _write_file(tmp_path, "src/impl.py", "x = 1\n")
        _write_file(tmp_path, "tests/test_impl.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["performance is acceptable"]',
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        assert result.results[0].status == "unverifiable"
        assert result.results[0].matcher == "none"

    async def test_unverifiable_subjective(self, tmp_path: Path) -> None:
        _write_file(tmp_path, "src/impl.py", "x = 1\n")
        _write_file(tmp_path, "tests/test_impl.py", "")
        result = await validate_task_ac(
            task_key="TDD-01",
            acceptance_criteria='["user experience is smooth"]',
            impl_file="src/impl.py",
            test_file="tests/test_impl.py",
            base_dir=tmp_path,
        )
        assert result.results[0].status == "unverifiable"
        assert result.results[0].matcher == "none"


# ---------------------------------------------------------------------------
# Aggregate / coverage metric
# ---------------------------------------------------------------------------


class TestAggregate:
    """Tests for aggregate results and summary formatting."""

    def test_summary_format(self) -> None:
        ac_result = TaskACResult(
            task_key="TDD-01",
            results=[
                ACResult("c1", "satisfied", "export", "found"),
                ACResult("c2", "not_satisfied", "export", "missing"),
                ACResult("c3", "unverifiable", "none", "no matcher"),
            ],
        )
        assert ac_result.total == 3
        assert ac_result.verifiable == 2
        assert ac_result.satisfied == 1

    def test_mixed_results(self) -> None:
        ac_result = TaskACResult(
            task_key="TDD-01",
            results=[
                ACResult("c1", "satisfied", "error_handling", "ok"),
                ACResult("c2", "satisfied", "export", "ok"),
                ACResult("c3", "not_satisfied", "import", "missing"),
                ACResult("c4", "unverifiable", "none", "no matcher"),
            ],
        )
        assert ac_result.total == 4
        assert ac_result.verifiable == 3
        assert ac_result.satisfied == 2

    def test_all_unverifiable(self) -> None:
        ac_result = TaskACResult(
            task_key="TDD-01",
            results=[
                ACResult("c1", "unverifiable", "none", ""),
                ACResult("c2", "unverifiable", "none", ""),
            ],
        )
        assert ac_result.total == 2
        assert ac_result.verifiable == 0
        assert ac_result.satisfied == 0

    async def test_validate_run_ac_multiple_tasks(self, tmp_path: Path) -> None:
        """validate_run_ac aggregates across multiple tasks."""
        _write_file(
            tmp_path,
            "src/a.py",
            """\
            def load_config():
                return {}
            """,
        )
        _write_file(tmp_path, "tests/test_a.py", "")
        _write_file(tmp_path, "src/b.py", "x = 1\n")
        _write_file(tmp_path, "tests/test_b.py", "")

        tasks: list[dict[str, Any]] = [
            {
                "task_key": "TDD-01",
                "acceptance_criteria": '["exports load_config"]',
                "impl_file": "src/a.py",
                "test_file": "tests/test_a.py",
            },
            {
                "task_key": "TDD-02",
                "acceptance_criteria": '["performance is fast"]',
                "impl_file": "src/b.py",
                "test_file": "tests/test_b.py",
            },
        ]
        summary = await validate_run_ac(tasks, tmp_path)
        # TDD-01: 1 verifiable, 1 satisfied. TDD-02: 0 verifiable.
        assert "1/2" in summary or "verifiable" in summary

    async def test_validate_run_ac_skips_no_ac(self, tmp_path: Path) -> None:
        """Tasks without acceptance_criteria are skipped."""
        tasks: list[dict[str, Any]] = [
            {
                "task_key": "TDD-01",
                "acceptance_criteria": None,
                "impl_file": "src/a.py",
                "test_file": "tests/test_a.py",
            },
        ]
        summary = await validate_run_ac(tasks, tmp_path)
        assert "0/0" in summary or summary == ""
