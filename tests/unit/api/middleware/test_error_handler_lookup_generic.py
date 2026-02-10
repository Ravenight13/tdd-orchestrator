"""Tests for LookupError and generic Exception handling in error_handler middleware."""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from tdd_orchestrator.api.middleware.error_handler import register_error_handlers


class TestLookupErrorHandler:
    """Tests for LookupError → 404 mapping."""

    def test_lookup_error_returns_404_json_response(self) -> None:
        """GIVEN app with error handlers, WHEN LookupError raised, THEN 404 JSON returned."""

        async def raise_lookup_error(request: Request) -> Response:
            raise LookupError("Task abc not found")

        app = Starlette(routes=[Route("/task", raise_lookup_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/task")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Task abc not found"}

    def test_key_error_subclass_returns_404_json_response(self) -> None:
        """GIVEN app with error handlers, WHEN KeyError (LookupError subclass) raised, THEN 404 JSON returned."""

        async def raise_key_error(request: Request) -> Response:
            raise KeyError("Task xyz not found")

        app = Starlette(routes=[Route("/task", raise_key_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/task")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Task xyz not found"}

    def test_index_error_subclass_returns_404_json_response(self) -> None:
        """GIVEN app with error handlers, WHEN IndexError (LookupError subclass) raised, THEN 404 JSON returned."""

        async def raise_index_error(request: Request) -> Response:
            raise IndexError("Item 5 not found")

        app = Starlette(routes=[Route("/item", raise_index_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/item")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Item 5 not found"}

    def test_lookup_error_with_empty_message_returns_default_detail(self) -> None:
        """GIVEN app with error handlers, WHEN LookupError with empty message, THEN 404 with default detail."""

        async def raise_empty_lookup_error(request: Request) -> Response:
            raise LookupError("")

        app = Starlette(routes=[Route("/empty", raise_empty_lookup_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/empty")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Not found"}

    def test_key_error_with_empty_message_returns_default_detail(self) -> None:
        """GIVEN app with error handlers, WHEN KeyError (subclass) with empty message, THEN 404 with default detail."""

        async def raise_empty_key_error(request: Request) -> Response:
            raise KeyError("")

        app = Starlette(routes=[Route("/empty-key", raise_empty_key_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/empty-key")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Not found"}

    def test_lookup_error_with_no_args_returns_default_detail(self) -> None:
        """GIVEN app with error handlers, WHEN LookupError with no args, THEN 404 with default detail."""

        async def raise_no_args_lookup_error(request: Request) -> Response:
            raise LookupError()

        app = Starlette(routes=[Route("/no-args", raise_no_args_lookup_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/no-args")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Not found"}


class TestGenericExceptionHandler:
    """Tests for unhandled Exception → sanitized 500 mapping."""

    def test_runtime_error_returns_sanitized_500_json_response(self) -> None:
        """GIVEN app with error handlers, WHEN RuntimeError raised, THEN sanitized 500 JSON returned."""

        async def raise_runtime_error(request: Request) -> Response:
            raise RuntimeError("db connection lost")

        app = Starlette(routes=[Route("/db", raise_runtime_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/db")

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Internal server error"}

    def test_generic_exception_does_not_leak_original_message(self) -> None:
        """GIVEN app with error handlers, WHEN Exception raised, THEN original message NOT in response."""
        secret_message = "secret_database_password_123"

        async def raise_exception_with_secret(request: Request) -> Response:
            raise Exception(secret_message)

        app = Starlette(routes=[Route("/secret", raise_exception_with_secret)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/secret")

        assert response.status_code == 500
        assert secret_message not in response.text
        assert response.json() == {"detail": "Internal server error"}

    def test_generic_exception_does_not_leak_traceback(self) -> None:
        """GIVEN app with error handlers, WHEN Exception raised, THEN traceback NOT in response body."""

        async def raise_traced_exception(request: Request) -> Response:
            raise Exception("Traceback sensitive info")

        app = Starlette(routes=[Route("/trace", raise_traced_exception)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/trace")

        assert response.status_code == 500
        assert "Traceback" not in response.text
        assert "File" not in response.text
        assert "line" not in response.text
        assert response.json() == {"detail": "Internal server error"}

    def test_type_error_returns_sanitized_500(self) -> None:
        """GIVEN app with error handlers, WHEN TypeError raised, THEN sanitized 500 returned."""

        async def raise_type_error(request: Request) -> Response:
            raise TypeError("unsupported operand type(s)")

        app = Starlette(routes=[Route("/type", raise_type_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/type")

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Internal server error"}
        assert "unsupported" not in response.text

    def test_attribute_error_returns_sanitized_500(self) -> None:
        """GIVEN app with error handlers, WHEN AttributeError raised, THEN sanitized 500 returned."""

        async def raise_attribute_error(request: Request) -> Response:
            raise AttributeError("'NoneType' object has no attribute 'foo'")

        app = Starlette(routes=[Route("/attr", raise_attribute_error)])
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/attr")

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Internal server error"}
        assert "NoneType" not in response.text


class TestHandlerCoexistence:
    """Tests that all error handlers coexist without conflict."""

    def test_lookup_error_and_value_error_handlers_coexist(self) -> None:
        """GIVEN app with register_error_handlers, WHEN LookupError and ValueError raised, THEN correct status codes."""

        async def raise_lookup_error(request: Request) -> Response:
            raise LookupError("Resource not found")

        async def raise_value_error(request: Request) -> Response:
            raise ValueError("Invalid value provided")

        app = Starlette(
            routes=[
                Route("/lookup", raise_lookup_error),
                Route("/value", raise_value_error),
            ]
        )
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        lookup_response = client.get("/lookup")
        value_response = client.get("/value")

        assert lookup_response.status_code == 404
        assert lookup_response.json() == {"detail": "Resource not found"}

        assert value_response.status_code == 400
        assert value_response.json() == {"detail": "Invalid value provided"}

    def test_all_three_handlers_coexist(self) -> None:
        """GIVEN app with register_error_handlers, WHEN LookupError, ValueError, and Exception raised, THEN all handled correctly."""

        async def raise_lookup_error(request: Request) -> Response:
            raise KeyError("Item missing")

        async def raise_value_error(request: Request) -> Response:
            raise ValueError("Bad input")

        async def raise_generic_exception(request: Request) -> Response:
            raise RuntimeError("Unexpected failure")

        app = Starlette(
            routes=[
                Route("/lookup", raise_lookup_error),
                Route("/value", raise_value_error),
                Route("/generic", raise_generic_exception),
            ]
        )
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        lookup_response = client.get("/lookup")
        value_response = client.get("/value")
        generic_response = client.get("/generic")

        assert lookup_response.status_code == 404
        assert lookup_response.headers["content-type"] == "application/json"
        assert lookup_response.json() == {"detail": "Item missing"}

        assert value_response.status_code == 400
        assert value_response.headers["content-type"] == "application/json"
        assert value_response.json() == {"detail": "Bad input"}

        assert generic_response.status_code == 500
        assert generic_response.headers["content-type"] == "application/json"
        assert generic_response.json() == {"detail": "Internal server error"}

    def test_single_registration_call_applies_all_handlers(self) -> None:
        """GIVEN register_error_handlers called once, WHEN different exceptions raised, THEN all handlers active."""

        async def success_route(request: Request) -> Response:
            from starlette.responses import JSONResponse

            return JSONResponse({"status": "ok"})

        async def lookup_route(request: Request) -> Response:
            raise LookupError("Not found here")

        async def value_route(request: Request) -> Response:
            raise ValueError("Invalid here")

        async def error_route(request: Request) -> Response:
            raise Exception("Generic error")

        app = Starlette(
            routes=[
                Route("/ok", success_route),
                Route("/lookup", lookup_route),
                Route("/value", value_route),
                Route("/error", error_route),
            ]
        )
        # Single registration call
        register_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        # Verify success route still works
        ok_response = client.get("/ok")
        assert ok_response.status_code == 200
        assert ok_response.json() == {"status": "ok"}

        # Verify all error handlers work
        assert client.get("/lookup").status_code == 404
        assert client.get("/value").status_code == 400
        assert client.get("/error").status_code == 500
