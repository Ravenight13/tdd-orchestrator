"""Edge case tests for GREEN retry mechanism (PLAN10)."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool import (
    MAX_TEST_OUTPUT_SIZE,
    Worker,
    WorkerConfig,
)


class TestGreenRetryEdgeCases:
    """Edge case tests for _run_green_with_retry."""

    @pytest.mark.asyncio
    async def test_aggregate_timeout_exceeded(self) -> None:
        """Test retry stops when total time exceeds aggregate timeout."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-TIMEOUT",
                "Timeout Task",
                phase=0,
                sequence=0,
                test_file="tests/test_timeout.py",
                impl_file="src/timeout.py",
            )

            # Set aggregate timeout to minimum bound (60 seconds)
            await db.set_config("max_green_retry_time_seconds", "60")
            # Set high max attempts (should never reach this due to timeout)
            await db.set_config("max_green_attempts", "10")
            # Set no delay to speed up test
            await db.set_config("green_retry_delay_ms", "0")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier to always fail pytest
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.return_value = (False, "FAILED: timeout test")

                # Mock Agent SDK with instant response
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Attempt code"
                    yield mock_message

                # Track attempt count to simulate passage of time
                attempt_count = [0]

                def mock_get_time() -> float:
                    # Increment time by 15 seconds per attempt
                    # This will cause timeout after ~4 attempts (4 * 15 = 60s)
                    return attempt_count[0] * 15.0

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.sdk_query",
                        side_effect=mock_query_gen,
                    ),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        # Patch the event loop time method
                        original_run_stage = worker._run_stage

                        async def counting_run_stage(
                            stage: Stage, task: dict[str, object], **kwargs: object
                        ) -> StageResult:
                            attempt_count[0] += 1
                            result = await original_run_stage(stage, task, **kwargs)
                            return result

                        with patch.object(worker, "_run_stage", side_effect=counting_run_stage):
                            with patch.object(
                                asyncio.get_event_loop(), "time", side_effect=mock_get_time
                            ):
                                task = await db.get_task_by_key("TDD-TIMEOUT")
                                assert task is not None

                                result = await worker._run_green_with_retry(
                                    task, test_output="RED output"
                                )

                                # Should timeout after ~4 attempts (4 * 15s = 60s)
                                assert result.success is False
                                # Should NOT reach 10 attempts due to 60s timeout
                                all_attempts = await db.get_stage_attempts(task["id"])
                                green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                                assert len(green_attempts) < 10
                                # Should be 3-5 attempts depending on timing
                                assert 3 <= len(green_attempts) <= 5

    @pytest.mark.asyncio
    async def test_empty_test_output(self) -> None:
        """Test handles empty/None test output gracefully."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-EMPTY",
                "Empty Output Task",
                phase=0,
                sequence=0,
                test_file="tests/test_empty.py",
                impl_file="src/empty.py",
            )

            await db.set_config("max_green_attempts", "2")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier to return empty/None output
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                # First attempt: empty string
                # Second attempt: None (should not crash)
                mock_pytest.side_effect = [(False, ""), (True, None)]

                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Code generated"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.sdk_query",
                        side_effect=mock_query_gen,
                    ),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-EMPTY")
                        assert task is not None

                        result = await worker._run_green_with_retry(task, test_output="RED output")

                        # Should succeed on second attempt despite None output
                        assert result.success is True
                        # Should have attempted twice
                        all_attempts = await db.get_stage_attempts(task["id"])
                        green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                        assert len(green_attempts) == 2

    @pytest.mark.asyncio
    async def test_large_test_output_truncation(self) -> None:
        """Test output exceeding MAX_TEST_OUTPUT_SIZE is truncated."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-LARGE",
                "Large Output Task",
                phase=0,
                sequence=0,
                test_file="tests/test_large.py",
                impl_file="src/large.py",
            )

            await db.set_config("max_green_attempts", "3")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Create output larger than MAX_TEST_OUTPUT_SIZE (3000)
            large_output = "x" * 5000

            # Track kwargs passed to _run_stage
            stage_kwargs_history: list[dict[str, object]] = []

            original_run_stage = worker._run_stage

            async def mock_run_stage(
                stage: Stage, task: dict[str, object], **kwargs: object
            ) -> StageResult:
                if stage == Stage.GREEN:
                    stage_kwargs_history.append(kwargs)
                    # Fail first 2 attempts, succeed on 3rd
                    if len(stage_kwargs_history) < 3:
                        return StageResult(
                            stage=Stage.GREEN,
                            success=False,
                            output=large_output,
                            error="Tests failed",
                        )
                    else:
                        return StageResult(
                            stage=Stage.GREEN, success=True, output="Tests passed", error=None
                        )
                return await original_run_stage(stage, task, **kwargs)

            with patch.object(worker, "_run_stage", side_effect=mock_run_stage):
                task = await db.get_task_by_key("TDD-LARGE")
                assert task is not None

                result = await worker._run_green_with_retry(task, test_output="RED output")

                # Should succeed on third attempt
                assert result.success is True

                # Verify truncation in kwargs
                # Attempt 1: no previous_failure
                assert "previous_failure" not in stage_kwargs_history[0]
                # Attempt 2: previous_failure should be truncated to MAX_TEST_OUTPUT_SIZE
                assert "previous_failure" in stage_kwargs_history[1]
                prev_failure = stage_kwargs_history[1]["previous_failure"]
                assert isinstance(prev_failure, str)
                assert len(prev_failure) == MAX_TEST_OUTPUT_SIZE
                assert len(prev_failure) < len(large_output)
                # Attempt 3: previous_failure should also be truncated
                assert "previous_failure" in stage_kwargs_history[2]
                prev_failure_3 = stage_kwargs_history[2]["previous_failure"]
                assert isinstance(prev_failure_3, str)
                assert len(prev_failure_3) == MAX_TEST_OUTPUT_SIZE

    @pytest.mark.asyncio
    async def test_invalid_config_uses_default(self) -> None:
        """Test invalid config values fall back to defaults."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-INVALID-CFG",
                "Invalid Config Task",
                phase=0,
                sequence=0,
                test_file="tests/test_invalid.py",
                impl_file="src/invalid.py",
            )

            # Set invalid config values (not integers)
            await db.set_config("max_green_attempts", "not_a_number")
            await db.set_config("green_retry_delay_ms", "invalid")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier to fail then succeed
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.side_effect = [(False, "FAILED"), (True, "1 passed")]

                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Generated code"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.sdk_query",
                        side_effect=mock_query_gen,
                    ),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-INVALID-CFG")
                        assert task is not None

                        result = await worker._run_green_with_retry(task, test_output="RED output")

                        # Should use defaults (max_attempts=2) and succeed on attempt 2
                        assert result.success is True
                        all_attempts = await db.get_stage_attempts(task["id"])
                        green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                        # Default max_green_attempts is 2
                        assert len(green_attempts) == 2

    @pytest.mark.asyncio
    async def test_config_bounds_clamping(self) -> None:
        """Test values outside bounds (1-10) get clamped."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-BOUNDS",
                "Bounds Task",
                phase=0,
                sequence=0,
                test_file="tests/test_bounds.py",
                impl_file="src/bounds.py",
            )

            # Set max_green_attempts out of bounds (should clamp to 1-10)
            await db.set_config("max_green_attempts", "50")  # Should clamp to 10
            # Set delay out of bounds (should clamp to 0-10000)
            await db.set_config("green_retry_delay_ms", "99999")  # Should clamp to 10000

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier to always fail
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.return_value = (False, "FAILED")

                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Code"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.sdk_query",
                        side_effect=mock_query_gen,
                    ),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-BOUNDS")
                        assert task is not None

                        result = await worker._run_green_with_retry(task, test_output="RED output")

                        # Should fail after max 10 attempts (clamped from 50)
                        assert result.success is False
                        all_attempts = await db.get_stage_attempts(task["id"])
                        green_attempts = [a for a in all_attempts if a["stage"] == "green"]
                        assert len(green_attempts) == 10  # Clamped to max bound

    @pytest.mark.asyncio
    async def test_zero_delay_no_sleep(self) -> None:
        """Test delay_ms=0 doesn't call asyncio.sleep."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-ZERO-DELAY",
                "Zero Delay Task",
                phase=0,
                sequence=0,
                test_file="tests/test_zero.py",
                impl_file="src/zero.py",
            )

            # Set zero delay
            await db.set_config("green_retry_delay_ms", "0")
            await db.set_config("max_green_attempts", "3")

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, Path.cwd())

            # Mock verifier to fail then succeed
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.side_effect = [
                    (False, "FAILED 1"),
                    (False, "FAILED 2"),
                    (True, "PASSED"),
                ]

                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Code"
                    yield mock_message

                # Track asyncio.sleep calls
                original_sleep = asyncio.sleep
                sleep_calls: list[float] = []

                async def tracked_sleep(delay: float) -> None:
                    sleep_calls.append(delay)
                    await original_sleep(delay)

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch(
                        "tdd_orchestrator.worker_pool.worker.sdk_query",
                        side_effect=mock_query_gen,
                    ),
                    patch("asyncio.sleep", side_effect=tracked_sleep),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-ZERO-DELAY")
                        assert task is not None

                        result = await worker._run_green_with_retry(task, test_output="RED output")

                        # Should succeed on third attempt
                        assert result.success is True
                        # Should NOT have called asyncio.sleep (delay_ms=0)
                        # Filter out any sleep calls from SDK or other sources
                        # The retry logic should NOT call sleep when delay_ms=0
                        retry_sleeps = [s for s in sleep_calls if s == 0.0]
                        assert len(retry_sleeps) == 0
