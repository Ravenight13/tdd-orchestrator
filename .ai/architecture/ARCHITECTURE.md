# TDD Orchestrator

Parallel task execution engine for Test-Driven Development workflows.

## Overview

The TDD Orchestrator manages parallel execution of TDD tasks across multiple Claude workers, with built-in circuit breakers for resilience. It supports end-to-end PRD-to-code pipelines with decomposition, parallel TDD execution, and optional PR creation.

## Quick Start

```bash
# Initialize project database
tdd-orchestrator init

# Run parallel execution
tdd-orchestrator run --parallel --workers 2

# Resume an interrupted run
tdd-orchestrator run --parallel --workers 2 --resume

# End-to-end PRD pipeline
tdd-orchestrator run-prd spec.md --workers 2

# Start API server with dashboard
tdd-orchestrator serve
```

## Components

### Core Engine
- `worker_pool/pool.py` — `WorkerPool` with claim-based task distribution and optimistic locking
- `worker_pool/worker.py` — Individual worker execution loop
- `worker_pool/pipeline.py` — TDD stage pipeline (RED → RED_FIX → GREEN → VERIFY → FIX → RE_VERIFY) with `_should_skip_stage()` for resume
- `worker_pool/config.py` — `WorkerConfig` dataclass
- `worker_pool/phase_gate.py` — Phase gate enforcement between decomposition phases

### Database Layer (`database/`)
- `core.py` — `OrchestratorDB` main class (composes all mixins)
- `connection.py` — Connection management and schema initialization
- `singleton.py` — `get_db()` / `reset_db()` singleton lifecycle
- `checkpoint.py` — `CheckpointMixin` for pipeline checkpoints, stage resume, and run-task tracking
- `tasks.py` — Task CRUD operations
- `workers.py` — Worker heartbeat and registration
- `runs.py` — Execution run lifecycle (start, complete, find resumable)

### Circuit Breakers (`circuit_breaker/`)
- `stage.py` — `StageCircuitBreaker` — per task:stage failure limits
- `worker.py` — `WorkerCircuitBreaker` — per worker consecutive failure limits
- `system.py` — `SystemCircuitBreaker` — global failure ratio threshold
- `registry.py` — Circuit breaker registry and lookup
- `circuit_breaker_config.py` — Configuration dataclasses
- States: CLOSED → OPEN → HALF_OPEN → CLOSED

### Decomposition (`decomposition/`)
- `decomposer.py` — 4-pass LLM pipeline (extract cycles → atomize → acceptance criteria → implementation hints)
- `parser.py` — PRD markdown parser
- `llm_client.py` — Claude API wrapper with SDK fallback
- `dependency_validator.py` — Circular dependency detection via Kahn's BFS
- `validators.py` — Acceptance criteria validation
- `overlap_detector.py` — Duplicate implementation detection

### CLI
- `cli.py` — Main CLI entry point with `run`, `status`, `health` commands
- `cli_run_prd.py` — `run-prd` end-to-end PRD pipeline command
- `cli_ingest.py` — `ingest` PRD decomposition-only command
- `cli_init.py` / `cli_init_prd.py` — Project and PRD template initialization
- `cli_circuits.py` — Circuit breaker status and reset commands
- `cli_validate.py` — Dependency validation command
- `cli_decompose.py` — Standalone decompose preview

### API Layer (`api/`)
- `app.py` — FastAPI application factory
- `routes/` — REST endpoints: health, tasks, workers, circuits, runs, metrics, analytics, events, prd
- `sse.py` / `sse_bridge.py` — Server-Sent Events broadcaster
- `serve.py` — `tdd-orchestrator serve` entry point (port 8420)
- `static_files.py` — Dashboard static file serving at `/app/`

### Supporting Modules
- `git_coordinator.py` — Branch creation, checkout, push
- `dep_graph.py` — Runtime dependency graph validation
- `models.py` — Domain models (Task, Attempt, etc.)
- `metrics.py` — Prometheus-style metrics collection
- `health.py` — Health check endpoint
- `notifications.py` — Slack notification with throttling
- `prompt_builder.py` / `prompt_templates.py` — TDD prompt construction
- `client/` — Async Python SDK client library

## Circuit Breakers

The orchestrator uses a three-level circuit breaker hierarchy:

### Stage Circuit Breaker
Prevents infinite retries on failing TDD stages.

```python
from tdd_orchestrator.circuit_breaker import StageCircuitBreaker

circuit = StageCircuitBreaker(db, task_id="TDD-1", stage="green")
if await circuit.check_and_allow():
    # Execute stage
    pass
```

### Worker Circuit Breaker
Pauses unhealthy worker processes.

```python
from tdd_orchestrator.circuit_breaker import WorkerCircuitBreaker

circuit = WorkerCircuitBreaker(db, worker_id="worker_1")
if await circuit.check_and_allow():
    # Process task
    pass
```

### System Circuit Breaker
Halts execution when widespread failure is detected.

