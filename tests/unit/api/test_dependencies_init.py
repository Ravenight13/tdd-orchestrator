"""Tests for dependency initialization and shutdown lifecycle.

Tests cover the init_dependencies() and shutdown_dependencies() functions
that manage module-level singletons for OrchestratorDB and SSEBroadcaster.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from src.tdd_orchestrator.api.dependencies import (
    get_broadcaster_dep,
    get_db_dep,
    init_dependencies,
    shutdown_dependencies,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDependenciesBeforeInit:
    """Tests for accessing dependencies before init_dependencies() is called."""

    @pytest.fixture(autouse=True)
    async def ensure_shutdown(self) -> None:
        """Ensure dependencies are shut down before each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_get_db_dep_raises_runtime_error_when_not_initialized(self) -> None:
        """GIVEN init_dependencies() has not been called.

        WHEN get_db_dep() is called
        THEN it raises RuntimeError indicating dependencies are not initialized.
        """
        with pytest.raises(RuntimeError) as exc_info:
            get_db_dep()

        assert "not initialized" in str(exc_info.value).lower()

    async def test_get_broadcaster_dep_raises_runtime_error_when_not_initialized(
        self,
    ) -> None:
        """GIVEN init_dependencies() has not been called.

        WHEN get_broadcaster_dep() is called
        THEN it raises RuntimeError indicating dependencies are not initialized.
        """
        with pytest.raises(RuntimeError) as exc_info:
            get_broadcaster_dep()

        assert "not initialized" in str(exc_info.value).lower()


class TestInitDependencies:
    """Tests for init_dependencies() function."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Clean up dependencies after each test."""
        yield
        await shutdown_dependencies()

    async def test_init_creates_db_singleton_when_called_with_valid_path(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN a valid db_path using tmp_path fixture.

        WHEN init_dependencies() is called
        THEN the module-level OrchestratorDB singleton is created and connected.
        """
        db_path = tmp_path / "test.db"

        await init_dependencies(db_path=str(db_path))

        db = get_db_dep()
        assert db is not None
        # Verify it's a database instance (has expected attributes)
        assert hasattr(db, "close")

    async def test_init_creates_broadcaster_singleton_when_called_with_valid_path(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN a valid db_path using tmp_path fixture.

        WHEN init_dependencies() is called
        THEN the module-level SSEBroadcaster singleton is created.
        """
        db_path = tmp_path / "test.db"

        await init_dependencies(db_path=str(db_path))

        broadcaster = get_broadcaster_dep()
        assert broadcaster is not None

    async def test_get_db_dep_returns_same_instance_on_subsequent_calls(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_db_dep() is called multiple times
        THEN it returns the same instance each time.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        db1 = get_db_dep()
        db2 = get_db_dep()

        assert db1 is db2

    async def test_get_broadcaster_dep_returns_same_instance_on_subsequent_calls(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_broadcaster_dep() is called multiple times
        THEN it returns the same instance each time.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        broadcaster1 = get_broadcaster_dep()
        broadcaster2 = get_broadcaster_dep()

        assert broadcaster1 is broadcaster2


class TestInitDependenciesIdempotency:
    """Tests for init_dependencies() idempotency."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Clean up dependencies after each test."""
        yield
        await shutdown_dependencies()

    async def test_init_is_idempotent_for_db_singleton(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time
        THEN the existing OrchestratorDB singleton remains the same object.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))
        db_first = get_db_dep()

        # Call init again
        await init_dependencies(db_path=str(db_path))
        db_second = get_db_dep()

        assert db_first is db_second

    async def test_init_is_idempotent_for_broadcaster_singleton(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time
        THEN the existing SSEBroadcaster singleton remains the same object.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))
        broadcaster_first = get_broadcaster_dep()

        # Call init again
        await init_dependencies(db_path=str(db_path))
        broadcaster_second = get_broadcaster_dep()

        assert broadcaster_first is broadcaster_second

    async def test_init_does_not_create_new_instances_on_second_call(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time
        THEN it does not create new instances (both singletons verified).
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))
        db_first = get_db_dep()
        broadcaster_first = get_broadcaster_dep()

        # Call init again
        await init_dependencies(db_path=str(db_path))
        db_second = get_db_dep()
        broadcaster_second = get_broadcaster_dep()

        assert db_first is db_second
        assert broadcaster_first is broadcaster_second


