"""Unit tests for non-Python file guards across verification tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from tdd_orchestrator.ast_checker import ASTCheckResult
from tdd_orchestrator.code_verifier import CodeVerifier, _is_python_file
from tdd_orchestrator.refactor_checker import check_needs_refactor
from tdd_orchestrator.worker_pool.git_ops import run_ruff_fix


# =========================================================================
# _is_python_file() tests
# =========================================================================


def test_is_python_file_py() -> None:
    assert _is_python_file("src/foo.py") is True


def test_is_python_file_pyi() -> None:
    assert _is_python_file("src/foo.pyi") is True


def test_is_python_file_init() -> None:
    assert _is_python_file("src/__init__.py") is True


def test_is_python_file_toml() -> None:
    assert _is_python_file("pyproject.toml") is False


def test_is_python_file_cfg() -> None:
    assert _is_python_file("setup.cfg") is False


def test_is_python_file_no_extension() -> None:
    assert _is_python_file("Makefile") is False


def test_is_python_file_empty() -> None:
    assert _is_python_file("") is False


# =========================================================================
# CodeVerifier.run_ruff() / run_mypy() skip non-Python
# =========================================================================


async def test_run_ruff_skips_non_python(tmp_path: Path) -> None:
    """run_ruff returns skip message for non-Python files."""
    verifier = CodeVerifier(base_dir=tmp_path)

    with patch.object(verifier, "_run_command", new_callable=AsyncMock) as mock_cmd:
        passed, output = await verifier.run_ruff("pyproject.toml")

    assert passed is True
    assert "Skipped" in output
    mock_cmd.assert_not_called()


async def test_run_mypy_skips_non_python(tmp_path: Path) -> None:
    """run_mypy returns skip message for non-Python files."""
    verifier = CodeVerifier(base_dir=tmp_path)

    with patch.object(verifier, "_run_command", new_callable=AsyncMock) as mock_cmd:
        passed, output = await verifier.run_mypy("pyproject.toml")

    assert passed is True
    assert "Skipped" in output
    mock_cmd.assert_not_called()


# =========================================================================
# CodeVerifier.run_ast_checks() skip non-Python
# =========================================================================


async def test_run_ast_checks_skips_non_python(tmp_path: Path) -> None:
    """run_ast_checks returns empty result for non-Python files."""
    verifier = CodeVerifier(base_dir=tmp_path)

    result = await verifier.run_ast_checks("pyproject.toml")

    assert isinstance(result, ASTCheckResult)
    assert result.violations == []
    assert result.file_path == "pyproject.toml"


# =========================================================================
# CodeVerifier.verify_all() with non-Python impl_file
# =========================================================================


async def test_verify_all_non_python_skips_ruff_mypy_ast(tmp_path: Path) -> None:
    """verify_all with .toml impl_file skips ruff/mypy/ast but runs pytest."""
    verifier = CodeVerifier(base_dir=tmp_path)

    with patch.object(
        verifier, "run_pytest", new_callable=AsyncMock, return_value=(True, "1 passed")
    ) as mock_pytest:
        result = await verifier.verify_all("tests/test_foo.py", "pyproject.toml")

    mock_pytest.assert_called_once_with("tests/test_foo.py")
    assert result.pytest_passed is True
    assert result.ruff_passed is True
    assert "Skipped" in result.ruff_output
    assert result.mypy_passed is True
    assert "Skipped" in result.mypy_output
    assert result.ast_result.violations == []


# =========================================================================
# AST checker.check_file() guard
# =========================================================================


async def test_ast_checker_check_file_skips_non_python() -> None:
    """ASTQualityChecker.check_file() returns empty for .toml."""
    from tdd_orchestrator.ast_checker import ASTQualityChecker

    checker = ASTQualityChecker()
    result = await checker.check_file(Path("pyproject.toml"))

    assert result.violations == []
    assert result.file_path == "pyproject.toml"


# =========================================================================
# run_ruff_fix() guard
# =========================================================================


async def test_run_ruff_fix_skips_non_python(tmp_path: Path) -> None:
    """run_ruff_fix returns True immediately for non-Python files."""
    result = await run_ruff_fix("pyproject.toml", "TASK-01", tmp_path)
    assert result is True


# =========================================================================
# check_needs_refactor() guard
# =========================================================================


async def test_check_needs_refactor_skips_non_python(tmp_path: Path) -> None:
    """check_needs_refactor returns needs_refactor=False for non-Python."""
    result = await check_needs_refactor("pyproject.toml", tmp_path)

    assert result.needs_refactor is False
    assert result.reasons == []
    assert result.file_lines == 0
