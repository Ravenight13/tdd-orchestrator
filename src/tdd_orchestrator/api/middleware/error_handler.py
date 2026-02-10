"""Error handler middleware for FastAPI application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Error response model."""

    detail: str


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request, exc: ValueError
    ) -> JSONResponse:
        """Handle ValueError exceptions.

        Args:
            request: The request that caused the exception.
            exc: The ValueError exception.

        Returns:
            JSONResponse with 400 status and ErrorResponse body.
        """
        error_message = str(exc) if exc.args else ""
        error_response = ErrorResponse(detail=error_message)
        return JSONResponse(
            status_code=400,
            content=error_response.model_dump(),
        )
