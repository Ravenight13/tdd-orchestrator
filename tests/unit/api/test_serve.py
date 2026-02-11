"""Tests for the API server runner module.

Tests verify that run_server correctly configures and starts uvicorn
with appropriate defaults and forwarded arguments.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

    def test_run_server_passes_create_app_to_uvicorn(self) -> None:
        """GIVEN run_server is called with no arguments
        WHEN uvicorn.run is mocked
        THEN it is invoked with the create_app application.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server()

            mock_uvicorn.run.assert_called_once()
            call_args = mock_uvicorn.run.call_args
            # First positional argument should be the app
            assert len(call_args.args) >= 1 or "app" in call_args.kwargs, (
                "uvicorn.run should receive an app argument"
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
        """GIVEN run_server is called with host='0.0.0.0', port=9000, log_level='debug'
        WHEN uvicorn.run is mocked
        THEN it is invoked with exactly those overridden values.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(host="0.0.0.0", port=9000, log_level="debug")

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

    def test_run_server_forwards_arbitrary_uvicorn_kwargs(self) -> None:
        """GIVEN run_server is called with additional uvicorn kwargs
        WHEN uvicorn.run is mocked
        THEN those kwargs are forwarded to uvicorn.run.
        """
        from tdd_orchestrator.api.serve import run_server

        with patch("tdd_orchestrator.api.serve.uvicorn") as mock_uvicorn:
            run_server(workers=4, timeout_keep_alive=30)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("workers") == 4, (
                "workers kwarg should be forwarded"
            )
            assert call_kwargs.get("timeout_keep_alive") == 30, (
                "timeout_keep_alive kwarg should be forwarded"
            )


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
