"""TDD Orchestrator REST API package.

This package provides a FastAPI-based REST API for the TDD Orchestrator,
exposing task management, worker status, and circuit breaker endpoints.
"""

from tdd_orchestrator.api.app import create_app

__all__ = ["create_app"]
