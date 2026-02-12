"""Code verifier tests - pytest, ruff, mypy execution.

This module tests the CodeVerifier class which runs external verification
tools (pytest, ruff, mypy) as async subprocesses and captures their output.
"""

from __future__ import annotations

import pytest
from tdd_orchestrator.code_verifier import CodeVerifier


class TestCodeVerifier:
    """Code verification tool execution tests."""

    @pytest.fixture
    def verifier(self, tmp_path) -> CodeVerifier:
        """Create verifier with temp directory."""
        return CodeVerifier(base_dir=tmp_path, timeout=5)

    @pytest.mark.asyncio
    async def test_pytest_returns_pass_on_success(self, verifier, tmp_path) -> None:
        """pytest returns (True, output) on passing tests."""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("def test_pass(): assert True")
        passed, output = await verifier.run_pytest(str(test_file))
        assert passed is True
        assert "1 passed" in output

    @pytest.mark.asyncio
    async def test_pytest_returns_fail_on_failure(self, verifier, tmp_path) -> None:
        """pytest returns (False, output) on failing tests."""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("def test_fail(): assert False")
        passed, output = await verifier.run_pytest(str(test_file))
        assert passed is False
        assert "1 failed" in output

    @pytest.mark.asyncio
    async def test_ruff_returns_pass_on_clean_code(self, verifier, tmp_path) -> None:
        """ruff returns (True, output) on clean code."""
        impl_file = tmp_path / "clean.py"
        impl_file.write_text("x = 1\n")
        passed, output = await verifier.run_ruff(str(impl_file))
        assert passed is True

    @pytest.mark.asyncio
    async def test_ruff_returns_fail_on_lint_error(self, verifier, tmp_path) -> None:
        """ruff returns (False, output) on lint errors."""
        impl_file = tmp_path / "bad.py"
        impl_file.write_text("import os\n")  # Unused import
        passed, output = await verifier.run_ruff(str(impl_file))
        assert passed is False
        assert "F401" in output  # Unused import error code

    @pytest.mark.asyncio
    async def test_mypy_returns_pass_on_valid_types(self, verifier, tmp_path) -> None:
        """mypy returns (True, output) on valid typed code."""
        impl_file = tmp_path / "typed.py"
        impl_file.write_text("def f(x: int) -> int:\n    return x * 2\n")
        passed, output = await verifier.run_mypy(str(impl_file))
        assert passed is True

    @pytest.mark.asyncio
    async def test_mypy_returns_fail_on_type_error(self, verifier, tmp_path) -> None:
        """mypy returns (False, output) on type errors."""
        impl_file = tmp_path / "typed.py"
        impl_file.write_text("def f(x: int) -> str:\n    return x\n")
        passed, output = await verifier.run_mypy(str(impl_file))
        assert passed is False
        assert "error" in output.lower()

    @pytest.mark.asyncio
    async def test_verify_all_runs_parallel(self, verifier, tmp_path) -> None:
        """verify_all runs all tools concurrently."""
        test_file = tmp_path / "test_x.py"
        test_file.write_text("def test_x(): pass")
        impl_file = tmp_path / "x.py"
        impl_file.write_text("x = 1\n")

        result = await verifier.verify_all(str(test_file), str(impl_file))

        assert result.all_passed is True
        assert result.pytest_passed is True
        assert result.ruff_passed is True
        assert result.mypy_passed is True


class TestVerifierTimeout:
    """Timeout handling tests."""

    @pytest.mark.asyncio
    async def test_timeout_returns_false_not_raises(self, tmp_path) -> None:
        """Timeout returns (False, message) instead of raising."""
        verifier = CodeVerifier(base_dir=tmp_path, timeout=0.001)
        test_file = tmp_path / "test_slow.py"
        test_file.write_text("import time\ndef test_slow(): time.sleep(10)")

        passed, output = await verifier.run_pytest(str(test_file))

        assert passed is False
        assert "timed out" in output.lower()

    @pytest.mark.asyncio
    async def test_verify_all_handles_tool_timeout(self, tmp_path) -> None:
        """verify_all handles timeout from any tool gracefully."""
        verifier = CodeVerifier(base_dir=tmp_path, timeout=0.001)
        test_file = tmp_path / "test_x.py"
        test_file.write_text("import time\ndef test_x(): time.sleep(10)")
        impl_file = tmp_path / "x.py"
        impl_file.write_text("x = 1\n")

        result = await verifier.verify_all(str(test_file), str(impl_file))

        # At least pytest should have timed out
        assert result.all_passed is False


