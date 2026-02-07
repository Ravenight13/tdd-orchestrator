---
description: Run quick sanity checks on TDD Orchestrator project health - tests, linting, types, and database
allowed-tools:
  - Bash(cd * && python* *)
  - Bash(python* -m pytest *)
  - Bash(python* -m mypy *)
  - Bash(python* -m ruff *)
  - Bash(python* -c *)
  - Bash(git *)
  - Bash(ls *)
  - Bash(pip *)
  - Read
  - Glob
---

<objective>
Quick project health validation for TDD Orchestrator.
Run all checks in parallel where possible and report a consolidated status table.
</objective>

<checks>

## 1. Python Environment

```bash
python --version
pip show tdd-orchestrator 2>/dev/null | grep -E "^(Name|Version|Location)" || echo "WARN: Package not installed (run: pip install -e '.[dev,sdk]')"
```

## 2. Linting (ruff)

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m ruff check src/ 2>&1 | tail -5
echo "EXIT: $?"
```

## 3. Type Checking (mypy)

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m mypy src/ --strict 2>&1 | tail -5
echo "EXIT: $?"
```

## 4. Unit Tests

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m pytest tests/unit/ --tb=short -q 2>&1 | tail -10
```

## 5. Integration Tests

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m pytest tests/integration/ --tb=short -q 2>&1 | tail -10
```

## 6. Import Check

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -c "from tdd_orchestrator import OrchestratorDB, WorkerPool; print('OK: Core imports work')" 2>&1
python -c "from tdd_orchestrator.circuit_breaker import StageCircuitBreaker, WorkerCircuitBreaker, SystemCircuitBreaker; print('OK: Circuit breaker imports work')" 2>&1
python -c "from tdd_orchestrator.decomposition import decompose_spec; print('OK: Decomposition imports work')" 2>&1
```

## 7. Schema Validation

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -c "
import sqlite3, sys
conn = sqlite3.connect(':memory:')
with open('schema/schema.sql') as f:
    conn.executescript(f.read())
tables = conn.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]
views = conn.execute(\"SELECT count(*) FROM sqlite_master WHERE type='view'\").fetchone()[0]
print(f'OK: Schema valid - {tables} tables, {views} views')
conn.close()
" 2>&1
```

## 8. Git State

```bash
cd /Users/cliffclarke/Projects/tdd_orchestrator
echo "Branch: $(git branch --show-current)"
echo "Status:"
git status --short | head -10
echo "Recent commits:"
git log --oneline -5
```

</checks>

<output>
### TDD Orchestrator - Quick Health Check

| Component | Status | Details |
|-----------|--------|---------|
| Python | [version] | [OK/issue] |
| Package | [installed/missing] | [version] |
| Ruff | PASS/FAIL | [error count or clean] |
| Mypy | PASS/FAIL | [error count or clean] |
| Unit Tests | PASS/FAIL | [pass/fail counts] |
| Integration Tests | PASS/FAIL | [pass/fail counts] |
| Imports | PASS/FAIL | [which failed] |
| Schema | PASS/FAIL | [table/view counts] |
| Git | [clean/dirty] | [branch, changes] |

### Ready to Work

- **YES**: All checks pass
- **NO**: List blockers

### Recommended Actions

[List any setup steps needed]
</output>