```python
from tdd_orchestrator.circuit_breaker import SystemCircuitBreaker

system_circuit = SystemCircuitBreaker(db)
await system_circuit.register_worker("worker_1")

if await system_circuit.check_and_allow():
    # Continue execution
    pass
```

## Checkpoint & Resume

The orchestrator supports resuming interrupted pipeline runs via the `--resume` flag on both `run` and `run-prd` commands.

### How It Works

1. **Pipeline checkpoints**: When execution starts, a checkpoint is saved to `execution_runs.pipeline_state` (JSON blob) containing the stage reached, branch name, task count, and (for `run-prd`) the PRD file hash.

2. **Stage skip logic**: `_should_skip_stage()` in `worker_pool/pipeline.py` checks each task's attempt history. If a stage was already completed successfully, it's skipped on resume.

3. **Run-task tracking**: The `run_tasks` junction table links tasks to execution runs, recording `resume_from_stage` when a task is resumed mid-pipeline.

4. **Dependency safety net**: `_recover_dependency_chain()` ensures that if a task is resumed, all its prerequisite tasks have also completed.

5. **PRD content hash**: For `run-prd`, a SHA256 hash of the PRD file is saved in the checkpoint. On resume, if the hash differs, a warning is logged that previously decomposed tasks will be used.

### Schema

```sql
-- Junction table: which tasks belong to which run
CREATE TABLE IF NOT EXISTS run_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES execution_runs(id),
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    resume_from_stage TEXT,
    final_status TEXT,
    completed_at TIMESTAMP,
    UNIQUE(run_id, task_id)
);

-- Pipeline state column on execution_runs
-- execution_runs.pipeline_state TEXT (JSON blob)
```

### Database Operations (`CheckpointMixin`)

- `get_last_completed_stage(task_id)` — Most recent successful stage for a task
- `get_resumable_tasks()` — Tasks with prior progress that can resume
- `associate_task_with_run(run_id, task_id, resume_from_stage)` — Link task to run
- `complete_run_task(run_id, task_id, final_status)` — Mark run-task done
- `save_pipeline_checkpoint(run_id, state)` — Save checkpoint JSON
- `load_pipeline_checkpoint(run_id)` — Load checkpoint JSON
- `find_resumable_run(pipeline_type)` — Find most recent incomplete run

## CLI Commands

### Run Commands
```bash
# Parallel execution with 3 workers
tdd-orchestrator run --parallel --workers 3

# Resume an interrupted run
tdd-orchestrator run --parallel --workers 3 --resume

# End-to-end PRD pipeline
tdd-orchestrator run-prd spec.md --workers 2

# Resume PRD pipeline
tdd-orchestrator run-prd spec.md --workers 2 --resume

# Single branch mode (all workers commit to same branch)
tdd-orchestrator run --parallel --single-branch
```

### Status Commands
```bash
# Overall health
tdd-orchestrator health

# Circuit breaker status
tdd-orchestrator circuits status
tdd-orchestrator circuits status --level worker
tdd-orchestrator circuits status --state open

# Circuit health
tdd-orchestrator circuits health
tdd-orchestrator circuits health --json
```

### Management Commands
```bash
# Initialize project
tdd-orchestrator init

# Scaffold PRD template
tdd-orchestrator init-prd --name my-feature

# Reset specific circuit
tdd-orchestrator circuits reset worker:worker_1

# Reset all circuits
tdd-orchestrator circuits reset all --force

# Start API server
tdd-orchestrator serve
```

## Configuration

### Environment Variables

```bash
# Worker configuration
export TDD_MAX_WORKERS=3
export TDD_MAX_INVOCATIONS=100

# Circuit breaker tuning
export TDD_CIRCUIT_STAGE_MAX_FAILURES=5
export TDD_CIRCUIT_WORKER_MAX_CONSECUTIVE=5

# Notifications
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# API key (required for LLM calls)
export ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TDD Orchestrator                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │ Worker 1  │  │ Worker 2  │  │ Worker 3  │               │
│  │ Pipeline  │  │ Pipeline  │  │ Pipeline  │               │
│  │ Circuit   │  │ Circuit   │  │ Circuit   │               │
│  └───────────┘  └───────────┘  └───────────┘               │
│        │              │              │                      │
│        └──────────────┴──────────────┘                      │
│                       │                                     │
│               ┌───────▼───────┐                             │
│               │ Worker Pool   │                             │
│               │ (claim-based) │                             │
│               └───────┬───────┘                             │
│                       │                                     │
│          ┌────────────┼────────────┐                        │
│          │            │            │                        │
│  ┌───────▼──────┐ ┌──▼──────┐ ┌──▼───────────┐            │
│  │   System     │ │ Stage   │ │  Checkpoint   │            │
│  │   Circuit    │ │ Circuit │ │  & Resume     │            │
│  └──────────────┘ └─────────┘ └──────────────-┘            │
│                       │                                     │
│               ┌───────▼───────┐                             │
│               │   Database    │                             │
│               │   (SQLite)    │                             │
│               └───────────────┘                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
