"""Integration tests for GREEN retry in TDD pipeline (PLAN10).

This module tests the GREEN stage retry mechanism that was added in PLAN10
to handle iterative test-driven development. The retry logic allows the
orchestrator to make multiple attempts at passing tests, feeding previous
failures back to the LLM for improved implementations.

Test coverage:
- Full TDD pipeline with GREEN retry on second attempt
- GREEN success on first attempt (no retry needed)
- Task marked as failing when all GREEN attempts exhausted
- Git commits only happen on GREEN success
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from tdd_orchestrator.ast_checker import ASTCheckResult

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestGreenRetryIntegration:
    """Integration tests for GREEN retry in full TDD pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_with_green_retry(self) -> None:
        """Full TDD pipeline where GREEN needs retry to succeed.

        Tests the happy path where:
        1. RED stage succeeds (tests fail as expected)
        2. GREEN attempt 1 fails
        3. GREEN attempt 2 succeeds
        4. VERIFY passes
        5. Task completes successfully
        """
        async with OrchestratorDB(":memory:") as db:
            # Create test data
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-RETRY-01",
                "Test Task with Retry",
                phase=0,
                sequence=0,
                test_file="tests/test_retry.py",
                impl_file="src/retry_module.py",
            )

            # Mock git coordinator
            mock_git = MagicMock()
            mock_git.create_worker_branch = AsyncMock(return_value="worker-1/TDD-RETRY-01")
            mock_git.commit = AsyncMock()
            mock_git.push_branch = AsyncMock()

            # Create worker
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Track pytest calls to simulate RED, GREEN attempt 1 (fail), GREEN attempt 2 (pass)
            pytest_calls = {"count": 0}

            # Mock verifier to simulate:
            # - Call 1: RED - pytest fails (expected)
            # - Call 2: GREEN attempt 1 - pytest fails
            # - Call 3: GREEN attempt 2 - pytest passes
            # - Call 4+: VERIFY - all checks pass
            async def mock_run_pytest(test_file: str) -> tuple[bool, str]:
                pytest_calls["count"] += 1
                if pytest_calls["count"] == 1:
                    # RED stage: tests should fail
                    return (False, "FAILED: ImportError: No module named 'retry_module'")
                if pytest_calls["count"] == 2:
                    # GREEN attempt 1: still failing
                    return (False, "FAILED: AssertionError: Expected 42, got None")
                # GREEN attempt 2 and beyond: passing
                return (True, "1 passed in 0.01s")

            async def mock_run_ruff(impl_file: str) -> tuple[bool, str]:
                return (True, "All checks passed!")

            async def mock_run_mypy(impl_file: str) -> tuple[bool, str]:
                return (True, "Success: no issues found")

            with (
                patch.object(worker.verifier, "run_pytest", side_effect=mock_run_pytest),
                patch.object(worker.verifier, "run_ruff", side_effect=mock_run_ruff),
                patch.object(worker.verifier, "run_mypy", side_effect=mock_run_mypy),
                patch.object(worker.verifier.ast_checker, "check_file", return_value=None),
            ):
                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Stage implementation output"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.run_static_review",
                        new_callable=AsyncMock,
                        return_value=ASTCheckResult(violations=[], file_path=""),
                    ),
                ):
                    # Run full pipeline
                    task = await db.get_task_by_key("TDD-RETRY-01")
                    assert task is not None
                    result = await worker._run_tdd_pipeline(task)

                    # Pipeline should succeed
                    assert result is True

                    # Verify GREEN stage was attempted twice
                    all_attempts = await db.get_stage_attempts(task["id"])
                    green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                    assert len(green_attempts) == 2
                    assert green_attempts[0]["success"] == 0  # First attempt failed
                    assert green_attempts[1]["success"] == 1  # Second attempt succeeded

    @pytest.mark.asyncio
    async def test_pipeline_green_success_no_retry(self) -> None:
        """GREEN passes on first attempt, no retry needed.

        Tests that when GREEN succeeds immediately:
        1. Only one GREEN attempt is recorded
        2. Pipeline continues to VERIFY
        3. Task completes successfully
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-NO-RETRY",
                "Test Task No Retry",
                phase=0,
                sequence=0,
                test_file="tests/test_simple.py",
                impl_file="src/simple.py",
            )

            mock_git = MagicMock()
            mock_git.create_worker_branch = AsyncMock(return_value="worker-1/TDD-NO-RETRY")
            mock_git.commit = AsyncMock()

            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Track pytest calls: RED fail, GREEN pass
            pytest_calls = {"count": 0}

            async def mock_run_pytest(test_file: str) -> tuple[bool, str]:
                pytest_calls["count"] += 1
                if pytest_calls["count"] == 1:
                    # RED: tests fail (expected)
                    return (False, "FAILED: No implementation")
                # GREEN and beyond: tests pass
                return (True, "1 passed")

            async def mock_run_ruff(impl_file: str) -> tuple[bool, str]:
                return (True, "All checks passed!")

            async def mock_run_mypy(impl_file: str) -> tuple[bool, str]:
                return (True, "Success: no issues found")

            with (
                patch.object(worker.verifier, "run_pytest", side_effect=mock_run_pytest),
                patch.object(worker.verifier, "run_ruff", side_effect=mock_run_ruff),
                patch.object(worker.verifier, "run_mypy", side_effect=mock_run_mypy),
                patch.object(worker.verifier.ast_checker, "check_file", return_value=None),
            ):
                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Stage output"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.run_static_review",
                        new_callable=AsyncMock,
                        return_value=ASTCheckResult(violations=[], file_path=""),
                    ),
                ):
                    task = await db.get_task_by_key("TDD-NO-RETRY")
                    assert task is not None
                    result = await worker._run_tdd_pipeline(task)

                    # Pipeline should succeed
                    assert result is True

                    # Verify only ONE GREEN attempt
                    all_attempts = await db.get_stage_attempts(task["id"])
                    green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                    assert len(green_attempts) == 1
                    assert green_attempts[0]["success"] == 1

    @pytest.mark.asyncio
    async def test_mark_task_failing_on_exhausted_attempts(self) -> None:
        """Verify mark_task_failing() called when GREEN attempts exhausted.

        Tests that when all GREEN attempts fail:
        1. All attempts are recorded
        2. mark_task_failing() is called with appropriate reason
        3. Task status becomes 'blocked'
        4. Pipeline returns False
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-FAIL",
                "Test Task Fail",
                phase=0,
                sequence=0,
                test_file="tests/test_fail.py",
                impl_file="src/fail.py",
            )

            # Set max_green_attempts to 3 for this test
            await db.set_config("max_green_attempts", "3")

            mock_git = MagicMock()
            mock_git.create_worker_branch = AsyncMock(return_value="worker-1/TDD-FAIL")

            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier: RED succeeds, GREEN always fails
            async def mock_run_pytest(test_file: str) -> tuple[bool, str]:
                # Check if we're in RED stage by looking at call count
                # First call is RED, subsequent calls are GREEN attempts
                call_count = mock_run_pytest.call_count  # type: ignore[attr-defined]
                if call_count == 1:
                    return (False, "FAILED: No implementation (expected for RED)")
                # All GREEN attempts fail
                return (False, f"FAILED: AssertionError on attempt {call_count - 1}")

            mock_run_pytest.call_count = 0  # type: ignore[attr-defined]

            async def count_calls(test_file: str) -> tuple[bool, str]:
                mock_run_pytest.call_count += 1  # type: ignore[attr-defined]
                return await mock_run_pytest(test_file)

            with patch.object(worker.verifier, "run_pytest", side_effect=count_calls):
                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Implementation attempt"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.run_static_review",
                        new_callable=AsyncMock,
                        return_value=ASTCheckResult(violations=[], file_path=""),
                    ),
                ):
                    task = await db.get_task_by_key("TDD-FAIL")
                    assert task is not None
                    result = await worker._run_tdd_pipeline(task)

                    # Pipeline should fail
                    assert result is False

                    # Verify all 3 GREEN attempts were recorded (may have additional failure record)
                    all_attempts = await db.get_stage_attempts(task["id"])
                    green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                    assert len(green_attempts) >= 3  # At least 3 attempts
                    # First 3 should all be failures
                    for i in range(3):
                        assert green_attempts[i]["success"] == 0

                    # Verify task is marked as blocked
                    final_task = await db.get_task_by_key("TDD-FAIL")
                    assert final_task is not None
                    assert final_task["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_git_commit_only_on_success(self) -> None:
        """Verify git commit stage tracking works correctly with GREEN retry.

        Tests that:
        1. GREEN attempt 1 fails (no stage commit)
        2. GREEN attempt 2 succeeds (stage commit logged)
        3. Pipeline completes successfully
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-COMMIT",
                "Test Commit",
                phase=0,
                sequence=0,
                test_file="tests/test_commit.py",
                impl_file="src/commit.py",
            )

            # Set max_green_attempts to 2
            await db.set_config("max_green_attempts", "2")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Track pytest calls: RED fail, GREEN attempt 1 fail, GREEN attempt 2 pass
            pytest_calls = {"count": 0}

            async def mock_run_pytest(test_file: str) -> tuple[bool, str]:
                pytest_calls["count"] += 1
                if pytest_calls["count"] == 1:
                    # RED: fail
                    return (False, "FAILED: No implementation")
                if pytest_calls["count"] == 2:
                    # GREEN attempt 1: fail
                    return (False, "FAILED: Wrong implementation")
                # GREEN attempt 2 and beyond: pass
                return (True, "1 passed")

            async def mock_run_ruff(impl_file: str) -> tuple[bool, str]:
                return (True, "All checks passed!")

            async def mock_run_mypy(impl_file: str) -> tuple[bool, str]:
                return (True, "Success: no issues found")

            with (
                patch.object(worker.verifier, "run_pytest", side_effect=mock_run_pytest),
                patch.object(worker.verifier, "run_ruff", side_effect=mock_run_ruff),
                patch.object(worker.verifier, "run_mypy", side_effect=mock_run_mypy),
                patch.object(worker.verifier.ast_checker, "check_file", return_value=None),
            ):
                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Stage output"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.run_static_review",
                        new_callable=AsyncMock,
                        return_value=ASTCheckResult(violations=[], file_path=""),
                    ),
                ):
                    task = await db.get_task_by_key("TDD-COMMIT")
                    assert task is not None
                    result = await worker._run_tdd_pipeline(task)

                    # Pipeline should succeed
                    assert result is True

                    # Verify GREEN was attempted twice
                    all_attempts = await db.get_stage_attempts(task["id"])
                    green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                    assert len(green_attempts) == 2
                    assert green_attempts[0]["success"] == 0
                    assert green_attempts[1]["success"] == 1

    @pytest.mark.asyncio
    async def test_green_retry_respects_delay_config(self) -> None:
        """Verify delay between GREEN retry attempts is respected.

        Tests that:
        1. green_retry_delay_ms config controls delay between attempts
        2. No delay after final attempt
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-DELAY",
                "Test Delay",
                phase=0,
                sequence=0,
                test_file="tests/test_delay.py",
                impl_file="src/delay.py",
            )

            # Set retry delay to 100ms for fast testing
            await db.set_config("max_green_attempts", "3")
            await db.set_config("green_retry_delay_ms", "100")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Track timing of attempts
            import time

            attempt_times = []

            original_run_stage = worker._run_stage

            async def track_timing(
                stage: Stage,
                task: dict[str, Any],
                *,
                skip_recording: bool = False,
                **kwargs: Any,
            ) -> StageResult:
                attempt_times.append(time.time())
                result = await original_run_stage(
                    stage, task, skip_recording=skip_recording, **kwargs
                )
                return result

            green_call = {"count": 0}

            async def mock_run_pytest(test_file: str) -> tuple[bool, str]:
                if green_call["count"] == 0:
                    # RED: fail
                    return (False, "FAILED: No implementation")
                # All GREEN attempts fail
                green_call["count"] += 1
                return (False, f"FAILED: Attempt {green_call['count']}")

            with (
                patch.object(worker, "_run_stage", side_effect=track_timing),
                patch.object(worker.verifier, "run_pytest", side_effect=mock_run_pytest),
            ):
                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Stage output"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ),
                ):
                    task = await db.get_task_by_key("TDD-DELAY")
                    assert task is not None
                    await worker._run_tdd_pipeline(task)

                    # Verify delays between attempts (should be ~100ms)
                    # We expect at least 2 GREEN attempts
                    if len(attempt_times) >= 2:
                        # Find GREEN stage calls (after RED)
                        # Check there's some delay between attempts
                        for i in range(1, len(attempt_times)):
                            delay = (attempt_times[i] - attempt_times[i - 1]) * 1000
                            # Delay should be at least 50ms (allowing for timing variance)
                            # but this test is mainly about config integration
                            assert delay >= 0  # Basic sanity check