class TestVerifierMissingTools:
    """Tests for missing tool handling."""

    @pytest.mark.asyncio
    async def test_pytest_not_found_returns_clear_error(self, tmp_path, monkeypatch) -> None:
        """Missing pytest returns descriptive error."""

        async def mock_exec_not_found(*args, **kwargs):
            raise FileNotFoundError("pytest not found")

        monkeypatch.setattr("asyncio.create_subprocess_exec", mock_exec_not_found)

        verifier = CodeVerifier(base_dir=tmp_path, timeout=5)
        passed, output = await verifier.run_pytest("test.py")

        assert passed is False
        assert "not found" in output.lower()

    @pytest.mark.asyncio
    async def test_ruff_not_found_returns_clear_error(self, tmp_path, monkeypatch) -> None:
        """Missing ruff returns descriptive error."""

        async def mock_exec_not_found(*args, **kwargs):
            raise FileNotFoundError("ruff not found")

        monkeypatch.setattr("asyncio.create_subprocess_exec", mock_exec_not_found)

        verifier = CodeVerifier(base_dir=tmp_path, timeout=5)
        passed, output = await verifier.run_ruff("code.py")

        assert passed is False
        assert "not found" in output.lower()

    @pytest.mark.asyncio
    async def test_mypy_not_found_returns_clear_error(self, tmp_path, monkeypatch) -> None:
        """Missing mypy returns descriptive error."""

        async def mock_exec_not_found(*args, **kwargs):
            raise FileNotFoundError("mypy not found")

        monkeypatch.setattr("asyncio.create_subprocess_exec", mock_exec_not_found)

        verifier = CodeVerifier(base_dir=tmp_path, timeout=5)
        passed, output = await verifier.run_mypy("code.py")

        assert passed is False
        assert "not found" in output.lower()


class TestRunPytestOnFiles:
    """Tests for run_pytest_on_files() sibling test runner."""

    @pytest.fixture
    def verifier(self, tmp_path) -> CodeVerifier:
        """Create verifier with temp directory."""
        return CodeVerifier(base_dir=tmp_path, timeout=10)

    @pytest.mark.asyncio
    async def test_run_pytest_on_files_empty_list_returns_true(self, verifier) -> None:
        """Empty file list returns (True, message) without running pytest."""
        passed, output = await verifier.run_pytest_on_files([])
        assert passed is True
        assert "No sibling test files" in output

    @pytest.mark.asyncio
    async def test_run_pytest_on_files_passes_when_all_pass(self, verifier, tmp_path) -> None:
        """All passing test files returns (True, output)."""
        test_a = tmp_path / "test_a.py"
        test_a.write_text("def test_a(): assert True")
        test_b = tmp_path / "test_b.py"
        test_b.write_text("def test_b(): assert True")

        passed, output = await verifier.run_pytest_on_files(
            [str(test_a), str(test_b)]
        )
        assert passed is True
        assert "2 passed" in output

    @pytest.mark.asyncio
    async def test_run_pytest_on_files_fails_when_one_fails(self, verifier, tmp_path) -> None:
        """One failing test file returns (False, output)."""
        test_ok = tmp_path / "test_ok.py"
        test_ok.write_text("def test_ok(): assert True")
        test_bad = tmp_path / "test_bad.py"
        test_bad.write_text("def test_bad(): assert False")

        passed, output = await verifier.run_pytest_on_files(
            [str(test_ok), str(test_bad)]
        )
        assert passed is False
        assert "1 failed" in output


class TestVerifierPathResolution:
    """Path resolution tests."""

    @pytest.mark.asyncio
    async def test_relative_path_resolved_to_base_dir(self, tmp_path) -> None:
        """Relative paths are resolved relative to base_dir."""
        verifier = CodeVerifier(base_dir=tmp_path, timeout=5)
        test_file = tmp_path / "test_x.py"
        test_file.write_text("def test_x(): pass")

        # Use relative path
        passed, output = await verifier.run_pytest("test_x.py")

        assert passed is True

    @pytest.mark.asyncio
    async def test_absolute_path_used_directly(self, tmp_path) -> None:
        """Absolute paths are used as-is."""
        verifier = CodeVerifier(base_dir=tmp_path, timeout=5)
        test_file = tmp_path / "test_x.py"
        test_file.write_text("def test_x(): pass")

        # Use absolute path
        passed, output = await verifier.run_pytest(str(test_file))

        assert passed is True
