"""Shared fixtures for API unit tests.

Patches ASGITransport at the class level so that lifespan startup/shutdown
events fire for every ``AsyncClient`` context manager, regardless of
which import path the test file used to obtain ``ASGITransport``.
"""

from __future__ import annotations

from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

_original_aexit = ASGITransport.__aexit__


async def _lifespan_aenter(self: Any) -> Any:
    """Start lifespan events when entering the transport context."""
    manager = LifespanManager(self.app)
    self._lifespan_manager = await manager.__aenter__()
    return self


async def _lifespan_aexit(self: Any, *args: Any) -> None:
    """Stop lifespan events when exiting the transport context."""
    manager: LifespanManager | None = getattr(self, "_lifespan_manager", None)
    if manager is not None:
        await manager.__aexit__(*args)
        self._lifespan_manager = None
    await _original_aexit(self, *args)


@pytest.fixture(autouse=True)
def patch_asgi_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ASGITransport class methods for proper lifespan handling."""
    monkeypatch.setattr(ASGITransport, "__aenter__", _lifespan_aenter)
    monkeypatch.setattr(ASGITransport, "__aexit__", _lifespan_aexit)
