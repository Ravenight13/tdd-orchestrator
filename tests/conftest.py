"""Root conftest.py for pytest configuration.

This file adds the project root to sys.path to enable imports like:
    from src.tdd_orchestrator import ...
"""

import sys
from pathlib import Path

# Add project root to sys.path for src.tdd_orchestrator imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
