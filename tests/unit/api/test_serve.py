"""Tests for the API server runner module.

Tests verify that run_server correctly configures and starts uvicorn
with appropriate defaults and forwarded arguments.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestCreateAppReExport:
    """Tests for create_app re-export from api package __init__.py."""

    def test_create_app_importable_from_api_package(self) -> None:
        """GIVEN the api package is imported
        WHEN accessing `from tdd_orchestrator.api import create_app`
        THEN the symbol resolves successfully and is callable.
        """
        from tdd_orchestrator.api import create_app

        assert callable(create_app), "create_app should be callable"


class TestRunServerDefaults:
    """Tests for run_server with default arguments."""

    def test_run_server_uses_default_host_when_not_specified(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with host='127.0.0.1'.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("host") == "127.0.0.1", (
                "Default host should be '127.0.0.1'"
            )

    def test_run_server_uses_default_port_when_not_specified(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with port=8420.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("port") == 8420, "Default port should be 8420"

    def test_run_server_uses_default_log_level_when_not_specified(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with log_level='info'.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("log_level") == "info", (
                "Default log_level should be 'info'"
            )

    def test_run_server_uses_default_reload_false_when_not_specified(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with reload=False.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("reload") is False, "Default reload should be False"

    def test_run_server_passes_app_factory_string_to_uvicorn(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with the factory import string and factory=True.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_args = mock_uvicorn.run.call_args
            # First positional argument should be the factory import string
            assert call_args.args[0] == "tdd_orchestrator.api.app:create_app", (
                "uvicorn.run should receive the factory import string"
            )
            assert call_args.kwargs.get("factory") is True, (
                "uvicorn.run should receive factory=True"
            )


class TestRunServerExplicitArguments:
    """Tests for run_server with explicitly provided arguments."""

    def test_run_server_forwards_explicit_host(self) -> None:
        """GIVEN run_server is called with explicit host='0.0.0.0'
        WHEN uvicorn.run is mocked
        THEN it is invoked with host='0.0.0.0'.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(host="0.0.0.0")

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("host") == "0.0.0.0", (
                "Explicit host should be forwarded"
            )

    def test_run_server_forwards_explicit_port(self) -> None:
        """GIVEN run_server is called with explicit port=9000
        WHEN uvicorn.run is mocked
        THEN it is invoked with port=9000.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(port=9000)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("port") == 9000, (
                "Explicit port should be forwarded"
            )

    def test_run_server_forwards_explicit_log_level(self) -> None:
        """GIVEN run_server is called with explicit log_level='debug'
        WHEN uvicorn.run is mocked
        THEN it is invoked with log_level='debug'.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(log_level="debug")

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("log_level") == "debug", (
                "Explicit log_level should be forwarded"
            )

    def test_run_server_forwards_all_explicit_arguments_together(self) -> None:
        """GIVEN run_server is called with host='0.0.0.0', port=9000, log_level='debug', reload=True
        WHEN uvicorn.run is mocked
        THEN it is invoked with exactly those overridden values.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(host="0.0.0.0", port=9000, log_level="debug", reload=True)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("host") == "0.0.0.0", (
                "Explicit host should be forwarded"
            )
            assert call_kwargs.get("port") == 9000, (
                "Explicit port should be forwarded"
            )
            assert call_kwargs.get("log_level") == "debug", (
                "Explicit log_level should be forwarded"
            )
            assert call_kwargs.get("reload") is True, (
                "Explicit reload should be forwarded"
            )


class TestRunServerKwargsForwarding:
    """Tests for run_server forwarding additional uvicorn kwargs."""

    def test_run_server_forwards_reload_true(self) -> None:
        """GIVEN run_server is called with reload=True
        WHEN uvicorn.run is mocked
        THEN reload=True is forwarded to uvicorn.run.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(reload=True)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("reload") is True, (
                "reload=True should be forwarded to uvicorn.run"
            )

    def test_run_server_forwards_reload_false(self) -> None:
        """GIVEN run_server is called with reload=False
        WHEN uvicorn.run is mocked
        THEN reload=False is forwarded to uvicorn.run.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(reload=False)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("reload") is False, (
                "reload=False should be forwarded to uvicorn.run"
            )


class TestRunServerDbPath:
    """Tests for run_server db_path environment variable handling."""

    def test_run_server_sets_env_var_when_db_path_provided(self) -> None:
        """GIVEN a db_path argument
        WHEN run_server(db_path='/tmp/test.db') is called
        THEN TDD_ORCHESTRATOR_DB_PATH is set to '/tmp/test.db' before uvicorn.run is invoked.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            captured_env: dict[str, str | None] = {}

            def capture_env(*args: object, **kwargs: object) -> None:
                captured_env["value"] = os.environ.get("TDD_ORCHESTRATOR_DB_PATH")

            mock_uvicorn.run.side_effect = capture_env

            run_server(db_path="/tmp/test.db")

            assert captured_env.get("value") == "/tmp/test.db", (
                "TDD_ORCHESTRATOR_DB_PATH should be set to the provided db_path"
            )

    def test_run_server_restores_env_var_after_successful_call(self) -> None:
        """GIVEN a db_path argument and no previous env var
        WHEN run_server completes successfully
        THEN the env var is cleaned up afterward.
        """
        from tdd_orchestrator.api.serve import run_server

        env_var_name = "TDD_ORCHESTRATOR_DB_PATH"
        original_value = os.environ.pop(env_var_name, None)

        try:
            with patch("tdd_orchestrator.api.serve.uvicorn"):
                run_server(db_path="/tmp/test.db")

            after_value = os.environ.get(env_var_name)
            assert after_value is None, (
                "TDD_ORCHESTRATOR_DB_PATH should be cleaned up after run_server"
            )
        finally:
            if original_value is not None:
                os.environ[env_var_name] = original_value

    def test_run_server_restores_previous_env_var_value(self) -> None:
        """GIVEN TDD_ORCHESTRATOR_DB_PATH is already set
        WHEN run_server(db_path=...) completes
        THEN the original value is restored.
        """
        from tdd_orchestrator.api.serve import run_server

        env_var_name = "TDD_ORCHESTRATOR_DB_PATH"
        original_value = "/original/path.db"

        os.environ[env_var_name] = original_value
        try:
            with patch("tdd_orchestrator.api.serve.uvicorn"):
                run_server(db_path="/tmp/test.db")

            assert os.environ.get(env_var_name) == original_value, (
                "Original TDD_ORCHESTRATOR_DB_PATH should be restored"
            )
        finally:
            os.environ.pop(env_var_name, None)

    def test_run_server_restores_env_var_on_exception(self) -> None:
        """GIVEN a db_path argument
        WHEN uvicorn.run raises an exception
        THEN the env var is still restored/cleaned up.
        """
        from tdd_orchestrator.api.serve import run_server

        env_var_name = "TDD_ORCHESTRATOR_DB_PATH"
        original_value = os.environ.pop(env_var_name, None)

        try:
            with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
                mock_uvicorn.run.side_effect = OSError("Test error")

                with pytest.raises(OSError):
                    run_server(db_path="/tmp/test.db")

            after_value = os.environ.get(env_var_name)
            assert after_value is None, (
                "TDD_ORCHESTRATOR_DB_PATH should be cleaned up even on exception"
            )
        finally:
            if original_value is not None:
                os.environ[env_var_name] = original_value

    def test_run_server_without_db_path_does_not_modify_env_var(self) -> None:
        """GIVEN no db_path argument
        WHEN run_server() is called
        THEN TDD_ORCHESTRATOR_DB_PATH is not modified.
        """
        from tdd_orchestrator.api.serve import run_server

        env_var_name = "TDD_ORCHESTRATOR_DB_PATH"
        original = os.environ.pop(env_var_name, None)

        try:
            with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
                captured_env: dict[str, str | None] = {}

                def capture_env(*args: object, **kwargs: object) -> None:
                    captured_env["value"] = os.environ.get(env_var_name)

                mock_uvicorn.run.side_effect = capture_env

                run_server()

                assert captured_env.get("value") is None, (
                    "TDD_ORCHESTRATOR_DB_PATH should not be set when db_path not provided"
                )
        finally:
            if original is not None:
                os.environ[env_var_name] = original


