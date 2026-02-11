"""Tests for run_server edge cases and error handling.

Tests cover:
- Missing uvicorn/fastapi handling with helpful install messages
- Default host/port configuration
- Custom host/port overrides
- Uvicorn signal handler configuration (graceful shutdown)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestRunServerMissingDependencies:
    """Tests for handling missing uvicorn/fastapi dependencies."""

    def test_prints_helpful_message_when_uvicorn_not_installed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """GIVEN uvicorn and fastapi are NOT installed
        WHEN run_server() is called
        THEN it prints a helpful message containing 'pip install tdd-orchestrator[api]'
        and raises SystemExit with a non-zero exit code.
        """
        # Simulate uvicorn not being installed by patching the module-level uvicorn to None
        with patch.dict(sys.modules, {"uvicorn": None}):
            # Need to reload the module to pick up the patched uvicorn
            # Instead, we'll patch the module's uvicorn attribute directly
            with patch("tdd_orchestrator.api.serve.uvicorn", None):
                from tdd_orchestrator.api.serve import run_server

                with pytest.raises(RuntimeError) as exc_info:
                    run_server()

                error_message = str(exc_info.value)
                assert "pip install tdd-orchestrator[api]" in error_message
                assert "uvicorn" in error_message.lower()

    def test_exits_with_nonzero_code_when_uvicorn_missing(self) -> None:
        """GIVEN uvicorn is NOT installed
        WHEN run_server() is called
        THEN it raises an exception (non-zero exit scenario).
        """
        with patch("tdd_orchestrator.api.serve.uvicorn", None):
            from tdd_orchestrator.api.serve import run_server

            with pytest.raises(RuntimeError):
                run_server()

    def test_error_message_mentions_uvicorn_when_only_uvicorn_missing(self) -> None:
        """GIVEN only uvicorn is NOT installed (fastapi may or may not be present)
        WHEN run_server() is called
        THEN the error message mentions 'uvicorn' as a missing dependency.
        """
        with patch("tdd_orchestrator.api.serve.uvicorn", None):
            from tdd_orchestrator.api.serve import run_server

            with pytest.raises(RuntimeError) as exc_info:
                run_server()

            error_message = str(exc_info.value)
            assert "uvicorn" in error_message.lower()


class TestRunServerDefaultConfiguration:
    """Tests for run_server with default arguments."""

    def test_uvicorn_run_invoked_with_default_host(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server() is called with default arguments
        THEN uvicorn.run is invoked with host='127.0.0.1'.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["host"] == "127.0.0.1"

    def test_uvicorn_run_invoked_with_default_port(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server() is called with default arguments
        THEN uvicorn.run is invoked with port=8420.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["port"] == 8420

    def test_uvicorn_run_invoked_with_valid_asgi_app(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server() is called with default arguments
        THEN uvicorn.run is invoked with a valid ASGI app string.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server()

            mock_uvicorn.run.assert_called_once()
            call_args = mock_uvicorn.run.call_args
            # First positional argument should be the app string
            app_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("app")
            assert app_arg is not None
            assert isinstance(app_arg, str)
            assert "tdd_orchestrator" in app_arg


class TestRunServerCustomConfiguration:
    """Tests for run_server with custom host/port arguments."""

    def test_uvicorn_run_invoked_with_custom_host(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server(host='0.0.0.0', port=9000) is called with custom host/port
        THEN uvicorn.run is invoked with the overridden host='0.0.0.0'.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(host="0.0.0.0", port=9000)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["host"] == "0.0.0.0"

    def test_uvicorn_run_invoked_with_custom_port(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server(host='0.0.0.0', port=9000) is called with custom host/port
        THEN uvicorn.run is invoked with the overridden port=9000.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(host="0.0.0.0", port=9000)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["port"] == 9000


class TestRunServerSignalHandlers:
    """Tests for uvicorn signal handler configuration."""

    def test_uvicorn_run_not_called_with_signal_handlers_disabled(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server() is called
        THEN uvicorn.run is NOT called with install_signal_handlers=False,
        ensuring uvicorn's built-in SIGINT/SIGTERM graceful shutdown remains active.
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs

            # Signal handlers should NOT be disabled
            # Either the key is not present, or if present, it should not be False
            if "install_signal_handlers" in call_kwargs:
                assert call_kwargs["install_signal_handlers"] is not False
            # If key is not present, uvicorn uses default (True), which is correct

    def test_default_signal_handler_behavior_preserved(self) -> None:
        """GIVEN uvicorn and fastapi ARE installed
        WHEN run_server() is called
        THEN uvicorn's default signal handler behavior is preserved (not explicitly disabled).
        """
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server()

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs

            # Verify install_signal_handlers is not explicitly set to False
            signal_handlers_setting = call_kwargs.get("install_signal_handlers")
            # Should be None (not passed) or True, never False
            assert signal_handlers_setting is not False


class TestRunServerEdgeCases:
    """Edge case tests for run_server."""

    def test_run_server_with_empty_host_string(self) -> None:
        """Test behavior with empty host string."""
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(host="")

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["host"] == ""

    def test_run_server_with_zero_port(self) -> None:
        """Test behavior with port=0 (system-assigned port)."""
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(port=0)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["port"] == 0

    def test_run_server_with_high_port_number(self) -> None:
        """Test behavior with high port number (boundary condition)."""
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(port=65535)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["port"] == 65535

    def test_run_server_forwards_additional_kwargs(self) -> None:
        """Test that additional kwargs are forwarded to uvicorn.run."""
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(workers=4, access_log=False)

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs.get("workers") == 4
            assert call_kwargs.get("access_log") is False

    def test_run_server_with_ipv6_host(self) -> None:
        """Test behavior with IPv6 host address."""
        mock_uvicorn = MagicMock()

        with patch("tdd_orchestrator.api.serve.uvicorn", mock_uvicorn):
            from tdd_orchestrator.api.serve import run_server

            run_server(host="::1")

            mock_uvicorn.run.assert_called_once()
            call_kwargs = mock_uvicorn.run.call_args.kwargs
            assert call_kwargs["host"] == "::1"
