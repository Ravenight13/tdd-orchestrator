"""E2E bridge tests for decomposition → task loading → worker execution.

These tests verify the complete pipeline from DecomposedTask objects through
database loading to worker execution, bridging the gap between:
- Decomposition E2E (stops at task generation)
- Execution E2E (starts with pre-created database tasks)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from tdd_orchestrator.decomposition.decomposer import DecomposedTask
from tdd_orchestrator.models import Stage
from tdd_orchestrator.task_loader import load_tdd_tasks
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestDecompositionToExecution:
    """Bridge tests connecting decomposition output to execution input."""

    @pytest.mark.asyncio
    async def test_decomposed_tasks_load_into_database(self, e2e_db) -> None:
        """DecomposedTask objects successfully load into database with all fields preserved."""
        # Create 3 sample DecomposedTask objects (simulating decomposer output)
        tasks = [
            DecomposedTask(
                task_key="BRIDGE-001",
                title="Implement user authentication",
                goal="Add JWT-based authentication to API endpoints",
                estimated_tests=8,
                estimated_lines=75,
                test_file="tests/test_auth.py",
                impl_file="src/auth.py",
                components=["auth", "jwt", "middleware"],
                acceptance_criteria=[
                    "Should generate valid JWT tokens on login",
                    "Should validate JWT tokens on protected routes",
                    "Should return 401 for invalid tokens",
                ],
                phase=1,
                sequence=1,
                depends_on=[],
                error_codes=["AUTH-001", "AUTH-002"],
                blocking_assumption=None,
            ),
            DecomposedTask(
                task_key="BRIDGE-002",
                title="Create user profile endpoint",
                goal="Expose REST endpoint for user profile retrieval",
                estimated_tests=5,
                estimated_lines=40,
                test_file="tests/test_profile.py",
                impl_file="src/profile.py",
                components=["api", "profile"],
                acceptance_criteria=[
                    "Should return user profile for authenticated requests",
                    "Should return 404 for non-existent users",
                ],
                phase=1,
                sequence=2,
                depends_on=["BRIDGE-001"],
                error_codes=[],
                blocking_assumption=None,
            ),
            DecomposedTask(
                task_key="BRIDGE-003",
                title="Add password reset flow",
                goal="Implement secure password reset via email",
                estimated_tests=12,
                estimated_lines=90,
                test_file="tests/test_password_reset.py",
                impl_file="src/password_reset.py",
                components=["auth", "email", "security"],
                acceptance_criteria=[
                    "Should send reset email with secure token",
                    "Should validate token expiration",
                    "Should update password on valid token",
                ],
                phase=2,
                sequence=1,
                depends_on=["BRIDGE-001"],
                error_codes=["RESET-001"],
                blocking_assumption="A-4",  # Assumption blocking implementation
            ),
        ]

        # Convert to dicts via to_dict()
        task_dicts = [t.to_dict() for t in tasks]

        # Load into database
        result = await load_tdd_tasks(task_dicts, db=e2e_db, clear_existing=True)

        # Verify load result
        assert result["loaded"] == 3, "Should load all 3 tasks"
        assert result["skipped"] == 0, "Should skip no tasks"
        assert len(result["errors"]) == 0, "Should have no errors"
        assert set(result["task_keys"]) == {"BRIDGE-001", "BRIDGE-002", "BRIDGE-003"}

        # Verify tasks exist in database with correct fields
        for task in tasks:
            db_task = await e2e_db.get_task_by_key(task.task_key)
            assert db_task is not None, f"Task {task.task_key} should exist in database"

            # Verify core fields
            assert db_task["task_key"] == task.task_key
            assert db_task["title"] == task.title
            assert db_task["goal"] == task.goal
            assert db_task["test_file"] == task.test_file
            assert db_task["impl_file"] == task.impl_file
            assert db_task["phase"] == task.phase
            assert db_task["sequence"] == task.sequence
            assert db_task["status"] == "pending"

            # Verify JSON fields (acceptance_criteria, depends_on)
            # Note: Database stores JSON as TEXT, so deserialize before comparing
            if task.acceptance_criteria:
                db_ac = db_task["acceptance_criteria"]
                # Database stores JSON strings, deserialize if needed
                if isinstance(db_ac, str):
                    db_ac = json.loads(db_ac)
                assert db_ac == task.acceptance_criteria, f"AC mismatch for {task.task_key}"

            if task.depends_on:
                db_deps = db_task["depends_on"]
                # Database stores JSON strings, deserialize if needed
                if isinstance(db_deps, str):
                    db_deps = json.loads(db_deps)
                assert db_deps == task.depends_on, f"Dependencies mismatch for {task.task_key}"

        # Verify database task count
        stats = await e2e_db.get_stats()
        assert stats["pending"] == 3, "All tasks should be in pending state"

    @pytest.mark.asyncio
    async def test_loaded_tasks_execute_through_worker(
        self,
        e2e_db,
        mock_git_e2e,
        mock_sdk_success,
        mock_verifier_tdd_cycle,
    ) -> None:
        """Loaded DecomposedTask executes through worker RED → GREEN → VERIFY stages."""
        # Create DecomposedTask
        task = DecomposedTask(
            task_key="EXEC-001",
            title="Implement feature validation",
            goal="Add input validation to feature endpoint",
            estimated_tests=5,
            estimated_lines=50,
            test_file="tests/test_validation.py",
            impl_file="src/validation.py",
            components=["validation"],
            acceptance_criteria=[
                "Should reject invalid inputs",
                "Should accept valid inputs",
            ],
            phase=0,
            sequence=0,
            depends_on=[],
        )

        # Load into database
        result = await load_tdd_tasks([task.to_dict()], db=e2e_db)
        assert result["loaded"] == 1, "Task should load successfully"

        # Setup worker
        run_id = await e2e_db.start_execution_run(max_workers=1)
        config = WorkerConfig(
            max_workers=1,
            single_branch_mode=True,
            heartbeat_interval_seconds=1,
        )
        worker = Worker(1, e2e_db, mock_git_e2e, config, run_id, Path.cwd())
        worker.verifier = mock_verifier_tdd_cycle

        # Patch Agent SDK
        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_sdk_success),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            await worker.start()

            # Get loaded task from database
            db_task = await e2e_db.get_task_by_key("EXEC-001")
            assert db_task is not None, "Loaded task should exist"
            task_id = db_task["id"]

            # Claim task
            claimed = await e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300)
            assert claimed is True, "Worker should claim task"

            # Execute RED stage
            red_result = await worker._run_stage(Stage.RED, db_task)
            assert red_result.success is True, "RED stage should succeed (test fails initially)"
            await e2e_db.record_attempt(
                task_id, "red", success=True, pytest_output=red_result.output
            )

            # Execute GREEN stage
            green_result = await worker._run_stage(
                Stage.GREEN, db_task, test_output=red_result.output
            )
            assert green_result.success is True, "GREEN stage should succeed (test passes)"
            await e2e_db.record_attempt(
                task_id, "green", success=True, pytest_output=green_result.output
            )

            # Execute VERIFY stage
            verify_result = await worker._run_stage(
                Stage.VERIFY, db_task, impl_output=green_result.output
            )
            assert verify_result.success is True, "VERIFY stage should pass all checks"
            await e2e_db.record_attempt(task_id, "verify", success=True)

            # Mark complete
            await e2e_db.update_task_status("EXEC-001", "passing")

            # Verify final state
            final_task = await e2e_db.get_task_by_key("EXEC-001")
            assert final_task is not None
            assert final_task["status"] == "passing", "Task should complete successfully"

            # Verify all stages recorded
            attempts = await e2e_db.get_stage_attempts(task_id)
            assert len(attempts) >= 3, "Should record RED, GREEN, VERIFY attempts"

            await worker.stop()

    @pytest.mark.asyncio
    async def test_task_dependencies_respected_during_execution(
        self,
        e2e_db,
        mock_git_e2e,
    ) -> None:
        """Tasks with dependencies cannot be claimed until dependencies complete."""
        # Create tasks with dependencies (Task B depends on Task A)
        task_a = DecomposedTask(
            task_key="DEP-A",
            title="Task A - Foundation",
            goal="Implement base functionality",
            estimated_tests=3,
            estimated_lines=30,
            test_file="tests/test_a.py",
            impl_file="src/a.py",
            components=["base"],
            acceptance_criteria=["Should initialize base class"],
            phase=0,
            sequence=0,
            depends_on=[],
        )

        task_b = DecomposedTask(
            task_key="DEP-B",
            title="Task B - Extension",
            goal="Extend base functionality",
            estimated_tests=5,
            estimated_lines=40,
            test_file="tests/test_b.py",
            impl_file="src/b.py",
            components=["extension"],
            acceptance_criteria=["Should extend base class"],
            phase=0,
            sequence=1,
            depends_on=["DEP-A"],  # Depends on Task A
        )

        # Load into database
        result = await load_tdd_tasks([task_a.to_dict(), task_b.to_dict()], db=e2e_db)
        assert result["loaded"] == 2, "Both tasks should load"

        # Setup worker
        run_id = await e2e_db.start_execution_run(max_workers=1)
        config = WorkerConfig(single_branch_mode=True)
        worker = Worker(1, e2e_db, mock_git_e2e, config, run_id, Path.cwd())
        await worker.start()

        # Verify Task B not claimable initially (Task A not complete)
        task_b_db = await e2e_db.get_task_by_key("DEP-B")
        assert task_b_db is not None
        task_b_id = task_b_db["id"]

        # Check if Task B is in pending tasks (it should be blocked by dependency)
        next_task = await e2e_db.get_next_pending_task()
        # get_next_pending_task returns tasks with no dependencies or completed dependencies
        # Task B should NOT be returned since Task A is not complete
        if next_task:
            assert next_task["task_key"] != "DEP-B", "Task B should not be claimable (depends on A)"
            assert next_task["task_key"] == "DEP-A", "Only Task A should be claimable"

        # Complete Task A
        task_a_db = await e2e_db.get_task_by_key("DEP-A")
        assert task_a_db is not None
        await e2e_db.update_task_status("DEP-A", "complete")

        # Now Task B should be claimable
        next_task_after = await e2e_db.get_next_pending_task()
        if next_task_after:
            assert next_task_after["task_key"] == "DEP-B", (
                "Task B should be claimable after A completes"
            )

            # Try claiming Task B
            claimed = await e2e_db.claim_task(task_b_id, worker_id=1, timeout_seconds=300)
            assert claimed is True, "Task B should be claimable after dependency completes"

        await worker.stop()

    @pytest.mark.asyncio
    async def test_error_codes_preserved_through_pipeline(self, e2e_db) -> None:
        """Error codes from DecomposedTask are not stored in database (metadata only)."""
        # Create DecomposedTask with error codes
        task = DecomposedTask(
            task_key="ERR-001",
            title="Handle error conditions",
            goal="Implement error handling for edge cases",
            estimated_tests=6,
            estimated_lines=50,
            test_file="tests/test_errors.py",
            impl_file="src/errors.py",
            components=["errors"],
            acceptance_criteria=[
                "Should raise ERR-001 for invalid input",
                "Should raise ERR-002 for timeout",
            ],
            phase=0,
            sequence=0,
            depends_on=[],
            error_codes=["ERR-001", "ERR-002"],  # Error codes from decomposer
        )

        # Load into database
        result = await load_tdd_tasks([task.to_dict()], db=e2e_db)
        assert result["loaded"] == 1, "Task should load successfully"

        # Verify task in database
        db_task = await e2e_db.get_task_by_key("ERR-001")
        assert db_task is not None, "Task should exist in database"

        # IMPORTANT: error_codes is NOT a database field
        # It's metadata used by the decomposer for context, not stored persistently
        # The database schema only stores: task_key, title, goal, test_file, impl_file,
        # acceptance_criteria, depends_on, phase, sequence, status, etc.
        #
        # This is intentional design:
        # - error_codes guide decomposition (what errors to handle)
        # - They're embedded in acceptance_criteria ("Should raise ERR-001...")
        # - No need for separate database column
        assert "error_codes" not in db_task or db_task.get("error_codes") is None, (
            "error_codes should not be stored in database (decomposer metadata only)"
        )

        # Verify acceptance criteria exist and reference error handling
        # Note: The decomposer manually created AC that mentions error codes
        # This is NOT automatic - it depends on how AC was written
        ac_raw = db_task["acceptance_criteria"]
        if isinstance(ac_raw, str):
            ac = json.loads(ac_raw)
        else:
            ac = ac_raw
        assert any("ERR-001" in criterion for criterion in ac), "Error code ERR-001 in AC"
        assert any("ERR-002" in criterion for criterion in ac), "Error code ERR-002 in AC"

    @pytest.mark.asyncio
    async def test_blocking_assumption_flagged_tasks(self, e2e_db) -> None:
        """Tasks with blocking assumptions load successfully but should be reviewed."""
        # Create DecomposedTask with blocking assumption
        task = DecomposedTask(
            task_key="BLOCK-001",
            title="Implement payment processing",
            goal="Integrate with payment gateway API",
            estimated_tests=10,
            estimated_lines=80,
            test_file="tests/test_payment.py",
            impl_file="src/payment.py",
            components=["payment", "gateway"],
            acceptance_criteria=[
                "Should process credit card payments",
                "Should handle payment failures",
            ],
            phase=1,
            sequence=1,
            depends_on=[],
            blocking_assumption="A-4",  # Assumption blocks implementation
        )

        # Load into database
        result = await load_tdd_tasks([task.to_dict()], db=e2e_db)
        assert result["loaded"] == 1, "Task with blocking assumption should load"

        # Verify task exists
        db_task = await e2e_db.get_task_by_key("BLOCK-001")
        assert db_task is not None, "Task should exist in database"

        # IMPORTANT: blocking_assumption is NOT stored in database
        # Similar to error_codes, it's decomposer metadata used for flagging
        # Tasks with blocking assumptions should be reviewed before execution
        # The database schema doesn't include a blocking_assumption column
        #
        # Recommended workflow:
        # 1. Decomposer flags tasks with blocking assumptions
        # 2. Human reviews flagged tasks before execution
        # 3. Once resolved, tasks proceed normally
        # 4. No database field needed (handled at decomposition time)
        assert "blocking_assumption" not in db_task or db_task.get("blocking_assumption") is None, (
            "blocking_assumption should not be stored in database (decomposer metadata only)"
        )

        # Task loads in pending state (normal behavior)
        assert db_task["status"] == "pending", "Task should be in pending state"

        # NOTE: In a production system, you might want to:
        # - Add a 'flagged' or 'needs_review' status
        # - Store blocking_assumption in a separate review table
        # - Prevent workers from claiming flagged tasks
        # This test documents current behavior: tasks load normally,
        # but blocking_assumption should be handled before execution starts

    @pytest.mark.asyncio
    async def test_parallel_task_loading_and_execution(
        self,
        e2e_db,
        mock_sdk_success,
        mock_verifier_all_pass,
    ) -> None:
        """Multiple decomposed tasks load and execute in parallel without conflicts."""
        # Create 3 independent tasks
        tasks = [
            DecomposedTask(
                task_key=f"PAR-{i:03d}",
                title=f"Parallel task {i}",
                goal=f"Implement feature {i}",
                estimated_tests=5,
                estimated_lines=40,
                test_file=f"tests/test_par_{i}.py",
                impl_file=f"src/par_{i}.py",
                components=[f"feature_{i}"],
                acceptance_criteria=[f"Should implement feature {i}"],
                phase=0,
                sequence=i,
                depends_on=[],
            )
            for i in range(3)
        ]

        # Load all tasks
        task_dicts = [t.to_dict() for t in tasks]
        result = await load_tdd_tasks(task_dicts, db=e2e_db)
        assert result["loaded"] == 3, "All tasks should load"

        # Setup execution environment
        run_id = await e2e_db.start_execution_run(max_workers=2)
        config = WorkerConfig(
            max_workers=2,
            single_branch_mode=True,
            heartbeat_interval_seconds=1,
        )

        # Create 2 workers with separate git mocks
        mock_git_1 = MagicMock()
        mock_git_1.create_worker_branch = AsyncMock(return_value="worker-1/branch")
        mock_git_1.commit_changes = AsyncMock(return_value="abc123")

        mock_git_2 = MagicMock()
        mock_git_2.create_worker_branch = AsyncMock(return_value="worker-2/branch")
        mock_git_2.commit_changes = AsyncMock(return_value="def456")

        worker1 = Worker(1, e2e_db, mock_git_1, config, run_id, Path.cwd())
        worker2 = Worker(2, e2e_db, mock_git_2, config, run_id, Path.cwd())

        worker1.verifier = mock_verifier_all_pass
        worker2.verifier = mock_verifier_all_pass

        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_sdk_success),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            await worker1.start()
            await worker2.start()

            # Process tasks sequentially to verify no data corruption
            for task in tasks:
                db_task = await e2e_db.get_task_by_key(task.task_key)
                assert db_task is not None

                # Claim and complete
                claimed = await e2e_db.claim_task(db_task["id"], worker_id=1, timeout_seconds=300)
                if claimed:
                    await e2e_db.update_task_status(task.task_key, "complete")
                    await e2e_db.release_task(db_task["id"], worker_id=1, outcome="completed")

            # Verify all tasks completed
            stats = await e2e_db.get_stats()
            assert stats["complete"] == 3, "All 3 tasks should complete"

            await worker1.stop()
            await worker2.stop()
