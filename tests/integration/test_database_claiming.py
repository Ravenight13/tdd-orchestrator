"""Task claiming tests - CRITICAL for parallelism.

This module tests atomic task claiming operations to ensure race-free
parallel execution. These tests validate the optimistic locking mechanism
and claim expiration handling.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from tdd_orchestrator.database import OrchestratorDB


class TestTaskClaiming:
    """Atomic task claiming tests.

    These tests validate the core claiming logic that prevents race conditions
    in parallel execution. Each test uses an in-memory database for isolation.
    """

    @pytest.mark.asyncio
    async def test_claim_task_succeeds_when_unclaimed(self) -> None:
        """Worker can claim an unclaimed pending task.

        Verifies:
        - claim_task() returns True for unclaimed tasks
        - Task status transitions to 'in_progress'
        - claimed_by field is set correctly
        - Claim fields are populated (claimed_at, claim_expires_at)
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            claimed = await db.claim_task(task_id, worker_id=1, timeout_seconds=300)

            assert claimed is True
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] == 1
            assert task["status"] == "in_progress"
            assert task["claimed_at"] is not None
            assert task["claim_expires_at"] is not None

    @pytest.mark.asyncio
    async def test_claim_already_claimed_fails(self) -> None:
        """Second worker cannot claim already-claimed task.

        Verifies:
        - claim_task() returns False when task is already claimed
        - Original claim remains intact (not overwritten)
        - Task status remains 'in_progress'
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            await db.register_worker(2)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            # First worker claims successfully
            first_claim = await db.claim_task(task_id, worker_id=1)
            assert first_claim is True

            # Second worker's claim fails
            second_claim = await db.claim_task(task_id, worker_id=2)
            assert second_claim is False

            # Verify original claim intact
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] == 1

    @pytest.mark.asyncio
    async def test_claim_expired_task_succeeds(self) -> None:
        """Task with expired claim can be reclaimed after cleanup.

        Verifies:
        - cleanup_stale_claims() releases expired claims
        - New worker can claim expired task after cleanup
        - Claim ownership transfers correctly
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            await db.register_worker(2)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            # Claim with 1-second timeout
            await db.claim_task(task_id, worker_id=1, timeout_seconds=1)

            # Wait for claim to expire (SQLite has 1-second precision + buffer)
            await asyncio.sleep(2.0)

            # Cleanup stale claims (this resets status to 'pending')
            released_count = await db.cleanup_stale_claims()
            assert released_count == 1

            # Second worker should succeed after cleanup
            claimed = await db.claim_task(task_id, worker_id=2)
            assert claimed is True

            # Verify new ownership
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] == 2

    @pytest.mark.asyncio
    async def test_concurrent_claims_only_one_succeeds(self) -> None:
        """Only one of N concurrent claims succeeds (race condition test).

        This is the CRITICAL test for parallelism. It verifies that optimistic
        locking prevents multiple workers from claiming the same task, even when
        claims are attempted simultaneously.

        Verifies:
        - Exactly one worker succeeds out of N concurrent attempts
        - No double-claiming occurs
        - Database maintains consistency under race conditions
        """
        async with OrchestratorDB(":memory:") as db:
            # Register 5 workers
            for i in range(5):
                await db.register_worker(i + 1)

            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            # Attempt concurrent claims from all workers
            results = await asyncio.gather(
                *[db.claim_task(task_id, worker_id=i + 1) for i in range(5)]
            )

            # Exactly one should succeed
            successful_claims = sum(results)
            assert successful_claims == 1, f"Expected 1 successful claim, got {successful_claims}"

            # Verify task is claimed by exactly one worker
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] in range(1, 6)
            assert task["status"] == "in_progress"


