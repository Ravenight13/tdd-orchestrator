# TDD Orchestrator

Parallel task execution engine with three-level circuit breakers.

## Installation

```bash
pip install -e ".[dev,sdk]"
```

## Quick Start

```bash
# Initialize database
tdd-orchestrator init

# Check health
tdd-orchestrator health

# Run tasks
tdd-orchestrator run --workers 2
```

## Features

- Parallel worker pool with claim-based task distribution
- Three-level circuit breakers (Stage, Worker, System)
- SQLite persistence with optimistic locking
- AST-based code quality analysis
- Integrated pytest/mypy/ruff verification
- Optional Claude SDK integration (MCP server, hooks)

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Project Structure

```
tdd_orchestrator/
├── src/tdd_orchestrator/      # Main package
│   ├── decomposition/         # Task decomposition submodule
│   ├── database.py            # SQLite persistence layer
│   ├── worker_pool.py         # Parallel worker management
│   ├── circuit_breaker.py     # Three-level breaker system
│   ├── ast_checker.py         # Code quality analysis
│   └── cli.py                 # Command-line interface
├── schema/schema.sql          # Database schema
├── tests/                     # Unit, integration, e2e tests
└── docs/                      # Documentation
```

## Development

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install with dev dependencies
uv pip install -e ".[dev,sdk]"

# Run linting
ruff check src/

# Run type checking
mypy src/

# Run tests
pytest tests/ -v
```

## License

MIT
