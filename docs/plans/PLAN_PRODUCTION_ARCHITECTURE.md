# TDD Orchestrator — Production Architecture Plan

## Context

TDD Orchestrator is a working CLI tool with 53 source files (~15k lines), 324 passing tests, mypy strict clean. The goal is to evolve it into a production system that:
1. Accepts PRDs and drives TDD RED-GREEN-REFACTOR cycles to produce working code in **any** project
2. Runs as a service (daemon mode) alongside the existing CLI
3. Provides a web dashboard for monitoring tasks, workers, and circuit breakers
4. Federates across multiple projects with a central registry/dashboard

**Architecture Direction:** Federated agents + central dashboard (not monolithic server). Each project runs its own orchestrator with its own SQLite DB. A lightweight aggregator provides multi-project visibility.

---

## Phase 1: API Layer (Critical Path — Everything Depends on This)

### What
Wrap the existing async engine with a FastAPI REST API + SSE for real-time events. Add `tdd-orchestrator serve` command.

### Why FastAPI
- Production-proven async ASGI framework
- Auto-generates OpenAPI/Swagger docs
- Pydantic v2 for request/response validation
- Largest ecosystem of any Python async web framework

### Files to Create
```
src/tdd_orchestrator/api/
├── __init__.py
├── app.py                 # FastAPI app factory (~250 lines)
├── serve.py               # Uvicorn wrapper for CLI (~150 lines)
├── dependencies.py        # DB injection, config (~200 lines)
├── sse.py                 # SSE broadcaster (~350 lines)
├── routes/
│   ├── __init__.py
│   ├── tasks.py           # GET/POST task endpoints (~350 lines)
│   ├── health.py          # Health check endpoints (~150 lines)
│   ├── circuits.py        # Circuit breaker management (~300 lines)
│   ├── workers.py         # Worker status (~200 lines)
│   ├── runs.py            # Execution runs (~200 lines)
│   └── metrics.py         # Prometheus export (~100 lines)
├── models/
│   ├── __init__.py
│   ├── requests.py        # Pydantic request schemas (~300 lines)
│   └── responses.py       # Pydantic response schemas (~350 lines)
└── middleware/
    ├── __init__.py
    ├── error_handler.py   # Exception handling (~200 lines)
    └── cors.py            # CORS config (~100 lines)
```

### Files to Modify
- `cli.py` — Add `serve` command (+40 lines)
- `hooks.py` — Publish events to SSE broadcaster (+50 lines)
- `pyproject.toml` — Add fastapi, uvicorn, pydantic, sse-starlette
- `database/tasks.py` — Add `get_all_tasks()`, `get_tasks_by_status()` methods

### Core Endpoints
```
GET  /health              — Health status + circuit breaker summary
GET  /tasks               — List tasks (filter by phase, status)
GET  /tasks/{key}         — Get task details + attempt history
POST /tasks/{key}/retry   — Retry a failed task
GET  /workers             — List workers with health
GET  /circuits            — Circuit breaker states (3 levels)
POST /circuits/{id}/reset — Manual circuit reset
GET  /runs                — Execution run history
GET  /metrics             — Prometheus format export
GET  /events              — SSE stream (task updates, circuit events)
```

### Key Design: API is a Thin Facade
No business logic in the API layer. Every endpoint delegates to existing engine methods:
- `GET /tasks` → `db.get_all_tasks()` / `db.get_claimable_tasks(phase)`
- `GET /health` → `health.get_circuit_health(db)`
- `GET /metrics` → `metrics.get_metrics_collector().export_prometheus()`
- `GET /events` → SSE broadcaster fed by extended `hooks.py`

### SSE Design
- `SSEBroadcaster` class with async subscriber queues
- Events: `task_status_changed`, `worker_heartbeat`, `circuit_state_changed`, `run_completed`
- Integration: hooks.py emits events → broadcaster fans out to all connected clients

### Dependencies to Add
```toml
"fastapi>=0.115.0"
"uvicorn[standard]>=0.32.0"
"pydantic>=2.10.0"
"sse-starlette>=2.2.0"
```

### Verification
1. `tdd-orchestrator serve` starts on port 8420
2. `curl localhost:8420/health` returns healthy JSON
3. `curl localhost:8420/tasks` returns task list
4. SSE stream updates when tasks change
5. All 324 existing tests still pass
6. mypy strict + ruff clean on new code
7. New tests: ~150 tests across unit + integration

---

## Phase 2: PRD Pipeline

### What
Enable TDD Orchestrator to accept PRD files, bootstrap target projects, and run end-to-end PRD → decompose → TDD → PR pipelines.

