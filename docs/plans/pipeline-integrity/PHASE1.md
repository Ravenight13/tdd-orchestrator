# Phase 1: Decomposition Hardening

## Overview

| Attribute | Value |
|-----------|-------|
| **Goal** | Prevent bad task graphs from reaching execution |
| **Gaps addressed** | G6 (integration boundary enforcement), G7 (circular dependency detection), G8 (task key uniqueness) |
| **Dependencies** | None -- fully independent |
| **Estimated sessions** | 2 |
| **Risk level** | LOW -- pure validation, no runtime changes |
| **Produces for downstream** | Validated task graphs consumed by Phase 2 (execution) and Phase 3 (gates) |

## Pre-existing State

- **Prompt-level enforcement for G6** is already implemented (uncommitted) in `decomposition/prompts.py`:
  - `INTEGRATION-BOUNDARY DETECTION` block added to Pass 2 prompts
  - `TEST CONTEXT RULES` block reinforces test_type vs impl_file consistency
- **Regression test** exists: `tests/unit/decomposition/test_boundary_detection.py` (52 lines) verifies the prompt strings are present
- **Phase 1A scope**: Adds _validator-level_ hard enforcement that catches violations even when the LLM ignores the prompt rules. The prompt-level work is the soft layer; Phase 1A adds the hard layer.

> **Prerequisite**: All uncommitted changes (prompts.py, test_boundary_detection.py, and unrelated API/circuit changes) should be committed before starting Phase 1. This ensures a clean baseline and avoids confusion about which changes belong to which phase.

## Task 1A: Integration Boundary Hard Validation

### Problem

Prompts now say "route handlers should be integration tests" but the LLM can ignore this. `validators.py` has no check for `test_type` vs `impl_file` consistency. A route handler task with `test_file: tests/unit/api/...` will pass all existing validators.

### Solution

Add `validate_integration_boundaries()` to `AtomicityValidator` in `validators.py`:
- If `impl_file` contains route/api/database keywords AND `test_file` starts with `tests/unit/` -> validation error
- Configurable keyword list in `DecompositionConfig`
- Escape hatch flag `enforce_integration_boundaries: bool = True` in config

### Implementation Details

**File: `src/tdd_orchestrator/decomposition/validators.py`** (378 -> ~410 lines)

Add method to `AtomicityValidator`:

```python
def validate_integration_boundaries(
    self,
    tasks: list[dict[str, Any]],
    config: DecompositionConfig,
) -> list[str]:
    """Validate that integration-boundary tasks use integration tests."""
    if not config.enforce_integration_boundaries:
        return []
    errors: list[str] = []
    for task in tasks:
        impl_file = task.get("impl_file", "")
        test_file = task.get("test_file", "")
        if any(kw in impl_file for kw in config.integration_keywords) and test_file.startswith("tests/unit/"):
            errors.append(
                f"Task {task.get('key', '?')}: impl_file '{impl_file}' contains "
                f"integration keywords but test_file '{test_file}' is in tests/unit/. "
                f"Use tests/integration/ instead."
            )
    return errors
```

**File: `src/tdd_orchestrator/decomposition/config.py`** (80 -> ~95 lines)

Add to `DecompositionConfig`:

```python
# Integration boundary enforcement
enforce_integration_boundaries: bool = True
integration_keywords: tuple[str, ...] = (
    "/api/", "/routes/", "database", "db_", "_db",
    "repository", "handler", "endpoint",
)
```

**Call site**: In `decompose_spec.py`, alongside existing spec conformance checks (near line 420-430). The validator is called after tasks are validated but before they are written to DB.

### Test Cases

**File: `tests/unit/decomposition/test_validators.py`** (extend existing)

```python
# Test: route handler in tests/unit/ -> error
# Test: route handler in tests/integration/ -> no error
# Test: non-route file in tests/unit/ -> no error
# Test: enforce_integration_boundaries=False -> no errors regardless
# Test: custom keyword list works
# Test: multiple violations reported
# Test: empty task list -> no errors
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| `decomposition/validators.py` | 378 | +32 | ~410 |
| `decomposition/config.py` | 80 | +15 | ~95 |
| `tests/unit/decomposition/test_validators.py` | TBD | +40 | TBD |

---

## Task 1B: Circular Dependency Detection

### Problem

`generator.py:_calculate_dependencies()` (line 220) calculates `depends_on` based on phase ordering but never validates the resulting graph for cycles. The current rule (Phase N depends on ALL Phase N-1 tasks) cannot produce cycles by construction, but:
- Manually edited tasks could introduce cycles
- Recursive validation splits could create unexpected dependencies
- Future dependency rules (e.g., cross-phase dependencies) could introduce them

This is defensive hardening -- prevent the class of bug before it occurs.

### Solution

New module `decomposition/dependency_validator.py` with Kahn's algorithm (topological sort). If nodes with non-zero in-degree remain after the sort completes, cycles exist. Report the cycle members in the error.

### Implementation Details

**File: `src/tdd_orchestrator/decomposition/dependency_validator.py`** (new, ~80 lines)

```python
"""Validate task dependency graphs for cycles using Kahn's algorithm."""
from __future__ import annotations
from collections import deque


