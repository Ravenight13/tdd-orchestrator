"""Post-RED test file discovery and path reconciliation.

After the RED stage, the Claude worker may create the test file at a
different path than expected. This module searches for the file and
returns the actual path so downstream stages use the correct location.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Search directories in priority order
_SEARCH_DIRS = ("tests/unit", "tests/integration", "tests", "test")


async def discover_test_file(expected_path: str, base_dir: Path) -> str | None:
    """Discover the actual location of a test file after RED stage.

    Args:
        expected_path: The path the task spec expects (relative to base_dir).
        base_dir: Root directory of the project.

    Returns:
        Relative path to the discovered file, or None if not found.
    """
    if not expected_path:
        return None

    # Fast path: file exists at expected location
    if (base_dir / expected_path).exists():
        return expected_path

    filename = Path(expected_path).name
    if not filename:
        return None

    # Strategy 1: search the expected parent directory first
    # e.g., if expected was tests/unit/api/models/test_foo.py,
    # search tests/unit/api/ first to disambiguate
    expected_parent = Path(expected_path).parent
    if expected_parent != Path("."):
        # Walk up from the expected parent to find any ancestor that exists
        search_dir = base_dir / expected_parent
        while not search_dir.exists() and search_dir != base_dir:
            search_dir = search_dir.parent

        if search_dir != base_dir and search_dir.exists():
            matches = list(search_dir.rglob(filename))
            if len(matches) == 1:
                return str(matches[0].relative_to(base_dir))
            if len(matches) > 1:
                # Multiple matches in expected parent tree — return first
                logger.warning(
                    "Multiple matches for %s in %s, using first: %s",
                    filename,
                    search_dir,
                    matches[0],
                )
                return str(matches[0].relative_to(base_dir))

    # Strategy 2: broaden search across standard test directories
    for search_dir_name in _SEARCH_DIRS:
        search_dir = base_dir / search_dir_name
        if not search_dir.exists():
            continue

        matches = list(search_dir.rglob(filename))
        if matches:
            result = str(matches[0].relative_to(base_dir))
            logger.info("Discovered test file: %s -> %s", expected_path, result)
            return result

    return None
