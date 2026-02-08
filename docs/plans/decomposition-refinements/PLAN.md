# Decomposition Pipeline Refinements

**Status:** Implemented
**Date:** 2026-02-07
**Goal:** Fix 5 root causes producing inaccurate task decompositions

## Implementation Summary

All 5 root causes fixed across 2 phases:

| RC | Fix | Status |
|----|-----|--------|
| RC-3 | Persist `depends_on` to DB after calculation | Done |
| RC-1 | Remove hardcoded `src/htmx/` path prefixes | Done |
| RC-2 | Pass `module_api` + `module_structure` to Pass 2 | Done |
| RC-4 | Validate decomposed paths against spec | Done |
| RC-5 | Fix integration test `impl_file` handling | Done |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `decomposition/decomposer.py` | Modified | 795 (was 841) |
| `decomposition/prompts.py` | Modified | 596 (was 547) |
| `decomposition/spec_validator.py` | Created | 200 |
| `decompose_spec.py` | Modified | 627 (was 596) |
| `task_loader.py` | Modified | 401 (was 363) |

## New Test Files

| File | Tests |
|------|-------|
| `tests/unit/test_task_loader.py` | 3 |
| `tests/unit/decomposition/test_prompts.py` | 10 |
| `tests/unit/decomposition/test_spec_validator.py` | 13 |
| `tests/unit/decomposition/test_decomposer_pass2.py` | 3 |

**Total: 29 new tests (525 -> 554), all passing**

## Verification

- All 554 tests pass
- mypy strict: clean (no new errors)
- ruff: clean
- All files under 800-line limit
