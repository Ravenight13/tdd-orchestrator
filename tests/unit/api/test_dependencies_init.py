"""Tests for dependency lifecycle management (init/shutdown)."""

from __future__ import annotations

import pytest

from tdd_orchestrator.api.dependencies import (
    get_broadcaster_dep,
    get_db_dep,
    init_dependencies,
    shutdown_dependencies,
)


class TestDependenciesBeforeInit:
    """Tests for accessing dependencies before init_dependencies() is called."""

    @pytest.fixture(autouse=True)
    async def ensure_shutdown(self) -> None:
        """Ensure dependencies are in uninitialized state before each test."""
        # Shutdown first to reset any state from previous tests
        await shutdown_dependencies()
        yield
        # Cleanup after test
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
    """Tests for init_dependencies() behavior."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Cleanup dependencies after each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_init_creates_db_singleton_when_called_with_valid_path(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN a valid db_path using tmp_path fixture.

        WHEN init_dependencies() is called and completes
        THEN the module-level OrchestratorDB singleton is created and connected.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        db = get_db_dep()
        assert db is not None
        # Verify it's actually connected by checking the type
        # The actual type check will validate it's an OrchestratorDB instance
        assert hasattr(db, "close") or hasattr(db, "conn")

    async def test_init_creates_broadcaster_singleton_when_called_with_valid_path(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN a valid db_path using tmp_path fixture.

        WHEN init_dependencies() is called and completes
        THEN the module-level SSEBroadcaster singleton is created.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        broadcaster = get_broadcaster_dep()
        assert broadcaster is not None

    async def test_get_db_dep_returns_same_instance_on_subsequent_calls(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_db_dep() is called multiple times
        THEN it returns the same instance each time.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        db1 = get_db_dep()
        db2 = get_db_dep()
        assert db1 is db2

    async def test_get_broadcaster_dep_returns_same_instance_on_subsequent_calls(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN get_broadcaster_dep() is called multiple times
        THEN it returns the same instance each time.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        broadcaster1 = get_broadcaster_dep()
        broadcaster2 = get_broadcaster_dep()
        assert broadcaster1 is broadcaster2


class TestInitIdempotency:
    """Tests for init_dependencies() idempotency."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Cleanup dependencies after each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_init_is_idempotent_for_db_singleton(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time
        THEN it is idempotent and the existing OrchestratorDB singleton remains
        the same object (verified via `is` identity check).
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))
        db_first = get_db_dep()

        # Call init again
        await init_dependencies(db_path=str(db_path))
        db_second = get_db_dep()

        assert db_first is db_second

    async def test_init_is_idempotent_for_broadcaster_singleton(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time
        THEN it is idempotent and the existing SSEBroadcaster singleton remains
        the same object (verified via `is` identity check).
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))
        broadcaster_first = get_broadcaster_dep()

        # Call init again
        await init_dependencies(db_path=str(db_path))
        broadcaster_second = get_broadcaster_dep()

        assert broadcaster_first is broadcaster_second