class TestShutdownDependencies:
    """Tests for shutdown_dependencies() function."""

    async def test_shutdown_closes_db_connection(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called and singletons are active.

        WHEN shutdown_dependencies() is called
        THEN the OrchestratorDB connection is closed.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))
        db = get_db_dep()

        # Mock the close method to verify it's called
        original_close = db.close
        close_called = False

        async def mock_close() -> None:
            nonlocal close_called
            close_called = True
            await original_close()

        db.close = mock_close  # type: ignore[method-assign]

        await shutdown_dependencies()

        assert close_called is True

    async def test_shutdown_resets_db_singleton_to_uninitialized(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called and singletons are active.

        WHEN shutdown_dependencies() is called
        THEN the module-level db singleton is reset to uninitialized state.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        await shutdown_dependencies()

        with pytest.raises(RuntimeError):
            get_db_dep()

    async def test_shutdown_resets_broadcaster_singleton_to_uninitialized(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called and singletons are active.

        WHEN shutdown_dependencies() is called
        THEN the module-level broadcaster singleton is reset to uninitialized state.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        await shutdown_dependencies()

        with pytest.raises(RuntimeError):
            get_broadcaster_dep()

    async def test_shutdown_is_safe_noop_when_called_twice(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN shutdown_dependencies() has already been called.

        WHEN shutdown_dependencies() is called again
        THEN it is a safe no-op that does not raise.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        await shutdown_dependencies()
        # Should not raise
        await shutdown_dependencies()

        # Verify still in uninitialized state
        with pytest.raises(RuntimeError):
            get_db_dep()

    async def test_shutdown_is_safe_noop_when_never_initialized(self) -> None:
        """GIVEN init_dependencies() was never called.

        WHEN shutdown_dependencies() is called
        THEN it is a safe no-op that does not raise.
        """
        # Ensure we start fresh
        await shutdown_dependencies()

        # Should not raise even though nothing was initialized
        await shutdown_dependencies()

        # Confirm still uninitialized
        with pytest.raises(RuntimeError):
            get_db_dep()


class TestFullLifecycle:
    """Tests for full init → shutdown → re-init lifecycle."""

    async def test_reinit_after_shutdown_creates_new_db_singleton(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init then shutdown has been called.

        WHEN init_dependencies() is called again
        THEN a new OrchestratorDB singleton is created successfully.
        """
        db_path = tmp_path / "test.db"

        # First cycle
        await init_dependencies(db_path=str(db_path))
        db_first = get_db_dep()
        await shutdown_dependencies()

        # Second cycle
        await init_dependencies(db_path=str(db_path))
        db_second = get_db_dep()

        # Should be a new instance, not the same object
        assert db_second is not db_first
        assert db_second is not None

        # Cleanup
        await shutdown_dependencies()

    async def test_reinit_after_shutdown_creates_new_broadcaster_singleton(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init then shutdown has been called.

        WHEN init_dependencies() is called again
        THEN a new SSEBroadcaster singleton is created successfully.
        """
        db_path = tmp_path / "test.db"

        # First cycle
        await init_dependencies(db_path=str(db_path))
        broadcaster_first = get_broadcaster_dep()
        await shutdown_dependencies()

        # Second cycle
        await init_dependencies(db_path=str(db_path))
        broadcaster_second = get_broadcaster_dep()

        # Should be a new instance, not the same object
        assert broadcaster_second is not broadcaster_first
        assert broadcaster_second is not None

        # Cleanup
        await shutdown_dependencies()

    async def test_full_lifecycle_multiple_cycles_works_without_errors(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN a fresh state.

        WHEN multiple init → shutdown cycles are performed
        THEN each cycle works without errors.
        """
        db_path = tmp_path / "test.db"

        for cycle in range(3):
            # Init
            await init_dependencies(db_path=str(db_path))

            # Verify singletons accessible
            db = get_db_dep()
            broadcaster = get_broadcaster_dep()
            assert db is not None
            assert broadcaster is not None

            # Shutdown
            await shutdown_dependencies()

            # Verify uninitialized
            with pytest.raises(RuntimeError):
                get_db_dep()
            with pytest.raises(RuntimeError):
                get_broadcaster_dep()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Clean up dependencies after each test."""
        yield
        await shutdown_dependencies()

    async def test_init_with_empty_db_path_raises_error(self) -> None:
        """GIVEN an empty string db_path.

        WHEN init_dependencies() is called
        THEN it raises an appropriate error.
        """
        with pytest.raises((ValueError, OSError, RuntimeError)):
            await init_dependencies(db_path="")

    async def test_init_with_invalid_db_path_raises_error(self) -> None:
        """GIVEN an invalid db_path (non-existent directory).

        WHEN init_dependencies() is called
        THEN it raises an appropriate error.
        """
        invalid_path = "/nonexistent/directory/that/does/not/exist/test.db"

        with pytest.raises((ValueError, OSError, RuntimeError)):
            await init_dependencies(db_path=invalid_path)

    async def test_get_db_dep_type_is_correct_after_init(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_db_dep() is called
        THEN the returned object has the expected OrchestratorDB interface.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        db = get_db_dep()

        # Check it has expected database methods
        assert hasattr(db, "close")
        assert callable(db.close)

    async def test_get_broadcaster_dep_type_is_correct_after_init(
        self,
        tmp_path: Path,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_broadcaster_dep() is called
        THEN the returned object has the expected SSEBroadcaster interface.
        """
        db_path = tmp_path / "test.db"
        await init_dependencies(db_path=str(db_path))

        broadcaster = get_broadcaster_dep()

        # Check it's not None (SSEBroadcaster specifics depend on implementation)
        assert broadcaster is not None
