"""Tests for the metrics router that exposes Prometheus-formatted metrics."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.routes.metrics import router


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class TestMetricsEndpointWithRecordedMetrics:
    """Tests for GET /metrics when the collector has recorded metrics."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_collector_with_metrics(self) -> MagicMock:
        """Create a mock collector that has recorded metrics."""
        collector = MagicMock()
        prometheus_output = (
            "# HELP circuit_breaker_failures_total Total failures recorded\n"
            "# TYPE circuit_breaker_failures_total counter\n"
            'circuit_breaker_failures_total{level="worker",identifier="w1",error_type="timeout"} 1.0\n'
            "# HELP circuit_breaker_state Current state (0=closed, 1=open, 2=half_open)\n"
            "# TYPE circuit_breaker_state gauge\n"
            'circuit_breaker_state{level="worker",identifier="w1"} 1'
        )
        collector.export_prometheus.return_value = prometheus_output
        return collector

    def test_get_metrics_returns_200_when_collector_has_metrics(
        self, client: TestClient, mock_collector_with_metrics: MagicMock
    ) -> None:
        """GET /metrics returns HTTP 200 when collector has recorded metrics."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_with_metrics,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_get_metrics_returns_prometheus_content_type(
        self, client: TestClient, mock_collector_with_metrics: MagicMock
    ) -> None:
        """GET /metrics returns Content-Type 'text/plain; version=0.0.4; charset=utf-8'."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_with_metrics,
        ):
            response = client.get("/metrics")
            content_type = response.headers.get("content-type", "")
            assert content_type == PROMETHEUS_CONTENT_TYPE

    def test_get_metrics_returns_body_with_help_lines(
        self, client: TestClient, mock_collector_with_metrics: MagicMock
    ) -> None:
        """GET /metrics body contains '# HELP' lines for Prometheus exposition format."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_with_metrics,
        ):
            response = client.get("/metrics")
            assert "# HELP" in response.text

    def test_get_metrics_returns_body_with_type_lines(
        self, client: TestClient, mock_collector_with_metrics: MagicMock
    ) -> None:
        """GET /metrics body contains '# TYPE' lines for Prometheus exposition format."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_with_metrics,
        ):
            response = client.get("/metrics")
            assert "# TYPE" in response.text

    def test_get_metrics_returns_body_with_metric_values(
        self, client: TestClient, mock_collector_with_metrics: MagicMock
    ) -> None:
        """GET /metrics body contains metric_name{labels} value format."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_with_metrics,
        ):
            response = client.get("/metrics")
            # Should have metric lines with labels and values
            assert "circuit_breaker_failures_total{" in response.text
            assert "} 1.0" in response.text


class TestMetricsEndpointWithNoMetrics:
    """Tests for GET /metrics when the collector has no recorded metrics (zero-state)."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_collector_empty(self) -> MagicMock:
        """Create a mock collector that has no recorded metrics."""
        collector = MagicMock()
        collector.export_prometheus.return_value = ""
        return collector

    @pytest.fixture
    def mock_collector_comments_only(self) -> MagicMock:
        """Create a mock collector that returns only comment lines."""
        collector = MagicMock()
        collector.export_prometheus.return_value = (
            "# HELP circuit_breaker_state Current circuit breaker state\n"
            "# TYPE circuit_breaker_state gauge"
        )
        return collector

    def test_get_metrics_returns_200_when_collector_has_no_metrics(
        self, client: TestClient, mock_collector_empty: MagicMock
    ) -> None:
        """GET /metrics returns HTTP 200 when collector has no recorded metrics."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_empty,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_get_metrics_returns_prometheus_content_type_when_empty(
        self, client: TestClient, mock_collector_empty: MagicMock
    ) -> None:
        """GET /metrics returns Prometheus Content-Type even when metrics are empty."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_empty,
        ):
            response = client.get("/metrics")
            content_type = response.headers.get("content-type", "")
            assert content_type == PROMETHEUS_CONTENT_TYPE

    def test_get_metrics_returns_empty_body_when_no_metrics(
        self, client: TestClient, mock_collector_empty: MagicMock
    ) -> None:
        """GET /metrics body is empty when collector has no recorded metrics."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_empty,
        ):
            response = client.get("/metrics")
            assert response.text == ""

    def test_get_metrics_returns_200_with_comments_only(
        self, client: TestClient, mock_collector_comments_only: MagicMock
    ) -> None:
        """GET /metrics returns 200 when body contains only comment lines (no metric values)."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector_comments_only,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200
            # Body should only have comment lines
            lines = response.text.strip().split("\n") if response.text.strip() else []
            for line in lines:
                assert line.startswith("#")


