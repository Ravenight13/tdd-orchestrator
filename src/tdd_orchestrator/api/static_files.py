"""Static file serving for the dashboard SPA."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse


def _find_dashboard_dir() -> Path | None:
    """Locate the built dashboard directory.

    Checks TDD_DASHBOARD_DIR env var first, then falls back to
    ``frontend/dist/`` relative to the project root.

    Returns:
        Path to the dashboard dist directory, or None if not found.
    """
    env_dir = os.environ.get("TDD_DASHBOARD_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p

    # Walk up from this file to find the project root
    candidates = [
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return None


def mount_dashboard(app: FastAPI) -> None:
    """Mount the dashboard SPA on ``/app/``.

    Serves static assets from ``/app/assets/`` and returns ``index.html``
    for all other ``/app/*`` routes (SPA fallback).

    Args:
        app: The FastAPI application instance.
    """
    dist_dir = _find_dashboard_dir()
    if dist_dir is None:
        return  # Dashboard not built; skip mounting

    index_html = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"

    if assets_dir.is_dir():
        from starlette.staticfiles import StaticFiles

        app.mount(
            "/app/assets",
            StaticFiles(directory=str(assets_dir)),
            name="dashboard-assets",
        )

    @app.get("/app/{path:path}")
    async def spa_fallback(path: str) -> Any:
        """Serve index.html for all /app/* routes (SPA fallback).

        Args:
            path: The requested path under /app/.

        Returns:
            FileResponse with the dashboard index.html.
        """
        return FileResponse(str(index_html))

    @app.get("/app")
    async def spa_root() -> Any:
        """Serve index.html for /app root.

        Returns:
            FileResponse with the dashboard index.html.
        """
        return FileResponse(str(index_html))
