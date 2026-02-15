"""CLI for TDD orchestrator.

Provides command-line interface for running parallel task execution.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from .cli_circuits import circuits
from .cli_ingest import ingest_command
from .cli_init import init_command
from .cli_init_prd import init_prd_command
from .cli_run_prd import run_prd_command
from .cli_validate import validate
from .database import OrchestratorDB
from .project_config import resolve_db_for_cli
from .worker_pool import PoolResult, WorkerConfig, WorkerPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(verbose: bool) -> None:
    """TDD Orchestrator - Parallel task execution for Test-Driven Development."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


# Register subcommand groups from separate modules
cli.add_command(circuits)
cli.add_command(ingest_command)
cli.add_command(init_command)
cli.add_command(init_prd_command)
cli.add_command(run_prd_command)
cli.add_command(validate)


@cli.command()
@click.option("--parallel", "-p", is_flag=True, help="Enable parallel execution")
@click.option("--workers", "-w", default=None, type=int,
              help="Max parallel workers (default: from config or 2)")
@click.option("--phase", type=int, default=None, help="Phase to execute (default: all phases)")
@click.option(
    "--all-phases",
    is_flag=True,
    help="Run all pending phases sequentially with failure gating",
)
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--slack-webhook", envvar="SLACK_WEBHOOK_URL", help="Slack webhook URL")
@click.option("--max-invocations", default=100, help="Max prompts per session (default: 100)")
@click.option("--local", is_flag=True, help="Use local branches from HEAD (for testing)")
@click.option(
    "--multi-branch",
    is_flag=True,
    help="Each worker uses its own branch (requires worktrees or separate clones)",
)
@click.option(
    "--no-phase-gates",
    is_flag=True,
    help="Disable phase gate validation between phases",
)
def run(
    parallel: bool,
    workers: int | None,
    phase: int | None,
    all_phases: bool,
    db: str | None,
    slack_webhook: str | None,
    max_invocations: int,
    local: bool,
    multi_branch: bool,
    no_phase_gates: bool,
) -> None:
    """Run the TDD orchestrator."""
    if all_phases and phase is not None:
        click.echo("Error: --all-phases and --phase are mutually exclusive", err=True)
        sys.exit(1)

    try:
        resolved_db_path, config = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Resolve workers: CLI > config > default
    resolved_workers = workers if workers is not None else (
        config.tdd.max_workers if config else 2
    )

    # Default to single-branch mode (all workers commit to current branch)
    single_branch = not multi_branch
    asyncio.run(
        _run_async(
            parallel, resolved_workers, phase, all_phases, resolved_db_path,
            slack_webhook, max_invocations, local, single_branch, no_phase_gates,
        )
    )


async def _run_async(
    parallel: bool,
    workers: int,
    phase: int | None,
    all_phases: bool,
    db_path: Path,
    slack_webhook: str | None,
    max_invocations: int,
    local: bool,
    single_branch: bool,
    no_phase_gates: bool = False,
) -> None:
    """Async implementation of run command."""
    _validate_workers(workers)

    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        if parallel:
            await _run_parallel(
                db, workers, phase, all_phases, slack_webhook,
                max_invocations, local, single_branch, no_phase_gates,
            )
        else:
            click.echo("Sequential execution not yet implemented")
            click.echo("Use --parallel flag for parallel execution")
            sys.exit(1)
    finally:
        await db.close()


def _validate_workers(workers: int) -> None:
    """Validate worker count."""
    if workers < 1:
        click.echo("Error: workers must be at least 1", err=True)
        sys.exit(1)
    if workers > 3:
        click.echo("Warning: using more than 3 workers not recommended", err=True)