def validate_no_cycles(tasks: list[dict[str, object]]) -> list[str]:
    """Check that task dependency graph is acyclic.

    Uses Kahn's algorithm (topological sort). If any nodes remain
    with non-zero in-degree after processing, cycles exist.

    Args:
        tasks: List of task dicts, each with 'key' and 'depends_on' fields.

    Returns:
        List of error strings. Empty if no cycles found.
    """
    # Build adjacency and in-degree maps
    # ... implementation ...


def _find_cycle_members(
    adj: dict[str, list[str]],
    remaining: set[str],
) -> list[str]:
    """Given remaining nodes after Kahn's, find one cycle for error reporting."""
    # ... DFS to find and report one cycle ...
```

**Call site: `src/tdd_orchestrator/decompose_spec.py`** (line ~418, after `generator._calculate_dependencies(validated_tasks)`)

```python
# After line 417: generator._calculate_dependencies(validated_tasks)
from tdd_orchestrator.decomposition.dependency_validator import validate_no_cycles
cycle_errors = validate_no_cycles(validated_tasks)
if cycle_errors:
    raise DecompositionError(f"Circular dependencies detected: {'; '.join(cycle_errors)}")
```

### Test Cases

**File: `tests/unit/decomposition/test_dependency_validator.py`** (new, ~100 lines)

```python
# Test: linear chain (A->B->C) -> no cycles
# Test: self-referencing task (A->A) -> cycle detected
# Test: simple cycle (A->B->A) -> cycle detected
# Test: diamond (A->B, A->C, B->D, C->D) -> no cycles
# Test: cycle in subgraph (A->B, C->D->C) -> reports C,D cycle
# Test: no dependencies at all -> no cycles
# Test: single task with no deps -> no cycles
# Test: missing dependency target (A depends on Z, Z not in tasks) -> handled gracefully
# Test: large graph (50+ tasks) -> performance acceptable
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `decomposition/dependency_validator.py` | 0 | ~80 | ~80 |
| `decompose_spec.py` | 635 | +15 | ~650 |
| NEW: `tests/unit/decomposition/test_dependency_validator.py` | 0 | ~100 | ~100 |

---

## Task 1C: Task Key Uniqueness

### Problem

`TaskGenerator` assigns keys sequentially (e.g., `TDD-001`, `TDD-002`) but never checks for duplicates. Duplicates could occur with:
- Split tasks during recursive validation
- Multiple runs with the same prefix
- Manual task editing

Additionally, duplicate `(impl_file, test_file)` pairs would cause execution collisions -- two tasks trying to write the same files.

### Solution

Add `validate_unique_task_keys()` as a standalone function in `validators.py`. Called in `decompose_spec.py` alongside spec conformance.

### Implementation Details

**File: `src/tdd_orchestrator/decomposition/validators.py`** (~410 -> ~440 lines, cumulative with 1A)

```python
def validate_unique_task_keys(tasks: list[dict[str, Any]]) -> list[str]:
    """Validate that all task keys are unique and no file pairs collide."""
    errors: list[str] = []
    seen_keys: dict[str, int] = {}
    seen_file_pairs: dict[tuple[str, str], str] = {}

    for i, task in enumerate(tasks):
        key = task.get("key", "")
        # Check key uniqueness
        if key in seen_keys:
            errors.append(f"Duplicate task key '{key}' at indices {seen_keys[key]} and {i}")
        else:
            seen_keys[key] = i

        # Check file pair uniqueness
        impl_file = task.get("impl_file", "")
        test_file = task.get("test_file", "")
        pair = (impl_file, test_file)
        if pair in seen_file_pairs and impl_file and test_file:
            errors.append(
                f"Task '{key}' has same (impl_file, test_file) pair as "
                f"task '{seen_file_pairs[pair]}': ({impl_file}, {test_file})"
            )
        elif impl_file and test_file:
            seen_file_pairs[pair] = key

    return errors
```

**Call site: `src/tdd_orchestrator/decompose_spec.py`** (near line 425, alongside spec conformance)

```python
from tdd_orchestrator.decomposition.validators import validate_unique_task_keys
key_errors = validate_unique_task_keys(validated_tasks)
if key_errors:
    raise DecompositionError(f"Task key/file violations: {'; '.join(key_errors)}")
```

