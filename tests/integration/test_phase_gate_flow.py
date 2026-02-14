"""Integration tests for multi-phase execution with phase gates.

Exercises the full flow: real in-memory DB with tasks across multiple
phases, phase gate validation between phases, and end-of-run validation
including AC summary. Uses mocked subprocess calls (no real pytest/ruff)
but real DB queries, real PhaseGateValidator, and real RunValidator.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.worker_pool.config import PoolResult, WorkerConfig
from tdd_orchestrator.worker_pool.phase_gate import PhaseGateValidator
from tdd_orchestrator.worker_pool.pool import WorkerPool
from tdd_orchestrator.worker_pool.run_validator import RunValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_two_phase_db(db: OrchestratorDB, tmp_path: Path) -> None:
    """Populate DB with tasks across 2 phases and matching code artifacts."""
    # Phase 0: Foundation task
    await db.create_task(
        "TDD-01",
        "Config loader",
        phase=0,
        sequence=0,
        test_file="tests/test_config.py",
        impl_file="src/config.py",
        acceptance_criteria=["exports load_config function"],
    )
    # Phase 1: Feature that depends on phase 0
    await db.create_task(
        "TDD-02",
        "API endpoint",
        phase=1,
        sequence=0,
        depends_on=["TDD-01"],
        test_file="tests/test_api.py",
        impl_file="src/api.py",
        acceptance_criteria=["responds to GET /health"],
    )

    # Create real code artifacts so AST matchers can find them
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)

    (tmp_path / "src" / "config.py").write_text(
        "def load_config():\n    return {}\n"
    )
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_load_config():\n    assert load_config() == {}\n"
    )
    (tmp_path / "src" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        '@app.get("/health")\n'
        "def health():\n"
        '    return {"status": "ok"}\n'
    )
    (tmp_path / "tests" / "test_api.py").write_text(
        "def test_health():\n    pass\n"
    )


# ---------------------------------------------------------------------------
# Phase gate with real DB
# ---------------------------------------------------------------------------


class TestPhaseGateWithRealDB:
    """Phase gate validation against a real in-memory database."""

    async def test_gate_passes_when_prior_phase_complete(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Phase 1 gate passes when all phase 0 tasks are complete."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")

        gate = PhaseGateValidator(db, tmp_path)

        # Mock subprocess (batch pytest) to pass
        with patch.object(gate, "_run_command", return_value=(True, "ok")):
            result = await gate.validate_phase(1)

        assert result.passed is True
        assert result.incomplete_tasks == []

    async def test_gate_blocks_when_prior_phase_incomplete(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Phase 1 gate fails when phase 0 has pending tasks."""
        await _seed_two_phase_db(db, tmp_path)
        # TDD-01 is still "pending" (default)

        gate = PhaseGateValidator(db, tmp_path)
        result = await gate.validate_phase(1)

        assert result.passed is False
        assert "TDD-01" in result.incomplete_tasks

    async def test_gate_passes_for_first_phase(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Phase 0 gate always passes (no prior phases)."""
        await _seed_two_phase_db(db, tmp_path)

        gate = PhaseGateValidator(db, tmp_path)
        result = await gate.validate_phase(0)

        assert result.passed is True

    async def test_gate_regression_failure_blocks(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Gate fails when prior phase tests fail regression."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")

        gate = PhaseGateValidator(db, tmp_path)

        # Batch pytest fails, individual re-run also fails
        async def mock_cmd(*args: str) -> tuple[bool, str]:
            return False, "FAILED test_config.py"

        with patch.object(gate, "_run_command", side_effect=mock_cmd):
            result = await gate.validate_phase(1)

        assert result.passed is False
        assert len(result.regression_results) > 0
        assert any(not r.passed for r in result.regression_results)


# ---------------------------------------------------------------------------
# End-of-run validation with real DB
# ---------------------------------------------------------------------------


class TestRunValidatorWithRealDB:
    """End-of-run validation against a real in-memory database."""

    async def test_run_validation_passes_all_checks(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """All tasks complete + subprocess passes -> validation passed."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")
        await db.update_task_status("TDD-02", "complete")

        run_id = await db.start_execution_run(max_workers=1)
        validator = RunValidator(db, tmp_path)

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(run_id)

        assert result.passed is True
        assert result.regression_passed is True
        assert result.lint_passed is True
        assert result.type_check_passed is True
        assert result.orphaned_tasks == []

    async def test_run_validation_detects_orphaned_tasks(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Pending tasks reported as orphaned."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")
        # TDD-02 remains "pending"

        run_id = await db.start_execution_run(max_workers=1)
        validator = RunValidator(db, tmp_path)

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(run_id)

        assert result.passed is False
        assert "TDD-02" in result.orphaned_tasks

    async def test_run_validation_includes_ac_summary(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """AC validation produces non-empty summary with real code artifacts."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")
        await db.update_task_status("TDD-02", "complete")

        run_id = await db.start_execution_run(max_workers=1)
        validator = RunValidator(db, tmp_path)

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(run_id)

        # Both tasks have AC, and code artifacts exist on disk for matchers
        assert result.ac_validation_summary != ""
        assert "verifiable" in result.ac_validation_summary

    async def test_run_validation_stored_in_db(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Validation result is stored in execution_runs via update_run_validation."""
        await _seed_two_phase_db(db, tmp_path)
        await db.update_task_status("TDD-01", "complete")
        await db.update_task_status("TDD-02", "complete")

        run_id = await db.start_execution_run(max_workers=1)
        validator = RunValidator(db, tmp_path)

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(run_id)

        await db.update_run_validation(
            run_id, "passed" if result.passed else "failed", result.to_json()
        )

        # Verify stored in DB
        rows = await db.execute_query(
            "SELECT validation_status, validation_details"
            " FROM execution_runs WHERE id = ?",
            (run_id,),
        )

        assert len(rows) == 1
        assert rows[0]["validation_status"] == "passed"
        details = json.loads(str(rows[0]["validation_details"]))
        assert details["passed"] is True
        assert "ac_validation_summary" in details


# ---------------------------------------------------------------------------
# Multi-phase pool flow (mocked worker execution, real DB + gates)
# ---------------------------------------------------------------------------


class TestMultiPhasePoolFlow:
    """End-to-end multi-phase flow through WorkerPool.run_all_phases().

    Uses real DB and real phase gate / run validator, but mocks
    run_parallel_phase (since that needs SDK workers) and subprocess calls.
    """

    async def test_full_flow_two_phases_pass(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Two phases both succeed -> run_all_phases returns no stopped_reason."""
        await _seed_two_phase_db(db, tmp_path)

        pool = WorkerPool(db, tmp_path, WorkerConfig(enable_phase_gates=True))

        # Track which phases were processed
        phases_run: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            phases_run.append(phase)
            # Mark tasks complete as the phase "runs"
            if phase == 0:
                await db.update_task_status("TDD-01", "complete")
            elif phase == 1:
                await db.update_task_status("TDD-02", "complete")
            return PoolResult(
                tasks_completed=1, tasks_failed=0,
                total_invocations=5, worker_stats=[],
            )

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        # Mock subprocess calls for phase gate regression + run validator
        with (
            patch(
                "tdd_orchestrator.worker_pool.phase_gate.PhaseGateValidator._run_command",
                return_value=(True, "ok"),
            ),
            patch(
                "tdd_orchestrator.worker_pool.run_validator.RunValidator._run_command",
                return_value=(True, "ok"),
            ),
        ):
            result = await pool.run_all_phases()

        assert phases_run == [0, 1]
        assert result.tasks_completed == 2
        assert result.stopped_reason is None

    async def test_gate_blocks_second_phase_on_incomplete(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """Phase 0 tasks not completed -> phase 1 gate blocks."""
        await _seed_two_phase_db(db, tmp_path)

        pool = WorkerPool(db, tmp_path, WorkerConfig(enable_phase_gates=True))

        phases_run: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            phases_run.append(phase)
            # Phase 0 runs but does NOT mark TDD-01 complete
            return PoolResult(
                tasks_completed=0, tasks_failed=0,
                total_invocations=1, worker_stats=[],
                stopped_reason="no_tasks",
            )

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()

        # Phase 0 ran (no_tasks is non-fatal), but phase 1 gate should block
        # because TDD-01 is still pending
        assert 0 in phases_run
        assert 1 not in phases_run
        assert result.stopped_reason == "gate_failure"

    async def test_disabled_gates_skip_validation(
        self, db: OrchestratorDB, tmp_path: Path
    ) -> None:
        """enable_phase_gates=False -> phases run without gate checks."""
        await _seed_two_phase_db(db, tmp_path)

        config = WorkerConfig(enable_phase_gates=False)
        pool = WorkerPool(db, tmp_path, config)

        phases_run: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            phases_run.append(phase)
            if phase == 0:
                await db.update_task_status("TDD-01", "complete")
            elif phase == 1:
                await db.update_task_status("TDD-02", "complete")
            return PoolResult(
                tasks_completed=1, tasks_failed=0,
                total_invocations=5, worker_stats=[],
            )

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        with patch(
            "tdd_orchestrator.worker_pool.run_validator.RunValidator._run_command",
            return_value=(True, "ok"),
        ):
            result = await pool.run_all_phases()

        assert phases_run == [0, 1]
        assert result.tasks_completed == 2
        assert result.stopped_reason is None