class TestMetricsEndpointExceptionHandling:
    """Tests for GET /metrics when get_metrics_collector() raises an exception."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_metrics_returns_500_when_collector_raises_exception(
        self, client: TestClient
    ) -> None:
        """GET /metrics returns HTTP 500 when get_metrics_collector raises an exception."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            side_effect=RuntimeError("Unexpected metrics collection error"),
        ):
            response = client.get("/metrics")
            assert response.status_code == 500

    def test_get_metrics_returns_json_error_detail_when_exception_raised(
        self, client: TestClient
    ) -> None:
        """GET /metrics returns JSON body with error detail when exception is raised."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            side_effect=RuntimeError("Metrics collection failed"),
        ):
            response = client.get("/metrics")
            json_body = response.json()
            assert "detail" in json_body
            detail = json_body["detail"]
            assert isinstance(detail, str)
            assert len(detail) > 0

    def test_get_metrics_error_detail_indicates_metrics_failure(
        self, client: TestClient
    ) -> None:
        """GET /metrics error detail indicates metrics collection failed."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            side_effect=RuntimeError("Something went wrong"),
        ):
            response = client.get("/metrics")
            json_body = response.json()
            detail = json_body.get("detail", "").lower()
            # Should indicate metrics-related failure
            assert "metric" in detail or "collection" in detail or "failed" in detail

    def test_get_metrics_does_not_leak_stack_trace_on_exception(
        self, client: TestClient
    ) -> None:
        """GET /metrics does not leak internal stack traces in response body."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            side_effect=RuntimeError("Internal error with sensitive details"),
        ):
            response = client.get("/metrics")
            body_text = response.text
            # Should not contain Python traceback indicators
            assert "Traceback" not in body_text
            assert "File \"" not in body_text
            assert "line " not in body_text or "failed" in body_text.lower()

    def test_get_metrics_handles_attribute_error(self, client: TestClient) -> None:
        """GET /metrics handles AttributeError gracefully."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            side_effect=AttributeError("Missing attribute"),
        ):
            response = client.get("/metrics")
            assert response.status_code == 500
            json_body = response.json()
            assert "detail" in json_body

    def test_get_metrics_handles_export_prometheus_exception(
        self, client: TestClient
    ) -> None:
        """GET /metrics handles exception from export_prometheus gracefully."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.side_effect = ValueError("Export failed")
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            assert response.status_code == 500
            json_body = response.json()
            assert "detail" in json_body


class TestMetricsEndpointContentTypeNotJson:
    """Tests confirming GET /metrics does NOT return application/json Content-Type."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_collector(self) -> MagicMock:
        """Create a mock collector."""
        collector = MagicMock()
        collector.export_prometheus.return_value = "# TYPE test gauge\ntest 1"
        return collector

    def test_get_metrics_does_not_return_json_content_type(
        self, client: TestClient, mock_collector: MagicMock
    ) -> None:
        """GET /metrics Content-Type is NOT application/json."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            content_type = response.headers.get("content-type", "")
            assert "application/json" not in content_type

    def test_get_metrics_returns_text_plain_not_json(
        self, client: TestClient, mock_collector: MagicMock
    ) -> None:
        """GET /metrics returns text/plain, confirming Prometheus format."""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            content_type = response.headers.get("content-type", "")
            assert content_type.startswith("text/plain")


class TestMetricsEndpointCollectorInvocation:
    """Tests verifying get_metrics_collector is called correctly per request."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_metrics_calls_get_metrics_collector_exactly_once_per_request(
        self, client: TestClient
    ) -> None:
        """GET /metrics calls get_metrics_collector exactly once per request."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = ""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ) as mock_get_collector:
            response = client.get("/metrics")
            assert response.status_code == 200
            assert mock_get_collector.call_count == 1

    def test_get_metrics_calls_collector_freshly_on_each_request(
        self, client: TestClient
    ) -> None:
        """GET /metrics resolves get_metrics_collector freshly for each request."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = ""
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ) as mock_get_collector:
            # Make multiple requests
            client.get("/metrics")
            client.get("/metrics")
            client.get("/metrics")
            # Each request should call get_metrics_collector once
            assert mock_get_collector.call_count == 3

    def test_get_metrics_uses_collector_export_prometheus_method(
        self, client: TestClient
    ) -> None:
        """GET /metrics uses the collector's export_prometheus method."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = "# TYPE test gauge\ntest 42"
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200
            mock_collector.export_prometheus.assert_called_once()


class TestMetricsEndpointMethodNotAllowed:
    """Tests for non-GET methods on /metrics returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_post_metrics_returns_405(self, client: TestClient) -> None:
        """POST /metrics returns HTTP 405 Method Not Allowed."""
        response = client.post("/metrics")
        assert response.status_code == 405

    def test_put_metrics_returns_405(self, client: TestClient) -> None:
        """PUT /metrics returns HTTP 405 Method Not Allowed."""
        response = client.put("/metrics")
        assert response.status_code == 405

    def test_delete_metrics_returns_405(self, client: TestClient) -> None:
        """DELETE /metrics returns HTTP 405 Method Not Allowed."""
        response = client.delete("/metrics")
        assert response.status_code == 405

    def test_patch_metrics_returns_405(self, client: TestClient) -> None:
        """PATCH /metrics returns HTTP 405 Method Not Allowed."""
        response = client.patch("/metrics")
        assert response.status_code == 405