### Files to Create
```
src/tdd_orchestrator/prd/
├── __init__.py
├── intake.py              # PRD loading/validation (~300 lines)
├── parser.py              # MD/YAML/JSON parsing (~350 lines)
└── templates.py           # PRD template generation (~200 lines)

src/tdd_orchestrator/project/
├── __init__.py
├── bootstrap.py           # `init --project` logic (~400 lines)
├── config.py              # .tdd/config.toml schema (~300 lines)
└── detector.py            # Auto-detect language/framework (~350 lines)

src/tdd_orchestrator/pipeline/
├── __init__.py
├── prd_to_pr.py           # End-to-end pipeline (~400 lines)
└── pr_creator.py          # GitHub PR creation (~250 lines)
```

### Key Commands
- `tdd-orchestrator init --project /path` — Bootstrap .tdd/ directory with config
- `tdd-orchestrator ingest feature.md` — Validate and show decomposition preview
- `tdd-orchestrator run-prd feature.md --target /path --pr` — Full pipeline

### Per-Project Config (.tdd/config.toml)
```toml
[project]
name = "my-app"
language = "python"
framework = "pytest"
source_root = "src"
test_root = "tests"

[tdd]
default_model = "opus"
max_workers = 2

[git]
base_branch = "main"
auto_merge = false
```

### Pipeline Flow
PRD file → parse → bootstrap project → 4-pass decomposition → load tasks → worker pool execution → verify all GREEN → create PR

---

## Phase 3: Web Dashboard

### What
React + Vite + Tailwind + shadcn/ui dashboard served by the daemon.

### Structure
```
dashboard/
├── package.json
├── vite.config.ts
└── src/
    ├── App.tsx
    ├── api/client.ts          # API client
    ├── hooks/useSSE.ts        # Real-time hook
    ├── pages/
    │   ├── Dashboard.tsx      # Task board (Kanban)
    │   ├── Workers.tsx        # Worker health panel
    │   ├── Circuits.tsx       # 3-level circuit breaker viz
    │   └── Metrics.tsx        # Analytics
    └── components/
        ├── TaskBoard.tsx      # Kanban columns
        ├── TaskCard.tsx       # Individual task
        ├── WorkerPanel.tsx    # Worker status cards
        └── CircuitBreakerViz.tsx  # Color-coded circuit states
```

### Critical Views
1. **Task Board (Kanban)** — PENDING → IN_PROGRESS → PASSING → COMPLETE → BLOCKED columns, SSE-driven
2. **Worker Health** — Per-worker cards with circuit breaker state, current task, heartbeat
3. **Circuit Breaker Dashboard** — 3-level hierarchy (system → worker → stage), manual reset buttons

### Serving
Daemon serves static build from `dashboard/dist/` via FastAPI `StaticFiles` mount.

---

## Phase 4: Multi-Project Federation

### What
Project registry + aggregator API for multi-project dashboard.

### Registry Design
- `~/.tdd/registry.db` — SQLite with projects table (name, path, api_url, status, last_seen)
- Daemon auto-registers on startup, sends heartbeats
- `tdd-orchestrator registry serve --port 8421` — Aggregator that proxies to per-project agents

### Dashboard Additions
- Project selector dropdown
- Multi-project overview page with progress bars per project

### Auth
Bearer token auth (`TDD_API_KEY` env var). Simple, no OAuth.

---

## Phase 5: Ecosystem

### GitHub Actions
- Action that runs `tdd-orchestrator run-prd` on PRD file changes in PR
- No Docker — action uses `pip install tdd-orchestrator[sdk]` directly

### SDK Client
- `OrchestratorClient` class for programmatic API access via httpx

### Worker Plugins
- `WorkerPlugin` protocol for pluggable workers (Claude, local LLM, human-in-the-loop)

### Deployment Model (No Docker)
- **Primary:** `pip install tdd-orchestrator` — pure Python, no containers
- **Daemon:** `tdd-orchestrator serve` runs as a background process (systemd, launchd, or screen/tmux)
- **Multi-project:** Each project runs its own daemon, registry aggregates

---

## Phase Summary

| Phase | Focus | New Files | Est. Lines | Key Dependency |
|-------|-------|-----------|-----------|----------------|
| 1 | API Layer | ~18 | ~4,000 | FastAPI, uvicorn |
| 2 | PRD Pipeline | ~13 | ~3,500 | pyyaml, frontmatter |
| 3 | Dashboard | ~40 | ~5,000 | React, Vite, Tailwind |
| 4 | Federation | ~7 | ~2,000 | (none new) |
| 5 | Ecosystem | ~8 | ~1,200 | (none new) |
