"""Tests for ValueError exception handler middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tdd_orchestrator.api.middleware.error_handler import register_error_handlers


class TestRegisterErrorHandlersValueError:
    """Test ValueError handling via register_error_handlers."""

    def test_returns_400_when_route_raises_value_error(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError('Invalid input')
        THEN the response status code is 400.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_value_error() -> dict[str, str]:
            raise ValueError("Invalid input")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400

    def test_returns_error_response_body_when_route_raises_value_error(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError('Invalid input')
        THEN the JSON body matches ErrorResponse schema with detail containing 'Invalid input'.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_value_error() -> dict[str, str]:
            raise ValueError("Invalid input")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        json_body = response.json()
        assert "detail" in json_body
        assert json_body["detail"] == "Invalid input"

    def test_returns_400_with_empty_detail_when_value_error_has_empty_message(
        self,
    ) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError with an empty message
        THEN the response status code is 400 and the JSON body is a valid ErrorResponse.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_empty_value_error() -> dict[str, str]:
            raise ValueError("")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400
        json_body = response.json()
        assert "detail" in json_body
        # Empty or default detail string is acceptable
        assert isinstance(json_body["detail"], str)

    def test_does_not_intercept_runtime_error(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises RuntimeError (not a ValueError)
        THEN the ValueError handler does NOT intercept it and FastAPI returns 500.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_runtime_error() -> dict[str, str]:
            raise RuntimeError("Something went wrong")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        # RuntimeError should propagate to FastAPI's default 500 handling
        assert response.status_code == 500

    def test_does_not_intercept_type_error(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises TypeError (not a ValueError)
        THEN the ValueError handler does NOT intercept it.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_type_error() -> dict[str, str]:
            raise TypeError("Type mismatch")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        # TypeError should propagate to FastAPI's default 500 handling
        assert response.status_code == 500

    def test_successful_route_returns_normal_response(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler completes successfully
        THEN the response is returned normally with its original status code and body.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def successful_route() -> dict[str, str]:
            return {"message": "success"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_successful_post_route_returns_201_unmodified(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler returns with status 201
        THEN the response status code remains 201 unmodified.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.post("/test", status_code=201)
        def create_resource() -> dict[str, str]:
            return {"id": "123", "created": "true"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/test")

        assert response.status_code == 201
        assert response.json() == {"id": "123", "created": "true"}

    def test_error_response_content_type_is_json(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError
        THEN the Content-Type of the 400 response is 'application/json'.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_value_error() -> dict[str, str]:
            raise ValueError("some error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_error_response_detail_field_serialization(self) -> None:
        """GIVEN the ErrorResponse model
        WHEN instantiated with detail='some error'
        THEN it serializes to JSON with a 'detail' field equal to 'some error'.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_value_error() -> dict[str, str]:
            raise ValueError("some error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        json_body = response.json()
        assert json_body["detail"] == "some error"

    def test_value_error_with_no_args(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError() with no arguments
        THEN the response status code is 400 and has a valid ErrorResponse.
        """
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/test")
        def raise_value_error_no_args() -> dict[str, str]:
            raise ValueError()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400
        json_body = response.json()
        assert "detail" in json_body
        assert isinstance(json_body["detail"], str)

    def test_value_error_with_special_characters_in_message(self) -> None:
        """GIVEN a FastAPI app with register_error_handlers applied
        WHEN a route handler raises ValueError with special characters
        THEN the detail field contains the special characters properly serialized.
        """
        app = FastAPI()
        register_error_handlers(app)

        error_message = 'Invalid: <script>alert("xss")</script> & "quotes"'

        @app.get("/test")
        def raise_value_error_special() -> dict[str, str]:
            raise ValueError(error_message)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400
        json_body = response.json()
        assert json_body["detail"] == error_message
