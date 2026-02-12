---
session_date: 2026-02-12
session_time: 15:03:01
status: Wire circuits routes to DB and clean up inline SQL
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Handoff: Wire circuits routes to DB and clean up inline SQL

**Date**: 2026-02-12 | **Time**: 15:03:01 CST

---

## Resume Checklist

Before starting, review:
1. This handoff document
2. Recent git log: `git log --oneline -10`
3. Run health check: `/cc-ready`

```bash
# Quick health check
cd /Users/cliffclarke/Projects/tdd_orchestrator
.venv/bin/pytest tests/unit/ --tb=no -q
.venv/bin/ruff check src/
.venv/bin/mypy src/ --strict
```

---

## Executive Summary

All 4 task route endpoints are now wired to the DB with seeded integration tests. Placeholder dead code removed. The API server actually works end-to-end (DB init bug fixed). 1319 unit + 123 integration tests passing, mypy strict clean. The biggest remaining gap in Phase 1 is the circuits route group.

---

## Current State

- **Branch**: main
- **Known issues**: None
- **Uncommitted changes**: None (committed in session handoff)

---

## Next Priorities

1. **Wire circuits routes to DB** — The `/circuits`, `/circuits/{id}/reset`, and `/circuits/health` endpoints are the last unimplemented route group in Phase 1. The route file likely exists at `src/tdd_orchestrator/api/routes/circuits.py` but needs DB wiring following the same pattern as tasks.py. Uses `v_circuit_breaker_status`, `v_open_circuits`, `v_circuit_health_summary` views. Reference: `docs/plans/PLAN_PHASE1_API_LAYER.md` Step 6.

2. **Clean up inline SQL in task routes** — `src/tdd_orchestrator/api/routes/tasks.py` has raw SQL in `get_tasks()` and `get_stats()` handlers. The Phase 1 plan specifies adding `db.get_tasks_filtered()` to `database/tasks.py` and delegating to it from the route. This would also remove the duplicated `db_status_map`/`api_status_map` dicts scattered across handlers.

3. **Wire SSE observer for real-time events** — Phase 1 Step 9: add `_callbacks: list[Callable]` to `TaskMixin`, dispatch after `commit()` in `update_task_status()`, and register the SSE broadcaster as a callback during API startup. This enables the `/events` SSE endpoint to broadcast real task status changes.

---

## Key Context

- **Full session log**: `.claude/docs/summaries/SESSION_2026-02-12_1503_seeded-task-tests-removed-placeholders-fixed-db-init.md`
- **CLAUDE.md**: Project conventions and rules
- **Architecture**: `docs/ARCHITECTURE.md`
- **Phase 1 Plan**: `docs/plans/PLAN_PHASE1_API_LAYER.md` (complete 10-step build sequence)
- **Task routes**: `src/tdd_orchestrator/api/routes/tasks.py` (299 lines, all endpoints DB-wired)
- **App factory**: `src/tdd_orchestrator/api/app.py` (DB init fixed this session)
- **Test helpers**: `tests/integration/api/helpers.py` (`_create_seeded_test_app()`)
- **DB schema views**: `schema/schema.sql` (v_circuit_breaker_status, v_open_circuits, v_circuit_health_summary)

---

*Handoff created: 2026-02-12 15:03:01 CST*
