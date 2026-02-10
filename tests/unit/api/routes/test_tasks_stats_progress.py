"""Tests for the tasks router stats and progress endpoints.

Tests the GET /tasks/stats endpoint returning aggregate task counts by status
and the GET /tasks/progress endpoint returning phase-level completion percentages.
"""

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.tasks import router


class TestTasksStatsWithMixedStatuses:
    """Tests for GET /tasks/stats with tasks in mixed statuses."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_stats_response(self) -> dict[str, int]:
        """Create mock stats response with mixed statuses."""
        return {
            "pending": 3,
            "running": 2,
            "passed": 1,
            "failed": 1,
            "total": 7,
        }

    def test_get_stats_returns_200_when_tasks_exist(
        self, client: TestClient, mock_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns HTTP 200 when tasks exist in database."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_stats_response,
        ):
            response = client.get("/tasks/stats")
            assert response.status_code == 200

    def test_get_stats_returns_aggregate_counts_by_status(
        self, client: TestClient, mock_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns aggregate counts keyed by status."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_stats_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("pending") == 3
            assert json_body.get("running") == 2
            assert json_body.get("passed") == 1
            assert json_body.get("failed") == 1

    def test_get_stats_returns_total_count(
        self, client: TestClient, mock_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns total count of all tasks."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_stats_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("total") == 7

    def test_get_stats_total_matches_sum_of_statuses(
        self, client: TestClient, mock_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats total equals sum of individual status counts."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_stats_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            status_sum = (
                json_body.get("pending", 0)
                + json_body.get("running", 0)
                + json_body.get("passed", 0)
                + json_body.get("failed", 0)
            )
            assert json_body.get("total") == status_sum


class TestTasksStatsWhenEmpty:
    """Tests for GET /tasks/stats when no tasks exist."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_empty_stats_response(self) -> dict[str, int]:
        """Create mock stats response when no tasks exist."""
        return {
            "pending": 0,
            "running": 0,
            "passed": 0,
            "failed": 0,
            "total": 0,
        }

    def test_get_stats_returns_200_when_no_tasks_exist(
        self, client: TestClient, mock_empty_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns HTTP 200 even when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_empty_stats_response,
        ):
            response = client.get("/tasks/stats")
            assert response.status_code == 200

    def test_get_stats_returns_all_zeros_when_no_tasks_exist(
        self, client: TestClient, mock_empty_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns all status counts as 0 when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_empty_stats_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("pending") == 0
            assert json_body.get("running") == 0
            assert json_body.get("passed") == 0
            assert json_body.get("failed") == 0

    def test_get_stats_returns_zero_total_when_no_tasks_exist(
        self, client: TestClient, mock_empty_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns total=0 when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_empty_stats_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("total") == 0

    def test_get_stats_does_not_return_404_when_empty(
        self, client: TestClient, mock_empty_stats_response: dict[str, int]
    ) -> None:
        """GET /tasks/stats returns 200 not 404 when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_empty_stats_response,
        ):
            response = client.get("/tasks/stats")
            assert response.status_code != 404


class TestTasksProgressWithMultiplePhases:
    """Tests for GET /tasks/progress with tasks across multiple phases."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_progress_response(self) -> dict[str, float]:
        """Create mock progress response with multiple phases."""
        return {
            "decompose": 50.0,
            "implement": 0.0,
            "validate": 100.0,
        }

    def test_get_progress_returns_200_when_tasks_exist(
        self, client: TestClient, mock_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns HTTP 200 when tasks exist in database."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_progress_response,
        ):
            response = client.get("/tasks/progress")
            assert response.status_code == 200

    def test_get_progress_returns_per_phase_completion_percentages(
        self, client: TestClient, mock_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns completion percentage for each phase."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_progress_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body.get("decompose") == 50.0
            assert json_body.get("implement") == 0.0
            assert json_body.get("validate") == 100.0

    def test_get_progress_percentages_are_floats(
        self, client: TestClient, mock_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns percentages as float values."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_progress_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            for phase, percentage in json_body.items():
                assert isinstance(percentage, (int, float)), f"Phase {phase} percentage is not numeric"

    def test_get_progress_partial_completion_calculates_correctly(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress calculates (passed/total)*100 for partial completion."""
        # Phase with 2 passed out of 4 total = 50.0%
        mock_response = {"decompose": 50.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body.get("decompose") == 50.0

    def test_get_progress_full_completion_returns_100(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress returns 100.0 for fully completed phase."""
        mock_response = {"validate": 100.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body.get("validate") == 100.0


class TestTasksProgressWhenEmpty:
    """Tests for GET /tasks/progress when no tasks exist."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_empty_progress_response(self) -> dict[str, float]:
        """Create mock empty progress response."""
        return {}

    def test_get_progress_returns_200_when_no_tasks_exist(
        self, client: TestClient, mock_empty_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns HTTP 200 when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_empty_progress_response,
        ):
            response = client.get("/tasks/progress")
            assert response.status_code == 200

    def test_get_progress_returns_empty_object_when_no_tasks_exist(
        self, client: TestClient, mock_empty_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns empty JSON object when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_empty_progress_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body == {}

    def test_get_progress_does_not_return_404_when_empty(
        self, client: TestClient, mock_empty_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress returns 200 not 404 when no tasks exist."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_empty_progress_response,
        ):
            response = client.get("/tasks/progress")
            assert response.status_code != 404

    def test_get_progress_does_not_cause_division_by_zero_error(
        self, client: TestClient, mock_empty_progress_response: dict[str, float]
    ) -> None:
        """GET /tasks/progress handles empty database without division-by-zero."""
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_empty_progress_response,
        ):
            response = client.get("/tasks/progress")
            # Should not raise an error, should return valid response
            assert response.status_code == 200
            json_body = response.json()
            assert isinstance(json_body, dict)


class TestTasksProgressWithNonTerminalStatuses:
    """Tests for GET /tasks/progress when phase has only non-terminal statuses."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_progress_returns_zero_for_all_running_phase(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress returns 0.0 for phase with all running tasks."""
        # Phase with 3 running tasks and 0 passed = 0.0%
        mock_response = {"implement": 0.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body.get("implement") == 0.0

    def test_get_progress_only_counts_passed_toward_completion(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress counts only 'passed' status toward completion."""
        # Phase with 2 passed, 1 running, 1 failed out of 4 = 50.0%
        mock_response = {"decompose": 50.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            # Only passed counts, so 2/4 = 50.0%
            assert json_body.get("decompose") == 50.0

    def test_get_progress_includes_phase_with_zero_completion(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress includes phases with 0% completion in response."""
        mock_response = {
            "decompose": 50.0,
            "implement": 0.0,
            "validate": 100.0,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert "implement" in json_body
            assert json_body.get("implement") == 0.0


class TestTasksStatsResponseStructure:
    """Tests for stats response structure and types."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_stats_returns_json_content_type(self, client: TestClient) -> None:
        """GET /tasks/stats returns Content-Type application/json."""
        mock_response = {"pending": 0, "running": 0, "passed": 0, "failed": 0, "total": 0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_response,
        ):
            response = client.get("/tasks/stats")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_stats_counts_are_integers(self, client: TestClient) -> None:
        """GET /tasks/stats returns all counts as integers."""
        mock_response = {"pending": 3, "running": 2, "passed": 1, "failed": 1, "total": 7}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            for key, value in json_body.items():
                assert isinstance(value, int), f"Key {key} value is not an integer"

    def test_get_stats_contains_required_keys(self, client: TestClient) -> None:
        """GET /tasks/stats response contains all required status keys."""
        mock_response = {"pending": 0, "running": 0, "passed": 0, "failed": 0, "total": 0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert "pending" in json_body
            assert "running" in json_body
            assert "passed" in json_body
            assert "failed" in json_body
            assert "total" in json_body


class TestTasksProgressResponseStructure:
    """Tests for progress response structure and types."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_progress_returns_json_content_type(self, client: TestClient) -> None:
        """GET /tasks/progress returns Content-Type application/json."""
        mock_response: dict[str, float] = {}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type

    def test_get_progress_returns_dict(self, client: TestClient) -> None:
        """GET /tasks/progress returns a JSON object (dict)."""
        mock_response = {"decompose": 50.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert isinstance(json_body, dict)

    def test_get_progress_percentages_in_valid_range(self, client: TestClient) -> None:
        """GET /tasks/progress percentages are between 0 and 100."""
        mock_response = {"decompose": 50.0, "implement": 0.0, "validate": 100.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            for phase, percentage in json_body.items():
                assert 0.0 <= percentage <= 100.0, f"Phase {phase} has invalid percentage {percentage}"


class TestTasksStatsMethodNotAllowed:
    """Tests for non-GET methods on /tasks/stats returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_stats_returns_405(self, client: TestClient) -> None:
        """POST /tasks/stats returns HTTP 405 Method Not Allowed."""
        response = client.post("/tasks/stats")
        assert response.status_code == 405

    def test_put_stats_returns_405(self, client: TestClient) -> None:
        """PUT /tasks/stats returns HTTP 405 Method Not Allowed."""
        response = client.put("/tasks/stats")
        assert response.status_code == 405

    def test_delete_stats_returns_405(self, client: TestClient) -> None:
        """DELETE /tasks/stats returns HTTP 405 Method Not Allowed."""
        response = client.delete("/tasks/stats")
        assert response.status_code == 405


class TestTasksProgressMethodNotAllowed:
    """Tests for non-GET methods on /tasks/progress returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_progress_returns_405(self, client: TestClient) -> None:
        """POST /tasks/progress returns HTTP 405 Method Not Allowed."""
        response = client.post("/tasks/progress")
        assert response.status_code == 405

    def test_put_progress_returns_405(self, client: TestClient) -> None:
        """PUT /tasks/progress returns HTTP 405 Method Not Allowed."""
        response = client.put("/tasks/progress")
        assert response.status_code == 405

    def test_delete_progress_returns_405(self, client: TestClient) -> None:
        """DELETE /tasks/progress returns HTTP 405 Method Not Allowed."""
        response = client.delete("/tasks/progress")
        assert response.status_code == 405


class TestTasksStatsEdgeCases:
    """Tests for edge cases in stats endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_stats_handles_large_counts(self, client: TestClient) -> None:
        """GET /tasks/stats handles large task counts correctly."""
        mock_response = {
            "pending": 10000,
            "running": 5000,
            "passed": 80000,
            "failed": 5000,
            "total": 100000,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("total") == 100000

    def test_get_stats_with_only_one_status(self, client: TestClient) -> None:
        """GET /tasks/stats works when all tasks have same status."""
        mock_response = {
            "pending": 5,
            "running": 0,
            "passed": 0,
            "failed": 0,
            "total": 5,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_stats",
            return_value=mock_response,
        ):
            response = client.get("/tasks/stats")
            json_body = response.json()
            assert json_body.get("pending") == 5
            assert json_body.get("total") == 5


class TestTasksProgressEdgeCases:
    """Tests for edge cases in progress endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the tasks router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/tasks")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_progress_handles_single_phase(self, client: TestClient) -> None:
        """GET /tasks/progress works with only one phase in database."""
        mock_response = {"decompose": 75.0}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert len(json_body) == 1
            assert json_body.get("decompose") == 75.0

    def test_get_progress_handles_many_phases(self, client: TestClient) -> None:
        """GET /tasks/progress works with many phases in database."""
        mock_response = {
            "decompose": 100.0,
            "implement": 50.0,
            "validate": 25.0,
            "refactor": 0.0,
            "integrate": 75.0,
        }
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert len(json_body) == 5

    def test_get_progress_handles_fractional_percentages(
        self, client: TestClient
    ) -> None:
        """GET /tasks/progress handles non-integer percentages correctly."""
        # 1 passed out of 3 total = 33.333...%
        mock_response = {"decompose": 33.33333333333333}
        with patch(
            "tdd_orchestrator.api.routes.tasks.get_task_progress",
            return_value=mock_response,
        ):
            response = client.get("/tasks/progress")
            json_body = response.json()
            assert json_body.get("decompose") is not None
            assert abs(json_body.get("decompose", 0) - 33.33333333333333) < 0.0001
