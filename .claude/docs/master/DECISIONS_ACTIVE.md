# Active Decisions

Current governing decisions for TDD Orchestrator. Single source of truth — if a decision here conflicts with other docs, this file wins.

---

### [2026-01-15] Path C: Federated Agents + Central Dashboard
**Confidence:** HIGH
**Decision:** Each project runs its own orchestrator instance with its own SQLite DB. A central dashboard aggregates status from all agents.
**Rationale:** Natural project isolation, no single point of failure, SQLite per-project avoids shared-write contention. Horizontal scaling without architectural changes.
**Would Revisit If:** Multi-tenant SaaS requirements emerge, or cross-project task dependencies become necessary.

### [2026-01-15] SQLite + aiosqlite for Persistence
**Confidence:** HIGH
**Decision:** Use SQLite with WAL mode via aiosqlite for all persistence. No Postgres, no external database.
**Rationale:** Per-project isolation makes SQLite a feature. Zero-config deployment. WAL mode handles 2-3 concurrent workers. Pip-installable without database setup.
**Would Revisit If:** Worker concurrency regularly exceeds 5, or multi-machine deployment becomes a requirement.

### [2026-01-15] Optional SDK Pattern (Graceful Degradation)
**Confidence:** HIGH
**Decision:** Claude Agent SDK is an optional dependency. All SDK imports guarded with try/except ImportError. Core functionality works without it.
**Rationale:** Keeps the library pip-installable without heavy dependencies. Users who don't need SDK workers shouldn't pay the cost.
**Would Revisit If:** SDK becomes a hard requirement for core functionality, or Anthropic provides a lightweight alternative.

### [2026-01-15] 800-Line File Limit, Split by Responsibility
**Confidence:** HIGH
**Decision:** 200-400 lines typical, 800 absolute maximum per file. Split proactively at 400 lines.
**Rationale:** Many small files over few large files. High cohesion, low coupling. Each module owns one responsibility. Prevents code sprawl and makes navigation easier.
**Would Revisit If:** Never — this is a non-negotiable project rule.

### [2026-01-15] src-Layout with Hatchling Build
**Confidence:** HIGH
**Decision:** Source code lives in `src/tdd_orchestrator/`. Build system is hatchling. Never create `src/__init__.py`.
**Rationale:** Standard Python packaging layout. Prevents accidental imports from the wrong path. Hatchling is simple and modern.
**Would Revisit If:** Build system requirements change (e.g., need for C extensions or complex build steps).

### [2026-01-20] Single-Branch Mode Default for Worker Pool
**Confidence:** MEDIUM
**Decision:** Workers default to single-branch mode (all workers commit to the same branch). Multi-branch mode available as opt-in.
**Rationale:** Simpler git workflow, fewer merge conflicts for typical use cases. Multi-branch adds complexity most users don't need.
**Would Revisit If:** User feedback strongly favors multi-branch, or merge conflicts in single-branch become a frequent pain point.

### [2026-01-20] `gh` CLI for PR Creation
**Confidence:** MEDIUM
**Decision:** Use `gh` CLI tool for GitHub operations (PR creation, issue management) rather than direct GitHub API calls.
**Rationale:** Simpler implementation, leverages user's existing auth. No need to manage GitHub tokens in the application.
**Would Revisit If:** Need to support non-GitHub platforms (GitLab, Bitbucket), or `gh` CLI proves unreliable in CI environments.

### [2026-01-25] 4-Pass LLM Decomposition Pipeline
**Confidence:** HIGH
**Decision:** PRDs decompose through 4 passes: extract cycles, atomize, acceptance criteria, implementation hints. Each pass is a separate LLM call.
**Rationale:** Breaking decomposition into passes allows validation between steps, better error recovery, and clearer debugging. Single-pass decomposition was too brittle for complex PRDs.
**Would Revisit If:** LLM context windows grow large enough that single-pass is reliable, or if 4-pass latency becomes unacceptable.

### [2026-01-15] Conventional Commits Format
**Confidence:** HIGH
**Decision:** All commits use `<type>(<scope>): <description>` format. Types: feat, fix, docs, style, refactor, perf, test, chore.
**Rationale:** Standardized commit history. Enables automated changelog generation. Clear intent in commit messages.
**Would Revisit If:** Never — this is a project convention.

### [2026-02-07] FastAPI for API Layer
**Confidence:** HIGH
**Decision:** Use FastAPI (not Litestar) as the ASGI framework for the REST API layer.
**Rationale:** Larger ecosystem, better documentation, more community support. Litestar is more modern but FastAPI's maturity won out.
**Would Revisit If:** FastAPI development stalls, or Litestar ecosystem catches up significantly.

### [2026-01-20] Model Selection Strategy
**Confidence:** HIGH
**Decision:** RED/decomposition always use Opus. Complexity-based selection: Low=Haiku, Medium=Sonnet, High=Opus. GREEN retries escalate through model tiers.
**Rationale:** Critical phases (RED, decomposition) need highest capability. Cost optimization for simpler tasks. Escalation pattern for retries maximizes success rate.
**Would Revisit If:** Model pricing changes significantly, or new model tiers are released.

### [2026-01-15] mypy Strict + ruff for Quality Gates
**Confidence:** HIGH
**Decision:** mypy with `strict = true` and ruff for linting. Both must pass before commits.
**Rationale:** Strict typing catches bugs early. Ruff is fast and comprehensive. Together they enforce code quality without manual review overhead.
**Would Revisit If:** Never — these are non-negotiable quality gates.
