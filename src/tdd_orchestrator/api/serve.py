"""Server runner module for the TDD Orchestrator API.

Provides a run_server utility that configures and starts uvicorn
with appropriate defaults.
"""

from __future__ import annotations

from typing import Any

import uvicorn

from tdd_orchestrator.api.app import create_app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8420,
    log_level: str = "info",
    **kwargs: Any,
) -> None:
    """Run the TDD Orchestrator API server.

    Args:
        host: The host to bind to. Defaults to '127.0.0.1'.
        port: The port to bind to. Defaults to 8420.
        log_level: The log level for uvicorn. Defaults to 'info'.
        **kwargs: Additional keyword arguments to forward to uvicorn.run.
    """
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level=log_level, **kwargs)
