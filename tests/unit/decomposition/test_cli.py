"""Tests for the decompose_spec CLI module.

This module tests the CLI entry point for app_spec decomposition,
including argument parsing, dry-run mode, and mock LLM integration.
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from tdd_orchestrator.decompose_spec import (
    _create_llm_client,
    _print_summary,
    _setup_mock_responses,
    main,
    run_decomposition,
)
from tdd_orchestrator.decomposition import (
    DecomposedTask,
    DecompositionMetrics,
    MockLLMClient,
    RecursiveValidationStats,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_spec_file() -> Path:
    """Create a temporary spec file for testing."""
    content = """
# Test Specification

## FUNCTIONAL REQUIREMENTS

FR-1: User Authentication
- Support OAuth2 login flow
- Validate JWT tokens

FR-2: Data Processing
- Process incoming data
- Validate against schema

## NON-FUNCTIONAL REQUIREMENTS

NFR-1: Performance
- Response time < 200ms

## ACCEPTANCE CRITERIA

AC-1: Login Flow
GIVEN a valid user credential
WHEN the user submits login
THEN the user receives a valid token

## IMPLEMENTATION PLAN

TDD Cycle 1: Authentication Setup
- AuthConfig
- TokenValidator
Tests: 8-10
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture
def mock_tasks() -> list[DecomposedTask]:
    """Create mock tasks for summary testing."""
    return [
        DecomposedTask(
            task_key="TEST-TDD-01-01",
            title="Implement auth config",
            goal="Set up authentication configuration",
            estimated_tests=8,
            estimated_lines=50,
            test_file="tests/test_auth.py",
            impl_file="src/auth.py",
            components=["AuthConfig"],
            acceptance_criteria=["Config loads successfully"],
            phase=1,
            sequence=1,
            depends_on=[],
        ),
        DecomposedTask(
            task_key="TEST-TDD-01-02",
            title="Add token validation",
            goal="Validate JWT tokens",
            estimated_tests=6,
            estimated_lines=40,
            test_file="tests/test_token.py",
            impl_file="src/token.py",
            components=["TokenValidator"],
            acceptance_criteria=["Valid tokens pass"],
            phase=1,
            sequence=2,
            depends_on=["TEST-TDD-01-01"],
        ),
    ]


@pytest.fixture
def mock_metrics() -> DecompositionMetrics:
    """Create mock metrics for summary testing."""
    return DecompositionMetrics(
        total_llm_calls=5,
        pass1_cycles_extracted=2,
        pass2_tasks_generated=4,
        pass3_ac_generated=12,
        total_duration_seconds=2.5,
    )


@pytest.fixture
def mock_validation_stats() -> RecursiveValidationStats:
    """Create mock validation stats for summary testing."""
    return RecursiveValidationStats(
        input_tasks=4,
        output_tasks=4,
        passed_validation=3,
        split_count=1,
        flagged_for_review=0,
        max_depth_reached=1,
    )


# =============================================================================
# Test Classes
# =============================================================================


class TestMockResponseSetup:
    """Tests for mock response setup."""

    def test_setup_mock_responses_returns_dict(self) -> None:
        """Test that mock responses are properly set up."""
        responses = _setup_mock_responses()

        assert isinstance(responses, dict)
        assert "extract TDD cycles" in responses
        assert "Break down this TDD cycle into" in responses
        assert "acceptance criteria" in responses

    def test_mock_responses_are_valid_json(self) -> None:
        """Test that mock responses are valid JSON strings."""
        import json

        responses = _setup_mock_responses()

        for key, value in responses.items():
            # Should not raise
            parsed = json.loads(value)
            assert isinstance(parsed, list)


class TestCreateLLMClient:
    """Tests for LLM client creation."""

    def test_create_mock_client(self) -> None:
        """Test creating a mock LLM client."""
        client = _create_llm_client(use_mock=True)

        assert isinstance(client, MockLLMClient)
        assert len(client.responses) > 0

    def test_create_production_client_returns_sdk_client(self) -> None:
        """Test that production client creation returns ClaudeAgentSDKClient."""
        # Patch at the decomposition package level (where it's imported from)
        with patch("tdd_orchestrator.decomposition.ClaudeAgentSDKClient") as mock_sdk_client:
            mock_client = MagicMock()
            mock_sdk_client.return_value = mock_client

            result = _create_llm_client(use_mock=False)

            mock_sdk_client.assert_called_once_with()
            assert result == mock_client

    def test_create_production_client_uses_subscription_auth(self) -> None:
        """Test that production client uses Claude Agent SDK (no API key needed)."""
        # This test verifies that we DON'T check for API keys
        # The ClaudeAgentSDKClient uses subscription auth via `claude login`
        with patch("tdd_orchestrator.decomposition.ClaudeAgentSDKClient") as mock_sdk_client:
            mock_client = MagicMock()
            mock_sdk_client.return_value = mock_client

            # Should not raise or exit - no API key required
            result = _create_llm_client(use_mock=False)

            assert result == mock_client


