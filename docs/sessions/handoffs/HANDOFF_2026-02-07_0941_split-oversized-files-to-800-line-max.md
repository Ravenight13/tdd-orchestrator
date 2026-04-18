---
session_date: 2026-02-07
session_time: 09:41:36
status: Split oversized files to 800-line max
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Handoff: Split oversized files to 800-line max

**Date**: 2026-02-07 | **Time**: 09:41:36 CST

---

## Resume Checklist

Before starting, review:
1. This handoff document
2. `TO-DOS.md` — has structured splitting plan for each file
3. Recent git log: `git log --oneline -10`
4. Run health check: `/cc-ready`

```bash
# Quick health check
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m pytest tests/unit/ --tb=no -q
python -m ruff check src/
python -m mypy src/ --strict
```

---

## Executive Summary

CLAUDE.md now enforces an 800-line max per file as a Non-Negotiable Rule. Four existing files violate this limit. TO-DOS.md contains structured splitting plans for each. The next session should tackle these one at a time, starting with circuit_breaker.py (the largest violator), ensuring tests pass and public APIs are preserved after each split.

---

## Current State

- **Branch**: main
- **Known issues**: 4 files over 800-line limit (circuit_breaker.py: 1866, worker_pool.py: 1459, database.py: 1425, ast_checker.py: 1085)
- **Uncommitted changes**: CLAUDE.md (modified), TO-DOS.md (new), uv.lock (unrelated)

---

## Next Priorities

1. **Split circuit_breaker.py (1866 lines)** — Convert to a package: `circuit_breaker/` with `__init__.py`, `base.py`, `stage.py`, `worker.py`, `system.py`. Re-export all public names from `__init__.py` so existing imports remain valid. Run full test suite after to verify nothing breaks.

2. **Split worker_pool.py (1459 lines)** — Analyze responsibilities (worker lifecycle, task claiming/distribution, execution logic) and extract into focused modules. Preserve the `WorkerPool` class as the main public interface.

3. **Split database.py (1425 lines)** — Separate by query domain (task operations, circuit breaker operations, metrics). Keep shared connection management in a base module.

4. **Split ast_checker.py (1085 lines)** — Group related AST checks into logical modules.

**Strategy for each split:**
- Read the file, identify logical groupings
- Create new modules, move code, update imports
- Run `ruff check src/`, `mypy src/ --strict`, `pytest tests/ -v` after each split
- Commit each split separately with `refactor(module): split into focused submodules`

---

## Key Context

- **Full session log**: `.claude/docs/summaries/SESSION_2026-02-07_0941_enhanced-claude-md-with-code-organization-rules.md`
- **TODO details**: `TO-DOS.md` — has file-specific splitting plans with line counts and solution approaches
- **CLAUDE.md**: Now includes Code Organization rules and 800-line Non-Negotiable Rule
- **Architecture**: `docs/ARCHITECTURE.md`

---

*Handoff created: 2026-02-07 09:41:36 CST*
