"""Tests for FastAPI dependency injection functions."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from tdd_orchestrator.api.dependencies import (
    get_db_dep,
    get_broadcaster_dep,
    init_dependencies,
    shutdown_dependencies,
)


class TestGetDbDep:
    """Tests for get_db_dep async generator dependency."""

    @pytest.mark.asyncio
    async def test_yields_db_instance_when_initialized(self) -> None:
        """GIVEN the OrchestratorDB singleton has been initialized,
        WHEN get_db_dep() is called as an async generator,
        THEN it yields the OrchestratorDB instance.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            gen = get_db_dep()
            db_instance = await gen.__anext__()

            assert db_instance is mock_db
        finally:
            shutdown_dependencies()

    @pytest.mark.asyncio
    async def test_yields_same_instance_on_every_call_when_initialized(self) -> None:
        """GIVEN the OrchestratorDB singleton has been initialized,
        WHEN get_db_dep() is called multiple times,
        THEN the same instance is yielded on every call.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            gen1 = get_db_dep()
            db_instance1 = await gen1.__anext__()

            gen2 = get_db_dep()
            db_instance2 = await gen2.__anext__()

            assert db_instance1 is db_instance2
            assert db_instance1 is mock_db
        finally:
            shutdown_dependencies()

    @pytest.mark.asyncio
    async def test_yields_none_when_db_uninitialized(self) -> None:
        """GIVEN the OrchestratorDB singleton has NOT been initialized,
        WHEN get_db_dep() is called,
        THEN it yields None (allowing route handlers to fall back to placeholders).
        """
        shutdown_dependencies()

        gen = get_db_dep()
        db_instance = await gen.__anext__()

        assert db_instance is None

    @pytest.mark.asyncio
    async def test_is_async_generator_function(self) -> None:
        """GIVEN get_db_dep is defined,
        WHEN checking its type,
        THEN it is an async generator function compatible with FastAPI Depends().
        """
        import inspect

        assert inspect.isasyncgenfunction(get_db_dep)


class TestGetBroadcasterDep:
    """Tests for get_broadcaster_dep dependency."""

    def test_returns_broadcaster_instance_when_initialized(self) -> None:
        """GIVEN the SSEBroadcaster singleton has been initialized,
        WHEN get_broadcaster_dep() is called,
        THEN it returns the SSEBroadcaster instance directly.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            broadcaster_instance = get_broadcaster_dep()

            assert broadcaster_instance is mock_broadcaster
        finally:
            shutdown_dependencies()

    def test_returns_same_instance_on_every_call_when_initialized(self) -> None:
        """GIVEN the SSEBroadcaster singleton has been initialized,
        WHEN get_broadcaster_dep() is called multiple times,
        THEN the same instance is returned on every call.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            broadcaster_instance1 = get_broadcaster_dep()
            broadcaster_instance2 = get_broadcaster_dep()

            assert broadcaster_instance1 is broadcaster_instance2
            assert broadcaster_instance1 is mock_broadcaster
        finally:
            shutdown_dependencies()

    def test_raises_runtime_error_when_broadcaster_uninitialized(self) -> None:
        """GIVEN the SSEBroadcaster singleton has NOT been initialized,
        WHEN get_broadcaster_dep() is called,
        THEN it raises RuntimeError with appropriate message.
        """
        shutdown_dependencies()

        with pytest.raises(RuntimeError) as exc_info:
            get_broadcaster_dep()

        assert "broadcaster" in str(exc_info.value).lower() or "uninitialized" in str(exc_info.value).lower()

    def test_is_callable_not_generator(self) -> None:
        """GIVEN get_broadcaster_dep is defined,
        WHEN checking its type,
        THEN it is a callable (not a generator) compatible with FastAPI Depends().
        """
        import inspect

        assert callable(get_broadcaster_dep)
        assert not inspect.isasyncgenfunction(get_broadcaster_dep)
        assert not inspect.isgeneratorfunction(get_broadcaster_dep)


class TestInitDependencies:
    """Tests for init_dependencies function."""

    def test_initializes_both_singletons(self) -> None:
        """GIVEN mock db and broadcaster instances,
        WHEN init_dependencies() is called with them,
        THEN both dependencies become available.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()

        init_dependencies(mock_db, mock_broadcaster)

        try:
            broadcaster = get_broadcaster_dep()
            assert broadcaster is mock_broadcaster
        finally:
            shutdown_dependencies()

    @pytest.mark.asyncio
    async def test_init_makes_db_available_via_async_generator(self) -> None:
        """GIVEN mock db instance,
        WHEN init_dependencies() is called,
        THEN db is available via get_db_dep() async generator.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()

        init_dependencies(mock_db, mock_broadcaster)

        try:
            gen = get_db_dep()
            db_instance = await gen.__anext__()
            assert db_instance is mock_db
        finally:
            shutdown_dependencies()


class TestShutdownDependencies:
    """Tests for shutdown_dependencies function."""

    def test_clears_broadcaster_singleton(self) -> None:
        """GIVEN dependencies have been initialized,
        WHEN shutdown_dependencies() is called,
        THEN get_broadcaster_dep() raises RuntimeError.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        shutdown_dependencies()

        with pytest.raises(RuntimeError):
            get_broadcaster_dep()

    @pytest.mark.asyncio
    async def test_clears_db_singleton(self) -> None:
        """GIVEN dependencies have been initialized,
        WHEN shutdown_dependencies() is called,
        THEN get_db_dep() yields None.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        shutdown_dependencies()

        gen = get_db_dep()
        db_instance = await gen.__anext__()
        assert db_instance is None

    def test_is_idempotent(self) -> None:
        """GIVEN dependencies are already shut down,
        WHEN shutdown_dependencies() is called again,
        THEN no error is raised.
        """
        shutdown_dependencies()
        shutdown_dependencies()  # Should not raise

        with pytest.raises(RuntimeError):
            get_broadcaster_dep()


class TestFastAPIDependsCompatibility:
    """Tests for FastAPI Depends() compatibility."""

    @pytest.mark.asyncio
    async def test_get_db_dep_works_as_fastapi_dependency(self) -> None:
        """GIVEN get_db_dep is used as a FastAPI Depends() target,
        WHEN the dependency is resolved,
        THEN it yields the db instance correctly.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            # Simulate how FastAPI would use the async generator dependency
            async for db in get_db_dep():
                assert db is mock_db
                break  # FastAPI would break after getting the value
        finally:
            shutdown_dependencies()

    def test_get_broadcaster_dep_works_as_fastapi_dependency(self) -> None:
        """GIVEN get_broadcaster_dep is used as a FastAPI Depends() target,
        WHEN the dependency is resolved,
        THEN it returns the broadcaster instance correctly.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            # Simulate how FastAPI would use the callable dependency
            broadcaster = get_broadcaster_dep()
            assert broadcaster is mock_broadcaster
        finally:
            shutdown_dependencies()

    @pytest.mark.asyncio
    async def test_async_generator_completes_cleanly(self) -> None:
        """GIVEN get_db_dep async generator is used,
        WHEN the generator is exhausted,
        THEN it completes without error.
        """
        mock_db = MagicMock()
        mock_broadcaster = MagicMock()
        init_dependencies(mock_db, mock_broadcaster)

        try:
            gen = get_db_dep()
            await gen.__anext__()  # Get the db
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()  # Should be exhausted after yielding once
        finally:
            shutdown_dependencies()
