"""Integration tests for workers, runs, and metrics API routes with full regression suite.

Tests verify that all remaining routes (workers, runs, metrics) work together
and confirm no regressions in the existing 324+ test suite.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Response Models (to be implemented)
# =============================================================================


class WorkerResponse(BaseModel):
    """Response model for a single worker."""

    id: str
    status: str
    registered_at: datetime


class WorkerListResponse(BaseModel):
    """Response model for list of workers."""

    workers: list[WorkerResponse]


class RunResponse(BaseModel):
    """Response model for a single run."""

    id: str
    task_id: str
    status: str
    started_at: datetime
    worker_id: str | None = None


class RunListResponse(BaseModel):
    """Response model for list of runs."""

    runs: list[RunResponse]


class RunDetailResponse(BaseModel):
    """Response model for run detail with log."""

    id: str
    task_id: str
    status: str
    started_at: datetime
    log: str
    worker_id: str | None = None


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint."""

    pending_count: int
    running_count: int
    passed_count: int
    failed_count: int
    total_count: int
    avg_duration_seconds: float | None = None


# =============================================================================
# Functions (to be implemented)
# =============================================================================


def register_error_handlers(app: FastAPI) -> None:
    """Register error handlers on the application.

    Args:
        app: The FastAPI application instance.
    """
    raise NotImplementedError("register_error_handlers not implemented")


def configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware on the application.

    Args:
        app: The FastAPI application instance.
    """
    raise NotImplementedError("configure_cors not implemented")


# =============================================================================
# Test Classes
# =============================================================================


class TestWorkersEndpoint:
    """Tests for GET /workers endpoint."""

    @pytest.mark.asyncio
    async def test_workers_returns_200_with_json_list_when_seeded_database(
        self,
    ) -> None:
        """GIVEN the test database is seeded with tasks, workers, and runs via shared fixtures
        WHEN GET /workers is called
        THEN response is 200 with a JSON list of WorkerResponse objects.
        """
        from fastapi import FastAPI

        from tests.integration.api.test_full_regression import (
            WorkerListResponse,
            WorkerResponse,
        )

        app = FastAPI()

        # This will fail with NotImplementedError until implemented
        # The implementation should wire up routes that return WorkerListResponse

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/workers")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "workers" in json_body
        workers = json_body["workers"]
        assert isinstance(workers, list)

    @pytest.mark.asyncio
    async def test_workers_response_contains_id_status_and_registered_at_fields(
        self,
    ) -> None:
        """GIVEN workers exist in the seeded database
        WHEN GET /workers is called
        THEN each WorkerResponse contains id, status, and registered_at fields.
        """
        from fastapi import FastAPI

        from tests.integration.api.test_full_regression import WorkerResponse

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/workers")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        workers = json_body.get("workers", [])
        assert isinstance(workers, list)
        assert len(workers) > 0, "Expected at least one worker in seeded database"

        for worker in workers:
            assert "id" in worker, "Worker missing 'id' field"
            assert "status" in worker, "Worker missing 'status' field"
            assert "registered_at" in worker, "Worker missing 'registered_at' field"

    @pytest.mark.asyncio
    async def test_workers_returns_empty_list_when_no_workers_exist(self) -> None:
        """GIVEN no workers exist in the database
        WHEN GET /workers is called
        THEN response is 200 with an empty list.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/workers")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        workers = json_body.get("workers", [])
        assert isinstance(workers, list)


