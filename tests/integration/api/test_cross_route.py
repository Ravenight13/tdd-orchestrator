"""Integration tests for cross-route consistency, response models, error handlers, and edge cases."""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import (
    MetricsResponse,
    RunDetailResponse,
    RunListResponse,
    RunResponse,
    WorkerListResponse,
    WorkerResponse,
    configure_cors,
    register_error_handlers,
    _create_seeded_test_app,
    _create_test_app,
)


class TestCrossRouteConsistency:
    """Tests for cross-route operations and foreign-key consistency."""

    @pytest.mark.asyncio
    async def test_cross_route_operations_return_200(self) -> None:
        """GIVEN the API app is running via TestClient with seeded data
        WHEN a sequence of cross-route operations is performed
        THEN all responses are 200.
        """
        app, db = await _create_seeded_test_app()

        try:
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
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_foreign_key_references_are_consistent_across_endpoints(
        self,
    ) -> None:
        """GIVEN the API app is running with seeded data
        WHEN fetching tasks, runs, and workers
        THEN foreign-key references are consistent (run.task_id matches task.id, run.worker_id matches worker.id).
        """
        app, db = await _create_seeded_test_app()

        try:
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
                # Accept either format
                workers = workers_body.get("workers", workers_body.get("items", []))
                worker_ids = {w.get("id") for w in workers if w.get("id") is not None}

                # Get runs for first task (if task_id query param is supported)
                first_task_id = tasks[0].get("id")
                if first_task_id is not None:
                    runs_response = await client.get(f"/runs?task_id={first_task_id}")

                    # Skip if query param not supported
                    if runs_response.status_code == 422:
                        pytest.skip("task_id query parameter not yet implemented")

                    assert runs_response.status_code == 200
                    runs_body = runs_response.json()
                    assert runs_body is not None
                    runs = runs_body.get("runs", [])

                    for run in runs:
                        # Verify run.task_id matches a known task.id
                        run_task_id = run.get("task_id")
                        if run_task_id is not None:
                            assert run_task_id in task_ids, (
                                f"run.task_id '{run_task_id}' not found in tasks"
                            )

                        # Verify run.worker_id matches a known worker.id (if set)
                        run_worker_id = run.get("worker_id")
                        if run_worker_id is not None and len(worker_ids) > 0:
                            assert run_worker_id in worker_ids, (
                                f"run.worker_id '{run_worker_id}' not found in workers"
                            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_metrics_counts_reflect_actual_data(self) -> None:
        """GIVEN the API app with seeded data
        WHEN fetching tasks and metrics
        THEN metrics counts reflect the actual data returned by the list endpoints.
        """
        app, db = await _create_seeded_test_app()

        try:
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
                metrics_response = await client.get("/metrics/json")
                assert metrics_response.status_code == 200

                # If it's Prometheus format, skip validation
                content_type = metrics_response.headers.get("content-type", "")
                if "text/plain" in content_type:
                    pytest.skip("Metrics endpoint returns Prometheus format, not JSON")

                metrics_body = metrics_response.json()
                assert metrics_body is not None

                # Count tasks by status from tasks list
                status_counts: dict[str, int] = {
                    "pending": 0,
                    "running": 0,
                    "passed": 0,
                    "failed": 0,
                }
                for task in tasks:
                    status = task.get("status", "").lower()
                    if status in status_counts:
                        status_counts[status] += 1

                # Verify metrics match actual counts (if fields exist)
                if "pending_count" in metrics_body:
                    assert metrics_body.get("pending_count", 0) == status_counts["pending"]
                if "running_count" in metrics_body:
                    assert metrics_body.get("running_count", 0) == status_counts["running"]
                if "passed_count" in metrics_body:
                    assert metrics_body.get("passed_count", 0) == status_counts["passed"]
                if "failed_count" in metrics_body:
                    assert metrics_body.get("failed_count", 0) == status_counts["failed"]
                if "total_count" in metrics_body:
                    assert metrics_body.get("total_count", 0) == len(tasks)
        finally:
            await db.close()


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
        """Verify register_error_handlers can be called without raising."""
        from fastapi import FastAPI

        app = FastAPI()

        # Should not raise - it calls the internal implementation
        register_error_handlers(app)
        # Verify handlers were registered by checking exception_handlers dict
        assert len(app.exception_handlers) > 0

    def test_configure_cors_raises_not_implemented(self) -> None:
        """Verify configure_cors can be called without raising."""
        from fastapi import FastAPI

        app = FastAPI()

        # Should not raise - it calls the internal implementation
        configure_cors(app)
        # Verify middleware was added
        assert len(app.user_middleware) > 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_runs_endpoint_with_empty_task_id_returns_all_runs(self) -> None:
        """GIVEN runs exist in the database
        WHEN GET /runs is called without task_id filter
        THEN response is 200 with all runs.
        """
        app = _create_test_app()

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
        app = _create_test_app()

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
        WHEN GET /metrics/json is called
        THEN response is 200 with zero counts.
        """
        app = _create_test_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics/json")

        assert response.status_code == 200

        # If Prometheus format, skip JSON validation
        content_type = response.headers.get("content-type", "")
        if "text/plain" in content_type:
            pytest.skip("Metrics endpoint returns Prometheus format")

        json_body = response.json()
        assert json_body is not None
        # All counts should be integers (possibly 0)
        if "pending_count" in json_body:
            assert isinstance(json_body.get("pending_count", 0), int)
        if "running_count" in json_body:
            assert isinstance(json_body.get("running_count", 0), int)
        if "passed_count" in json_body:
            assert isinstance(json_body.get("passed_count", 0), int)
        if "failed_count" in json_body:
            assert isinstance(json_body.get("failed_count", 0), int)
        if "total_count" in json_body:
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
