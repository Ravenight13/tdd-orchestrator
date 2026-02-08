"""Tests for API dependency setup in pyproject.toml.

These tests verify that the [api] optional dependency group is properly
configured with fastapi, uvicorn[standard], and pydantic.
"""

import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


class TestApiDependencyConfiguration:
    """Tests for [api] extra configuration in pyproject.toml."""

    @pytest.fixture
    def pyproject_path(self) -> Path:
        """Get the path to pyproject.toml."""
        # Navigate from tests/unit to project root
        test_dir = Path(__file__).parent
        project_root = test_dir.parent.parent
        return project_root / "pyproject.toml"

    @pytest.fixture
    def pyproject_data(self, pyproject_path: Path) -> dict:
        """Load and parse pyproject.toml."""
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)

    def test_api_extra_exists_in_optional_dependencies(
        self, pyproject_data: dict
    ) -> None:
        """Test that [api] extra exists in optional-dependencies."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        assert "api" in optional_deps, (
            "Expected 'api' key in [project.optional-dependencies]"
        )

    def test_api_extra_contains_fastapi(self, pyproject_data: dict) -> None:
        """Test that [api] extra includes fastapi package."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        fastapi_found = any(
            dep.lower().startswith("fastapi") for dep in api_deps
        )
        assert fastapi_found is True, (
            f"Expected 'fastapi' in api dependencies, got: {api_deps}"
        )

    def test_api_extra_contains_uvicorn_standard(
        self, pyproject_data: dict
    ) -> None:
        """Test that [api] extra includes uvicorn[standard] package."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        uvicorn_found = any(
            "uvicorn" in dep.lower() and "standard" in dep.lower()
            for dep in api_deps
        )
        assert uvicorn_found is True, (
            f"Expected 'uvicorn[standard]' in api dependencies, got: {api_deps}"
        )

    def test_api_extra_contains_pydantic(self, pyproject_data: dict) -> None:
        """Test that [api] extra includes pydantic package."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        pydantic_found = any(
            dep.lower().startswith("pydantic") for dep in api_deps
        )
        assert pydantic_found is True, (
            f"Expected 'pydantic' in api dependencies, got: {api_deps}"
        )

    def test_api_extra_has_exactly_three_packages(
        self, pyproject_data: dict
    ) -> None:
        """Test that [api] extra has exactly 3 packages."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        assert len(api_deps) == 3, (
            f"Expected exactly 3 packages in api extra, got {len(api_deps)}: {api_deps}"
        )


class TestApiDependencyInstallation:
    """Tests for successful installation of [api] dependencies."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get the project root directory."""
        test_dir = Path(__file__).parent
        return test_dir.parent.parent

    @pytest.fixture
    def venv_pip(self, project_root: Path) -> Path:
        """Get the path to the virtual environment pip."""
        return project_root / ".venv" / "bin" / "pip"

    def test_api_extra_install_succeeds_without_errors(
        self, project_root: Path, venv_pip: Path
    ) -> None:
        """Test that pip install -e '.[api]' succeeds without errors."""
        result = subprocess.run(
            [str(venv_pip), "install", "-e", ".[api]"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"pip install -e '.[api]' failed with return code {result.returncode}. "
            f"stderr: {result.stderr}"
        )


class TestApiDependencyImport:
    """Tests for successful import of API dependencies."""

    def test_fastapi_import_succeeds(self) -> None:
        """Test that fastapi can be imported after installation."""
        try:
            import fastapi

            assert fastapi is not None, "fastapi module should not be None"
            assert hasattr(fastapi, "FastAPI"), (
                "fastapi should have FastAPI class"
            )
        except ImportError as e:
            pytest.fail(f"Failed to import fastapi: {e}")

    def test_uvicorn_import_succeeds(self) -> None:
        """Test that uvicorn can be imported after installation."""
        try:
            import uvicorn

            assert uvicorn is not None, "uvicorn module should not be None"
            assert hasattr(uvicorn, "run"), "uvicorn should have run function"
        except ImportError as e:
            pytest.fail(f"Failed to import uvicorn: {e}")

    def test_pydantic_import_succeeds(self) -> None:
        """Test that pydantic can be imported after installation."""
        try:
            import pydantic

            assert pydantic is not None, "pydantic module should not be None"
            assert hasattr(pydantic, "BaseModel"), (
                "pydantic should have BaseModel class"
            )
        except ImportError as e:
            pytest.fail(f"Failed to import pydantic: {e}")


class TestApiDependencyEdgeCases:
    """Edge case tests for API dependency configuration."""

    @pytest.fixture
    def pyproject_path(self) -> Path:
        """Get the path to pyproject.toml."""
        test_dir = Path(__file__).parent
        project_root = test_dir.parent.parent
        return project_root / "pyproject.toml"

    @pytest.fixture
    def pyproject_data(self, pyproject_path: Path) -> dict:
        """Load and parse pyproject.toml."""
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)

    def test_api_extra_when_empty_should_have_packages(
        self, pyproject_data: dict
    ) -> None:
        """Test that api extra is not empty."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        assert len(api_deps) > 0, "api extra should not be empty"

    def test_api_packages_when_listed_should_have_valid_format(
        self, pyproject_data: dict
    ) -> None:
        """Test that all api packages have valid dependency format."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        for dep in api_deps:
            assert isinstance(dep, str), f"Dependency should be a string: {dep}"
            assert len(dep) > 0, "Dependency string should not be empty"
            # Package names should start with a letter
            base_name = dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0]
            assert base_name[0].isalpha() if base_name else False, (
                f"Package name should start with a letter: {dep}"
            )

    def test_api_packages_when_duplicated_should_be_unique(
        self, pyproject_data: dict
    ) -> None:
        """Test that api packages are unique (no duplicates)."""
        optional_deps = pyproject_data.get("project", {}).get(
            "optional-dependencies", {}
        )
        api_deps = optional_deps.get("api", [])
        # Extract base package names for comparison
        base_names = [
            dep.lower().split("[")[0].split(">")[0].split("<")[0].split("=")[0]
            for dep in api_deps
        ]
        assert len(base_names) == len(set(base_names)), (
            f"api extra should not have duplicate packages: {api_deps}"
        )

    def test_optional_dependencies_section_exists(
        self, pyproject_data: dict
    ) -> None:
        """Test that optional-dependencies section exists in pyproject.toml."""
        project_section = pyproject_data.get("project", {})
        assert "optional-dependencies" in project_section, (
            "pyproject.toml should have [project.optional-dependencies] section"
        )
