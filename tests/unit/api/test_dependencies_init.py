"""Tests for dependency lifecycle management (init/shutdown).

This module tests the LIFECYCLE scenarios for dependency management:
init -> use -> shutdown -> re-init cycles, idempotency, and edge cases.

Individual getter behavior (yields/raises, type checks, FastAPI compatibility)
is covered in test_dependencies_deps.py and is NOT duplicated here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

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
    def ensure_shutdown(self) -> Any:
        """Ensure dependencies are in uninitialized state before each test."""
        shutdown_dependencies()
        yield
        shutdown_dependencies()

    async def test_get_db_dep_yields_none_when_never_initialized(self) -> None:
        """GIVEN init_dependencies() has never been called.

        WHEN get_db_dep() is consumed as an async generator
        THEN it yields None (allowing route handlers to fall back to placeholders).
        """
        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None

    async def test_get_broadcaster_dep_raises_runtime_error_when_never_initialized(
        self,
    ) -> None:
        """GIVEN init_dependencies() has never been called.

        WHEN get_broadcaster_dep() is called
        THEN it raises RuntimeError indicating broadcaster is uninitialized.
        """
        with pytest.raises(RuntimeError, match="(?i)uninitialized"):
            get_broadcaster_dep()

    async def test_both_getters_return_uninitialized_before_init(self) -> None:
        """GIVEN init_dependencies() has never been called.

        WHEN both getters are invoked
        THEN db yields None and broadcaster raises RuntimeError.
        """
        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None

        with pytest.raises(RuntimeError):
            get_broadcaster_dep()


class TestInitDependencies:
    """Tests for init_dependencies() creating usable singletons."""

    @pytest.fixture(autouse=True)
    def cleanup_dependencies(self) -> Any:
        """Cleanup dependencies before and after each test."""
        shutdown_dependencies()
        yield
        shutdown_dependencies()

    async def test_init_makes_db_available(self) -> None:
        """GIVEN mock db and broadcaster instances.

        WHEN init_dependencies() is called with them
        THEN get_db_dep() yields the mock db instance.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        gen = get_db_dep()
        db = await gen.__anext__()
        assert db is mock_db

    async def test_init_makes_broadcaster_available(self) -> None:
        """GIVEN mock db and broadcaster instances.

        WHEN init_dependencies() is called with them
        THEN get_broadcaster_dep() returns the mock broadcaster instance.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        broadcaster = get_broadcaster_dep()
        assert broadcaster is mock_broadcaster

    async def test_init_makes_both_singletons_available_simultaneously(self) -> None:
        """GIVEN mock db and broadcaster instances.

        WHEN init_dependencies() is called once
        THEN both getters return the correct instances in the same test scope.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        gen = get_db_dep()
        db = await gen.__anext__()
        broadcaster = get_broadcaster_dep()

        assert db is mock_db
        assert broadcaster is mock_broadcaster


