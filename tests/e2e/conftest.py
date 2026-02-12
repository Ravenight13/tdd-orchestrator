"""E2E test fixtures for orchestrator full pipeline tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import VerifyResult


@pytest.fixture
async def e2e_db():
    """In-memory database for E2E tests."""
    async with OrchestratorDB(":memory:") as db:
        yield db


@pytest.fixture
def mock_git_e2e():
    """Mock GitCoordinator for E2E tests."""
    mock = MagicMock()
    mock.create_worker_branch = AsyncMock(return_value="worker-1/TDD-01")
    mock.commit_changes = AsyncMock(return_value="abc123")
    mock.rollback_to_main = AsyncMock()
    mock.has_uncommitted_changes = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def mock_sdk_success():
    """Mock Agent SDK that always succeeds with valid code."""

    async def mock_query(*args: object, **kwargs: object) -> object:
        """Return successful mock responses."""
        mock_message = MagicMock()
        mock_message.text = "Implementation complete - code generated successfully"
        yield mock_message

    return mock_query


@pytest.fixture
def mock_sdk_failure_then_success():
    """Mock Agent SDK that fails once, then succeeds (for retry tests)."""
    call_count = {"count": 0}

    async def mock_query(*args: object, **kwargs: object) -> object:
        """Fail first call, succeed on retry."""
        call_count["count"] += 1
        mock_message = MagicMock()
        if call_count["count"] == 1:
            # First call fails
            mock_message.text = "Error: Invalid syntax"
            yield mock_message
            raise RuntimeError("SDK error - simulated failure")
        else:
            # Subsequent calls succeed
            mock_message.text = "Implementation complete after retry"
            yield mock_message

    return mock_query


@pytest.fixture
def mock_verifier_tdd_cycle():
    """Mock CodeVerifier that simulates full TDD cycle progression."""

    class MockVerifier:
        """Mock verifier that tracks stage progression."""

        call_count = 0

        async def run_pytest(self, test_file: str) -> tuple[bool, str]:
            """Return appropriate pytest results based on stage."""
            self.call_count += 1
            # First call (RED) should fail, subsequent (GREEN) should pass
            if self.call_count == 1:
                return (False, "FAILED: ImportError - implementation not found")
            else:
                return (True, "1 passed in 0.01s")

        async def run_ruff(self, impl_file: str) -> tuple[bool, str]:
            """Return passing ruff results."""
            return (True, "All checks passed!")

        async def run_mypy(self, impl_file: str) -> tuple[bool, str]:
            """Return passing mypy results."""
            return (True, "Success: no issues found")

        async def verify_all(self, test_file: str, impl_file: str) -> VerifyResult:
            """Return successful verify result."""
            return VerifyResult(
                pytest_passed=True,
                pytest_output="1 passed in 0.01s",
                ruff_passed=True,
                ruff_output="All checks passed!",
                mypy_passed=True,
                mypy_output="Success: no issues found",
            )

    return MockVerifier()


@pytest.fixture
def mock_verifier_all_pass():
    """Mock CodeVerifier that always passes (for parallel tests)."""

    class MockVerifier:
        """Mock verifier with all passing results."""

        async def run_pytest(self, test_file: str) -> tuple[bool, str]:
            return (True, "1 passed in 0.01s")

        async def run_ruff(self, impl_file: str) -> tuple[bool, str]:
            return (True, "All checks passed!")

        async def run_mypy(self, impl_file: str) -> tuple[bool, str]:
            return (True, "Success: no issues found")

        async def verify_all(self, test_file: str, impl_file: str) -> VerifyResult:
            return VerifyResult(
                pytest_passed=True,
                pytest_output="1 passed in 0.01s",
                ruff_passed=True,
                ruff_output="All checks passed!",
                mypy_passed=True,
                mypy_output="Success: no issues found",
            )

    return MockVerifier()
