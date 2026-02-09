"""Shared fixtures for API unit tests.

Sets up proper ASGI lifespan handling for httpx AsyncClient tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# Store original ASGITransport.__init__
_original_asgi_transport_init = ASGITransport.__init__


class LifespanASGITransport(ASGITransport):
    """ASGITransport wrapper that manages ASGI lifespan events.

    This transport wraps the app with LifespanManager to ensure
    lifespan startup/shutdown events are properly triggered.
    """

    _lifespan_manager: LifespanManager | None = None

    def __init__(self, app: Any, **kwargs: Any) -> None:
        # Store the original app for lifespan management
        self._original_app = app
        self._lifespan_manager = None
        super().__init__(app, **kwargs)

    async def __aenter__(self) -> "LifespanASGITransport":
        """Start lifespan events when entering context."""
        self._lifespan_manager = LifespanManager(self._original_app)
        await self._lifespan_manager.__aenter__()
        # Update the app to use the managed app
        self.app = self._lifespan_manager._app
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Stop lifespan events when exiting context."""
        if self._lifespan_manager:
            await self._lifespan_manager.__aexit__(*args)


@pytest.fixture(autouse=True)
def patch_asgi_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ASGITransport to use LifespanASGITransport for proper lifespan handling."""
    monkeypatch.setattr("httpx.ASGITransport", LifespanASGITransport)
    monkeypatch.setattr("httpx._transports.asgi.ASGITransport", LifespanASGITransport)
    # Also patch the test module's namespace since it imports ASGITransport at module level
    monkeypatch.setattr(
        "tests.unit.api.test_dependencies_lifespan.ASGITransport", LifespanASGITransport
    )
    # Debug
    import tests.unit.api.test_dependencies_lifespan as test_mod
    print(f"DEBUG: test module ASGITransport = {test_mod.ASGITransport}")
