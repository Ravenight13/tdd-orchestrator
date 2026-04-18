---
session_date: 2026-02-07
session_time: 09:41:36
status: Enhanced CLAUDE.md with code organization rules
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Enhanced CLAUDE.md with code organization rules

**Date**: 2026-02-07 | **Time**: 09:41:36 CST

---

## Executive Summary

Reviewed an external example CLAUDE.md for best practices and adapted core concepts to the TDD Orchestrator project. Added five new sections to CLAUDE.md: File Structure, Environment Variables, Code Organization (mission critical), Testing Strategy, and an 800-line file size backstop in Non-Negotiable Rules. Identified 4 files currently violating the new 800-line limit and logged them as structured TODOs.

---

## Key Decisions

- **Code Organization is mission critical**: Adopted the "many small files" philosophy with 200-400 lines typical, 800 absolute max. This was given dedicated section status plus a Non-Negotiable Rule backstop (Option B approach over just adding to rules).
- **Splitting signals documented**: Defined concrete triggers for when to split files (multiple classes, unrelated functions, imports spanning many domains).
- **File size thresholds**: 400 lines = soft target (proactively split), 800 lines = hard ceiling (Non-Negotiable Rule).
- **Did not adopt**: Numbered critical rules format, TypeScript patterns, PR review workflow (solo project), or anything duplicating existing security.md/dev-patterns.md rules.

---

## Completed Work

### Accomplishments

- Fetched and analyzed external example CLAUDE.md from `affaan-m/everything-claude-code` repo
- Added **File Structure** section with full directory tree and per-module descriptions
- Added **Environment Variables** section documenting all optional env vars grouped by purpose
- Added **Code Organization (Mission Critical)** section with file size limits and splitting guidance
- Added **Testing Strategy** section with test hierarchy, TDD expectations, and 80% coverage target
- Added 800-line hard ceiling as first Non-Negotiable Rule
- Audited all source files for compliance — identified 4 violators
- Created TO-DOS.md with structured, actionable items for each oversized file

### Files Modified

- `CLAUDE.md` — Added 5 new sections (File Structure, Environment Variables, Code Organization, Testing Strategy, 800-line backstop rule)
- `TO-DOS.md` — Created with 4 structured TODO items for file splitting work

### Git State

- **Branch**: main
- **Recent commits**: ffd926b chore(session): evaluated-codebase-health-and-cataloged-test-failures
- **Uncommitted changes**: CLAUDE.md (modified), TO-DOS.md (new), uv.lock (new/unrelated)

---

## Known Issues

- 4 source files exceed the new 800-line limit: circuit_breaker.py (1866), worker_pool.py (1459), database.py (1425), ast_checker.py (1085)
- prompt_builder.py at 725 lines is approaching the limit

---

## Next Priorities

1. **Split circuit_breaker.py (1866 lines)** — Decompose into separate modules per breaker type (stage, worker, system) with shared base. Re-export from `circuit_breaker/__init__.py` to preserve public API. This is the largest violator at 2x+ the limit.
2. **Split worker_pool.py (1459 lines)** — Identify responsibility boundaries (lifecycle, task distribution, execution) and separate into focused modules.
3. **Split database.py (1425 lines)** — Separate query operations by domain (tasks, circuit breakers, metrics) with shared connection module.
4. **Split ast_checker.py (1085 lines)** — Group AST checks by logical category into separate modules.

---

*Session logged: 2026-02-07 09:41:36 CST*
