"""Metrics router for Prometheus exposition format."""

import json
from typing import Any

from fastapi import APIRouter, Response

from tdd_orchestrator.metrics import get_metrics_collector

router = APIRouter()

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("")
def metrics_endpoint() -> Response:
    """Return metrics in Prometheus exposition format.

    Returns:
        A Response with Prometheus-formatted text and appropriate content-type.
        Returns HTTP 500 with JSON error if metrics collection fails.
    """
    try:
        collector = get_metrics_collector()
        prometheus_text = collector.export_prometheus()

        return Response(
            content=prometheus_text,
            media_type=PROMETHEUS_CONTENT_TYPE,
        )
    except Exception as e:
        # Return 500 with JSON error
        error_response: dict[str, Any] = {
            "detail": f"Metrics collection failed: {str(e)}"
        }
        return Response(
            content=json.dumps(error_response),
            status_code=500,
            media_type="application/json",
        )
