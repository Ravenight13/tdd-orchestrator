"""CLI for TDD orchestrator.

Provides command-line interface for running parallel task execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from .database import OrchestratorDB
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


@cli.command()
@click.option("--parallel", "-p", is_flag=True, help="Enable parallel execution")
@click.option("--workers", "-w", default=2, help="Max parallel workers (default: 2)")
@click.option("--phase", type=int, default=None, help="Phase to execute (default: all phases)")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--slack-webhook", envvar="SLACK_WEBHOOK_URL", help="Slack webhook URL")
@click.option("--max-invocations", default=100, help="Max prompts per session (default: 100)")
@click.option("--local", is_flag=True, help="Use local branches from HEAD (for testing)")
@click.option(
    "--multi-branch",
    is_flag=True,
    help="Each worker uses its own branch (requires worktrees or separate clones)",
)
def run(
    parallel: bool,
    workers: int,
    phase: int | None,
    db: str | None,
    slack_webhook: str | None,
    max_invocations: int,
    local: bool,
    multi_branch: bool,
) -> None:
    """Run the TDD orchestrator."""
    # Default to single-branch mode (all workers commit to current branch)
    single_branch = not multi_branch
    asyncio.run(
        _run_async(
            parallel, workers, phase, db, slack_webhook, max_invocations, local, single_branch
        )
    )


async def _run_async(
    parallel: bool,
    workers: int,
    phase: int | None,
    db_path: str | None,
    slack_webhook: str | None,
    max_invocations: int,
    local: bool,
    single_branch: bool,
) -> None:
    """Async implementation of run command."""
    # Validate workers
    if workers < 1:
        click.echo("Error: workers must be at least 1", err=True)
        sys.exit(1)
    if workers > 3:
        click.echo("Warning: using more than 3 workers not recommended", err=True)

    # Initialize database
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        if parallel:
            mode = "single-branch" if single_branch else "multi-branch"
            click.echo(f"Starting parallel execution with {workers} workers ({mode} mode)...")

            config = WorkerConfig(
                max_workers=workers,
                max_invocations_per_session=max_invocations,
                budget_warning_threshold=int(max_invocations * 0.8),
                use_local_branches=local,
                single_branch_mode=single_branch,
                git_stash_enabled=False,  # Disable stash for simpler conventional commit workflow
            )

            pool = WorkerPool(
                db=db,
                base_dir=Path.cwd(),
                config=config,
                slack_webhook_url=slack_webhook,
            )

            result = await pool.run_parallel_phase(phase)

            _print_results(result)

            # Exit with error code if failures
            if result.tasks_failed > 0 or result.stopped_reason:
                sys.exit(1)
        else:
            click.echo("Sequential execution not yet implemented")
            click.echo("Use --parallel flag for parallel execution")
            sys.exit(1)

    finally:
        await db.close()


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
    asyncio.run(_status_async(db))


async def _status_async(db_path: str | None) -> None:
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


# =============================================================================
# Circuit Breaker Commands
# =============================================================================


@cli.group()
def circuits() -> None:
    """Circuit breaker management commands."""
    pass


@circuits.command(name="status")
@click.option("--db", type=click.Path(), help="Database path")
@click.option(
    "--level",
    type=click.Choice(["stage", "worker", "system"]),
    help="Filter by level",
)
@click.option(
    "--state",
    type=click.Choice(["closed", "open", "half_open"]),
    help="Filter by state",
)
def circuits_status(db: str | None, level: str | None, state: str | None) -> None:
    """Show circuit breaker status."""
    asyncio.run(_circuits_status_async(db, level, state))


async def _circuits_status_async(db_path: str | None, level: str | None, state: str | None) -> None:
    """Async implementation of circuits status command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        # Build query with optional filters
        query = "SELECT * FROM v_circuit_breaker_status WHERE 1=1"
        params: list[str] = []

        if level:
            query += " AND level = ?"
            params.append(level)
        if state:
            query += " AND state = ?"
            params.append(state)

        query += " ORDER BY level, identifier"

        async with db._conn.execute(query, tuple(params) if params else ()) as cursor:
            rows = await cursor.fetchall()

        click.echo("\n" + "=" * 60)
        click.echo("Circuit Breaker Status")
        click.echo("=" * 60)

        if not rows:
            click.echo("No circuits found.")
            return

        # Group by level
        by_level: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            row_dict = dict(row)
            lvl = row_dict["level"]
            if lvl not in by_level:
                by_level[lvl] = []
            by_level[lvl].append(row_dict)

        for lvl, circuit_list in by_level.items():
            click.echo(f"\n{lvl.upper()} CIRCUITS:")
            click.echo("-" * 40)
            for circuit in circuit_list:
                state_icon = {
                    "closed": "[OK]",
                    "open": "[X]",
                    "half_open": "[~]",
                }.get(circuit["state"], "?")
                click.echo(
                    f"  {state_icon} {circuit['identifier']}: "
                    f"{circuit['state']} "
                    f"(failures={circuit['failure_count']}, "
                    f"successes={circuit['success_count']})"
                )
                if circuit["state"] == "open" and circuit["opened_at"]:
                    click.echo(f"    Opened at: {circuit['opened_at']}")

    finally:
        await db.close()


