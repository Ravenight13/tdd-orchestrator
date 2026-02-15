# Assumptions

Foundational beliefs the project bets on. If any of these are challenged or invalidated, flag immediately — they may require architectural changes.

---

### Claude Agent SDK Will Remain Available and Backward-Compatible
**Confidence:** MEDIUM
**Depends On:** Anthropic maintaining the SDK as a public package with stable API.
**If Wrong:** Core orchestrator still works (SDK is optional), but SDK-based workers would break. Would need to rewrite worker integration against raw API.
**Mitigation:** Optional SDK pattern already in place. All SDK imports are guarded.

### SQLite WAL Mode Sufficient for Parallel Worker Concurrency
**Confidence:** HIGH
**Depends On:** Worker count staying at 2-3 per project. WAL mode allowing concurrent reads with single writer.
**If Wrong:** Write contention would cause task claim failures and database locks. Would need to move to Postgres or implement application-level write queuing.
**Mitigation:** Optimistic locking already handles claim conflicts. Worker count is configurable and capped.

### Single-Machine Execution Is the Primary Use Case
**Confidence:** HIGH
**Depends On:** Users running the orchestrator locally against local projects. No distributed execution requirement.
**If Wrong:** SQLite doesn't work across machines. Would need network-accessible database and distributed task coordination (message queue, etc.).
**Mitigation:** Federated architecture (Path C) is designed for this — each machine runs its own instance. Dashboard aggregation could work across machines via HTTP.

### Python 3.11+ Is the Minimum Supported Version
**Confidence:** HIGH
**Depends On:** Users having Python 3.11 or newer available. Key features used: `asyncio.TaskGroup`, `tomllib`, type syntax improvements.
**If Wrong:** Would need to backport async patterns and find alternative for `tomllib`. Significant effort for minimal benefit.
**Mitigation:** 3.11 is widely available. pyproject.toml enforces `requires-python = ">=3.11"`.

### `gh` CLI Is Widely Available for GitHub Integration
**Confidence:** MEDIUM
**Depends On:** Users having GitHub CLI installed and authenticated.
**If Wrong:** PR creation and GitHub integration would fail silently or with unhelpful errors. Users on GitLab/Bitbucket have no path.
**Mitigation:** Git operations (branch, commit) work without `gh`. GitHub integration is additive, not required for core TDD execution.

### Anthropic API Pricing Remains Viable for Multi-Worker TDD
**Confidence:** MEDIUM
**Depends On:** API costs not becoming prohibitive for running 2-3 workers on decomposed tasks.
**If Wrong:** Users would avoid parallel execution, reducing the core value proposition. Would need cost estimation and budget controls.
**Mitigation:** Model selection strategy (Haiku for simple, Opus for complex) already optimizes costs. Dry-run mode allows pre-execution review.

### Click Is Sufficient for CLI Complexity
**Confidence:** HIGH
**Depends On:** CLI remaining a command-line tool without needing TUI features or complex interactive workflows.
**If Wrong:** Would need to migrate to Typer, Rich, or Textual for richer CLI experiences.
**Mitigation:** Click has good extensibility. Migration to Typer (Click-based) would be incremental.