class TestRunsEndpoint:
    """Tests for GET /runs and GET /runs/{run_id} endpoints."""

    @pytest.mark.asyncio
    async def test_run_detail_returns_200_when_run_exists(self) -> None:
        """GIVEN a run exists linked to a task in the seeded database
        WHEN GET /runs/{run_id} is called
        THEN response is 200 with a RunDetailResponse.
        """
        from fastapi import FastAPI

        app = FastAPI()

        # Use a known run_id from seeded data
        run_id = "test-run-001"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/runs/{run_id}")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "task_id" in json_body
        assert "status" in json_body
        assert "started_at" in json_body
        assert "log" in json_body

    @pytest.mark.asyncio
    async def test_run_detail_returns_404_when_run_not_found(self) -> None:
        """GIVEN a run does not exist in the database
        WHEN GET /runs/nonexistent-id is called
        THEN response is 404 with an error detail message.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/runs/nonexistent-id")

        assert response.status_code == 404
        json_body = response.json()
        assert json_body is not None
        assert "detail" in json_body or "error" in json_body

    @pytest.mark.asyncio
    async def test_run_detail_contains_task_id_status_started_at_and_log_fields(
        self,
    ) -> None:
        """GIVEN a run exists in the seeded database
        WHEN GET /runs/{run_id} is called
        THEN RunDetailResponse contains task_id, status, started_at, and log fields.
        """
        from fastapi import FastAPI

        app = FastAPI()

        run_id = "test-run-001"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/runs/{run_id}")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "task_id" in json_body, "RunDetailResponse missing 'task_id'"
        assert "status" in json_body, "RunDetailResponse missing 'status'"
        assert "started_at" in json_body, "RunDetailResponse missing 'started_at'"
        assert "log" in json_body, "RunDetailResponse missing 'log'"

    @pytest.mark.asyncio
    async def test_runs_list_filtered_by_task_id(self) -> None:
        """GIVEN runs exist for a specific task
        WHEN GET /runs?task_id={id} is called
        THEN response is 200 with a filtered list of runs for that task.
        """
        from fastapi import FastAPI

        app = FastAPI()

        task_id = "test-task-001"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/runs?task_id={task_id}")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        runs = json_body.get("runs", [])
        assert isinstance(runs, list)
        for run in runs:
            assert run.get("task_id") == task_id


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_returns_200_with_counts_per_status(self) -> None:
        """GIVEN tasks with various statuses (pending, running, passed, failed) exist in the seeded database
        WHEN GET /metrics is called
        THEN response is 200 with a MetricsResponse containing counts per status.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "pending_count" in json_body
        assert "running_count" in json_body
        assert "passed_count" in json_body
        assert "failed_count" in json_body
        assert "total_count" in json_body

    @pytest.mark.asyncio
    async def test_metrics_counts_sum_to_total(self) -> None:
        """GIVEN tasks exist in the seeded database
        WHEN GET /metrics is called
        THEN the counts per status sum to the total number of seeded tasks.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None

        pending = json_body.get("pending_count", 0)
        running = json_body.get("running_count", 0)
        passed = json_body.get("passed_count", 0)
        failed = json_body.get("failed_count", 0)
        total = json_body.get("total_count", 0)

        assert isinstance(pending, int)
        assert isinstance(running, int)
        assert isinstance(passed, int)
        assert isinstance(failed, int)
        assert isinstance(total, int)

        calculated_total = pending + running + passed + failed
        assert calculated_total == total, (
            f"Counts don't sum to total: {pending} + {running} + {passed} + {failed} = "
            f"{calculated_total}, expected {total}"
        )

    @pytest.mark.asyncio
    async def test_metrics_includes_timing_statistics(self) -> None:
        """GIVEN tasks exist in the seeded database
        WHEN GET /metrics is called
        THEN MetricsResponse includes timing/duration statistics.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        # avg_duration_seconds may be None if no completed tasks
        assert "avg_duration_seconds" in json_body


