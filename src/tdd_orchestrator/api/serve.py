"""Server runner module for the TDD Orchestrator API.

Provides a run_server utility that configures and starts uvicorn
with appropriate defaults.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

# Import uvicorn at module level so it can be patched in tests.
# This is a soft dependency - the import error is handled at runtime.
try:
    import uvicorn
except ImportError:
    uvicorn = None  # type: ignore[assignment]

_DB_PATH_ENV_VAR = "TDD_ORCHESTRATOR_DB_PATH"


@contextmanager
def _temporary_env_var(name: str, value: str | None) -> Iterator[None]:
    """Temporarily set an environment variable, restoring original state on exit."""
    if value is None:
        yield
        return
    old_value = os.environ.get(name)
    was_set = name in os.environ
    os.environ[name] = value
    try:
        yield
    finally:
        if was_set and old_value is not None:
            os.environ[name] = old_value
        elif not was_set:
            os.environ.pop(name, None)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8420,
    log_level: str = "info",
    reload: bool = False,
    db_path: str | None = None,
    **kwargs: Any,
) -> None:
    """Run the TDD Orchestrator API server.

    Args:
        host: The host to bind to. Defaults to '127.0.0.1'.
        port: The port to bind to. Defaults to 8420.
        log_level: The log level for uvicorn. Defaults to 'info'.
        reload: Whether to enable auto-reload. Defaults to False.
        db_path: Optional database path. If provided, sets TDD_ORCHESTRATOR_DB_PATH env var.
        **kwargs: Additional keyword arguments to forward to uvicorn.run.

    Raises:
        RuntimeError: If uvicorn is not installed.
    """
    if uvicorn is None:
        raise RuntimeError(
            "uvicorn is not installed. Install it with: pip install tdd-orchestrator[api]"
        )

    with _temporary_env_var(_DB_PATH_ENV_VAR, db_path):
        uvicorn.run(
            "tdd_orchestrator.api.app:create_app",
            factory=True,
            host=host,
            port=port,
            log_level=log_level,
            reload=reload,
            **kwargs,
        )