class TestShutdownDependencies:
    """Tests for shutdown_dependencies() behavior."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Cleanup dependencies after each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_shutdown_resets_singletons_to_uninitialized_state(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has been called and singletons are active.

        WHEN shutdown_dependencies() is called
        THEN the module-level singletons are reset to their uninitialized state.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        # Verify singletons are initialized
        db = get_db_dep()
        broadcaster = get_broadcaster_dep()
        assert db is not None
        assert broadcaster is not None

        # Shutdown
        await shutdown_dependencies()

        # Verify singletons are now uninitialized
        with pytest.raises(RuntimeError):
            get_db_dep()
        with pytest.raises(RuntimeError):
            get_broadcaster_dep()

    async def test_shutdown_closes_db_connection(
        self,
        tmp_path: pytest.TempPathFactory,
        mocker: pytest.MonkeyPatch,
    ) -> None:
        """GIVEN init_dependencies() has been called and singletons are active.

        WHEN shutdown_dependencies() is called
        THEN the OrchestratorDB connection is closed.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))

        db = get_db_dep()
        # Create a spy on the close method if it exists
        close_spy = mocker.spy(db, "close") if hasattr(db, "close") else None

        await shutdown_dependencies()

        if close_spy is not None:
            close_spy.assert_awaited_once()

    async def test_shutdown_is_safe_noop_when_called_again(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN shutdown_dependencies() has already been called.

        WHEN shutdown_dependencies() is called again
        THEN it is a safe no-op that does not raise.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        await init_dependencies(db_path=str(db_path))
        await shutdown_dependencies()

        # Second shutdown should not raise
        await shutdown_dependencies()
        # Third shutdown should also not raise
        await shutdown_dependencies()

        # Verify state is still uninitialized
        with pytest.raises(RuntimeError):
            get_db_dep()

    async def test_shutdown_is_safe_noop_when_never_initialized(self) -> None:
        """GIVEN init_dependencies() was never called.

        WHEN shutdown_dependencies() is called
        THEN it is a safe no-op that does not raise.
        """
        # Should not raise even if never initialized
        await shutdown_dependencies()
        await shutdown_dependencies()

        # State should still be uninitialized
        with pytest.raises(RuntimeError):
            get_db_dep()


class TestFullLifecycle:
    """Tests for full init → shutdown → re-init lifecycle."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Cleanup dependencies after each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_full_lifecycle_init_shutdown_reinit(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN init_dependencies() has been called and then shutdown_dependencies()
        has been called.

        WHEN init_dependencies() is called again (simulating a fresh app lifespan cycle)
        THEN new OrchestratorDB and SSEBroadcaster singletons are created successfully.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]

        # First init
        await init_dependencies(db_path=str(db_path))
        db_first = get_db_dep()
        broadcaster_first = get_broadcaster_dep()
        assert db_first is not None
        assert broadcaster_first is not None

        # Shutdown
        await shutdown_dependencies()

        # Re-init
        await init_dependencies(db_path=str(db_path))
        db_second = get_db_dep()
        broadcaster_second = get_broadcaster_dep()

        # New instances should be created (not the same objects)
        assert db_second is not None
        assert broadcaster_second is not None
        assert db_second is not db_first
        assert broadcaster_second is not broadcaster_first

    async def test_multiple_lifecycle_cycles(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN multiple init/shutdown cycles.

        WHEN each cycle completes
        THEN each cycle creates new singletons and shutdown properly resets state.
        """
        db_path = tmp_path / "test.db"  # type: ignore[operator]
        previous_db = None
        previous_broadcaster = None

        for cycle in range(3):
            # Init
            await init_dependencies(db_path=str(db_path))
            current_db = get_db_dep()
            current_broadcaster = get_broadcaster_dep()

            assert current_db is not None
            assert current_broadcaster is not None

            # Each cycle should create new instances
            if previous_db is not None:
                assert current_db is not previous_db
            if previous_broadcaster is not None:
                assert current_broadcaster is not previous_broadcaster

            previous_db = current_db
            previous_broadcaster = current_broadcaster

            # Shutdown
            await shutdown_dependencies()

            # Verify shutdown worked
            with pytest.raises(RuntimeError):
                get_db_dep()


class TestEdgeCases:
    """Edge case tests for dependency management."""

    @pytest.fixture(autouse=True)
    async def cleanup_dependencies(self) -> None:
        """Cleanup dependencies after each test."""
        await shutdown_dependencies()
        yield
        await shutdown_dependencies()

    async def test_init_with_empty_string_path(self) -> None:
        """GIVEN an empty string db_path.

        WHEN init_dependencies() is called
        THEN it should handle the edge case appropriately (either raise or use default).
        """
        # This tests edge case behavior - implementation may raise or use default
        try:
            await init_dependencies(db_path="")
            # If it doesn't raise, ensure singletons are created
            db = get_db_dep()
            assert db is not None
        except (ValueError, OSError, RuntimeError):
            # Expected to raise for invalid path
            pass

    async def test_init_with_nonexistent_directory_path(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """GIVEN a db_path in a non-existent directory.

        WHEN init_dependencies() is called
        THEN behavior depends on implementation (may create dir or raise).
        """
        db_path = tmp_path / "nonexistent" / "subdir" / "test.db"  # type: ignore[operator]
        try:
            await init_dependencies(db_path=str(db_path))
            db = get_db_dep()
            assert db is not None
        except (OSError, RuntimeError):
            # Expected if implementation doesn't create directories
            pass
