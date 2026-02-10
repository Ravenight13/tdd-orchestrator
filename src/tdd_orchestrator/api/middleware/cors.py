"""CORS middleware configuration for FastAPI."""

import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware on the FastAPI app.

    Reads TDD_CORS_ORIGINS environment variable to determine allowed origins.
    - If not set: uses default localhost origins for development
    - If set to '*': enables wildcard CORS access
    - If set to comma-separated list: uses those specific origins

    Args:
        app: The FastAPI application instance to configure
    """
    cors_origins_env = os.environ.get("TDD_CORS_ORIGINS")

    if cors_origins_env is None:
        # Default localhost origins for development
        allow_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    elif cors_origins_env == "*":
        # Wildcard access
        allow_origins = ["*"]
    else:
        # Custom origins from env var - split by comma, trim whitespace, exclude empty
        allow_origins = [
            origin.strip()
            for origin in cors_origins_env.split(",")
            if origin.strip()
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