class TestPrintSummary:
    """Tests for summary printing."""

    def test_print_summary_output(
        self,
        mock_tasks: list[DecomposedTask],
        mock_metrics: DecompositionMetrics,
        mock_validation_stats: RecursiveValidationStats,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that summary is printed correctly."""
        spec_path = Path("/test/app_spec.txt")

        _print_summary(
            spec_path=spec_path,
            prefix="TEST",
            tasks=mock_tasks,
            metrics=mock_metrics,
            validation_stats=mock_validation_stats,
        )

        captured = capsys.readouterr()

        assert "DECOMPOSITION SUMMARY" in captured.out
        assert "Input spec: /test/app_spec.txt" in captured.out
        assert "Prefix: TEST" in captured.out
        assert "Total tasks: 2" in captured.out
        assert "LLM calls: 5" in captured.out
        assert "Duration: 2.5s" in captured.out
        assert "TEST-TDD-01-01" in captured.out
        assert "Implement auth config" in captured.out

    def test_print_summary_with_many_tasks(
        self,
        mock_metrics: DecompositionMetrics,
        mock_validation_stats: RecursiveValidationStats,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that summary truncates task list when > 10 tasks."""
        # Create 15 mock tasks
        many_tasks = [
            DecomposedTask(
                task_key=f"TEST-TDD-01-{i:02d}",
                title=f"Task {i}",
                goal=f"Goal {i}",
                estimated_tests=5,
                estimated_lines=50,
                test_file=f"tests/test_{i}.py",
                impl_file=f"src/impl_{i}.py",
                phase=1,
                sequence=i,
                depends_on=[],
            )
            for i in range(15)
        ]

        _print_summary(
            spec_path=Path("/test/spec.txt"),
            prefix="TEST",
            tasks=many_tasks,
            metrics=mock_metrics,
            validation_stats=mock_validation_stats,
        )

        captured = capsys.readouterr()

        assert "Total tasks: 15" in captured.out
        assert "... and 5 more" in captured.out


class TestRunDecomposition:
    """Tests for the main decomposition function."""

    @pytest.mark.asyncio
    async def test_dry_run_skips_database(self, temp_spec_file: Path) -> None:
        """Test that dry-run mode skips database loading."""
        with patch("tdd_orchestrator.decompose_spec.get_existing_prefixes", return_value=[]):
            result = await run_decomposition(
                spec_path=temp_spec_file,
                prefix="TEST",
                dry_run=True,
                use_mock_llm=True,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_missing_spec_file_fails(self) -> None:
        """Test that missing spec file causes failure before decomposition."""
        nonexistent = Path("/nonexistent/app_spec.txt")

        # The SpecParser should raise SpecParseError for missing files
        from tdd_orchestrator.decomposition import SpecParseError

        with pytest.raises(SpecParseError):
            await run_decomposition(
                spec_path=nonexistent,
                prefix="TEST",
                dry_run=True,
                use_mock_llm=True,
            )

    @pytest.mark.asyncio
    async def test_verbose_logging_enabled(
        self, temp_spec_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that verbose flag enables debug logging."""
        with patch("tdd_orchestrator.decompose_spec.get_existing_prefixes", return_value=[]):
            with caplog.at_level(logging.DEBUG):
                await run_decomposition(
                    spec_path=temp_spec_file,
                    prefix="TEST",
                    dry_run=True,
                    use_mock_llm=True,
                    verbose=True,
                )

        # Should have some debug-level log messages
        assert any(rec.levelno == logging.INFO for rec in caplog.records)


class TestCLIMain:
    """Tests for the main CLI entry point."""

    @pytest.mark.asyncio
    async def test_main_with_missing_spec_returns_error(self) -> None:
        """Test that CLI returns error code for missing spec file."""
        test_args = [
            "decompose_spec",
            "--spec",
            "/nonexistent/file.txt",
            "--prefix",
            "TEST",
        ]

        with patch("sys.argv", test_args):
            result = await main()

        assert result == 1

    @pytest.mark.asyncio
    async def test_main_with_valid_args_and_dry_run(self, temp_spec_file: Path) -> None:
        """Test that CLI runs successfully with valid args in dry-run mode."""
        test_args = [
            "decompose_spec",
            "--spec",
            str(temp_spec_file),
            "--prefix",
            "TEST",
            "--mock-llm",
            "--dry-run",
        ]

        with patch("sys.argv", test_args), patch(
            "tdd_orchestrator.decompose_spec.get_existing_prefixes", return_value=[]
        ):
            result = await main()

        assert result == 0

    @pytest.mark.asyncio
    async def test_main_with_verbose_flag(self, temp_spec_file: Path) -> None:
        """Test that verbose flag is properly handled."""
        test_args = [
            "decompose_spec",
            "--spec",
            str(temp_spec_file),
            "--prefix",
            "TEST",
            "--mock-llm",
            "--dry-run",
            "-v",
        ]

        with patch("sys.argv", test_args), patch(
            "tdd_orchestrator.decompose_spec.get_existing_prefixes", return_value=[]
        ):
            result = await main()

        assert result == 0


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_required_args(self) -> None:
        """Test that required arguments are enforced."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--spec", required=True, type=Path)
        parser.add_argument("--prefix", required=True)

        # Should raise SystemExit when missing required args
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_all_args_parsed(self) -> None:
        """Test that all arguments are correctly parsed."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--spec", required=True, type=Path)
        parser.add_argument("--prefix", required=True)
        parser.add_argument("--clear", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--mock-llm", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")

        args = parser.parse_args(
            [
                "--spec",
                "/path/to/spec.txt",
                "--prefix",
                "SF",
                "--clear",
                "--dry-run",
                "--mock-llm",
                "-v",
            ]
        )

        assert args.spec == Path("/path/to/spec.txt")
        assert args.prefix == "SF"
        assert args.clear is True
        assert args.dry_run is True
        assert args.mock_llm is True
        assert args.verbose is True
