---
session_date: 2026-02-07
session_time: 21:42:38
status: Decomposition pipeline refinements and mypy fixes
branch: main
tags: [session-complete, tdd-orchestrator]
---

# Session: Decomposition pipeline refinements and mypy fixes

**Date**: 2026-02-07 | **Time**: 21:42:38 CST

---

## Executive Summary

Fixed 5 root causes producing inaccurate task decompositions in the 4-pass LLM pipeline (hardcoded paths, unpersisted dependencies, unused module API data, missing validation, bogus integration test paths). Also resolved all 16 pre-existing mypy strict errors across 5 files, achieving zero-error compliance across all 59 source files. Added 29 new tests (525 -> 554 total).

---

## Key Decisions

- **Dynamic path prefixes over hardcoded list**: Replaced static `src/htmx/` prefix list with `_build_valid_prefixes()` that extracts paths from the spec's MODULE STRUCTURE. Falls back to `src/` generically rather than any project-specific default.
- **Validate-only spec conformance**: `SpecConformanceValidator` reports violations but does not auto-fix. Users review warnings and re-run if needed.
- **`--scaffolding-ref` opt-in flag**: MODULE API SPECIFICATION forwarding to Pass 2 requires explicit opt-in rather than changing the default, since not all specs have this section.
- **`dataclasses.replace()` for decomposer.py**: Replaced 48 lines of manual field-by-field `DecomposedTask` reconstruction with one-liner `replace()` calls, bringing the file from 841 to 795 lines (under 800-line limit).
- **Remove type: ignore comments for installed SDK**: Since `claude_agent_sdk` is installed via `[sdk]` extra, the `type: ignore[import-not-found]` comments were unnecessary and causing `[unused-ignore]` errors under strict mode.

---

## Completed Work

### Accomplishments

- **RC-3 (CRITICAL)**: Added `update_task_depends_on()` to `task_loader.py` and wired into `decompose_spec.py` Step 6 so calculated dependencies survive to the database
- **RC-1 (CRITICAL)**: Replaced hardcoded `src/htmx/` path prefixes in `prompts.py` with dynamic `_build_valid_prefixes()` that extracts from spec's MODULE STRUCTURE
- **RC-2 (CRITICAL)**: Forward `module_api` and `module_structure` to Pass 2 prompts in `decomposer.py`; added `--scaffolding-ref` CLI flag for opt-in
- **RC-4 (HIGH)**: Created `spec_validator.py` with 3 validation checks (impl_file paths, module_exports, integration test paths) integrated between Steps 5 and 6
- **RC-5 (HIGH)**: Updated integration/e2e prompt rules to instruct LLM to set `impl_file` equal to `test_file`
- **Pre-req**: Refactored `_generate_all_hints()` with `dataclasses.replace()` (841 -> 795 lines)
- **Mypy**: Resolved all 16 strict errors across `mcp_tools.py`, `hooks.py`, `worker_pool/config.py`, `llm_client.py`, `__init__.py`

### Files Modified

**New files:**
- `src/tdd_orchestrator/decomposition/spec_validator.py` (200 lines)
- `tests/unit/test_task_loader.py` (3 tests)
- `tests/unit/decomposition/test_prompts.py` (10 tests)
- `tests/unit/decomposition/test_spec_validator.py` (13 tests)
- `tests/unit/decomposition/test_decomposer_pass2.py` (3 tests)
- `docs/plans/decomposition-refinements/PLAN.md`

**Modified files:**
- `src/tdd_orchestrator/decomposition/decomposer.py` (841 -> 795 lines)
- `src/tdd_orchestrator/decomposition/prompts.py` (547 -> 596 lines)
- `src/tdd_orchestrator/decompose_spec.py` (596 -> 627 lines)
- `src/tdd_orchestrator/task_loader.py` (363 -> 401 lines)
- `src/tdd_orchestrator/mcp_tools.py` (removed 6 unused type: ignore)
- `src/tdd_orchestrator/hooks.py` (removed 2 unused type: ignore)
- `src/tdd_orchestrator/worker_pool/config.py` (removed 1 unused type: ignore)
- `src/tdd_orchestrator/decomposition/llm_client.py` (fixed aclose type + removed unused ignore)
- `src/tdd_orchestrator/__init__.py` (added 5 type: ignore[assignment])

### Git State

- **Branch**: main
- **Recent commits**:
  - `2b80734` Merge pull request #1 from Ravenight13/fix/decomposition-refinements-and-mypy
  - `573f775` chore: update tdd-progress.md timestamps
  - `0646549` fix(types): resolve all 16 mypy strict errors across 5 files
  - `f1584ca` fix(decomposition): fix 5 root causes producing inaccurate task decompositions
- **Uncommitted changes**: None

---

## Known Issues

- `test_decomposer.py` is at 1042 lines (over 800-line limit) -- split deferred to follow-up
- RC-6 (cycle-level deps) and RC-7 (NFR/AC coverage) deferred as low-value/high-complexity

---

## Next Priorities

1. **Re-decompose the API spec** to validate fixes: `.venv/bin/python -m tdd_orchestrator.decompose_spec --spec docs/specs/api_layer_spec.txt --prefix API --clear --scaffolding-ref -v`
2. **Verify results**: Check that `impl_file` paths no longer contain `src/htmx/`, `depends_on` is populated for phase > 1, and no `src/integration/` impl paths exist
3. **Split `test_decomposer.py`** (1042 lines) into domain-specific test files

---

*Session logged: 2026-02-07 21:42:38 CST*
