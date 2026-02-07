# TDD Orchestrator — Production Vision

**Date:** 2026-02-07
**Status:** Draft — Awaiting Review
**Author:** Cliff Clarke + Claude Opus 4.6

---

## Executive Summary

TDD Orchestrator is a parallel task execution engine for TDD workflows. Today it's a pip-installable CLI tool that runs locally against a single project. This document captures the vision, ideas, and architecture for evolving it into a production system that can:

1. **Accept PRDs/Features** and orchestrate full TDD RED-GREEN-REFACTOR cycles to produce working code
2. **Deploy into other projects** as either an installed agent or a networked service
3. **Provide a web dashboard** for monitoring tasks, worker health, and multi-project status

---

## Evaluation Summary (Mental Models Applied)

### First Principles
- The core value is the **decomposition pipeline + parallel TDD execution + circuit breaker resilience** — not the delivery mechanism
- Production adoption requires **zero-friction onboarding** — `pip install` is already strong
- Multi-project orchestration requires **project isolation** — each project needs its own DB, workers, and git context
- Monitoring != control plane — you can observe from a dashboard without routing all execution through a server
- The LLM is the bottleneck and cost center, not the orchestrator itself

### SWOT
- **Strengths:** Async-native, 3-level circuit breakers, pip-installable, 4-pass decomposition, 324 tests, mypy strict
- **Weaknesses:** SQLite single-writer, no HTTP API, no auth/multi-tenancy, no project registry, CLI-only
- **Opportunities:** AI dev tools market exploding, no good OSS TDD orchestrator, "Terraform for TDD" positioning
- **Threats:** Anthropic/OpenAI competing tools, Claude SDK lock-in, SQLite ceiling for high-concurrency

### Second-Order Effects — Architecture Paths

| Path | 1st Order | 2nd Order | 3rd Order | Verdict |
|------|-----------|-----------|-----------|---------|
| **A: Monolithic Server** | Dashboard works, PRDs via UI | Must maintain server, auth, uptime | Lose pip-install, become infra | **Avoid** |
| **B: API Layer + Dashboard** | FastAPI wraps engine, dashboard reads API | CLI and dashboard both work | Other tools integrate via API | **Good** |
| **C: Federated Agents + Central Dashboard** | Per-project orchestrator, dashboard aggregates | Natural isolation, SQLite per-project | Horizontal scaling, no SPOF | **Best** |

**Chosen Direction:** Path C — Federated agent model with central dashboard aggregator.

---

## Idea Catalog

### I. PRD Intake & TDD Execution Across Projects

| # | Idea | Description | Priority |
|---|------|-------------|----------|
| 1 | **PRD Intake Command** | `tdd-orchestrator ingest <prd-file>` — accepts PRD files (MD/YAML/JSON) and feeds into 4-pass decomposition pipeline | P0 |
| 2 | **PRD Template System** | `tdd-orchestrator init-prd` — ships opinionated templates aligned with decomposition expectations | P1 |
| 3 | **Project Bootstrap** | `tdd-orchestrator init --project /path/to/target` — creates `.tdd/` directory with config, DB, task definitions | P0 |
| 4 | **Language-Agnostic Execution** | Pluggable `TestRunner` protocol — adapters for pytest, jest, cargo test, go test, etc. | P1 |
| 5 | **Git Integration as Default** | Auto-create feature branches per PRD, per-task branches, auto-merge on GREEN | P0 |
| 6 | **PRD-to-PR Pipeline** | `tdd-orchestrator run-prd <file> --target /path` — end-to-end: ingest, decompose, TDD, open PR | P0 |
| 7 | **Dry-Run / Preview Mode** | `tdd-orchestrator decompose <prd> --dry-run` — shows task breakdown without executing | P1 |
| 8 | **Task Dependency Graph** | Decomposition outputs DAG, not flat list; worker pool respects dependency edges | P1 |
| 9 | **Per-Project Configuration** | `.tdd/config.toml` — language, test framework, source layout, branch strategy, model prefs | P0 |
| 10 | **Checkpoint & Resume** | `tdd-orchestrator resume` — picks up from last completed task after failure/stop | P1 |

### II. Deployment & Integration as a Service

| # | Idea | Description | Priority |
|---|------|-------------|----------|
| 1 | **Daemon Mode** | `tdd-orchestrator serve --port 8420` — runs as local daemon with REST API via ASGI framework | P0 |
| 2 | **Per-Project Agent Model** | Each project installs as dev dependency, runs locally. No centralized server required | P0 |
| 3 | **REST API Layer** | Endpoints: `POST /prd`, `GET /tasks`, `POST /tasks/{id}/retry`, `GET /health`, `GET /metrics`, `WS /events` | P0 |
| 4 | **Webhook / Event System** | Generalize `hooks.py` + `notifications.py` to emit events on state changes; external subscribers | P1 |
| 5 | **Docker Packaging** | `docker run tdd-orchestrator --mount` — packages with all deps. Include `docker-compose.yml` | P2 |
| 6 | **GitHub Actions Integration** | Action that runs `tdd-orchestrator run-prd` on PR creation when PRD file added | P1 |
| 7 | **Project Registry** | Lightweight registry where running agents register: project name, location, status, task counts | P0 |
| 8 | **Auth & API Keys** | Bearer token auth for daemon/API mode. Simple, no OAuth unless multi-tenant | P2 |
| 9 | **SDK / Client Library** | `from tdd_orchestrator.client import OrchestratorClient` — Python client for REST API | P1 |
| 10 | **Plugin Architecture for Workers** | Pluggable workers: Claude, local LLM, human-in-the-loop. Define `Worker` protocol | P2 |