@circuits.command(name="health")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def circuits_health(db: str | None, as_json: bool) -> None:
    """Show circuit breaker health summary."""
    asyncio.run(_circuits_health_async(db, as_json))


async def _circuits_health_async(db_path: str | None, as_json: bool) -> None:
    """Async implementation of circuits health command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        # Get circuit counts by state
        async with db._conn.execute(
            """
            SELECT state, COUNT(*) as count
            FROM circuit_breakers
            GROUP BY state
            """
        ) as cursor:
            state_rows = await cursor.fetchall()

        total = 0
        closed = 0
        opened = 0
        half_open = 0

        for row in state_rows:
            count = row["count"]
            total += count
            if row["state"] == "closed":
                closed = count
            elif row["state"] == "open":
                opened = count
            elif row["state"] == "half_open":
                half_open = count

        # Get open circuits for details
        async with db._conn.execute(
            """
            SELECT level, identifier, opened_at,
                   CAST(
                       (julianday('now') - julianday(opened_at)) * 24 * 60 AS INTEGER
                   ) as minutes_open
            FROM circuit_breakers
            WHERE state = 'open' AND opened_at IS NOT NULL
            ORDER BY opened_at ASC
            """
        ) as cursor:
            open_circuits = [dict(row) for row in await cursor.fetchall()]

        # Determine health status
        if total == 0:
            health_status = "UNKNOWN"
        elif opened == 0 and half_open == 0:
            health_status = "HEALTHY"
        elif opened > 0 and opened >= total * 0.5:
            health_status = "UNHEALTHY"
        else:
            health_status = "DEGRADED"

        # Check for flapping (circuits that opened/closed multiple times recently)
        async with db._conn.execute(
            """
            SELECT cb.identifier, COUNT(*) as state_changes
            FROM circuit_breaker_events cbe
            JOIN circuit_breakers cb ON cbe.circuit_id = cb.id
            WHERE cbe.event_type IN ('threshold_reached', 'recovery_succeeded')
              AND cbe.created_at >= datetime('now', '-1 hour')
            GROUP BY cb.id
            HAVING COUNT(*) >= 3
            """
        ) as cursor:
            flapping_rows = list(await cursor.fetchall())
        flapping_count = len(flapping_rows)

        health_data = {
            "status": health_status,
            "total_circuits": total,
            "circuits_closed": closed,
            "circuits_open": opened,
            "circuits_half_open": half_open,
            "flapping_circuits": flapping_count,
            "details": {"open_circuits": open_circuits},
        }

        if as_json:
            click.echo(json.dumps(health_data, indent=2))
        else:
            status_colors = {
                "HEALTHY": "green",
                "DEGRADED": "yellow",
                "UNHEALTHY": "red",
                "UNKNOWN": "white",
            }
            color = status_colors.get(health_status, "white")

            click.echo("\n" + "=" * 60)
            click.echo("Circuit Breaker Health")
            click.echo("=" * 60)
            click.secho(f"Status: {health_status}", fg=color, bold=True)
            click.echo(f"Total circuits: {total}")
            click.echo(f"  Closed: {closed}")
            click.echo(f"  Open: {opened}")
            click.echo(f"  Half-open: {half_open}")
            click.echo(f"Flapping: {flapping_count}")

            if open_circuits:
                click.echo("\nOpen Circuits:")
                for circuit in open_circuits:
                    click.echo(
                        f"  - {circuit['level']}:{circuit['identifier']} "
                        f"({circuit['minutes_open']} min)"
                    )

    finally:
        await db.close()


@circuits.command(name="reset")
@click.argument("circuit_id")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--force", is_flag=True, help="Force reset without confirmation")
def circuits_reset(circuit_id: str, db: str | None, force: bool) -> None:
    """Reset a circuit breaker.

    CIRCUIT_ID format: level:identifier (e.g., worker:worker_1, stage:TDD-1:green)
    Use 'all' to reset all circuits.
    """
    asyncio.run(_circuits_reset_async(circuit_id, db, force))


async def _circuits_reset_async(circuit_id: str, db_path: str | None, force: bool) -> None:
    """Async implementation of circuits reset command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        if circuit_id == "all":
            if not force:
                click.confirm("Reset ALL circuits?", abort=True)

            cursor = await db._conn.execute(
                """
                UPDATE circuit_breakers
                SET state = 'closed',
                    failure_count = 0,
                    success_count = 0,
                    half_open_requests = 0,
                    opened_at = NULL,
                    last_state_change_at = datetime('now'),
                    version = version + 1
                """
            )
            result = cursor.rowcount
            await db._conn.commit()
            click.echo(f"Reset {result} circuit(s).")

            # Log the reset events
            await db._conn.execute(
                """
                INSERT INTO circuit_breaker_events (circuit_id, event_type, from_state, to_state)
                SELECT id, 'manual_reset', state, 'closed'
                FROM circuit_breakers
                """
            )
            await db._conn.commit()
        else:
            # Parse circuit_id (level:identifier)
            parts = circuit_id.split(":", 1)
            if len(parts) != 2:
                click.echo(
                    "Error: Invalid circuit ID format. Use level:identifier",
                    err=True,
                )
                return

            level, identifier = parts

            if not force:
                click.confirm(f"Reset circuit {circuit_id}?", abort=True)

            # Get current state for event logging
            async with db._conn.execute(
                "SELECT id, state FROM circuit_breakers WHERE level = ? AND identifier = ?",
                (level, identifier),
            ) as cursor:
                current = await cursor.fetchone()

            if not current:
                click.echo(f"Error: Circuit not found: {circuit_id}", err=True)
                return

            circuit_db_id = current["id"]
            from_state = current["state"]

            # Reset the circuit
            cursor = await db._conn.execute(
                """
                UPDATE circuit_breakers
                SET state = 'closed',
                    failure_count = 0,
                    success_count = 0,
                    half_open_requests = 0,
                    opened_at = NULL,
                    last_state_change_at = datetime('now'),
                    version = version + 1
                WHERE level = ? AND identifier = ?
                """,
                (level, identifier),
            )
            result = cursor.rowcount
            await db._conn.commit()

            if result > 0:
                # Log the reset event
                await db._conn.execute(
                    """
                    INSERT INTO circuit_breaker_events
                    (circuit_id, event_type, from_state, to_state)
                    VALUES (?, 'manual_reset', ?, 'closed')
                    """,
                    (circuit_db_id, from_state),
                )
                await db._conn.commit()
                click.echo(f"Reset circuit: {circuit_id}")
            else:
                click.echo(f"No circuit updated: {circuit_id}", err=True)

    finally:
        await db.close()


def main() -> None:
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
