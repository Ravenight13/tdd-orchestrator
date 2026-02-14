"""Unit tests for circuit breaker monitoring modules.

Tests for health.py, notifications.py, and metrics.py from Phase 5.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import the modules under test
from tdd_orchestrator.health import (
    CircuitDetail,
    CircuitHealthResponse,
    CircuitHealthStatus,
    get_circuit_health,
)
from tdd_orchestrator.metrics import (
    MetricsCollector,
    MetricType,
    MetricValue,
    get_metrics_collector,
    reset_metrics_collector,
)
from tdd_orchestrator.notifications import (
    NotificationConfig,
    NotificationThrottler,
    SlackNotifier,
)


# =============================================================================
# Health Module Tests
# =============================================================================


class TestCircuitHealthStatus:
    """Tests for CircuitHealthStatus enum."""

    def test_status_values(self) -> None:
        """Verify all status values exist."""
        assert CircuitHealthStatus.HEALTHY.value == "HEALTHY"
        assert CircuitHealthStatus.DEGRADED.value == "DEGRADED"
        assert CircuitHealthStatus.UNHEALTHY.value == "UNHEALTHY"
        assert CircuitHealthStatus.UNKNOWN.value == "UNKNOWN"


class TestCircuitHealthResponse:
    """Tests for CircuitHealthResponse dataclass."""

    def test_default_values(self) -> None:
        """Test default initialization."""
        response = CircuitHealthResponse(status=CircuitHealthStatus.HEALTHY)
        assert response.total_circuits == 0
        assert response.circuits_closed == 0
        assert response.circuits_open == 0
        assert response.flapping_circuits == 0
        assert isinstance(response.timestamp, datetime)

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        response = CircuitHealthResponse(
            status=CircuitHealthStatus.DEGRADED,
            total_circuits=5,
            circuits_closed=3,
            circuits_open=1,
            circuits_half_open=1,
            flapping_circuits=0,
        )
        d = response.to_dict()
        assert d["status"] == "DEGRADED"
        assert d["total_circuits"] == 5
        assert d["circuits_open"] == 1


class TestCircuitDetail:
    """Tests for CircuitDetail dataclass."""

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        detail = CircuitDetail(
            level="worker",
            identifier="worker_1",
            state="open",
            failure_count=5,
            opened_at="2026-01-12T10:00:00",
            minutes_open=30,
        )
        d = detail.to_dict()
        assert d["level"] == "worker"
        assert d["identifier"] == "worker_1"
        assert d["state"] == "open"
        assert d["failure_count"] == 5


class TestGetCircuitHealth:
    """Tests for get_circuit_health function."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database with async context manager for cursor."""
        db = AsyncMock()
        db._conn = MagicMock()  # Use MagicMock for _conn, not AsyncMock
        return db

    def _mock_cursor(self, rows: list[dict[str, Any]]) -> AsyncMock:
        """Create mock cursor that returns rows."""
        cursor = AsyncMock()
        # Convert dicts to mock Row objects with dict() support
        mock_rows = []
        for row_dict in rows:
            # Create a class that behaves like an aiosqlite Row
            class MockRow:
                def __init__(self, data: dict[str, Any]) -> None:
                    self._data = data

                def __iter__(self) -> Any:
                    return iter(self._data.items())

                def __getitem__(self, key: str) -> Any:
                    return self._data[key]

            mock_rows.append(MockRow(row_dict))
        cursor.fetchall = AsyncMock(return_value=mock_rows)
        # Also add fetchone support for single row queries
        cursor.fetchone = AsyncMock(return_value=mock_rows[0] if mock_rows else None)
        return cursor

    @pytest.mark.asyncio
    async def test_healthy_status(self, mock_db: AsyncMock) -> None:
        """Test healthy status when all circuits closed."""
        # Mock v_circuit_health_summary query
        summary_cursor = self._mock_cursor(
            [
                {
                    "level": "stage",
                    "total_circuits": 5,
                    "closed_count": 5,
                    "open_count": 0,
                    "half_open_count": 0,
                }
            ]
        )
        # Mock v_flapping_circuits count query
        flapping_cursor = self._mock_cursor([{"count": 0}])
        # Mock v_open_circuits query
        open_cursor = self._mock_cursor([])

        # Mock the async context manager properly
        def mock_execute(sql: str) -> MagicMock:
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock()
            ctx.__aexit__ = AsyncMock()
            if "v_circuit_health_summary" in sql:
                ctx.__aenter__.return_value = summary_cursor
            elif "COUNT(*)" in sql:
                ctx.__aenter__.return_value = flapping_cursor
            else:
                ctx.__aenter__.return_value = open_cursor
            return ctx

        mock_db._conn.execute = mock_execute

        health = await get_circuit_health(mock_db)
        assert health.status == CircuitHealthStatus.HEALTHY
        assert health.total_circuits == 5
        assert health.circuits_closed == 5
        assert health.circuits_open == 0

    @pytest.mark.asyncio
    async def test_degraded_status_open_circuits(self, mock_db: AsyncMock) -> None:
        """Test degraded status when circuits are open."""
        summary_cursor = self._mock_cursor(
            [
                {
                    "level": "worker",
                    "total_circuits": 3,
                    "closed_count": 2,
                    "open_count": 1,
                    "half_open_count": 0,
                }
            ]
        )
        flapping_cursor = self._mock_cursor([{"count": 0}])
        open_cursor = self._mock_cursor(
            [
                {
                    "level": "worker",
                    "identifier": "worker_1",
                    "state": "open",
                    "failure_count": 5,
                    "opened_at": "2026-01-12",
                    "minutes_open": 10,
                }
            ]
        )

        def mock_execute(sql: str) -> MagicMock:
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock()
            ctx.__aexit__ = AsyncMock()
            if "v_circuit_health_summary" in sql:
                ctx.__aenter__.return_value = summary_cursor
            elif "COUNT(*)" in sql:
                ctx.__aenter__.return_value = flapping_cursor
            else:
                ctx.__aenter__.return_value = open_cursor
            return ctx

        mock_db._conn.execute = mock_execute

        health = await get_circuit_health(mock_db)
        assert health.status == CircuitHealthStatus.DEGRADED
        assert health.circuits_open == 1

    @pytest.mark.asyncio
    async def test_unhealthy_status_system_open(self, mock_db: AsyncMock) -> None:
        """Test unhealthy status when system circuit is open."""
        summary_cursor = self._mock_cursor(
            [
                {
                    "level": "system",
                    "total_circuits": 1,
                    "closed_count": 0,
                    "open_count": 1,
                    "half_open_count": 0,
                }
            ]
        )
        flapping_cursor = self._mock_cursor([{"count": 0}])
        open_cursor = self._mock_cursor(
            [
                {
                    "level": "system",
                    "identifier": "system",
                    "state": "open",
                    "failure_count": 3,
                    "opened_at": "2026-01-12",
                    "minutes_open": 5,
                }
            ]
        )

        def mock_execute(sql: str) -> MagicMock:
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock()
            ctx.__aexit__ = AsyncMock()
            if "v_circuit_health_summary" in sql:
                ctx.__aenter__.return_value = summary_cursor
            elif "COUNT(*)" in sql:
                ctx.__aenter__.return_value = flapping_cursor
            else:
                ctx.__aenter__.return_value = open_cursor
            return ctx

        mock_db._conn.execute = mock_execute

        health = await get_circuit_health(mock_db)
        assert health.status == CircuitHealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_unknown_status_on_error(self, mock_db: AsyncMock) -> None:
        """Test unknown status on database error."""
        mock_db._conn.execute = MagicMock(side_effect=Exception("DB error"))

        health = await get_circuit_health(mock_db)
        assert health.status == CircuitHealthStatus.UNKNOWN
        assert "error" in health.details


