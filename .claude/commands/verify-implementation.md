---
description: Verify implementation completeness for TDD Orchestrator modules and features
argument-hint: "[module name or feature, or leave blank for full verification]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(cd * && python* *)
  - Bash(python* -m pytest *)
  - Bash(python* -m mypy *)
  - Bash(python* -m ruff *)
  - Bash(git *)
---

<objective>
Verify implementation completeness for $ARGUMENTS (or the full project if blank) against TDD Orchestrator quality standards.

This command checks that code, tests, types, and documentation are complete and consistent.
</objective>

<module_mapping>
Map $ARGUMENTS to module paths:
- circuit/breaker → `src/tdd_orchestrator/circuit_breaker.py`, `src/tdd_orchestrator/circuit_breaker_config.py`
- worker/pool → `src/tdd_orchestrator/worker_pool.py`
- database/db → `src/tdd_orchestrator/database.py`
- decomposition/decompose → `src/tdd_orchestrator/decomposition/`
- ast/checker → `src/tdd_orchestrator/ast_checker.py`
- cli → `src/tdd_orchestrator/cli.py`
- prompt → `src/tdd_orchestrator/prompt_builder.py`
- git → `src/tdd_orchestrator/git_coordinator.py`, `src/tdd_orchestrator/git_stash_guard.py`, `src/tdd_orchestrator/merge_coordinator.py`
- (blank) → Check all modules
</module_mapping>

<checks>

## 1. Test Coverage

For each target module, verify corresponding tests exist:

```
src/tdd_orchestrator/{module}.py → tests/unit/test_{module}.py
src/tdd_orchestrator/{module}.py → tests/integration/test_{module}*.py (if applicable)
```

Check test files contain:
- [ ] At least one test per public function/method
- [ ] Async tests use `async def test_*` (pytest-asyncio auto mode)
- [ ] Error/edge case tests exist
- [ ] No skipped tests without explanation

## 2. Type Checking

Run mypy on target modules:
```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m mypy src/tdd_orchestrator/{module}.py --strict 2>&1
```

Verify:
- [ ] No mypy errors
- [ ] All public functions have type annotations
- [ ] Return types specified
- [ ] No `# type: ignore` without explanation

## 3. Linting

Run ruff on target modules:
```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m ruff check src/tdd_orchestrator/{module}.py 2>&1
```

Verify:
- [ ] No ruff errors
- [ ] Line length <= 100
- [ ] Import ordering correct

## 4. Module Consistency

Check module follows project patterns:
- [ ] Async functions use `async def` with proper `await`
- [ ] Database operations use parameterized queries (? placeholders)
- [ ] Error handling follows project patterns
- [ ] Logging uses standard library logging module
- [ ] Public API exports in `__init__.py` match actual usage

## 5. Schema Alignment

If module interacts with database:
- [ ] SQL queries reference valid table/column names from `schema/schema.sql`
- [ ] New tables/columns added to schema if needed
- [ ] Views updated if query patterns changed
- [ ] Indexes exist for frequently queried columns

## 6. Documentation

Check documentation exists and is current:
- [ ] Module docstring present
- [ ] Public functions have docstrings
- [ ] `docs/ARCHITECTURE.md` reflects current architecture
- [ ] `README.md` updated if CLI commands changed
- [ ] CLAUDE.md updated if major structural changes

## 7. Integration Points

Verify module integrates correctly:
- [ ] Circuit breaker modules: state machine transitions tested
- [ ] Worker pool: claim/release cycle complete
- [ ] Database: optimistic locking preserved
- [ ] CLI: help text accurate, options validated
- [ ] SDK: optional import with graceful degradation

## 8. Cross-References

Verify internal consistency:
- [ ] Imports resolve correctly
- [ ] No circular dependencies
- [ ] Model classes match database schema
- [ ] CLI options match underlying function parameters

</checks>

<output>
### Implementation Verification: {Module/Feature Name}

| Check | Status | Issues |
|-------|--------|--------|
| Test Coverage | PASS/FAIL | [missing tests] |
| Type Checking | PASS/FAIL | [mypy errors] |
| Linting | PASS/FAIL | [ruff errors] |
| Module Consistency | PASS/FAIL | [pattern violations] |
| Schema Alignment | PASS/FAIL/N/A | [mismatches] |
| Documentation | PASS/FAIL | [gaps] |
| Integration Points | PASS/FAIL | [broken integrations] |
| Cross-References | PASS/FAIL | [broken refs] |

### Issues Found

- `{file}:{line}` - {description of issue}

### Quality Gaps

| Gap | Priority | Suggested Action |
|-----|----------|------------------|
| {gap} | High/Medium/Low | {action} |

### Verification Result

- **COMPLETE**: All checks pass, module ready
- **NEEDS WORK**: Gaps identified, address before merge
- **BLOCKED**: Critical issues prevent progress

### Recommended Next Steps

1. [Specific actionable step]
2. [Specific actionable step]
</output>
