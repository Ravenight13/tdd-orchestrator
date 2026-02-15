"""Validate CLI commands for TDD orchestrator.

Provides CLI subcommands for manually running phase gate
and end-of-run validation checks.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from .database import OrchestratorDB
from .dep_graph import validate_dependencies
from .project_config import resolve_db_for_cli
from .worker_pool.phase_gate import PhaseGateValidator
from .worker_pool.run_validator import RunValidator


@click.group()
def validate() -> None:
    """Run validation checks on execution state."""


@validate.command("phase")
@click.option("--phase", "-p", type=int, required=True, help="Phase number to validate")
@click.option("--db", type=click.Path(), default=None, help="Database path")
def validate_phase(phase: int, db: str | None) -> None:
    """Run phase gate validation for a specific phase."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_validate_phase_async(phase, resolved_db_path))


@validate.command("run")
@click.option("--run-id", "-r", type=int, default=None, help="Execution run ID (latest if omitted)")
@click.option("--db", type=click.Path(), default=None, help="Database path")
def validate_run(run_id: int | None, db: str | None) -> None:
    """Run end-of-run validation."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_validate_run_async(run_id, resolved_db_path))


@validate.command("all")
@click.option("--db", type=click.Path(), default=None, help="Database path")
def validate_all(db: str | None) -> None:
    """Run all phase gates and end-of-run validation."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_validate_all_async(resolved_db_path))


async def _validate_phase_async(phase: int, db_path: Path) -> None:
    """Run phase gate validation for a single phase."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        validator = PhaseGateValidator(db, base_dir=Path.cwd())
        result = await validator.validate_phase(phase)

        click.echo(result.summary)

        if not result.passed:
            if result.incomplete_tasks:
                click.echo("\nIncomplete tasks:")
                for task_key in result.incomplete_tasks:
                    click.echo(f"  - {task_key}")

            failed_tests = [r for r in result.regression_results if not r.passed]
            if failed_tests:
                click.echo("\nFailed regression tests:")
                for tr in failed_tests:
                    click.echo(f"  - {tr.file}")

            if result.errors:
                click.echo("\nErrors:")
                for err in result.errors:
                    click.echo(f"  - {err}")

            sys.exit(1)
    finally:
        await db.close()


async def _validate_run_async(run_id: int | None, db_path: Path) -> None:
    """Run end-of-run validation."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        if run_id is None:
            run_id = await db.get_latest_run_id()
            if run_id is None:
                click.echo("Error: No execution runs found", err=True)
                sys.exit(1)

        validator = RunValidator(db, base_dir=Path.cwd())
        result = await validator.validate_run(run_id)

        click.echo(result.summary)

        if not result.passed:
            if result.errors:
                click.echo("\nErrors:")
                for err in result.errors:
                    click.echo(f"  - {err}")

            if result.orphaned_tasks:
                click.echo("\nOrphaned tasks:")
                for task_key in result.orphaned_tasks:
                    click.echo(f"  - {task_key}")

            sys.exit(1)
    finally:
        await db.close()


async def _validate_all_async(db_path: Path) -> None:
    """Run all phase gates and end-of-run validation."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        phases = await db.get_all_phases()
        any_failed = False

        # Phase gate validations
        if phases:
            gate_validator = PhaseGateValidator(db, base_dir=Path.cwd())
            for phase in phases:
                result = await gate_validator.validate_phase(phase)
                click.echo(result.summary)
                if not result.passed:
                    any_failed = True

        # End-of-run validation
        run_id = await db.get_latest_run_id()
        if run_id is not None:
            run_validator = RunValidator(db, base_dir=Path.cwd())
            run_result = await run_validator.validate_run(run_id)
            click.echo(run_result.summary)
            if not run_result.passed:
                any_failed = True
        else:
            click.echo("No execution runs found — skipping end-of-run validation")

        if any_failed:
            sys.exit(1)
    finally:
        await db.close()


@validate.command("dependencies")
@click.option("--db", type=click.Path(), default=None, help="Database path")
def validate_deps(db: str | None) -> None:
    """Check for dangling dependency references in tasks."""
    try:
        resolved_db_path, _ = resolve_db_for_cli(db)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    asyncio.run(_validate_deps_async(resolved_db_path))


async def _validate_deps_async(db_path: Path) -> None:
    """Async implementation of dependency validation."""
    db = OrchestratorDB(db_path)
    await db.connect()

    try:
        issues = await validate_dependencies(db)
        if not issues:
            click.echo("All dependency references are valid.")
            return

        click.echo(f"Found {len(issues)} task(s) with dangling dependency references:")
        for issue in issues:
            refs = ", ".join(issue["dangling_refs"])
            click.echo(f"  {issue['task_key']} -> [{refs}]")
        sys.exit(1)
    finally:
        await db.close()