### III. Frontend Web Dashboard

| # | Idea | Description | Priority |
|---|------|-------------|----------|
| 1 | **Tech Stack** | React + Vite + TailwindCSS — lightweight, static build served by daemon | P0 |
| 2 | **Real-Time Task Board** | Kanban: PENDING -> RED -> GREEN -> VERIFY -> COMPLETE -> FAILED. WebSocket/SSE live updates | P0 |
| 3 | **Worker Health Panel** | Per-worker circuit breaker state, current task, success/failure rates, heartbeat | P0 |
| 4 | **Circuit Breaker Dashboard** | 3-level viz: System -> Worker -> Stage. Color-coded, click-through, manual reset | P1 |
| 5 | **Multi-Project Overview** | Top-level page: all registered projects, status, progress bars, last activity | P0 |
| 6 | **PRD Submission Interface** | Form/drag-drop for PRD files, decomposition preview before execution | P1 |
| 7 | **Task Detail View** | TDD stage progression, LLM prompts (redacted), test output, code diff, timing | P1 |
| 8 | **Metrics & Analytics** | Charts: tasks/time, avg time/stage, circuit trip frequency, model usage, cost estimates | P2 |
| 9 | **Server-Sent Events** | SSE from API for unidirectional updates — simpler than WebSocket for monitoring | P0 |
| 10 | **Embeddable Status Widget** | Iframe/JS widget for GitHub PRs, Slack, team dashboards. Read-only status view | P2 |

---

## Target Architecture

```
+----------------------------------------------------------------+
|                    Web Dashboard (React + Vite)                 |
|  Multi-project overview | Task board | Circuit breaker viz     |
+----------------------------+-----------------------------------+
                             | REST + SSE
+----------------------------v-----------------------------------+
|              Registry / Aggregator API                         |
|         (lightweight service, reads from all agents)           |
+--------+------------------+------------------+-----------------+
         |                  |                  |
+--------v--------+ +-------v--------+ +-------v--------+
|  Project A      | |  Project B     | |  Project C     |
|  tdd-orchestrator| |  tdd-orchestrator| |  tdd-orchestrator|
|  (daemon mode)  | |  (CLI mode)    | |  (daemon mode) |
|  SQLite DB      | |  SQLite DB     | |  SQLite DB     |
|  Workers (2-3)  | |  Workers (1)   | |  Workers (3)   |
|  Circuit Breakers| |  Circuit Breakers| |  Circuit Breakers|
+-----------------+ +----------------+ +----------------+
```

### Key Architecture Decisions

1. **Federated, not centralized** — Each project runs its own orchestrator instance with its own SQLite DB
2. **SQLite stays** — Per-project isolation makes SQLite a feature (no shared-write contention)
3. **API is additive** — The REST layer wraps the existing async engine; CLI becomes a thin client
4. **Dashboard aggregates** — Reads from the registry, proxies to per-project agents
5. **Pip-installable remains primary** — Docker and service modes are secondary delivery mechanisms

---

## Implementation Phases (High Level)

### Phase 1: API Layer (The One Thing)
- ASGI framework (Litestar or FastAPI) wrapping existing engine
- REST endpoints for tasks, health, metrics
- SSE for real-time updates
- `tdd-orchestrator serve` command

### Phase 2: PRD Pipeline
- PRD intake command and templates
- Project bootstrap (`init --project`)
- Per-project `.tdd/config.toml`
- PRD-to-PR end-to-end pipeline

### Phase 3: Web Dashboard
- React + Vite + Tailwind setup
- Task board (Kanban)
- Worker health panel
- Circuit breaker visualization

### Phase 4: Multi-Project Federation
- Project registry
- Aggregator API
- Multi-project dashboard overview
- Webhook/event system

### Phase 5: Ecosystem
- Docker packaging
- GitHub Actions integration
- SDK client library
- Plugin architecture for workers

---

## Open Questions

1. **ASGI Framework:** Litestar vs FastAPI? (Litestar is more modern, FastAPI has larger ecosystem)
2. **Dashboard hosting:** Served by daemon, or separate static deployment?
3. **Registry storage:** SQLite file, JSON file, or its own lightweight service?
4. **Auth model:** API keys sufficient, or need JWT/OAuth for team use?
5. **PRD format:** Markdown-only, or support YAML/JSON structured formats?
6. **Task DAG:** How to encode dependencies in the decomposition output?

---

*This document will be refined through structured evaluation in the next session.*