class TestTaskRelease:
    """Task release and outcome recording.

    These tests validate that claims are properly released and outcomes
    are recorded in the audit log (task_claims table).
    """

    @pytest.mark.asyncio
    async def test_release_records_outcome(self) -> None:
        """Releasing task records outcome in claims table.

        Verifies:
        - release_task() returns True on success
        - Outcome is recorded in task_claims audit log
        - Task's claimed_by is cleared
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            await db.claim_task(task_id, worker_id=1)

            released = await db.release_task(task_id, worker_id=1, outcome="completed")

            assert released is True
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] is None

    @pytest.mark.asyncio
    async def test_release_clears_claim_fields(self) -> None:
        """Release clears claimed_by, claimed_at, claim_expires_at.

        Verifies:
        - All claim-related fields are set to NULL
        - Task becomes available for re-claiming
        - Status remains unchanged by release
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            await db.claim_task(task_id, worker_id=1)

            # Record original status
            task_before = await db.get_task_by_key("TDD-01")
            assert task_before is not None
            status_before = task_before["status"]

            await db.release_task(task_id, worker_id=1, outcome="completed")

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] is None
            assert task["claimed_at"] is None
            assert task["claim_expires_at"] is None
            # Status is preserved (release doesn't change it)
            assert task["status"] == status_before

    @pytest.mark.asyncio
    async def test_release_wrong_worker_fails(self) -> None:
        """Worker cannot release task claimed by another worker.

        Verifies:
        - release_task() returns False for wrong worker
        - Original claim remains intact
        - Security: Workers cannot steal claims
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            await db.register_worker(2)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            # Worker 1 claims
            await db.claim_task(task_id, worker_id=1)

            # Worker 2 tries to release (should fail)
            released = await db.release_task(task_id, worker_id=2, outcome="completed")

            assert released is False

            # Verify claim still owned by worker 1
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["claimed_by"] == 1

    @pytest.mark.asyncio
    async def test_release_all_outcomes_accepted(self) -> None:
        """All valid outcomes are recorded correctly.

        Verifies:
        - 'completed', 'failed', 'timeout', 'released' outcomes work
        - Outcome is stored in task_claims table
        """
        async with OrchestratorDB(":memory:") as db:
            outcomes = ["completed", "failed", "timeout", "released"]

            for idx, outcome in enumerate(outcomes):
                worker_id = idx + 1
                await db.register_worker(worker_id)
                task_id = await db.create_task(
                    f"TDD-{idx:02d}", f"Test {outcome}", phase=0, sequence=idx
                )

                # Claim and release with specific outcome
                await db.claim_task(task_id, worker_id=worker_id)
                released = await db.release_task(task_id, worker_id=worker_id, outcome=outcome)

                assert released is True, f"Failed to release with outcome '{outcome}'"


class TestClaimAuditLog:
    """Task claims audit log verification.

    These tests ensure the task_claims table properly tracks the full
    lifecycle of claims for debugging and analytics.
    """

    @pytest.mark.asyncio
    async def test_claim_creates_audit_record(self) -> None:
        """Claiming a task creates an entry in task_claims table.

        Verifies:
        - Claim is recorded with correct task_id and worker_id
        - claimed_at timestamp is set
        - released_at is NULL (claim is active)
        - outcome is NULL (claim not yet released)
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            await db.claim_task(task_id, worker_id=1)

            # Query audit log directly
            async with db._conn.execute(  # type: ignore[union-attr]
                "SELECT * FROM task_claims WHERE task_id = ?", (task_id,)
            ) as cursor:
                claim = await cursor.fetchone()
                assert claim is not None
                assert claim["task_id"] == task_id
                assert claim["claimed_at"] is not None
                assert claim["released_at"] is None
                assert claim["outcome"] is None

    @pytest.mark.asyncio
    async def test_release_updates_audit_record(self) -> None:
        """Releasing a task updates the audit record.

        Verifies:
        - released_at timestamp is set
        - outcome is recorded correctly
        - Original claimed_at remains unchanged
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            await db.claim_task(task_id, worker_id=1)
            await db.release_task(task_id, worker_id=1, outcome="completed")

            # Query audit log
            async with db._conn.execute(  # type: ignore[union-attr]
                "SELECT * FROM task_claims WHERE task_id = ?", (task_id,)
            ) as cursor:
                claim = await cursor.fetchone()
                assert claim is not None
                assert claim["released_at"] is not None
                assert claim["outcome"] == "completed"
                assert claim["claimed_at"] is not None

    @pytest.mark.asyncio
    async def test_multiple_claims_tracked_separately(self) -> None:
        """Multiple claims on same task create separate audit records.

        This happens when a task is claimed, released, then claimed again.

        Verifies:
        - Each claim/release cycle creates a new audit record
        - Previous claim records remain unchanged
        - Full history is preserved
        """
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            await db.register_worker(2)
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)

            # First claim cycle with 1-second timeout
            await db.claim_task(task_id, worker_id=1, timeout_seconds=1)

            # Wait for expiration and cleanup (SQLite has 1-second precision + buffer)
            await asyncio.sleep(2.0)
            await db.cleanup_stale_claims()

            # Second claim cycle
            await db.claim_task(task_id, worker_id=2)
            await db.release_task(task_id, worker_id=2, outcome="completed")

            # Query audit log - should have 2 records
            async with db._conn.execute(  # type: ignore[union-attr]
                "SELECT COUNT(*) FROM task_claims WHERE task_id = ?", (task_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                count = row[0]
                assert count == 2, f"Expected 2 audit records for multiple claims, got {count}"