# =============================================================================
# Notifications Module Tests
# =============================================================================


class TestNotificationConfig:
    """Tests for NotificationConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration."""
        config = NotificationConfig()
        assert config.throttle_seconds == 60
        assert config.flapping_threshold == 5
        assert config.flapping_window_seconds == 300
        assert config.enabled is True


class TestNotificationThrottler:
    """Tests for NotificationThrottler class."""

    @pytest.fixture
    def throttler(self) -> NotificationThrottler:
        """Create throttler with short windows for testing."""
        config = NotificationConfig(
            throttle_seconds=1,
            flapping_threshold=3,
            flapping_window_seconds=5,
        )
        return NotificationThrottler(config)

    @pytest.mark.asyncio
    async def test_first_notification_allowed(self, throttler: NotificationThrottler) -> None:
        """First notification should always be allowed."""
        should_send, reason = await throttler.should_send("worker", "w1", "opened")
        assert should_send is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_throttle_rapid_notifications(self, throttler: NotificationThrottler) -> None:
        """Rapid notifications should be throttled."""
        # First notification
        await throttler.should_send("worker", "w1", "opened")
        await throttler.record_sent("worker", "w1", "opened", "test")

        # Immediate second notification - should be throttled
        should_send, reason = await throttler.should_send("worker", "w1", "closed")
        assert should_send is False
        assert reason is not None
        assert "throttled" in reason

    @pytest.mark.asyncio
    async def test_throttle_expires(self, throttler: NotificationThrottler) -> None:
        """Throttle should expire after timeout."""
        await throttler.should_send("worker", "w1", "opened")
        await throttler.record_sent("worker", "w1", "opened", "test")

        # Wait for throttle to expire
        await asyncio.sleep(1.1)

        should_send, reason = await throttler.should_send("worker", "w1", "closed")
        assert should_send is True

    @pytest.mark.asyncio
    async def test_flapping_detection(self, throttler: NotificationThrottler) -> None:
        """Flapping circuits should be detected."""
        # Record multiple rapid state changes (need to wait for throttle to expire)
        for _ in range(3):
            await throttler.record_sent("worker", "w1", "opened", "test")
            await asyncio.sleep(1.1)  # Wait for throttle to expire
            await throttler.record_sent("worker", "w1", "closed", "test")
            await asyncio.sleep(1.1)  # Wait for throttle to expire

        # Next notification should be blocked due to flapping
        should_send, reason = await throttler.should_send("worker", "w1", "opened")
        assert should_send is False
        assert reason == "flapping_detected"

    @pytest.mark.asyncio
    async def test_get_flapping_circuits(self, throttler: NotificationThrottler) -> None:
        """Should return list of flapping circuits."""
        # Record flapping behavior
        for _ in range(4):
            await throttler.record_sent("worker", "w1", "opened", "test")

        flapping = await throttler.get_flapping_circuits()
        assert "worker:w1" in flapping

    @pytest.mark.asyncio
    async def test_disabled_notifications(self) -> None:
        """Disabled notifications should not send."""
        config = NotificationConfig(enabled=False)
        throttler = NotificationThrottler(config)

        should_send, reason = await throttler.should_send("worker", "w1", "opened")
        assert should_send is False
        assert reason == "notifications_disabled"


