"""Root conftest.py for pytest configuration.

Adds project root to sys.path so test modules are importable by dotted path
(e.g., tests.unit.api.test_dependencies_lifespan) in monkeypatch.setattr calls.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
