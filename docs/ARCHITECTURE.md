# TDD Orchestrator

Parallel task execution engine for Test-Driven Development workflows.

## Overview

The TDD Orchestrator manages parallel execution of TDD tasks across multiple Claude workers, with built-in circuit breakers for resilience.

## Quick Start

```bash
# Run parallel execution
orchestrator run --parallel --workers 2

# Check status
orchestrator status

# View circuit breaker health
orchestrator circuits health
```

## Components

### Core
- `worker_pool.py` - Parallel worker management
- `database.py` - SQLite persistence layer
- `cli.py` - Command-line interface

### Circuit Breakers
- `circuit_breaker.py` - Circuit breaker implementations (Stage, Worker, System)
- `circuit_breaker_config.py` - Configuration dataclasses

### Monitoring
- `health.py` - Health check endpoint
- `notifications.py` - Slack notification with throttling
- `metrics.py` - Prometheus-style metrics collection

## Circuit Breakers

The orchestrator uses a three-level circuit breaker hierarchy:

### Stage Circuit Breaker
Prevents infinite retries on failing TDD stages.

```python
from agents.orchestrator.circuit_breaker import StageCircuitBreaker

circuit = StageCircuitBreaker(db, task_id="TDD-1", stage="green")
if await circuit.check_and_allow():
    # Execute stage
    pass
```

### Worker Circuit Breaker
Pauses unhealthy worker processes.

```python
from agents.orchestrator.circuit_breaker import WorkerCircuitBreaker

circuit = WorkerCircuitBreaker(db, worker_id="worker_1")
if await circuit.check_and_allow():
    # Process task
    pass
```

### System Circuit Breaker
Halts execution when widespread failure is detected.

```python
from agents.orchestrator.circuit_breaker import SystemCircuitBreaker

system_circuit = SystemCircuitBreaker(db)
await system_circuit.register_worker("worker_1")

if await system_circuit.check_and_allow():
    # Continue execution
    pass
```

## CLI Commands

### Run Commands
```bash
# Parallel execution with 3 workers
orchestrator run --parallel --workers 3

# Single branch mode (all workers commit to same branch)
orchestrator run --parallel --single-branch

# With Slack notifications
orchestrator run --parallel --slack-webhook $SLACK_WEBHOOK_URL
```

### Status Commands
```bash
# Overall status
orchestrator status

# Circuit breaker status
orchestrator circuits status
orchestrator circuits status --level worker
orchestrator circuits status --state open

# Circuit health
orchestrator circuits health
orchestrator circuits health --json
```

### Management Commands
```bash
# Reset specific circuit
orchestrator circuits reset worker:worker_1

# Reset all circuits
orchestrator circuits reset all --force
```

## Configuration

See [Circuit Breaker Configuration Reference](../../../docs/reference/CIRCUIT_BREAKER_CONFIG.md) for complete options.

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
```

## Monitoring

### Health Endpoint

```python
from agents.orchestrator.health import get_circuit_health

health = await get_circuit_health(db)
print(health.status)  # HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN
```

### Metrics

```python
from agents.orchestrator.metrics import get_metrics_collector

collector = get_metrics_collector()
print(collector.export_prometheus())
```

### Database Views

```sql
-- Open circuits
SELECT * FROM v_open_circuits;

-- Health summary
SELECT * FROM v_circuit_health_summary;

-- Flapping circuits
SELECT * FROM v_flapping_circuits;
```

## Documentation

- [Monitoring Guide](../../../docs/reference/CIRCUIT_BREAKER_MONITORING.md)
- [Configuration Reference](../../../docs/reference/CIRCUIT_BREAKER_CONFIG.md)
- [Grafana Dashboard](../../../docs/reference/CIRCUIT_BREAKER_DASHBOARD_README.md)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TDD Orchestrator                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Worker 1   │    │  Worker 2   │    │  Worker 3   │     │
│  │  Circuit    │    │  Circuit    │    │  Circuit    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                          │                                  │
│                  ┌───────▼───────┐                         │
│                  │    System     │                         │
│                  │    Circuit    │                         │
│                  └───────────────┘                         │
│                          │                                  │
│                  ┌───────▼───────┐                         │
│                  │   Database    │                         │
│                  │   (SQLite)    │                         │
│                  └───────────────┘                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
