"""Test for API-TDD-0A-02: Create src/tdd_orchestrator/api package structure.

This test verifies that the api package structure exists and is importable.
Expected to FAIL until the package is created (RED stage).
"""

from pathlib import Path


def test_api_directory_exists() -> None:
    """Verify that src/tdd_orchestrator/api/ directory exists."""
    api_dir = Path("src/tdd_orchestrator/api")
    assert api_dir.exists(), f"Directory {api_dir} should exist"
    assert api_dir.is_dir(), f"{api_dir} should be a directory"


def test_api_init_file_exists() -> None:
    """Verify that src/tdd_orchestrator/api/__init__.py exists."""
    init_file = Path("src/tdd_orchestrator/api/__init__.py")
    assert init_file.exists(), f"File {init_file} should exist"
    assert init_file.is_file(), f"{init_file} should be a file"


def test_api_package_importable() -> None:
    """Verify that tdd_orchestrator.api package is importable."""
    try:
        import tdd_orchestrator.api  # noqa: F401
    except ImportError as e:
        raise AssertionError(f"Package tdd_orchestrator.api should be importable: {e}") from e
