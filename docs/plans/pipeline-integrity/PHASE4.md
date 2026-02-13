# Phase 4: Quality Detectors

## Overview

| Attribute | Value |
|-----------|-------|
| **Goal** | Detect placeholder code and mock-only tests that pass VERIFY but prove nothing |
| **Gaps addressed** | G9 (no placeholder/stub detection), G10 (no mock-only test detection) |
| **Dependencies** | None -- fully independent |
| **Estimated sessions** | 3 |
| **Risk level** | LOW -- AST analysis only, pluggable into existing framework |
| **Produces for downstream** | Phase 3A gates are enhanced when detectors are available; stub_detector findings feed into phase gate reports |

## Pre-existing State

- `ast_checker/checker.py` (209 lines) dispatches to detector classes via an established pattern
- `ast_checker/models.py` (108 lines) contains `ASTCheckConfig` dataclass
- Existing detectors: `quality_detectors.py`, `test_detectors.py` (follow the `ast.NodeVisitor` subclass + `violations` list pattern)
- `static_review_metrics` table already exists in schema (for shadow mode data collection)

## Task 4A: Placeholder/Stub Detection

### Problem

A GREEN stage could produce `def process(): pass` or `raise NotImplementedError()`. VERIFY passes if tests don't call that function. Task is marked complete with stub code.

### Solution

New AST detector that identifies non-functional code bodies:
- `pass` as sole function body
- `raise NotImplementedError()` / `raise NotImplementedError`
- `...` (Ellipsis) as sole function body
- Functions with only a docstring and no implementation
- Return of hardcoded sentinel values (`return None`, `return {}`, `return []`) as sole body

### Design Decisions

- **Blocking**: `severity="error"` -- stubs in "complete" tasks are real failures that should prevent task completion
- **Plugs into existing framework**: `checker.py` dispatches to detector classes. New detector follows the `ast.NodeVisitor` subclass pattern with a `violations` list.
- **Runs during VERIFY**: Automatically via AST check pipeline in `CodeVerifier.verify_all()` -> `ASTQualityChecker.check_file()`
- **Configuration**: New `check_stubs: bool = True` in `ASTCheckConfig`
- **Exclusions** (important to avoid false positives):
  - Protocol methods (`class Foo(Protocol):`)
  - Abstract methods (decorated with `@abstractmethod`)
  - `__init__` with no logic needed (only `self` param, super().__init__() call)
  - `.pyi` type stub files
  - Test fixtures and conftest functions (common to have simple pass/return)

### Implementation Details

**File: `src/tdd_orchestrator/ast_checker/stub_detector.py`** (new, ~160 lines)

```python
"""AST detector for placeholder/stub function bodies."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StubViolation:
    """A detected stub/placeholder in source code."""
    file: str
    line: int
    function_name: str
    stub_type: str  # "pass", "not_implemented", "ellipsis", "docstring_only", "sentinel_return"
    message: str


class StubDetector(ast.NodeVisitor):
    """Detect placeholder/stub function bodies.

    Identifies functions that have no real implementation:
    - pass-only bodies
    - raise NotImplementedError()
    - Ellipsis-only bodies
    - docstring-only bodies
    - hardcoded sentinel returns (None, {}, [])
    """

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self.violations: list[StubViolation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._is_excluded(node):
            self.generic_visit(node)
            return

        body = self._get_effective_body(node)
        if not body:
            self.generic_visit(node)
            return

        if self._is_pass_only(body):
            self._add_violation(node, "pass", "Function body is only 'pass'")
        elif self._is_not_implemented(body):
            self._add_violation(node, "not_implemented", "Function raises NotImplementedError")
        elif self._is_ellipsis_only(body):
            self._add_violation(node, "ellipsis", "Function body is only '...'")
        elif self._is_docstring_only(node):
            self._add_violation(node, "docstring_only", "Function has docstring but no implementation")
        elif self._is_sentinel_return(body):
            self._add_violation(node, "sentinel_return", "Function returns hardcoded sentinel value")

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # Handle async functions identically

    def _is_excluded(self, node: ast.FunctionDef) -> bool:
        """Check if function should be excluded from detection."""
        # Check for @abstractmethod decorator
        # Check if parent class inherits from Protocol
        # Check if file is .pyi
        # Check for __init__ with only super().__init__()
        ...

    def _get_effective_body(self, node: ast.FunctionDef) -> list[ast.stmt]:
        """Get function body, stripping leading docstring."""
        ...

    # ... _is_pass_only, _is_not_implemented, etc. ...


def detect_stubs(source: str, file_path: str) -> list[StubViolation]:
    """Convenience function: parse source and detect stubs."""
    tree = ast.parse(source)
    detector = StubDetector(file_path)
    detector.visit(tree)
    return detector.violations
```

