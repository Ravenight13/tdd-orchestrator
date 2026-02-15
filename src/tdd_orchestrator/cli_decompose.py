"""CLI command for standalone decomposition preview.

Thin wrapper exposing decompose_spec.run_decomposition() via
``tdd-orchestrator decompose <prd-file> --dry-run``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from .project_config import resolve_db_for_cli


@click.command("decompose")
@click.argument("prd_file", type=click.Path(exists=True))
@click.option("--prefix", "-p", required=True, help="Task key prefix (e.g., SF)")
@click.option("--dry-run", is_flag=True, default=True, help="Preview only, no DB writes (default)")
@click.option("--write", is_flag=True, help="Actually write tasks to DB (overrides --dry-run)")
@click.option("--mock-llm", is_flag=True, help="Use mock LLM client for testing")
@click.option("--phases", default=None, help="Comma-separated phase numbers to decompose")
@click.option("--db", type=click.Path(), default=None, help="Database path")
def decompose_command(
    prd_file: str,
    prefix: str,
    dry_run: bool,
    write: bool,
    mock_llm: bool,
    phases: str | None,
    db: str | None,
) -> None:
    """Preview PRD decomposition into TDD tasks.

    Runs the 4-pass LLM decomposition pipeline on a PRD file.
    Defaults to dry-run mode (no DB writes). Use --write to persist.
    """
    # Resolve DB only if writing
    effective_dry_run = not write
    if not effective_dry_run:
        try:
            resolve_db_for_cli(db)
        except (FileNotFoundError, ValueError) as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

    phases_filter = _parse_phases(phases)

    from .decompose_spec import run_decomposition

    exit_code = asyncio.run(
        run_decomposition(
            spec_path=Path(prd_file),
            prefix=prefix,
            dry_run=effective_dry_run,
            use_mock_llm=mock_llm,
            phases_filter=phases_filter,
        )
    )
    sys.exit(exit_code)


def _parse_phases(phases_str: str | None) -> set[int] | None:
    """Parse comma-separated phase numbers."""
    if phases_str is None:
        return None
    return {int(p.strip()) for p in phases_str.split(",")}
