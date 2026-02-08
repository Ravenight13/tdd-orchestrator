"""Unit tests for post-RED test file discovery."""

from __future__ import annotations

from pathlib import Path

from tdd_orchestrator.worker_pool.file_discovery import discover_test_file


async def test_file_at_expected_path(tmp_path: Path) -> None:
    """Returns expected path when file exists there (fast path)."""
    test_dir = tmp_path / "tests" / "unit"
    test_dir.mkdir(parents=True)
    (test_dir / "test_foo.py").write_text("# test")

    result = await discover_test_file("tests/unit/test_foo.py", tmp_path)

    assert result == "tests/unit/test_foo.py"


async def test_file_in_different_subdirectory(tmp_path: Path) -> None:
    """Finds file when it's in a subdirectory of the expected parent."""
    # Expected: tests/unit/api/models/test_foo.py
    # Actual: tests/unit/test_foo.py
    test_dir = tmp_path / "tests" / "unit"
    test_dir.mkdir(parents=True)
    (test_dir / "test_foo.py").write_text("# test")

    result = await discover_test_file("tests/unit/api/models/test_foo.py", tmp_path)

    assert result == "tests/unit/test_foo.py"


async def test_file_not_found_returns_none(tmp_path: Path) -> None:
    """Returns None when file doesn't exist anywhere."""
    test_dir = tmp_path / "tests" / "unit"
    test_dir.mkdir(parents=True)

    result = await discover_test_file("tests/unit/test_missing.py", tmp_path)

    assert result is None


async def test_empty_path_returns_none(tmp_path: Path) -> None:
    """Returns None for empty path."""
    result = await discover_test_file("", tmp_path)

    assert result is None


async def test_disambiguates_by_expected_parent(tmp_path: Path) -> None:
    """Prefers the match in the expected parent directory tree."""
    # Two files with same name in different directories
    unit_dir = tmp_path / "tests" / "unit"
    unit_dir.mkdir(parents=True)
    (unit_dir / "test_foo.py").write_text("# unit test")

    integration_dir = tmp_path / "tests" / "integration"
    integration_dir.mkdir(parents=True)
    (integration_dir / "test_foo.py").write_text("# integration test")

    # Expected path is under tests/unit/..., should prefer tests/unit/test_foo.py
    result = await discover_test_file("tests/unit/api/test_foo.py", tmp_path)

    assert result == "tests/unit/test_foo.py"


async def test_broadens_to_standard_dirs(tmp_path: Path) -> None:
    """Falls back to searching standard test directories."""
    # File exists in tests/integration/ but expected under tests/unit/
    integration_dir = tmp_path / "tests" / "integration"
    integration_dir.mkdir(parents=True)
    (integration_dir / "test_bar.py").write_text("# integration test")

    result = await discover_test_file("tests/unit/test_bar.py", tmp_path)

    assert result == "tests/integration/test_bar.py"


async def test_finds_in_nested_subdirectory(tmp_path: Path) -> None:
    """Finds file nested deeper than expected."""
    nested = tmp_path / "tests" / "unit" / "api" / "models"
    nested.mkdir(parents=True)
    (nested / "test_schemas.py").write_text("# test")

    result = await discover_test_file("tests/unit/test_schemas.py", tmp_path)

    assert result == "tests/unit/api/models/test_schemas.py"
