"""Tests for CORS middleware configuration."""

import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from tdd_orchestrator.api.middleware.cors import configure_cors


class TestConfigureCorsDefaultOrigins:
    """Tests for default localhost origins when TDD_CORS_ORIGINS is not set."""

    def test_adds_cors_middleware_when_env_not_set(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN CORSMiddleware is added to the app.
        """
        with patch.dict(os.environ, {}, clear=True):
            # Ensure TDD_CORS_ORIGINS is not in environment
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            middleware_classes = [m.cls for m in app.user_middleware]
            assert CORSMiddleware in middleware_classes

    def test_default_origins_include_localhost_3000(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN allow_origins includes 'http://localhost:3000'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "http://localhost:3000" in origins

    def test_default_origins_include_localhost_5173(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN allow_origins includes 'http://localhost:5173'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "http://localhost:5173" in origins

    def test_default_origins_include_127_0_0_1_3000(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN allow_origins includes 'http://127.0.0.1:3000'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "http://127.0.0.1:3000" in origins

    def test_default_origins_include_127_0_0_1_5173(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN allow_origins includes 'http://127.0.0.1:5173'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "http://127.0.0.1:5173" in origins

    def test_default_origins_contains_exactly_four_entries(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is not set
        WHEN configure_cors(app) is called
        THEN allow_origins contains exactly the four default localhost origins.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            expected_origins = [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
            assert set(origins) == set(expected_origins)
            assert len(origins) == 4


class TestConfigureCorsCustomOrigins:
    """Tests for custom origins when TDD_CORS_ORIGINS is set."""

    def test_uses_custom_origins_from_env_var(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is set to custom origins
        WHEN configure_cors(app) is called
        THEN CORSMiddleware is added with exactly those origins.
        """
        custom_origins = "https://my-app.example.com,https://staging.example.com"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": custom_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "https://my-app.example.com" in origins
            assert "https://staging.example.com" in origins

    def test_custom_origins_exclude_localhost_defaults(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is set to custom origins
        WHEN configure_cors(app) is called
        THEN allow_origins does NOT include localhost defaults.
        """
        custom_origins = "https://my-app.example.com,https://staging.example.com"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": custom_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "http://localhost:3000" not in origins
            assert "http://localhost:5173" not in origins
            assert "http://127.0.0.1:3000" not in origins
            assert "http://127.0.0.1:5173" not in origins

    def test_custom_origins_contains_exactly_specified_entries(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is set to two origins
        WHEN configure_cors(app) is called
        THEN allow_origins contains exactly those two origins.
        """
        custom_origins = "https://my-app.example.com,https://staging.example.com"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": custom_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert len(origins) == 2
            assert set(origins) == {
                "https://my-app.example.com",
                "https://staging.example.com",
            }


class TestConfigureCorsWildcard:
    """Tests for wildcard CORS access when TDD_CORS_ORIGINS is set to '*'."""

    def test_wildcard_origin_enables_any_origin(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is set to '*'
        WHEN configure_cors(app) is called
        THEN CORSMiddleware is added with allow_origins=['*'].
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "*"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert origins == ["*"]

    def test_wildcard_origin_contains_only_asterisk(self) -> None:
        """GIVEN TDD_CORS_ORIGINS env var is set to '*'
        WHEN configure_cors(app) is called
        THEN allow_origins contains exactly one element: '*'.
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "*"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert len(origins) == 1
            assert origins[0] == "*"


class TestConfigureCorsMethodsAndHeaders:
    """Tests for HTTP methods and headers configuration."""

    def test_allow_methods_includes_get(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_methods includes GET.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "GET" in methods

    def test_allow_methods_includes_post(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_methods includes POST.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "POST" in methods

    def test_allow_methods_includes_put(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_methods includes PUT.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "PUT" in methods

    def test_allow_methods_includes_delete(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_methods includes DELETE.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "DELETE" in methods

    def test_allow_methods_includes_options(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_methods includes OPTIONS.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "OPTIONS" in methods

    def test_allow_headers_includes_content_type(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_headers includes 'Content-Type'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            headers = cors_middleware.kwargs.get("allow_headers", [])
            assert "Content-Type" in headers

    def test_allow_headers_includes_authorization(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_headers includes 'Authorization'.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            headers = cors_middleware.kwargs.get("allow_headers", [])
            assert "Authorization" in headers

    def test_allow_credentials_is_true(self) -> None:
        """GIVEN configure_cors(app) has been called
        WHEN the middleware config is inspected
        THEN allow_credentials is True.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TDD_CORS_ORIGINS", None)
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            credentials = cors_middleware.kwargs.get("allow_credentials", False)
            assert credentials is True


class TestConfigureCorsWhitespaceTrimming:
    """Tests for whitespace trimming in origin values."""

    def test_trims_leading_whitespace_from_origins(self) -> None:
        """GIVEN TDD_CORS_ORIGINS contains entries with leading whitespace
        WHEN configure_cors(app) is called
        THEN origins are trimmed.
        """
        whitespace_origins = " https://example.com, https://other.com"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": whitespace_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "https://example.com" in origins
            assert " https://example.com" not in origins

    def test_trims_trailing_whitespace_from_origins(self) -> None:
        """GIVEN TDD_CORS_ORIGINS contains entries with trailing whitespace
        WHEN configure_cors(app) is called
        THEN origins are trimmed.
        """
        whitespace_origins = "https://example.com ,https://other.com "
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": whitespace_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "https://example.com" in origins
            assert "https://example.com " not in origins
            assert "https://other.com" in origins
            assert "https://other.com " not in origins

    def test_excludes_empty_strings_from_trailing_commas(self) -> None:
        """GIVEN TDD_CORS_ORIGINS contains trailing commas producing empty strings
        WHEN configure_cors(app) is called
        THEN empty strings are excluded from origins.
        """
        trailing_comma_origins = "https://example.com,https://other.com,"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": trailing_comma_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "" not in origins
            assert len(origins) == 2

    def test_handles_multiple_commas_producing_empty_strings(self) -> None:
        """GIVEN TDD_CORS_ORIGINS contains multiple consecutive commas
        WHEN configure_cors(app) is called
        THEN empty strings are excluded from origins.
        """
        multi_comma_origins = "https://example.com,,https://other.com"
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": multi_comma_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "" not in origins
            assert len(origins) == 2
            assert "https://example.com" in origins
            assert "https://other.com" in origins

    def test_trims_mixed_whitespace_and_excludes_empty(self) -> None:
        """GIVEN TDD_CORS_ORIGINS contains leading/trailing whitespace and trailing commas
        WHEN configure_cors(app) is called
        THEN origins are trimmed and empty strings excluded.
        """
        messy_origins = " https://example.com , https://other.com , "
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": messy_origins}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            origins = cors_middleware.kwargs.get("allow_origins", [])
            assert "" not in origins
            assert " " not in origins
            assert "https://example.com" in origins
            assert "https://other.com" in origins
            assert len(origins) == 2


class TestConfigureCorsWithCustomOriginsMethodsAndHeaders:
    """Tests that methods/headers/credentials apply regardless of origin source."""

    def test_custom_origins_have_correct_methods(self) -> None:
        """GIVEN TDD_CORS_ORIGINS is set to custom origins
        WHEN configure_cors(app) is called
        THEN allow_methods includes GET, POST, PUT, DELETE, OPTIONS.
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "https://example.com"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "GET" in methods
            assert "POST" in methods
            assert "PUT" in methods
            assert "DELETE" in methods
            assert "OPTIONS" in methods

    def test_custom_origins_have_correct_headers(self) -> None:
        """GIVEN TDD_CORS_ORIGINS is set to custom origins
        WHEN configure_cors(app) is called
        THEN allow_headers includes 'Content-Type' and 'Authorization'.
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "https://example.com"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            headers = cors_middleware.kwargs.get("allow_headers", [])
            assert "Content-Type" in headers
            assert "Authorization" in headers

    def test_custom_origins_have_credentials_enabled(self) -> None:
        """GIVEN TDD_CORS_ORIGINS is set to custom origins
        WHEN configure_cors(app) is called
        THEN allow_credentials is True.
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "https://example.com"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            credentials = cors_middleware.kwargs.get("allow_credentials", False)
            assert credentials is True

    def test_wildcard_origins_have_correct_methods(self) -> None:
        """GIVEN TDD_CORS_ORIGINS is set to '*'
        WHEN configure_cors(app) is called
        THEN allow_methods includes GET, POST, PUT, DELETE, OPTIONS.
        """
        with patch.dict(os.environ, {"TDD_CORS_ORIGINS": "*"}):
            app = FastAPI()
            configure_cors(app)

            cors_middleware = _get_cors_middleware(app)
            assert cors_middleware is not None
            methods = cors_middleware.kwargs.get("allow_methods", [])
            assert "GET" in methods
            assert "POST" in methods
            assert "PUT" in methods
            assert "DELETE" in methods
            assert "OPTIONS" in methods


def _get_cors_middleware(app: FastAPI) -> Any:
    """Helper to extract CORS middleware configuration from app.

    Returns the middleware object if found, otherwise None.
    """
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            return middleware
    return None