class TestRunServerUvicornNotInstalled:
    """Tests for run_server when uvicorn is not installed."""

    def test_run_server_raises_runtime_error_when_uvicorn_not_installed(self) -> None:
        """GIVEN uvicorn is not installed (ImportError on import)
        WHEN run_server() is called
        THEN a RuntimeError is raised with a message indicating uvicorn must be installed.
        """
        import sys

        # Save original module references
        original_uvicorn = sys.modules.get("uvicorn")
        original_serve = sys.modules.get("tdd_orchestrator.api.serve")

        try:
            # Remove uvicorn and serve module from cache
            sys.modules.pop("uvicorn", None)
            sys.modules.pop("tdd_orchestrator.api.serve", None)

            # Mock the import to raise ImportError for uvicorn
            original_import = __builtins__["__import__"]

            def mock_import(
                name: str,
                globals: dict[str, object] | None = None,
                locals: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "uvicorn":
                    raise ImportError("No module named 'uvicorn'")
                return original_import(name, globals, locals, fromlist, level)

            with patch.dict("builtins.__dict__", {"__import__": mock_import}):
                with pytest.raises(RuntimeError) as exc_info:
                    from tdd_orchestrator.api.serve import run_server as fresh_run_server

                    fresh_run_server()

                error_msg = str(exc_info.value).lower()
                assert "uvicorn" in error_msg or "pip install" in error_msg, (
                    "RuntimeError should mention uvicorn or installation instructions"
                )
        finally:
            # Restore original modules
            if original_uvicorn is not None:
                sys.modules["uvicorn"] = original_uvicorn
            if original_serve is not None:
                sys.modules["tdd_orchestrator.api.serve"] = original_serve

    def test_run_server_error_message_suggests_api_extra(self) -> None:
        """GIVEN uvicorn is not installed
        WHEN run_server() raises RuntimeError
        THEN the message suggests installing tdd-orchestrator[api].
        """
        import sys

        original_uvicorn = sys.modules.get("uvicorn")
        original_serve = sys.modules.get("tdd_orchestrator.api.serve")

        try:
            sys.modules.pop("uvicorn", None)
            sys.modules.pop("tdd_orchestrator.api.serve", None)

            original_import = __builtins__["__import__"]

            def mock_import(
                name: str,
                globals: dict[str, object] | None = None,
                locals: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "uvicorn":
                    raise ImportError("No module named 'uvicorn'")
                return original_import(name, globals, locals, fromlist, level)

            with patch.dict("builtins.__dict__", {"__import__": mock_import}):
                with pytest.raises(RuntimeError) as exc_info:
                    from tdd_orchestrator.api.serve import run_server as fresh_run_server

                    fresh_run_server()

                error_msg = str(exc_info.value)
                assert "pip install" in error_msg.lower() or "api" in error_msg.lower(), (
                    "RuntimeError should suggest installation method"
                )
        finally:
            if original_uvicorn is not None:
                sys.modules["uvicorn"] = original_uvicorn
            if original_serve is not None:
                sys.modules["tdd_orchestrator.api.serve"] = original_serve


class TestRunServerErrorPropagation:
    """Tests for run_server error handling behavior."""

    def test_run_server_propagates_oserror_from_uvicorn(self) -> None:
        """GIVEN run_server is called and uvicorn.run raises an OSError
        WHEN the exception propagates
        THEN run_server does not swallow the error and the OSError is raised.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            mock_uvicorn.run.side_effect = OSError("Address already in use")

            with pytest.raises(OSError) as exc_info:
                run_server()

            assert "Address already in use" in str(exc_info.value), (
                "OSError message should be preserved"
            )

    def test_run_server_propagates_oserror_with_port_in_use_message(self) -> None:
        """GIVEN run_server is called and uvicorn.run raises an OSError for port in use
        WHEN the exception propagates
        THEN the original OSError is raised to the caller unchanged.
        """
        from tdd_orchestrator.api.serve import run_server

        port_error = OSError(98, "Address already in use")
        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            mock_uvicorn.run.side_effect = port_error

            with pytest.raises(OSError) as exc_info:
                run_server()

            assert exc_info.value is port_error, (
                "The exact same OSError instance should be raised"
            )

    def test_run_server_propagates_oserror_with_specific_port(self) -> None:
        """GIVEN run_server(port=8420) is called and uvicorn.run raises an OSError
        WHEN the exception propagates
        THEN the OSError propagates to the caller without being swallowed.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            mock_uvicorn.run.side_effect = OSError("Address already in use")

            with pytest.raises(OSError) as exc_info:
                run_server(port=8420)

            assert "Address already in use" in str(exc_info.value), (
                "OSError should propagate when using specific port"
            )

    def test_run_server_does_not_catch_generic_exceptions(self) -> None:
        """GIVEN run_server is called and uvicorn.run raises a RuntimeError
        WHEN the exception propagates
        THEN run_server does not swallow the error.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            mock_uvicorn.run.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(RuntimeError) as exc_info:
                run_server()

            assert "Unexpected error" in str(exc_info.value), (
                "RuntimeError should propagate unchanged"
            )
