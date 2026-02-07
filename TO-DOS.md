# TO-DOS

## Split oversized files to comply with 800-line max - 2026-02-07 09:38

- **Split circuit_breaker.py** - Decompose into smaller modules by circuit breaker level. **Problem:** At 1866 lines, this is the most oversized file — over 2x the 800-line hard limit established in CLAUDE.md. Contains Stage, Worker, and System circuit breakers in a single file. **Files:** `src/tdd_orchestrator/circuit_breaker.py:1-1866`. **Solution:** Split into separate modules per breaker type (e.g., `circuit_breaker_stage.py`, `circuit_breaker_worker.py`, `circuit_breaker_system.py`) with shared base in `circuit_breaker_base.py`. Re-export from `circuit_breaker/__init__.py` to preserve public API.

- **Split worker_pool.py** - Break apart worker management into focused modules. **Problem:** At 1459 lines, nearly 2x the 800-line limit. Likely mixes worker lifecycle, task claiming, and execution logic. **Files:** `src/tdd_orchestrator/worker_pool.py:1-1459`. **Solution:** Identify responsibility boundaries (lifecycle management, task distribution, execution) and split accordingly.

- **Split database.py** - Separate database operations by domain. **Problem:** At 1425 lines, nearly 2x the 800-line limit. Single file handling all query domains. **Files:** `src/tdd_orchestrator/database.py:1-1425`. **Solution:** Split by domain (task queries, circuit breaker queries, metrics queries) with a shared connection/base module.

- **Split ast_checker.py** - Break apart AST analysis into focused modules. **Problem:** At 1085 lines, ~35% over the 800-line limit. **Files:** `src/tdd_orchestrator/ast_checker.py:1-1085`. **Solution:** Identify logical groupings of AST checks and split into separate modules.
