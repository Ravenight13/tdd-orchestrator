# Dead Ends

Failed approaches that should not be re-attempted. Check this file before proposing solutions to avoid known pitfalls.

---

### Testing Through `_run_with_cleanup()`
**Date:** 2026-01-20
**What Was Tried:** Writing tests that exercise the full CLI entry point through `_run_with_cleanup()`.
**Why It Failed:** `_run_with_cleanup()` calls `os._exit(0)` which terminates the test process entirely. No way to capture results or assert outcomes.
**Correct Approach:** Test `main()` directly, bypassing the cleanup wrapper. The cleanup logic is a thin shell that doesn't need unit testing.

### DB Singleton Pattern for Tests
**Date:** 2026-01-18
**What Was Tried:** Using the `get_db()` singleton to share database connections across test functions.
**Why It Failed:** Connections leaked between tests, causing state pollution. Tests that passed in isolation failed when run together.
**Correct Approach:** Use `reset_db()` in test fixtures to ensure clean state. Each test gets its own in-memory database.

### Creating `src/__init__.py`
**Date:** 2026-01-17
**What Was Tried:** Adding `src/__init__.py` to make the src directory a proper Python package.
**Why It Failed:** Enables the wrong import pattern (`from src.tdd_orchestrator import ...`) which breaks when installed as a package. The src-layout intentionally avoids this.
**Correct Approach:** Never create `src/__init__.py`. Import paths are `from tdd_orchestrator import ...` — the `src/` prefix is a filesystem detail, not a package path.

### Hardcoded External File Paths in Parser Tests
**Date:** 2026-01-22
**What Was Tried:** Parser tests referenced hardcoded external file paths for test fixtures.
**Why It Failed:** Tests broke when run from different directories or on different machines. Path assumptions made tests fragile and non-portable.
**Correct Approach:** Use inline `_FIXTURE_CONTENT` constants defined directly in the test module. Self-contained tests that work anywhere.

### Skipping `get_existing_prefixes()` Mock in Dry-Run Tests
**Date:** 2026-01-25
**What Was Tried:** Assuming `run_decomposition()` in dry-run mode wouldn't call `get_existing_prefixes()`.
**Why It Failed:** The function calls `get_existing_prefixes()` regardless of dry-run flag. Without mocking, tests fail with database errors.
**Correct Approach:** Always mock `get_existing_prefixes()` in unit tests for `run_decomposition()`, even in dry-run mode.

### Adding `type: ignore` to All Fallback Import Lines
**Date:** 2026-01-20
**What Was Tried:** Adding `# type: ignore[import-not-found]` to every line in try/except ImportError blocks (both the import and fallback).
**Why It Failed:** Unnecessary ignores suppress real errors. mypy only errors on specific lines, not all lines in the block.
**Correct Approach:** Only add `# type: ignore` where mypy actually reports an error. Run mypy first, then add ignores only to flagged lines.