class TestSlackNotifier:
    """Tests for SlackNotifier class."""

    @pytest.fixture
    def notifier(self) -> SlackNotifier:
        """Create notifier without webhook."""
        return SlackNotifier()

    @pytest.fixture
    def notifier_with_webhook(self) -> SlackNotifier:
        """Create notifier with webhook."""
        return SlackNotifier(webhook_url="https://hooks.slack.com/test")

    @pytest.mark.asyncio
    async def test_notify_without_webhook(self, notifier: SlackNotifier) -> None:
        """Notification without webhook should log only."""
        result = await notifier.notify_circuit_event(
            level="worker",
            identifier="w1",
            event_type="opened",
            reason="Test failure",
        )
        assert result is True  # Logged successfully

    @pytest.mark.asyncio
    async def test_message_colors(self, notifier: SlackNotifier) -> None:
        """Test that message colors are assigned correctly."""
        # Access internal method for testing
        msg = notifier._build_message("worker", "w1", "opened", "test", None)
        assert msg["attachments"][0]["color"] == "#FF0000"  # Red for opened

        msg = notifier._build_message("worker", "w1", "closed", "test", None)
        assert msg["attachments"][0]["color"] == "#00FF00"  # Green for closed


# =============================================================================
# Metrics Module Tests
# =============================================================================


