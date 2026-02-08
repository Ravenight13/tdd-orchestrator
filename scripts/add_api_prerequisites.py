#!/usr/bin/env python3
"""One-shot script to insert Phase 0 prerequisite tasks for the API layer.

The existing 46 API tasks (Phases 1-12) were created before Phase 0
prerequisite generation existed. This script adds 2 Phase 0 setup tasks
and wires Phase 1 tasks to depend on them.

Usage:
    .venv/bin/python scripts/add_api_prerequisites.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add src to path so we can import tdd_orchestrator
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


PHASE_0_TASKS = [
    {
        "task_key": "API-TDD-0A-01",
        "title": "Add [api] optional dependencies to pyproject.toml",
        "goal": (
            "Add fastapi, uvicorn[standard], pydantic to pyproject.toml "
            "[project.optional-dependencies] and install"
        ),
        "spec_id": "api-layer",
        "acceptance_criteria": [
            "pyproject.toml has [api] extra with 3 packages",
            "pip install -e '.[api]' succeeds without errors",
            "import of first package (fastapi) succeeds",
        ],
        "test_file": "tests/unit/test_api_dependency_setup.py",
        "impl_file": "pyproject.toml",
        "depends_on": [],
        "phase": 0,
        "sequence": 1,
        "verify_command": ".venv/bin/pip install -e '.[api]'",
        "done_criteria": "All [api] packages installable",
    },
    {
        "task_key": "API-TDD-0A-02",
        "title": "Create src/tdd_orchestrator/api package structure",
        "goal": "Create directory tree and __init__.py files for src/tdd_orchestrator/api",
        "spec_id": "api-layer",
        "acceptance_criteria": [
            "Directory src/tdd_orchestrator/api/ exists",
            "src/tdd_orchestrator/api/__init__.py exists and is importable",
            "Package tdd_orchestrator.api is importable",
        ],
        "test_file": "tests/unit/test_package_structure.py",
        "impl_file": "src/tdd_orchestrator/api/__init__.py",
        "depends_on": [],
        "phase": 0,
        "sequence": 2,
        "verify_command": "python -c 'import tdd_orchestrator.api'",
        "done_criteria": "Package src/tdd_orchestrator/api importable",
    },
]

PHASE_0_KEYS = ["API-TDD-0A-01", "API-TDD-0A-02"]


async def main() -> None:
    from tdd_orchestrator.database import OrchestratorDB
    from tdd_orchestrator.task_loader import load_tdd_tasks, update_task_depends_on

    async with OrchestratorDB() as db:
        # Step 1: Insert Phase 0 tasks
        print("=== Inserting Phase 0 prerequisite tasks ===")
        result = await load_tdd_tasks(PHASE_0_TASKS, db=db, skip_duplicates=True)
        print(f"  Loaded: {result['loaded']}")
        print(f"  Skipped: {result['skipped']}")
        if result["errors"]:
            print(f"  Errors: {result['errors']}")
        for key in result["task_keys"]:
            print(f"  + {key}")

        # Step 2: Update Phase 1 tasks to depend on Phase 0
        print("\n=== Updating Phase 1 depends_on ===")
        rows = await db.execute_query(
            "SELECT task_key, depends_on FROM tasks WHERE phase = ?",
            (1,),
        )
        updated = 0
        for row in rows:
            task_key = row["task_key"]
            current_deps = json.loads(row["depends_on"]) if row["depends_on"] else []
            # Add Phase 0 keys if not already present
            new_deps = list(set(current_deps) | set(PHASE_0_KEYS))
            if new_deps != current_deps:
                await update_task_depends_on(task_key, sorted(new_deps), db=db)
                print(f"  Updated {task_key}: depends_on={sorted(new_deps)}")
                updated += 1

        print(f"\n  Updated {updated} Phase 1 tasks")

        # Step 3: Summary
        total_rows = await db.execute_query("SELECT COUNT(*) as cnt FROM tasks")
        total = total_rows[0]["cnt"]
        p0_rows = await db.execute_query(
            "SELECT task_key, title, phase, sequence FROM tasks WHERE phase = ? ORDER BY sequence",
            (0,),
        )
        print(f"\n=== Summary ===")
        print(f"  Total tasks in DB: {total}")
        print(f"  Phase 0 tasks:")
        for r in p0_rows:
            print(f"    {r['task_key']}: {r['title']} (phase={r['phase']}, seq={r['sequence']})")


if __name__ == "__main__":
    asyncio.run(main())
