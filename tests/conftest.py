"""Root conftest.py for pytest configuration.

Adds project root to sys.path so test modules are importable by dotted path
(e.g., tests.unit.api.test_dependencies_lifespan) in monkeypatch.setattr calls.

Provides --run-slow flag to opt in to slow tests (skipped by default).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="Run tests marked @pytest.mark.slow"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="needs --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