class TestMetricValue:
    """Tests for MetricValue dataclass."""

    def test_to_prometheus_simple(self) -> None:
        """Test Prometheus format without labels."""
        metric = MetricValue(
            name="test_metric",
            value=42.0,
            metric_type=MetricType.GAUGE,
        )
        assert metric.to_prometheus() == "test_metric 42.0"

    def test_to_prometheus_with_labels(self) -> None:
        """Test Prometheus format with labels."""
        metric = MetricValue(
            name="test_metric",
            value=42.0,
            metric_type=MetricType.GAUGE,
            labels={"level": "worker", "id": "w1"},
        )
        result = metric.to_prometheus()
        assert 'level="worker"' in result
        assert 'id="w1"' in result
        assert "42.0" in result


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        """Create fresh collector."""
        reset_metrics_collector()
        return MetricsCollector()

    def test_record_state_change(self, collector: MetricsCollector) -> None:
        """Test state change recording."""
        collector.record_state_change("worker", "w1", "closed", "open")

        metrics = collector.get_all_metrics()
        names = [m.name for m in metrics]
        assert "circuit_breaker_state_changes_total" in names
        assert "circuit_breaker_state" in names

    def test_record_failure(self, collector: MetricsCollector) -> None:
        """Test failure recording."""
        collector.record_failure("worker", "w1", "timeout")

        metrics = collector.get_all_metrics()
        failure_metrics = [m for m in metrics if m.name == "circuit_breaker_failures_total"]
        assert len(failure_metrics) == 1
        assert failure_metrics[0].labels["error_type"] == "timeout"

    def test_record_success(self, collector: MetricsCollector) -> None:
        """Test success recording."""
        collector.record_success("worker", "w1")

        metrics = collector.get_all_metrics()
        success_metrics = [m for m in metrics if m.name == "circuit_breaker_successes_total"]
        assert len(success_metrics) == 1

    def test_record_recovery(self, collector: MetricsCollector) -> None:
        """Test recovery recording."""
        collector.record_recovery("worker", "w1", 120.5)

        metrics = collector.get_all_metrics()
        names = [m.name for m in metrics]
        assert "circuit_breaker_recovery_duration_seconds" in names
        assert "circuit_breaker_recoveries_total" in names

    def test_record_check_latency(self, collector: MetricsCollector) -> None:
        """Test check latency recording."""
        collector.record_check_latency("worker", "w1", 5.5)

        metrics = collector.get_all_metrics()
        latency_metrics = [m for m in metrics if m.name == "circuit_breaker_check_latency_ms"]
        assert len(latency_metrics) == 1
        assert latency_metrics[0].value == 5.5

    def test_export_prometheus(self, collector: MetricsCollector) -> None:
        """Test Prometheus export format."""
        collector.record_failure("worker", "w1", "error")
        collector.record_success("worker", "w1")

        output = collector.export_prometheus()
        assert "# TYPE" in output
        assert "circuit_breaker_failures_total" in output

    def test_callback_registration(self, collector: MetricsCollector) -> None:
        """Test metric callback is invoked."""
        callback_values: list[MetricValue] = []
        collector.register_callback(lambda m: callback_values.append(m))

        collector.record_failure("worker", "w1", "test")
        assert len(callback_values) == 1
        assert callback_values[0].name == "circuit_breaker_failures_total"

    def test_state_duration_tracking(self, collector: MetricsCollector) -> None:
        """Test state duration is tracked."""
        import time

        # First state change starts timer
        collector.record_state_change("worker", "w1", "closed", "open")
        time.sleep(0.1)

        # Second state change should record duration
        collector.record_state_change("worker", "w1", "open", "half_open")

        metrics = collector.get_all_metrics()
        duration_metrics = [
            m for m in metrics if m.name == "circuit_breaker_state_duration_seconds"
        ]
        assert len(duration_metrics) >= 1


class TestGlobalMetricsCollector:
    """Tests for global metrics collector functions."""

    def test_singleton_pattern(self) -> None:
        """Test get_metrics_collector returns same instance."""
        reset_metrics_collector()
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is c2

    def test_reset_creates_new_instance(self) -> None:
        """Test reset creates new collector."""
        c1 = get_metrics_collector()
        reset_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is not c2
