---
session_date: 2026-02-11
session_time: 05:35:30
status: Plan pipeline context enrichment enhancements
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Handoff: Plan pipeline context enrichment enhancements

**Date**: 2026-02-11 | **Time**: 05:35:30 CST

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

RED stage sibling awareness is implemented and validated across 11 API tasks (phases 5-7). During validation, we identified 6 context gaps in the TDD pipeline where stages lack information they need. The next session should create a comprehensive implementation plan for all 6 enhancements, prioritized by impact on pipeline success rate.

---

## Current State

- **Branch**: main
- **Test suite**: 1,047 unit tests passing
- **API progress**: 28/48 tasks complete (58.3%)
- **Known issues**: See gap list below
- **Uncommitted changes**: None

---

## Next Priorities

1. **Create implementation plan for all 6 pipeline context gaps**

   The user explicitly requested: "in the next session, create a plan to implement all of these enhancements." Use `EnterPlanMode` and design changes to `prompt_builder.py` and `prompt_templates.py`.

   **The 6 gaps (priority order):**

   | # | Gap | Files | Effort |
   |---|-----|-------|--------|
   | 1 | **Sibling behavioral contracts in RED** — extract status codes, imports, key assertions from sibling tests (not just `await`) | prompt_builder.py | Small |
   | 2 | **FIX stage context enrichment** — add test file content, existing impl, sibling context, acceptance criteria, module exports | prompt_builder.py, prompt_templates.py | Medium |
   | 3 | **conftest.py visibility in GREEN** — surface shared fixtures so GREEN doesn't duplicate or conflict with them | prompt_builder.py | Small |
   | 4 | **Criteria/exports in FIX** — pass acceptance_criteria and module_exports through to FIX template | prompt_builder.py, prompt_templates.py | Small |
   | 5 | **RED_FIX context** — add goal, criteria, import hint so RED_FIX can reason about test intent | prompt_builder.py, prompt_templates.py | Small |
   | 6 | **REFACTOR context** — currently receives minimal info; add impl content and sibling awareness | prompt_builder.py, prompt_templates.py | Low |

   **Key constraint**: `prompt_builder.py` is currently ~557 lines. Adding all 6 enhancements will push it toward 700+. Plan should include a split strategy if it approaches 800.

2. **Continue API pipeline** — 20 pending tasks remain. Can run in parallel with or after enhancements.

3. **Consider decomposition-level behavioral constraints** — The 422/400 mismatch could also be prevented at task spec generation time by encoding cross-task behavioral dependencies in acceptance criteria.

---

## Key Context

- **Full session log**: `.claude/docs/summaries/SESSION_2026-02-11_0535_red-sibling-awareness-and-api-phases-5-7.md`
- **CLAUDE.md**: Project conventions and rules
- **Architecture**: `docs/ARCHITECTURE.md`
- **Pipeline context audit**: Detailed in the session conversation — the explore agent produced a comprehensive "Context Richness by Stage" table showing exactly what each stage sees and what it's missing
- **Phase 5 failure analysis**: 05-02's RED wrote `assert value_response.status_code == 422` but 05-01 established 400. Root cause: sibling hints only extract `await` patterns, not behavioral assertions.

---

*Handoff created: 2026-02-11 05:35:30 CST*
