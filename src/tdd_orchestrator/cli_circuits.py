"""Circuit breaker CLI commands for TDD orchestrator.

Provides CLI subcommands for managing circuit breakers.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from .database import OrchestratorDB
from .project_config import resolve_db_for_cli


@click.group()
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
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_circuits_status_async(resolved_db_path, level, state))


async def _circuits_status_async(db_path: Path, level: str | None, state: str | None) -> None:
    """Async implementation of circuits status command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        rows = await _fetch_circuit_rows(db, level, state)
        _print_circuit_status(rows)

    finally:
        await db.close()


async def _fetch_circuit_rows(
    db: OrchestratorDB, level: str | None, state: str | None
) -> list[Any]:
    """Fetch circuit breaker rows with optional filters."""
    assert db._conn is not None

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
        return list(await cursor.fetchall())


def _print_circuit_status(rows: list[Any]) -> None:
    """Print circuit status output."""
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


@circuits.command(name="health")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def circuits_health(db: str | None, as_json: bool) -> None:
    """Show circuit breaker health summary."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_circuits_health_async(resolved_db_path, as_json))


async def _circuits_health_async(db_path: Path, as_json: bool) -> None:
    """Async implementation of circuits health command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        health_data = await _compute_health_data(db)
        _print_health_output(health_data, as_json)

    finally:
        await db.close()


async def _compute_health_data(db: OrchestratorDB) -> dict[str, Any]:
    """Compute circuit breaker health data."""
    assert db._conn is not None

    state_counts = await _get_state_counts(db)
    open_circuits = await _get_open_circuits(db)
    flapping_count = await _get_flapping_count(db)

    total = state_counts["total"]
    closed = state_counts["closed"]
    opened = state_counts["open"]
    half_open = state_counts["half_open"]

    health_status = _determine_health_status(total, opened, half_open)

    return {
        "status": health_status,
        "total_circuits": total,
        "circuits_closed": closed,
        "circuits_open": opened,
        "circuits_half_open": half_open,
        "flapping_circuits": flapping_count,
        "details": {"open_circuits": open_circuits},
    }


async def _get_state_counts(db: OrchestratorDB) -> dict[str, int]:
    """Get counts of circuits by state."""
    assert db._conn is not None

    async with db._conn.execute(
        """
        SELECT state, COUNT(*) as count
        FROM circuit_breakers
        GROUP BY state
        """
    ) as cursor:
        state_rows = await cursor.fetchall()

    counts = {"total": 0, "closed": 0, "open": 0, "half_open": 0}
    for row in state_rows:
        count = row["count"]
        counts["total"] += count
        if row["state"] in counts:
            counts[row["state"]] = count

    return counts


async def _get_open_circuits(db: OrchestratorDB) -> list[dict[str, Any]]:
    """Get details of open circuits."""
    assert db._conn is not None

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
        return [dict(row) for row in await cursor.fetchall()]


async def _get_flapping_count(db: OrchestratorDB) -> int:
    """Get count of flapping circuits."""
    assert db._conn is not None

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
    return len(flapping_rows)


def _determine_health_status(total: int, opened: int, half_open: int) -> str:
    """Determine overall health status."""
    if total == 0:
        return "UNKNOWN"
    elif opened == 0 and half_open == 0:
        return "HEALTHY"
    elif opened > 0 and opened >= total * 0.5:
        return "UNHEALTHY"
    else:
        return "DEGRADED"


def _print_health_output(health_data: dict[str, Any], as_json: bool) -> None:
    """Print health data output."""
    if as_json:
        click.echo(json.dumps(health_data, indent=2))
    else:
        _print_health_text(health_data)


def _print_health_text(health_data: dict[str, Any]) -> None:
    """Print health data as formatted text."""
    health_status = health_data["status"]
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
    click.echo(f"Total circuits: {health_data['total_circuits']}")
    click.echo(f"  Closed: {health_data['circuits_closed']}")
    click.echo(f"  Open: {health_data['circuits_open']}")
    click.echo(f"  Half-open: {health_data['circuits_half_open']}")
    click.echo(f"Flapping: {health_data['flapping_circuits']}")

    open_circuits = health_data["details"]["open_circuits"]
    if open_circuits:
        click.echo("\nOpen Circuits:")
        for circuit in open_circuits:
            click.echo(
                f"  - {circuit['level']}:{circuit['identifier']} "
                f"({circuit['minutes_open']} min)"
            )


@circuits.command(name="reset")
@click.argument("circuit_id")
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--force", is_flag=True, help="Force reset without confirmation")
def circuits_reset(circuit_id: str, db: str | None, force: bool) -> None:
    """Reset a circuit breaker.

    CIRCUIT_ID format: level:identifier (e.g., worker:worker_1, stage:TDD-1:green)
    Use 'all' to reset all circuits.
    """
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_circuits_reset_async(circuit_id, resolved_db_path, force))


async def _circuits_reset_async(circuit_id: str, db_path: Path, force: bool) -> None:
    """Async implementation of circuits reset command."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        await db._ensure_connected()
        if not db._conn:
            click.echo("Error: Database not connected", err=True)
            return

        if circuit_id == "all":
            await _reset_all_circuits(db, force)
        else:
            await _reset_single_circuit(db, circuit_id, force)

    finally:
        await db.close()


async def _reset_all_circuits(db: OrchestratorDB, force: bool) -> None:
    """Reset all circuits."""
    assert db._conn is not None

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


async def _reset_single_circuit(db: OrchestratorDB, circuit_id: str, force: bool) -> None:
    """Reset a single circuit by ID."""
    assert db._conn is not None

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

    current = await _get_circuit_current_state(db, level, identifier)
    if not current:
        click.echo(f"Error: Circuit not found: {circuit_id}", err=True)
        return

    circuit_db_id = current["id"]
    from_state = current["state"]

    result = await _update_circuit_to_closed(db, level, identifier)

    if result > 0:
        await _log_circuit_reset_event(db, circuit_db_id, from_state)
        click.echo(f"Reset circuit: {circuit_id}")
    else:
        click.echo(f"No circuit updated: {circuit_id}", err=True)


async def _get_circuit_current_state(
    db: OrchestratorDB, level: str, identifier: str
) -> dict[str, Any] | None:
    """Get current state of a circuit."""
    assert db._conn is not None

    async with db._conn.execute(
        "SELECT id, state FROM circuit_breakers WHERE level = ? AND identifier = ?",
        (level, identifier),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def _update_circuit_to_closed(db: OrchestratorDB, level: str, identifier: str) -> int:
    """Update a circuit to closed state. Returns rowcount."""
    assert db._conn is not None

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
    return result


async def _log_circuit_reset_event(db: OrchestratorDB, circuit_db_id: int, from_state: str) -> None:
    """Log a manual reset event for a circuit."""
    assert db._conn is not None

    await db._conn.execute(
        """
        INSERT INTO circuit_breaker_events
        (circuit_id, event_type, from_state, to_state)
        VALUES (?, 'manual_reset', ?, 'closed')
        """,
        (circuit_db_id, from_state),
    )
    await db._conn.commit()