class TestInitIdempotency:
    """Tests for init_dependencies() idempotency."""

    @pytest.fixture(autouse=True)
    def cleanup_dependencies(self) -> Any:
        """Cleanup dependencies before and after each test."""
        shutdown_dependencies()
        yield
        shutdown_dependencies()

    async def test_double_init_with_same_args_preserves_db_identity(self) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time with the same args
        THEN the db singleton remains the same object (identity via `is`).
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()

        init_dependencies(mock_db, mock_broadcaster)
        gen1 = get_db_dep()
        db_first = await gen1.__anext__()

        init_dependencies(mock_db, mock_broadcaster)
        gen2 = get_db_dep()
        db_second = await gen2.__anext__()

        assert db_first is db_second

    async def test_double_init_with_same_args_preserves_broadcaster_identity(self) -> None:
        """GIVEN init_dependencies() has already been called.

        WHEN init_dependencies() is called a second time with the same args
        THEN the broadcaster singleton remains the same object (identity via `is`).
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()

        init_dependencies(mock_db, mock_broadcaster)
        broadcaster_first = get_broadcaster_dep()

        init_dependencies(mock_db, mock_broadcaster)
        broadcaster_second = get_broadcaster_dep()

        assert broadcaster_first is broadcaster_second

    async def test_init_with_different_args_replaces_singletons(self) -> None:
        """GIVEN init_dependencies() has already been called with instances A.

        WHEN init_dependencies() is called again with different instances B (no shutdown)
        THEN the getters return the NEW instances B.
        """
        mock_db_a = MagicMock(name="db_a")
        mock_broadcaster_a = MagicMock(name="broadcaster_a")
        init_dependencies(mock_db_a, mock_broadcaster_a)

        mock_db_b = MagicMock(name="db_b")
        mock_broadcaster_b = MagicMock(name="broadcaster_b")
        init_dependencies(mock_db_b, mock_broadcaster_b)

        gen = get_db_dep()
        db = await gen.__anext__()
        broadcaster = get_broadcaster_dep()

        assert db is mock_db_b
        assert broadcaster is mock_broadcaster_b
        assert db is not mock_db_a
        assert broadcaster is not mock_broadcaster_a


class TestShutdownDependencies:
    """Tests for shutdown_dependencies() behavior."""

    @pytest.fixture(autouse=True)
    def cleanup_dependencies(self) -> Any:
        """Cleanup dependencies before and after each test."""
        shutdown_dependencies()
        yield
        shutdown_dependencies()

    async def test_shutdown_resets_db_to_uninitialized(self) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN shutdown_dependencies() is called
        THEN get_db_dep() yields None again.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        shutdown_dependencies()

        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None

    async def test_shutdown_resets_broadcaster_to_uninitialized(self) -> None:
        """GIVEN init_dependencies() has been called.

        WHEN shutdown_dependencies() is called
        THEN get_broadcaster_dep() raises RuntimeError again.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        shutdown_dependencies()

        with pytest.raises(RuntimeError):
            get_broadcaster_dep()

    async def test_shutdown_without_init_is_safe_noop(self) -> None:
        """GIVEN init_dependencies() was never called.

        WHEN shutdown_dependencies() is called
        THEN it does not raise (safe no-op).
        """
        # Should not raise even if never initialized
        shutdown_dependencies()
        shutdown_dependencies()

        # State remains uninitialized — yields None
        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None

    async def test_repeated_shutdown_after_init_is_idempotent(self) -> None:
        """GIVEN init_dependencies() was called and then shutdown.

        WHEN shutdown_dependencies() is called again (double shutdown)
        THEN it does not raise and state remains uninitialized.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        shutdown_dependencies()
        shutdown_dependencies()  # second call should be safe
        shutdown_dependencies()  # third call should be safe

        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None
        with pytest.raises(RuntimeError):
            get_broadcaster_dep()


class TestFullLifecycle:
    """Tests for full init -> shutdown -> re-init lifecycle."""

    @pytest.fixture(autouse=True)
    def cleanup_dependencies(self) -> Any:
        """Cleanup dependencies before and after each test."""
        shutdown_dependencies()
        yield
        shutdown_dependencies()

    async def test_full_lifecycle_creates_new_instances_after_reinit(self) -> None:
        """GIVEN init -> use -> shutdown has completed.

        WHEN init_dependencies() is called again with NEW mock instances
        THEN the getters return the NEW instances (not the old ones).
        """
        mock_db_1 = MagicMock(name="db_cycle_1")
        mock_broadcaster_1 = MagicMock(name="broadcaster_cycle_1")
        init_dependencies(mock_db_1, mock_broadcaster_1)

        # Use
        gen1 = get_db_dep()
        db_first = await gen1.__anext__()
        broadcaster_first = get_broadcaster_dep()
        assert db_first is mock_db_1
        assert broadcaster_first is mock_broadcaster_1

        # Shutdown
        shutdown_dependencies()

        # Re-init with new instances
        mock_db_2 = MagicMock(name="db_cycle_2")
        mock_broadcaster_2 = MagicMock(name="broadcaster_cycle_2")
        init_dependencies(mock_db_2, mock_broadcaster_2)

        gen2 = get_db_dep()
        db_second = await gen2.__anext__()
        broadcaster_second = get_broadcaster_dep()

        # New instances should be the cycle-2 mocks
        assert db_second is mock_db_2
        assert broadcaster_second is mock_broadcaster_2
        # And NOT the old ones
        assert db_second is not db_first
        assert broadcaster_second is not broadcaster_first

    async def test_multiple_lifecycle_cycles(self) -> None:
        """GIVEN three successive init/shutdown cycles.

        WHEN each cycle uses fresh mock instances
        THEN each cycle's getters return that cycle's instances
        AND shutdown properly resets state between cycles.
        """
        previous_db: object | None = None
        previous_broadcaster: object | None = None

        for cycle in range(3):
            mock_db = MagicMock(name=f"db_cycle_{cycle}")
            mock_broadcaster = MagicMock(name=f"broadcaster_cycle_{cycle}")

            init_dependencies(mock_db, mock_broadcaster)

            gen = get_db_dep()
            current_db = await gen.__anext__()
            current_broadcaster = get_broadcaster_dep()

            assert current_db is mock_db
            assert current_broadcaster is mock_broadcaster

            # Each cycle should have distinct instances from prior cycle
            if previous_db is not None:
                assert current_db is not previous_db
            if previous_broadcaster is not None:
                assert current_broadcaster is not previous_broadcaster

            previous_db = current_db
            previous_broadcaster = current_broadcaster

            shutdown_dependencies()

            # Verify shutdown worked
            gen_after = get_db_dep()
            db_after = await gen_after.__anext__()
            assert db_after is None
            with pytest.raises(RuntimeError):
                get_broadcaster_dep()

    async def test_reinit_after_shutdown_restores_functionality(self) -> None:
        """GIVEN dependencies were initialized then shut down.

        WHEN init_dependencies() is called again
        THEN the async generator for db works end-to-end (yields then exhausts).
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()

        # First cycle
        init_dependencies(mock_db, mock_broadcaster)
        shutdown_dependencies()

        # Re-init
        new_db = MagicMock(name="new_db")
        new_broadcaster = MagicMock(name="new_broadcaster")
        init_dependencies(new_db, new_broadcaster)

        # Verify async generator works end-to-end
        gen = get_db_dep()
        db = await gen.__anext__()
        assert db is new_db

        # Generator should be exhausted after one yield
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