async def _run_parallel(
    db: OrchestratorDB,
    workers: int,
    phase: int | None,
    all_phases: bool,
    slack_webhook: str | None,
    max_invocations: int,
    local: bool,
    single_branch: bool,
    no_phase_gates: bool = False,
) -> None:
    """Run parallel execution with worker pool."""
    mode = "single-branch" if single_branch else "multi-branch"
    click.echo(f"Starting parallel execution with {workers} workers ({mode} mode)...")

    config = WorkerConfig(
        max_workers=workers,
        max_invocations_per_session=max_invocations,
        budget_warning_threshold=int(max_invocations * 0.8),
        use_local_branches=local,
        single_branch_mode=single_branch,
        git_stash_enabled=False,  # Disable stash for simpler conventional commit workflow
        enable_phase_gates=not no_phase_gates,
    )

    pool = WorkerPool(
        db=db,
        base_dir=Path.cwd(),
        config=config,
        slack_webhook_url=slack_webhook,
    )

    if all_phases:
        result = await pool.run_all_phases()
    else:
        result = await pool.run_parallel_phase(phase)
    _print_results(result)

    if result.tasks_failed > 0 or result.stopped_reason:
        sys.exit(1)


def _print_results(result: PoolResult) -> None:
    """Print execution results to console."""
    click.echo("\n" + "=" * 50)
    click.echo("Execution Complete")
    click.echo("=" * 50)
    click.echo(f"Tasks completed: {result.tasks_completed}")
    click.echo(f"Tasks failed: {result.tasks_failed}")
    click.echo(f"Total invocations: {result.total_invocations}")

    if result.stopped_reason:
        click.echo(f"Stopped reason: {result.stopped_reason}")

    click.echo("\nWorker Statistics:")
    for ws in result.worker_stats:
        click.echo(
            f"  Worker {ws.worker_id}: "
            f"{ws.tasks_completed} completed, "
            f"{ws.tasks_failed} failed, "
            f"{ws.invocations} invocations, "
            f"{ws.elapsed_seconds:.1f}s"
        )


@cli.command()
@click.option("--db", type=click.Path(), help="Database path")
def status(db: str | None) -> None:
    """Show orchestrator status."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_status_async(resolved_db_path))


async def _status_async(db_path: Path) -> None:
    """Async implementation of status command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        progress = await db.get_progress()
        stats = await db.get_stats()

        click.echo("\n" + "=" * 50)
        click.echo("TDD Orchestrator Status")
        click.echo("=" * 50)
        click.echo(f"Total tasks: {progress['total']}")
        click.echo(f"Completed: {progress['completed']}")
        click.echo(f"Progress: {progress['percentage']:.1f}%")

        click.echo("\nBy Status:")
        for status_name, count in stats.items():
            if count > 0:
                click.echo(f"  {status_name}: {count}")

        # Check for stale tasks/workers
        stale_tasks = await db.get_stale_tasks()
        if stale_tasks:
            click.echo(f"\nWarning: Stale tasks: {len(stale_tasks)}")
            for t in stale_tasks[:5]:
                click.echo(f"  - {t['task_key']}")

        stale_workers = await db.get_stale_workers()
        if stale_workers:
            click.echo(f"\nWarning: Stale workers: {len(stale_workers)}")
            for w in stale_workers[:5]:
                click.echo(f"  - Worker {w['worker_id']}: {w['minutes_since_heartbeat']:.1f}min")

    finally:
        await db.close()


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
@click.option("--port", default=8420, type=int, help="Port to bind to (default: 8420)")
@click.option("--db-path", type=click.Path(), default=None, help="Database path")
@click.option("--reload", is_flag=True, help="Enable auto-reload on code changes")
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error", "critical"], case_sensitive=False),
    default="info",
    help="Logging level (default: info)",
)
def serve(
    host: str,
    port: int,
    db_path: str | None,
    reload: bool,
    log_level: str,
) -> None:
    """Start the API server."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    run_server(
        host=host,
        port=port,
        db_path=resolved_db_path,
        reload=reload,
        log_level=log_level,
    )


def run_server(
    host: str,
    port: int,
    db_path: Path | None,
    reload: bool,
    log_level: str,
) -> None:
    """Run the API server.

    Delegates to the real API server implementation in api.serve.

    Args:
        host: Host to bind to
        port: Port to bind to
        db_path: Optional database path
        reload: Enable auto-reload on code changes
        log_level: Logging level
    """
    from tdd_orchestrator.api.serve import run_server as _run_api_server

    _run_api_server(
        host=host,
        port=port,
        db_path=str(db_path) if db_path is not None else None,
        reload=reload,
        log_level=log_level,
    )


def main() -> None:
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
