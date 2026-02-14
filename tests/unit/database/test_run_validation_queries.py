"""Tests for update_run_validation() in RunsMixin.

Verifies that validation_status and validation_details are stored
correctly on execution_runs rows.
"""

from __future__ import annotations

from tdd_orchestrator.database.singleton import get_db


class TestUpdateRunValidation:
    """Tests for update_run_validation()."""

    async def test_stores_passed_result(self) -> None:
        """validation_status='passed' stored correctly."""
        db = await get_db()
        assert db._conn is not None

        run_id = await db.start_execution_run(max_workers=2)
        await db.update_run_validation(run_id, "passed", '{"summary": "ok"}')

        rows = await db.execute_query(
            "SELECT validation_status, validation_details FROM execution_runs WHERE id = ?",
            (run_id,),
        )
        assert len(rows) == 1
        assert rows[0]["validation_status"] == "passed"
        assert rows[0]["validation_details"] == '{"summary": "ok"}'

    async def test_stores_failed_result(self) -> None:
        """validation_status='failed' stored correctly."""
        db = await get_db()
        assert db._conn is not None

        run_id = await db.start_execution_run(max_workers=2)
        await db.update_run_validation(run_id, "failed", '{"errors": ["lint"]}')

        rows = await db.execute_query(
            "SELECT validation_status, validation_details FROM execution_runs WHERE id = ?",
            (run_id,),
        )
        assert len(rows) == 1
        assert rows[0]["validation_status"] == "failed"
        assert rows[0]["validation_details"] == '{"errors": ["lint"]}'

    async def test_overwrites_previous_validation(self) -> None:
        """Calling update_run_validation twice overwrites the first result."""
        db = await get_db()
        assert db._conn is not None

        run_id = await db.start_execution_run(max_workers=2)
        await db.update_run_validation(run_id, "failed", '{"v": 1}')
        await db.update_run_validation(run_id, "passed", '{"v": 2}')

        rows = await db.execute_query(
            "SELECT validation_status, validation_details FROM execution_runs WHERE id = ?",
            (run_id,),
        )
        assert rows[0]["validation_status"] == "passed"
        assert rows[0]["validation_details"] == '{"v": 2}'
