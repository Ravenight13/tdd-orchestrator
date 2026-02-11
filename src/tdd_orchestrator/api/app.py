"""FastAPI application factory with lifespan dependency management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    async def health() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            A dictionary with status "ok".
        """
        return {"status": "ok"}


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
        The configured FastAPI application instance.
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
