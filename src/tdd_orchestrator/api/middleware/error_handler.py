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
            JSONResponse with 422 status and ErrorResponse body.
        """
        error_message = str(exc) if exc.args else ""
        error_response = ErrorResponse(detail=error_message)
        return JSONResponse(
            status_code=422,
            content=error_response.model_dump(),
        )

    @app.exception_handler(LookupError)
    async def lookup_error_handler(
        request: Request, exc: LookupError
    ) -> JSONResponse:
        """Handle LookupError exceptions (including KeyError, IndexError).

        Args:
            request: The request that caused the exception.
            exc: The LookupError exception.

        Returns:
            JSONResponse with 404 status and ErrorResponse body.
        """
        # Extract the actual message from exc.args to avoid KeyError quote wrapping
        if exc.args and exc.args[0]:
            error_message = str(exc.args[0])
        else:
            error_message = "Not found"
        error_response = ErrorResponse(detail=error_message)
        return JSONResponse(
            status_code=404,
            content=error_response.model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle all unhandled exceptions.

        Args:
            request: The request that caused the exception.
            exc: The exception.

        Returns:
            JSONResponse with 500 status and sanitized error message.
        """
        # Sanitized response - never leak internal error details
        error_response = ErrorResponse(detail="Internal server error")
        return JSONResponse(
            status_code=500,
            content=error_response.model_dump(),
        )