class TestMetricsRouterMounting:
    """Tests for metrics router mountability."""

    def test_router_is_mountable_on_fastapi_app(self) -> None:
        """The metrics router can be mounted on a FastAPI app."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = ""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        client = TestClient(app)
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_router_mounted_at_custom_prefix(self) -> None:
        """The metrics router can be mounted at a custom prefix."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = "# TYPE test gauge\ntest 1"
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/metrics")
        client = TestClient(app)
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/api/v1/metrics")
            assert response.status_code == 200


class TestMetricsEndpointEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the metrics router mounted."""
        app = FastAPI()
        app.include_router(router, prefix="/metrics")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client for the app."""
        return TestClient(app)

    def test_get_metrics_with_query_params_still_works(self, client: TestClient) -> None:
        """GET /metrics with query parameters still returns metrics."""
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = "# TYPE test gauge\ntest 1"
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics?format=text&verbose=true")
            assert response.status_code == 200

    def test_get_metrics_with_large_output(self, client: TestClient) -> None:
        """GET /metrics handles large metric output."""
        mock_collector = MagicMock()
        # Simulate a large number of metrics
        large_output_lines = []
        for i in range(1000):
            large_output_lines.append(f"# HELP metric_{i} Description for metric {i}")
            large_output_lines.append(f"# TYPE metric_{i} gauge")
            large_output_lines.append(f'metric_{i}{{worker="{i}"}} {i}.0')
        mock_collector.export_prometheus.return_value = "\n".join(large_output_lines)
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200
            assert len(response.text) > 10000  # Should be substantial

    def test_get_metrics_with_special_characters_in_labels(
        self, client: TestClient
    ) -> None:
        """GET /metrics handles special characters in metric labels."""
        mock_collector = MagicMock()
        # Labels with special characters (properly escaped in Prometheus format)
        mock_collector.export_prometheus.return_value = (
            "# TYPE test gauge\n"
            'test{path="/api/v1/users",method="GET"} 42'
        )
        with patch(
            "tdd_orchestrator.api.routes.metrics.get_metrics_collector",
            return_value=mock_collector,
        ):
            response = client.get("/metrics")
            assert response.status_code == 200
            assert "/api/v1/users" in response.text
