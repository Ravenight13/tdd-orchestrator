# Work In Progress

Partially-completed work across sessions. Updated at session end via `/cc-handoff`.

---

### Phase 2: CLI Pipeline
**Type:** Feature
**Started:** 2026-02-05
**Status:** ~90% complete
**What's Done:**
- Phase 2A: Project config system and `init` command (`cli_init.py`)
- Phase 2B: PRD ingest command with `--dry-run`, `--phases`, `--prefix` (`cli_ingest.py`)
- Phase 2C: CLI auto-discovery — all commands wired to `resolve_db_for_cli()`
- Phase 2D: `run-prd` end-to-end pipeline with `--create-pr`, `--dry-run`, `--no-phase-gates` (`cli_run_prd.py`)
**What Remains:**
- `init-prd` template scaffolding command (P1 in PRODUCTION_VISION)
- Standalone preview/decomposition command (--dry-run flags exist on `ingest` and `run-prd`, no dedicated command)
**Next Action:** Implement `tdd-orchestrator init-prd` template scaffolding

### Phase 1: API Layer (FastAPI)
**Type:** Feature
**Started:** 2026-01-25
**Status:** Complete for current scope
**What's Done:**
- FastAPI chosen as ASGI framework (resolved open question from PRODUCTION_VISION)
- 20+ REST endpoints: health (live/ready), tasks (CRUD/stats/progress), workers (list/stale), circuits (health/reset), runs, metrics (Prometheus + JSON), SSE events
- SSE broadcaster with async queue management
- Middleware: CORS, error handlers (ValueError, RuntimeError, general)
- Pydantic request/response models, dependency injection lifecycle
- `tdd-orchestrator serve` command (port 8420 default)
- SSE streaming tests stabilized with timeouts
- Circuit route refactor with integration tests
**What Remains (deferred to later phases):**
- Project registry endpoints (Phase 4 in PRODUCTION_VISION)
- Auth/API key support (Phase 5 in PRODUCTION_VISION)

### Pipeline Integrity
**Type:** Refactor
**Started:** 2026-02-10
**Status:** ~85% complete
**What's Done:**
- Circular dependency detection via Kahn's BFS + DFS (`dependency_validator.py`)
- Acceptance criteria validation with min/max bounds (`validators.py`)
- Atomicity constraints with auto re-decomposition on violation
- Overlap detection — same impl_file + export intersection (`overlap_detector.py`)
- Task ordering via (phase, sequence) tuple + depends_on (`task_model.py`)
- Integration boundary validation (unit tests not on integration layers)
- Unique task key enforcement
- Spec conformance — paths match MODULE STRUCTURE (`spec_validator.py`)
- Phase gate flow integration tests
- Test suite hang fixes (subprocess/lifecycle timeouts)
**What Remains:**
- Explicit deterministic ordering validator (currently implicit via phase+sequence)
- Cross-task dependency conflict detection (e.g., if task B becomes verify-only, A's depends_on ref untested)
**Next Action:** Evaluate whether explicit ordering/conflict validators are needed or if current implicit checks are sufficient

### Test Suite Health
**Type:** Infrastructure
**Started:** 2026-02-12
**Status:** ~95% complete
**What's Done:**
- 1984 tests collected, 1980 passing, 3 skipped
- Dead test removal and hang prevention (timeouts on subprocess and SSE tests)
- Warning reduction (58 → 4 warnings)
**What Remains:**
- 1 failing test: `test_shutdown_releases_resources_without_warnings` (app lifecycle)
- 4 remaining warnings (1 PytestCollectionWarning for `TestFileResult` dataclass + others)
- Coverage gap analysis on newer modules (API layer, CLI pipeline)
**Next Action:** Investigate the failing lifecycle test and remaining warnings

### PRODUCTION_VISION Open Questions
**Type:** Tracking
**Resolved:**
- ASGI Framework: **FastAPI** (pyproject.toml `[project.optional-dependencies] api`)
- PRD Format: **Markdown primary**, extensible via parser
**Still Open:**
- Dashboard hosting: served by daemon or separate static deployment? (Phase 3)
- Registry storage: SQLite, JSON, or lightweight service? (Phase 4)
- Auth model: API keys sufficient or need JWT/OAuth? (Phase 5)
- Task DAG encoding in decomposition output (Phase 4)

### CLAUDE.md Restructure
**Type:** Docs
**Started:** 2026-02-14
**Status:** Complete
**What's Done:**
- Restructured per best practices audit (181 → 84 lines)
- Cut discoverable content (tech stack, file tree, env vars, agents table)
- Removed duplicated rules already auto-loaded from `.claude/rules/`
- Converted `@imports` to plain references
- Added "Things That Will Bite You" section with common gotchas
- Added new CLI commands (`serve`, `run-prd`) to essential commands