### Test Cases

**Extend: `tests/unit/decomposition/test_validators.py`**

```python
# Test: all unique keys -> no errors
# Test: duplicate key -> error with both indices
# Test: duplicate (impl_file, test_file) pair -> error naming both tasks
# Test: same impl_file but different test_file -> no error
# Test: empty key -> handled (key="" is still checked)
# Test: empty task list -> no errors
# Test: tasks with missing impl_file/test_file -> handled gracefully
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| `decomposition/validators.py` | ~410 (after 1A) | +30 | ~440 |
| `decompose_spec.py` | ~650 (after 1B) | +5 | ~655 |
| `tests/unit/decomposition/test_validators.py` | TBD | +20 | TBD |

---

## Session Breakdown

### Session 1: Boundary Validation (1A) + Key Uniqueness (1C)

**Why together**: Both modify `validators.py` and both add call sites in `decompose_spec.py`. Doing them together avoids merge conflicts and lets us test the full validation pipeline.

**Steps**:
1. Read `validators.py`, `config.py`, `decompose_spec.py`
2. Add `enforce_integration_boundaries` + `integration_keywords` to `DecompositionConfig`
3. Add `validate_integration_boundaries()` to `AtomicityValidator`
4. Add `validate_unique_task_keys()` as standalone function
5. Add call sites in `decompose_spec.py`
6. Write/extend tests
7. Verify: pytest + mypy + ruff

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/decomposition/ -v
.venv/bin/mypy src/tdd_orchestrator/decomposition/ --strict
.venv/bin/ruff check src/tdd_orchestrator/decomposition/
```

### Session 2: Cycle Detection (1B) + Integration Testing

**Why separate**: New module (`dependency_validator.py`) with algorithm implementation. Benefits from focused attention and thorough edge-case testing.

**Steps**:
1. Read `generator.py:_calculate_dependencies()` to understand dependency format
2. Create `dependency_validator.py` with `validate_no_cycles()`
3. Add call site in `decompose_spec.py` after `_calculate_dependencies()`
4. Write comprehensive tests including edge cases (self-ref, diamond, large graph)
5. Integration test: run decomposition on a sample spec and verify all three validators fire
6. Verify: pytest + mypy + ruff

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/decomposition/ -v
.venv/bin/pytest tests/integration/ -v  # regression
.venv/bin/mypy src/tdd_orchestrator/decomposition/ --strict
.venv/bin/ruff check src/tdd_orchestrator/decomposition/
```

---

## Verification Commands

```bash
# Unit tests for all decomposition validators
.venv/bin/pytest tests/unit/decomposition/ -v

# Type checking (strict)
.venv/bin/mypy src/tdd_orchestrator/decomposition/ --strict

# Linting
.venv/bin/ruff check src/tdd_orchestrator/decomposition/

# Integration regression (ensure existing decomposition still works)
.venv/bin/pytest tests/integration/ -v
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Integration keywords are too broad (false positives) | Tasks incorrectly flagged | Configurable keyword list + escape hatch flag. Can disable per-run. |
| Integration keywords miss real cases (false negatives) | Route handlers still get unit tests | Prompt-level enforcement (soft layer) catches most cases. Validator is the hard backstop. |
| Kahn's algorithm implementation bug | Cycles not detected or false cycles | Comprehensive test suite including known graph patterns. Algorithm is well-studied. |
| Duplicate key check breaks existing prefixes | Decomposition errors on valid runs | Only flags actual duplicates within a single run, not across runs. |

---

## Integration Checklist (Post-Phase 1)

- [ ] `validate_integration_boundaries()` catches route handlers in `tests/unit/`
- [ ] `validate_no_cycles()` detects self-reference and multi-node cycles
- [ ] `validate_unique_task_keys()` catches duplicate keys and file pair collisions
- [ ] All three validators are called during `run_decomposition()` flow
- [ ] Existing decomposition tests still pass (no regression)
- [ ] `enforce_integration_boundaries` config flag disables boundary checks
- [ ] Error messages are actionable (include task key, file paths, cycle members)
- [ ] mypy strict passes on all modified files
- [ ] ruff check passes on all modified files

---

## Dependency Tracking

### What Phase 1 Produces

| Output | Consumer |
|--------|----------|
| Validated, cycle-free dependency graph | Phase 2 (pipeline execution relies on valid deps) |
| Guaranteed unique task keys | Phase 3 (phase gates query tasks by key) |
| Integration boundary enforcement | Phase 3A (gate checks are redundant if decomp catches violations) |

### What Phase 1 Consumes

Nothing -- Phase 1 is fully independent and can start immediately.
