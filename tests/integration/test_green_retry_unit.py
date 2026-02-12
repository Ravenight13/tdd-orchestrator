"""Unit tests for GREEN retry mechanism (PLAN10).

This module tests the _run_green_with_retry method in Worker, which implements
Ralph Wiggum-inspired iterative implementation with test failure feedback.

Key behaviors tested:
- First-attempt success (no retry needed)
- Retry on failure with context propagation
- Max attempts exhaustion
- Configuration value respect (max_attempts, delay_ms, timeout)
- Attempt number tracking in database records
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool import (
    DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS,
    Worker,
    WorkerConfig,
)


class TestGreenRetryUnit:
    """Unit tests for _run_green_with_retry method."""

    @pytest.fixture
    async def mock_worker(self, tmp_path: Path) -> AsyncMock:  # type: ignore[misc]
        """Create a mock Worker with necessary attributes for testing.

        Returns:
            Worker instance with mocked dependencies.
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock _run_stage to avoid actual SDK calls
            worker._run_stage = AsyncMock()  # type: ignore[method-assign]

            yield worker

    @pytest.mark.asyncio
    async def test_green_succeeds_first_attempt(self, mock_worker: Worker, tmp_path: Path) -> None:
        """GREEN passes on first attempt - no retry needed.

        Verifies:
        - Only one attempt is made
        - Success returned immediately
        - Only one database record created
        - No delay between attempts
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            task_id = await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_foo.py",
                impl_file="src/foo.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock successful GREEN result
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                return_value=StageResult(
                    stage=Stage.GREEN,
                    success=True,
                    output="All tests passed on first try",
                )
            )

            # Mock config values
            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock) as mock_record,
            ):
                mock_get_config.side_effect = [2, 1000, 1800]  # max_attempts, delay, timeout

                task = await db.get_task_by_key("TDD-01")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify success
                assert result.success is True
                assert "passed" in result.output

                # Verify only one _run_stage call
                assert worker._run_stage.call_count == 1

                # Verify only one database record (attempt 1)
                assert mock_record.call_count == 1
                mock_record.assert_called_once_with(
                    task_id=task_id,
                    stage="green",
                    attempt_number=1,
                    success=True,
                    pytest_exit_code=0,
                    error_message=None,
                )

    @pytest.mark.asyncio
    async def test_green_fails_then_succeeds(self, mock_worker: Worker, tmp_path: Path) -> None:
        """First attempt fails, second succeeds.

        Verifies:
        - Retry logic triggers on failure
        - Second attempt receives failure context
        - Success on retry ends iteration
        - Two database records created (attempt 1 fail, attempt 2 success)
        - Delay applied between attempts
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            task_id = await db.create_task(
                "TDD-02",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_bar.py",
                impl_file="src/bar.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock GREEN results: first fail, second succeed
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                side_effect=[
                    StageResult(
                        stage=Stage.GREEN,
                        success=False,
                        output="Tests failed: AssertionError",
                        error="Implementation incorrect",
                    ),
                    StageResult(
                        stage=Stage.GREEN,
                        success=True,
                        output="Tests passed on retry",
                    ),
                ]
            )

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock) as mock_record,
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                mock_get_config.side_effect = [2, 500, 1800]  # max_attempts, delay, timeout

                task = await db.get_task_by_key("TDD-02")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify eventual success
                assert result.success is True
                assert "passed on retry" in result.output

                # Verify two _run_stage calls
                assert worker._run_stage.call_count == 2

                # Verify second call includes failure context
                second_call = worker._run_stage.call_args_list[1]
                assert second_call.kwargs["attempt"] == 2
                assert "AssertionError" in second_call.kwargs["previous_failure"]

                # Verify delay was applied (500ms = 0.5s)
                mock_sleep.assert_called_once_with(0.5)

                # Verify two database records
                assert mock_record.call_count == 2
                calls = mock_record.call_args_list
                assert calls[0] == call(
                    task_id=task_id,
                    stage="green",
                    attempt_number=1,
                    success=False,
                    pytest_exit_code=1,
                    error_message="Implementation incorrect",
                )
                assert calls[1] == call(
                    task_id=task_id,
                    stage="green",
                    attempt_number=2,
                    success=True,
                    pytest_exit_code=0,
                    error_message=None,
                )

    @pytest.mark.asyncio
    async def test_green_exhausts_all_attempts(self, mock_worker: Worker, tmp_path: Path) -> None:
        """All attempts fail, returns failure.

        Verifies:
        - All max_attempts are used
        - Final failure result returned
        - All attempts recorded in database
        - No delay after final attempt
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            task_id = await db.create_task(
                "TDD-03",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_baz.py",
                impl_file="src/baz.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock GREEN results: all fail
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                side_effect=[
                    StageResult(
                        stage=Stage.GREEN,
                        success=False,
                        output=f"Attempt {i} failed",
                        error=f"Error {i}",
                    )
                    for i in range(1, 4)  # 3 attempts
                ]
            )

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock) as mock_record,
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                mock_get_config.side_effect = [3, 200, 1800]  # 3 max_attempts, delay, timeout

                task = await db.get_task_by_key("TDD-03")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify final failure
                assert result.success is False
                assert "Attempt 3 failed" in result.output

                # Verify all attempts made
                assert worker._run_stage.call_count == 3

                # Verify delay called only between attempts (not after last)
                assert mock_sleep.call_count == 2  # Between 1-2 and 2-3, not after 3
                mock_sleep.assert_called_with(0.2)  # 200ms = 0.2s

                # Verify three database records
                assert mock_record.call_count == 3
                calls = mock_record.call_args_list
                for i in range(1, 4):
                    assert calls[i - 1] == call(
                        task_id=task_id,
                        stage="green",
                        attempt_number=i,
                        success=False,
                        pytest_exit_code=1,
                        error_message=f"Error {i}",
                    )

    @pytest.mark.asyncio
    async def test_config_respected(self, mock_worker: Worker, tmp_path: Path) -> None:
        """max_attempts and delay_ms are read from config.

        Verifies:
        - Config values override defaults
        - Correct config keys queried
        - Values applied correctly to retry logic
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-04",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_config.py",
                impl_file="src/config.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock GREEN results: all fail to test max_attempts
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                side_effect=[
                    StageResult(stage=Stage.GREEN, success=False, output=f"Fail {i}")
                    for i in range(1, 6)
                ]
            )

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                # Custom config: 5 attempts, 750ms delay, 3600s timeout
                mock_get_config.side_effect = [5, 750, 3600]

                task = await db.get_task_by_key("TDD-04")
                assert task is not None

                await worker._run_green_with_retry(task, "RED output")

                # Verify config was queried correctly
                config_calls = mock_get_config.call_args_list
                assert config_calls[0] == call("max_green_attempts", 2)
                assert config_calls[1] == call("green_retry_delay_ms", 1000)
                assert config_calls[2] == call(
                    "max_green_retry_time_seconds", DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS
                )

                # Verify 5 attempts made
                assert worker._run_stage.call_count == 5

                # Verify delay of 750ms used (4 delays between 5 attempts)
                assert mock_sleep.call_count == 4
                for call_obj in mock_sleep.call_args_list:
                    assert call_obj == call(0.75)  # 750ms = 0.75s

    @pytest.mark.asyncio
    async def test_attempt_numbers_increment(self, mock_worker: Worker, tmp_path: Path) -> None:
        """Each attempt recorded with correct attempt_number.

        Verifies:
        - attempt_number starts at 1
        - attempt_number increments sequentially
        - attempt_number passed to record_stage_attempt correctly
        - Second+ attempts include attempt in kwargs
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-05",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_attempt.py",
                impl_file="src/attempt.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock GREEN results: 3 failures then success
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                side_effect=[
                    StageResult(stage=Stage.GREEN, success=False, output="Fail 1"),
                    StageResult(stage=Stage.GREEN, success=False, output="Fail 2"),
                    StageResult(stage=Stage.GREEN, success=False, output="Fail 3"),
                    StageResult(stage=Stage.GREEN, success=True, output="Success"),
                ]
            )

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock) as mock_record,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                mock_get_config.side_effect = [4, 100, 1800]  # 4 max_attempts

                task = await db.get_task_by_key("TDD-05")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify success after 4 attempts
                assert result.success is True

                # Verify 4 attempts made
                assert worker._run_stage.call_count == 4

                # Verify attempt numbers in database records
                assert mock_record.call_count == 4
                calls = mock_record.call_args_list
                for i in range(1, 5):
                    assert calls[i - 1].kwargs["attempt_number"] == i

                # Verify _run_stage received attempt kwarg for attempts 2+
                stage_calls = worker._run_stage.call_args_list
                assert "attempt" not in stage_calls[0].kwargs  # First attempt
                assert stage_calls[1].kwargs["attempt"] == 2
                assert stage_calls[2].kwargs["attempt"] == 3
                assert stage_calls[3].kwargs["attempt"] == 4

    @pytest.mark.asyncio
    async def test_aggregate_timeout_enforced(self, mock_worker: Worker, tmp_path: Path) -> None:
        """Aggregate timeout stops retry attempts early.

        Verifies:
        - Timeout checked before each attempt
        - Loop breaks when timeout exceeded
        - Partial results returned when timeout hit
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-06",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_timeout.py",
                impl_file="src/timeout.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Track call count to advance mock time
            call_count = 0
            start_time = asyncio.get_event_loop().time()

            # Mock GREEN results: each call advances time
            async def slow_fail(*args: object, **kwargs: object) -> StageResult:
                nonlocal call_count
                call_count += 1
                # Simulate 0.15s per attempt by advancing mock time
                return StageResult(stage=Stage.GREEN, success=False, output="Slow fail")

            worker._run_stage = AsyncMock(side_effect=slow_fail)  # type: ignore[method-assign]

            # Mock event loop time() to simulate time passage
            def mock_time() -> float:
                # Each call to _run_stage advances time by 0.15s
                return start_time + (call_count * 0.15)

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock),
                patch("asyncio.sleep", new_callable=AsyncMock),
                patch.object(asyncio.get_event_loop(), "time", side_effect=mock_time),
            ):
                # Short timeout: 0.3 seconds (should allow ~2 attempts at 0.15s each)
                mock_get_config.side_effect = [
                    5,  # max_attempts
                    0,  # delay_ms (no delay)
                    0.3,  # timeout in seconds
                ]

                task = await db.get_task_by_key("TDD-06")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify timeout stopped attempts early
                # With 0.3s timeout and 0.15s per attempt, should get 2 attempts then timeout check fails
                assert worker._run_stage.call_count <= 3  # Should stop around attempt 2-3
                assert worker._run_stage.call_count < 5  # Should NOT reach max_attempts

                # Verify failure result returned
                assert result.success is False

    @pytest.mark.asyncio
    async def test_previous_failure_truncated(self, mock_worker: Worker, tmp_path: Path) -> None:
        """Previous failure output truncated to MAX_TEST_OUTPUT_SIZE.

        Verifies:
        - Large failure output is truncated
        - Truncated output passed to next attempt
        """
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-07",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_large.py",
                impl_file="src/large.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock GREEN results: large failure then success
            large_output = "X" * 100000  # Very large output
            worker._run_stage = AsyncMock(  # type: ignore[method-assign]
                side_effect=[
                    StageResult(
                        stage=Stage.GREEN,
                        success=False,
                        output=large_output,
                        error="Large error",
                    ),
                    StageResult(stage=Stage.GREEN, success=True, output="Success"),
                ]
            )

            with (
                patch.object(db, "get_config_int", new_callable=AsyncMock) as mock_get_config,
                patch.object(db, "record_stage_attempt", new_callable=AsyncMock),
                patch("asyncio.sleep", new_callable=AsyncMock),
                patch("tdd_orchestrator.worker_pool.MAX_TEST_OUTPUT_SIZE", 5000),
            ):
                mock_get_config.side_effect = [2, 0, 1800]

                task = await db.get_task_by_key("TDD-07")
                assert task is not None

                result = await worker._run_green_with_retry(task, "RED output")

                # Verify success
                assert result.success is True

                # Verify second call has truncated previous_failure
                second_call = worker._run_stage.call_args_list[1]
                previous_failure = second_call.kwargs["previous_failure"]
                assert len(previous_failure) <= 5000  # Truncated to MAX_TEST_OUTPUT_SIZE
                assert "X" in previous_failure  # But still contains part of output
