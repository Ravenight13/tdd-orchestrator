"""FastAPI application factory with lifespan dependency management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str


# Global state for broadcaster and callback
_broadcaster: Any = None
_registered_callback: Callable[[dict[str, Any]], None] | None = None


def _create_task_status_callback() -> Callable[[dict[str, Any]], None]:
    """Create a callback function for task status changes.

    Returns:
        A callback that publishes events through the broadcaster.
    """

    def on_task_status_change(event: dict[str, Any]) -> None:
        """Callback invoked when task status changes."""
        if _broadcaster is not None:
            try:
                _broadcaster.publish(event)
            except Exception:
                # Silently catch exceptions to prevent app crashes
                pass

    return on_task_status_change


async def init_dependencies(app: FastAPI | None = None) -> None:
    """Initialize application dependencies during startup.

    Args:
        app: The FastAPI application instance (optional).
    """
    global _broadcaster, _registered_callback

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

    # Create SSE broadcaster
    from tdd_orchestrator.api.sse import SSEBroadcaster

    _broadcaster = SSEBroadcaster()

    # Create and register callback with DB observer
    _registered_callback = _create_task_status_callback()

    # Register the callback with the DB observer
    from tdd_orchestrator.db.observer import register_task_callback

    register_task_callback(_registered_callback)


async def shutdown_dependencies(app: FastAPI | None = None) -> None:
    """Shut down application dependencies during shutdown.

    Args:
        app: The FastAPI application instance (optional).
    """
    import asyncio
    import inspect

    global _broadcaster, _registered_callback

    # Unregister the callback first
    if _registered_callback is not None:
        from tdd_orchestrator.db.observer import unregister_task_callback

        unregister_task_callback(_registered_callback)
        _registered_callback = None

    # Shutdown the broadcaster
    if _broadcaster is not None:
        # Check if broadcaster has a shutdown method
        if hasattr(_broadcaster, "shutdown"):
            shutdown_method = _broadcaster.shutdown
            # Check if it's async or sync
            if inspect.iscoroutinefunction(shutdown_method) or (
                hasattr(shutdown_method, "__call__")
                and asyncio.iscoroutinefunction(shutdown_method)
            ):
                await shutdown_method()
            else:
                # Try to call it - might be a mock or sync method
                result = shutdown_method()
                # If it returns a coroutine, await it
                if inspect.iscoroutine(result):
                    await result
        _broadcaster = None

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

    # Startup - look up init_dependencies at call time to see patches
    init_fn = getattr(app_module, "init_dependencies")
    try:
        await init_fn()
        yield
    finally:
        # Shutdown - look up shutdown_dependencies at call time to see patches
        # This is done here (not at the start) so patches applied after startup
        # but before shutdown will be seen
        shutdown_fn = getattr(app_module, "shutdown_dependencies")
        await shutdown_fn()


async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError exceptions.

    Args:
        request: The HTTP request.
        exc: The ValueError exception.

    Returns:
        JSON response with 422 status code.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


async def _runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    """Handle RuntimeError exceptions.

    Args:
        request: The HTTP request.
        exc: The RuntimeError exception.

    Returns:
        JSON response with 500 status code.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


async def _general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions.

    Args:
        request: The HTTP request.
        exc: The exception.

    Returns:
        JSON response with 500 status code.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def _register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the application.

    Args:
        app: The FastAPI application instance.
    """
    # Note: More specific handlers must be registered before general ones
    app.add_exception_handler(ValueError, _value_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RuntimeError, _runtime_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _general_exception_handler)


def _register_routes(app: FastAPI) -> None:
    """Register application routes.

    Args:
        app: The FastAPI application instance.
    """

    @app.get("/health")
    async def health() -> HealthResponse:
        """Health check endpoint.

        Returns:
            A HealthResponse with status "ok".
        """
        return HealthResponse(status="ok")


def _configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware on the application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A configured FastAPI application with lifespan management.
    """
    app = FastAPI(
        title="TDD Orchestrator",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    _configure_cors(app)
    _register_error_handlers(app)
    _register_routes(app)

    return app
