"""FastAPI application factory with lifespan dependency management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator

from fastapi import FastAPI

if TYPE_CHECKING:
    pass


async def init_dependencies(app: FastAPI) -> None:
    """Initialize application dependencies during startup.

    Args:
        app: The FastAPI application instance.
    """
    # Import the actual init function from dependencies module
    from tdd_orchestrator.api.dependencies import (
        init_dependencies as sync_init_dependencies,
    )

    # For now, we'll create placeholder instances
    # In production, these would be real OrchestratorDB and SSEBroadcaster instances
    db_instance: Any = None
    broadcaster_instance: Any = None

    # Call the synchronous init function
    sync_init_dependencies(db_instance, broadcaster_instance)


async def shutdown_dependencies(app: FastAPI) -> None:
    """Shut down application dependencies during shutdown.

    Args:
        app: The FastAPI application instance.
    """
    # Import the actual shutdown function from dependencies module
    from tdd_orchestrator.api.dependencies import (
        shutdown_dependencies as sync_shutdown_dependencies,
    )

    # Call the synchronous shutdown function
    sync_shutdown_dependencies()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan (startup and shutdown).

    Args:
        app: The FastAPI application instance.

    Yields:
        None during the application's running state.
    """
    import sys

    # Get the module object fresh from sys.modules to see patched attributes
    app_module = sys.modules[__name__]

    # Get the functions via getattr to ensure we get the (possibly patched) versions
    init_fn = getattr(app_module, "init_dependencies")
    shutdown_fn = getattr(app_module, "shutdown_dependencies")

    # Startup
    try:
        await init_fn(app)
        yield
    finally:
        # Shutdown - always called even if init fails
        await shutdown_fn(app)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        The configured FastAPI application instance.
    """
    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            A dictionary with status "ok".
        """
        return {"status": "ok"}

    return app