**File: `src/tdd_orchestrator/ast_checker/models.py`** (108 -> ~110 lines)

```python
@dataclass
class ASTCheckConfig:
    # ... existing fields ...
    check_stubs: bool = True  # NEW: Enable stub/placeholder detection
```

**File: `src/tdd_orchestrator/ast_checker/checker.py`** (209 -> ~224 lines)

Register the new detector in the check dispatch:

```python
# In check_file() or equivalent dispatch method:
if config.check_stubs:
    from tdd_orchestrator.ast_checker.stub_detector import detect_stubs
    stub_violations = detect_stubs(source, file_path)
    for v in stub_violations:
        violations.append(ASTViolation(
            file=v.file,
            line=v.line,
            message=v.message,
            severity="error",
            rule="stub-detected",
        ))
```

### Test Cases

**File: `tests/unit/ast_checks/test_stub_detector.py`** (new, ~120 lines)

```python
# Detection tests:
# Test: "def foo(): pass" -> violation (pass)
# Test: "async def foo(): pass" -> violation (pass)
# Test: "def foo(): raise NotImplementedError()" -> violation (not_implemented)
# Test: "def foo(): raise NotImplementedError" -> violation (no parens)
# Test: "def foo(): ..." -> violation (ellipsis)
# Test: 'def foo(): "docstring"' (no impl after docstring) -> violation
# Test: "def foo(): return None" -> violation (sentinel)
# Test: "def foo(): return {}" -> violation (sentinel)
# Test: "def foo(): return []" -> violation (sentinel)

# Non-violation tests (exclusions):
# Test: "def foo(): return compute()" -> no violation
# Test: "def foo(): pass" with @abstractmethod -> no violation
# Test: Protocol class method with ... -> no violation
# Test: __init__ with super().__init__() -> no violation
# Test: .pyi file -> no violations
# Test: "def foo(): x = 1; return x" -> no violation
# Test: "def foo(): 'docstring'; return 42" -> no violation (has impl after docstring)

# Edge cases:
# Test: nested function with stub -> violation on inner function
# Test: class method (not just functions) -> detected
# Test: property with only pass -> detected
# Test: check_stubs=False -> no violations reported
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `ast_checker/stub_detector.py` | 0 | ~160 | ~160 |
| `ast_checker/models.py` | 108 | +2 | ~110 |
| `ast_checker/checker.py` | 209 | +15 | ~224 |
| NEW: `tests/unit/ast_checks/test_stub_detector.py` | 0 | ~120 | ~120 |

---

## Task 4B: Mock-Only Test Detection

### Problem

A test that only asserts against mocks (`mock.assert_called_with(...)`) proves nothing about real behavior. It passes VERIFY but doesn't test actual code. This is especially problematic for integration-boundary tasks that should test real database/API interactions.

### Solution

AST analysis of test functions. Flag functions where ALL assertions check mock behavior with zero assertions on real function returns.

### Design Decisions

- **Warning initially (shadow mode)**: `severity="warning"`. Collect data via `static_review_metrics` table before promoting to error. This avoids blocking on false positives during initial rollout.
- **Heuristic**: Will have false positives for legitimate mock-heavy unit tests. Acceptable -- the goal is catching integration-boundary tasks that should test real behavior.
- **Scope**: Only flags test functions where 100% of assertions are mock-only. A test with even one real assertion passes.
- **Test file only**: Only runs on files matching `test_*.py` or `*_test.py` pattern.
- **Mock assertion patterns detected**:
  - `mock.assert_called_with(...)`
  - `mock.assert_called_once_with(...)`
  - `mock.assert_called_once()`
  - `mock.assert_called()`
  - `mock.assert_not_called()`
  - `assert mock.call_count == N`
  - `assert mock.called`
  - `mock.assert_has_calls(...)`
  - `mock.assert_any_call(...)`

### Implementation Details

**File: `src/tdd_orchestrator/ast_checker/mock_only_detector.py`** (new, ~180 lines)

```python
"""AST detector for test functions that only assert against mocks."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


# Mock assertion method names
MOCK_ASSERT_METHODS: frozenset[str] = frozenset({
    "assert_called_with",
    "assert_called_once_with",
    "assert_called_once",
    "assert_called",
    "assert_not_called",
    "assert_has_calls",
    "assert_any_call",
})

# Attributes that indicate mock assertion context
MOCK_ASSERT_ATTRS: frozenset[str] = frozenset({
    "call_count",
    "called",
    "call_args",
    "call_args_list",
})


@dataclass
class MockOnlyViolation:
    """A detected mock-only test function."""
    file: str
    line: int
    function_name: str
    assertion_count: int
    mock_assertion_count: int
    message: str


class MockOnlyDetector(ast.NodeVisitor):
    """Detect test functions where all assertions only check mock behavior."""

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self.violations: list[MockOnlyViolation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        assertions = self._collect_assertions(node)
        if not assertions:
            self.generic_visit(node)
            return  # No assertions = not our problem

        mock_assertions = [a for a in assertions if self._is_mock_assertion(a)]
        if len(mock_assertions) == len(assertions):
            self.violations.append(MockOnlyViolation(
                file=self._file_path,
                line=node.lineno,
                function_name=node.name,
                assertion_count=len(assertions),
                mock_assertion_count=len(mock_assertions),
                message=(
                    f"Test '{node.name}' has {len(assertions)} assertion(s), "
                    f"all against mocks. No real behavior is tested."
                ),
            ))

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _collect_assertions(self, node: ast.FunctionDef) -> list[ast.stmt]:
        """Collect all assertion statements from a test function."""
        # assert statements, mock.assert_* calls, pytest.raises
        ...

    def _is_mock_assertion(self, stmt: ast.stmt) -> bool:
        """Check if an assertion only tests mock behavior."""
        # Check for mock.assert_called_with, assert mock.called, etc.
        ...


def detect_mock_only_tests(source: str, file_path: str) -> list[MockOnlyViolation]:
    """Convenience function: parse source and detect mock-only tests."""
    tree = ast.parse(source)
    detector = MockOnlyDetector(file_path)
    detector.visit(tree)
    return detector.violations
```

**File: `src/tdd_orchestrator/ast_checker/models.py`** (~110 -> ~112 lines)

```python
@dataclass
class ASTCheckConfig:
    # ... existing fields ...
    check_stubs: bool = True
    check_mock_only_tests: bool = True  # NEW: Enable mock-only test detection
```

**File: `src/tdd_orchestrator/ast_checker/checker.py`** (~224 -> ~239 lines)

Register the new detector:

```python
# In check_file() or equivalent dispatch method:
if config.check_mock_only_tests and is_test_file(file_path):
    from tdd_orchestrator.ast_checker.mock_only_detector import detect_mock_only_tests
    mock_violations = detect_mock_only_tests(source, file_path)
    for v in mock_violations:
        violations.append(ASTViolation(
            file=v.file,
            line=v.line,
            message=v.message,
            severity="warning",  # Shadow mode initially
            rule="mock-only-test",
        ))
        # Record in static_review_metrics for shadow mode analysis
        await _record_shadow_metric("mock-only-test", v.file, v.function_name)
```

### Test Cases

**File: `tests/unit/ast_checks/test_mock_only_detector.py`** (new, ~120 lines)

```python
# Detection tests (violations):
# Test: test with only mock.assert_called_with -> violation
# Test: test with only mock.assert_called_once_with -> violation
# Test: test with only "assert mock.called" -> violation
# Test: test with only "assert mock.call_count == 1" -> violation
# Test: test with multiple mock assertions, zero real -> violation

# Non-violation tests:
# Test: test with real assertion + mock assertion -> no violation
# Test: test with only assert result == expected -> no violation
# Test: test with pytest.raises -> no violation (real behavior test)
# Test: test with no assertions -> no violation (not our problem)
# Test: non-test function (no test_ prefix) -> no violation
# Test: non-test file -> no violations

# Edge cases:
# Test: test using patch decorator with real assertion -> no violation
# Test: async test function -> detected correctly
# Test: check_mock_only_tests=False -> no violations reported
# Test: nested mock assertion in helper -> correctly attributed
```

### Files Changed

| File | Current | Delta | Projected |
|------|---------|-------|-----------|
| NEW: `ast_checker/mock_only_detector.py` | 0 | ~180 | ~180 |
| `ast_checker/models.py` | ~110 | +2 | ~112 |
| `ast_checker/checker.py` | ~224 | +15 | ~239 |
| NEW: `tests/unit/ast_checks/test_mock_only_detector.py` | 0 | ~120 | ~120 |

---

## Session Breakdown

### Session 1: Stub Detector (4A)

**Steps**:
1. Read `ast_checker/checker.py` and existing detectors to understand the pattern
2. Read `ast_checker/models.py` for `ASTCheckConfig` structure
3. Create `stub_detector.py` with `StubDetector` class
4. Add `check_stubs` config field to `models.py`
5. Register detector in `checker.py`
6. Write comprehensive tests covering all stub types and exclusions
7. Verify: pytest + mypy + ruff

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/ast_checks/test_stub_detector.py -v
.venv/bin/mypy src/tdd_orchestrator/ast_checker/ --strict
.venv/bin/ruff check src/tdd_orchestrator/ast_checker/
```

### Session 2: Mock-Only Detector (4B)

**Steps**:
1. Review mock assertion patterns in existing test files for real-world examples
2. Create `mock_only_detector.py` with `MockOnlyDetector` class
3. Add `check_mock_only_tests` config field to `models.py`
4. Register detector in `checker.py` with `severity="warning"`
5. Wire shadow mode metrics recording
6. Write comprehensive tests
7. Verify: pytest + mypy + ruff

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/ast_checks/test_mock_only_detector.py -v
.venv/bin/mypy src/tdd_orchestrator/ast_checker/ --strict
.venv/bin/ruff check src/tdd_orchestrator/ast_checker/
```

### Session 3: Integration Testing

**Steps**:
1. Test both detectors run as part of the full AST check pipeline
2. Test that stub detector blocks task completion (error severity)
3. Test that mock-only detector logs warnings but doesn't block (shadow mode)
4. Verify both detectors play nicely with existing detectors
5. Run full test suite regression
6. Verify checker.py stays under 300 lines

**Session boundary check**:
```bash
.venv/bin/pytest tests/unit/ast_checks/ -v
.venv/bin/pytest tests/ -v  # full regression
.venv/bin/mypy src/tdd_orchestrator/ast_checker/ --strict
.venv/bin/ruff check src/tdd_orchestrator/ast_checker/
```

---

## Verification Commands

```bash
# Unit tests for AST detectors
.venv/bin/pytest tests/unit/ast_checks/ -v

# Type checking
.venv/bin/mypy src/tdd_orchestrator/ast_checker/ --strict

# Linting
.venv/bin/ruff check src/tdd_orchestrator/ast_checker/

# Full regression
.venv/bin/pytest tests/ -v
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stub detector false positives (legitimate simple functions) | Tasks incorrectly blocked | Comprehensive exclusion list (Protocol, abstractmethod, __init__, .pyi). `check_stubs` config flag to disable. |
| Mock-only detector false positives (legitimate mock-heavy unit tests) | Unnecessary warnings | Warning-only (shadow mode). Only flags 100% mock-assertion tests. Data collection before promoting to error. |
| AST parsing breaks on unusual syntax | Detector crashes | Try/except around parse, skip file with warning on parse error. |
| Performance impact of additional AST traversal | Slower VERIFY stage | Detectors are AST visitors (fast, O(n) in AST nodes). Negligible vs. subprocess calls for pytest/mypy. |

---

## Integration Checklist (Post-Phase 4)

- [ ] `stub_detector.py` detects all five stub types (pass, NotImplementedError, ellipsis, docstring-only, sentinel)
- [ ] Exclusions work correctly (Protocol, abstractmethod, __init__, .pyi)
- [ ] Stub detector has `severity="error"` (blocking)
- [ ] `mock_only_detector.py` detects all mock assertion patterns
- [ ] Mock-only detector has `severity="warning"` (shadow mode)
- [ ] Shadow mode metrics recorded in `static_review_metrics`
- [ ] Both detectors registered in `checker.py`
- [ ] Both detectors configurable via `ASTCheckConfig`
- [ ] Both detectors integrate with existing AST check pipeline
- [ ] checker.py stays under 300 lines
- [ ] models.py stays under 150 lines
- [ ] mypy strict passes on all ast_checker files
- [ ] ruff check passes

---

## Dependency Tracking

### What Phase 4 Produces

| Output | Consumer |
|--------|----------|
| Stub detector findings | Phase 3A phase gates (if both phases implemented, gate checks for stubs across phase) |
| Mock-only test warnings | Phase 3A gates (logged in gate report, non-blocking) |
| Shadow mode data in `static_review_metrics` | Future decision: promote mock-only detection to error severity |

### What Phase 4 Consumes

Nothing -- Phase 4 is fully independent and can start immediately.

### Phase 3 Integration Note

When Phase 4 detectors exist alongside Phase 3A phase gates, the gate automatically benefits:
- Phase gate calls `CodeVerifier.verify_all()` which runs AST checks including the new detectors
- Stub violations (errors) in any phase's impl files will cause the phase gate to fail
- Mock-only violations (warnings) will be logged in the gate report but won't block

No explicit wiring is needed -- the existing AST check pipeline handles the integration.