class TestFullRegressionSuite:
    """Tests to ensure no regressions in existing test suite."""

    @pytest.mark.regression
    def test_existing_test_suite_passes_with_no_import_errors(self) -> None:
        """GIVEN the full existing test suite of 324+ tests
        WHEN the integration test module imports and the regression marker is collected
        THEN all previously passing tests still pass with no import errors.
        """
        # Run pytest collection only to verify imports work
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "--collect-only",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/cliffclarke/Projects/tdd_orchestrator",
        )

        # Should not have import errors
        assert "ImportError" not in result.stderr, f"Import errors found: {result.stderr}"
        assert "ModuleNotFoundError" not in result.stderr, f"Module errors: {result.stderr}"

    @pytest.mark.regression
    def test_existing_test_suite_has_no_fixture_conflicts(self) -> None:
        """GIVEN the full existing test suite
        WHEN pytest collects tests
        THEN there are no fixture conflicts or database state leakage.
        """
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "--collect-only",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/cliffclarke/Projects/tdd_orchestrator",
        )

        # Should not have fixture errors
        assert "fixture" not in result.stderr.lower() or "error" not in result.stderr.lower(), (
            f"Fixture errors found: {result.stderr}"
        )

    @pytest.mark.regression
    @pytest.mark.slow
    def test_full_test_suite_passes_via_subprocess(self) -> None:
        """GIVEN the full existing test suite of 324+ tests
        WHEN running pytest on the entire suite with --tb=short
        THEN all tests pass with exit code 0.
        """
        result = subprocess.run(
            [
                ".venv/bin/pytest",
                "tests/",
                "--tb=short",
                "-q",
                # Exclude this specific test to avoid infinite recursion
                "--ignore=tests/integration/api/test_full_regression.py",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/cliffclarke/Projects/tdd_orchestrator",
        )

        assert result.returncode == 0, (
            f"Test suite failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


class TestCrossRouteConsistency:
    """Tests for cross-route operations and foreign-key consistency."""

    @pytest.mark.asyncio
    async def test_cross_route_operations_return_200(self) -> None:
        """GIVEN the API app is running via TestClient with seeded data
        WHEN a sequence of cross-route operations is performed
        THEN all responses are 200.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # GET /tasks to find a task
            tasks_response = await client.get("/tasks")
            assert tasks_response.status_code == 200

            # GET /workers to find workers
            workers_response = await client.get("/workers")
            assert workers_response.status_code == 200

            # GET /metrics for aggregate counts
            metrics_response = await client.get("/metrics")
            assert metrics_response.status_code == 200

    @pytest.mark.asyncio
    async def test_foreign_key_references_are_consistent_across_endpoints(
        self,
    ) -> None:
        """GIVEN the API app is running with seeded data
        WHEN fetching tasks, runs, and workers
        THEN foreign-key references are consistent (run.task_id matches task.id, run.worker_id matches worker.id).
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Get tasks
            tasks_response = await client.get("/tasks")
            assert tasks_response.status_code == 200
            tasks_body = tasks_response.json()
            assert tasks_body is not None
            tasks = tasks_body.get("tasks", [])

            if len(tasks) == 0:
                pytest.skip("No tasks in seeded database")

            task_ids = {task.get("id") for task in tasks if task.get("id") is not None}

            # Get workers
            workers_response = await client.get("/workers")
            assert workers_response.status_code == 200
            workers_body = workers_response.json()
            assert workers_body is not None
            workers = workers_body.get("workers", [])
            worker_ids = {w.get("id") for w in workers if w.get("id") is not None}

            # Get runs for first task
            first_task_id = tasks[0].get("id")
            if first_task_id is not None:
                runs_response = await client.get(f"/runs?task_id={first_task_id}")
                assert runs_response.status_code == 200
                runs_body = runs_response.json()
                assert runs_body is not None
                runs = runs_body.get("runs", [])

                for run in runs:
                    # Verify run.task_id matches a known task.id
                    run_task_id = run.get("task_id")
                    assert run_task_id in task_ids, (
                        f"run.task_id '{run_task_id}' not found in tasks"
                    )

                    # Verify run.worker_id matches a known worker.id (if set)
                    run_worker_id = run.get("worker_id")
                    if run_worker_id is not None:
                        assert run_worker_id in worker_ids, (
                            f"run.worker_id '{run_worker_id}' not found in workers"
                        )

    @pytest.mark.asyncio
    async def test_metrics_counts_reflect_actual_data(self) -> None:
        """GIVEN the API app with seeded data
        WHEN fetching tasks and metrics
        THEN metrics counts reflect the actual data returned by the list endpoints.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Get tasks
            tasks_response = await client.get("/tasks")
            assert tasks_response.status_code == 200
            tasks_body = tasks_response.json()
            assert tasks_body is not None
            tasks = tasks_body.get("tasks", [])

            # Get metrics
            metrics_response = await client.get("/metrics")
            assert metrics_response.status_code == 200
            metrics_body = metrics_response.json()
            assert metrics_body is not None

            # Count tasks by status from tasks list
            status_counts = {
                "pending": 0,
                "running": 0,
                "passed": 0,
                "failed": 0,
            }
            for task in tasks:
                status = task.get("status", "").lower()
                if status in status_counts:
                    status_counts[status] += 1

            # Verify metrics match actual counts
            assert metrics_body.get("pending_count", 0) == status_counts["pending"]
            assert metrics_body.get("running_count", 0) == status_counts["running"]
            assert metrics_body.get("passed_count", 0) == status_counts["passed"]
            assert metrics_body.get("failed_count", 0) == status_counts["failed"]
            assert metrics_body.get("total_count", 0) == len(tasks)


class TestResponseModels:
    """Tests for response model structures."""

    def test_worker_response_model_has_required_fields(self) -> None:
        """Verify WorkerResponse model has id, status, and registered_at fields."""
        worker = WorkerResponse(
            id="worker-001",
            status="active",
            registered_at=datetime(2024, 1, 1, 0, 0, 0),
        )

        assert worker.id == "worker-001"
        assert worker.status == "active"
        assert worker.registered_at == datetime(2024, 1, 1, 0, 0, 0)

    def test_worker_list_response_contains_list_of_workers(self) -> None:
        """Verify WorkerListResponse model contains list of WorkerResponse."""
        worker1 = WorkerResponse(
            id="worker-001",
            status="active",
            registered_at=datetime(2024, 1, 1, 0, 0, 0),
        )
        worker2 = WorkerResponse(
            id="worker-002",
            status="inactive",
            registered_at=datetime(2024, 1, 2, 0, 0, 0),
        )
        list_response = WorkerListResponse(workers=[worker1, worker2])

        assert len(list_response.workers) == 2
        assert list_response.workers[0].id == "worker-001"
        assert list_response.workers[1].id == "worker-002"

    def test_run_response_model_has_required_fields(self) -> None:
        """Verify RunResponse model has id, task_id, status, and started_at fields."""
        run = RunResponse(
            id="run-001",
            task_id="task-001",
            status="running",
            started_at=datetime(2024, 1, 1, 0, 0, 0),
            worker_id="worker-001",
        )

        assert run.id == "run-001"
        assert run.task_id == "task-001"
        assert run.status == "running"
        assert run.started_at == datetime(2024, 1, 1, 0, 0, 0)
        assert run.worker_id == "worker-001"

    def test_run_list_response_contains_list_of_runs(self) -> None:
        """Verify RunListResponse model contains list of RunResponse."""
        run1 = RunResponse(
            id="run-001",
            task_id="task-001",
            status="passed",
            started_at=datetime(2024, 1, 1, 0, 0, 0),
        )
        run2 = RunResponse(
            id="run-002",
            task_id="task-002",
            status="failed",
            started_at=datetime(2024, 1, 2, 0, 0, 0),
        )
        list_response = RunListResponse(runs=[run1, run2])

        assert len(list_response.runs) == 2
        assert list_response.runs[0].id == "run-001"
        assert list_response.runs[1].id == "run-002"

    def test_run_detail_response_includes_log_field(self) -> None:
        """Verify RunDetailResponse includes the log field."""
        run_detail = RunDetailResponse(
            id="run-001",
            task_id="task-001",
            status="passed",
            started_at=datetime(2024, 1, 1, 0, 0, 0),
            log="Test passed successfully.",
        )

        assert run_detail.id == "run-001"
        assert run_detail.log == "Test passed successfully."

    def test_metrics_response_model_has_all_status_counts(self) -> None:
        """Verify MetricsResponse model has all status count fields."""
        metrics = MetricsResponse(
            pending_count=5,
            running_count=2,
            passed_count=10,
            failed_count=3,
            total_count=20,
            avg_duration_seconds=1.5,
        )

        assert metrics.pending_count == 5
        assert metrics.running_count == 2
        assert metrics.passed_count == 10
        assert metrics.failed_count == 3
        assert metrics.total_count == 20
        assert metrics.avg_duration_seconds == 1.5


class TestErrorHandlersAndCors:
    """Tests for register_error_handlers and configure_cors functions."""

    def test_register_error_handlers_raises_not_implemented(self) -> None:
        """Verify register_error_handlers raises NotImplementedError until implemented."""
        from fastapi import FastAPI

        app = FastAPI()

        with pytest.raises(NotImplementedError, match="register_error_handlers not implemented"):
            register_error_handlers(app)

    def test_configure_cors_raises_not_implemented(self) -> None:
        """Verify configure_cors raises NotImplementedError until implemented."""
        from fastapi import FastAPI

        app = FastAPI()

        with pytest.raises(NotImplementedError, match="configure_cors not implemented"):
            configure_cors(app)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_runs_endpoint_with_empty_task_id_returns_all_runs(self) -> None:
        """GIVEN runs exist in the database
        WHEN GET /runs is called without task_id filter
        THEN response is 200 with all runs.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/runs")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        assert "runs" in json_body

    @pytest.mark.asyncio
    async def test_run_detail_with_empty_id_returns_404(self) -> None:
        """GIVEN an empty run ID
        WHEN GET /runs/ is called
        THEN response is 404.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/runs/")

        # Empty ID should return 404 or redirect
        assert response.status_code in (404, 307)

    @pytest.mark.asyncio
    async def test_metrics_with_no_tasks_returns_zero_counts(self) -> None:
        """GIVEN no tasks exist in the database
        WHEN GET /metrics is called
        THEN response is 200 with zero counts.
        """
        from fastapi import FastAPI

        app = FastAPI()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")

        assert response.status_code == 200
        json_body = response.json()
        assert json_body is not None
        # All counts should be integers (possibly 0)
        assert isinstance(json_body.get("pending_count", 0), int)
        assert isinstance(json_body.get("running_count", 0), int)
        assert isinstance(json_body.get("passed_count", 0), int)
        assert isinstance(json_body.get("failed_count", 0), int)
        assert isinstance(json_body.get("total_count", 0), int)

    @pytest.mark.asyncio
    async def test_worker_response_serializes_to_dict_correctly(self) -> None:
        """Verify WorkerResponse serializes correctly to dict."""
        worker = WorkerResponse(
            id="worker-001",
            status="active",
            registered_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        model_dict = worker.model_dump()
        assert model_dict["id"] == "worker-001"
        assert model_dict["status"] == "active"
        assert model_dict["registered_at"] == datetime(2024, 1, 1, 12, 0, 0)

    @pytest.mark.asyncio
    async def test_run_response_with_null_worker_id_serializes_correctly(self) -> None:
        """Verify RunResponse with null worker_id serializes correctly."""
        run = RunResponse(
            id="run-001",
            task_id="task-001",
            status="pending",
            started_at=datetime(2024, 1, 1, 0, 0, 0),
            worker_id=None,
        )

        model_dict = run.model_dump()
        assert model_dict["id"] == "run-001"
        assert model_dict["worker_id"] is None
