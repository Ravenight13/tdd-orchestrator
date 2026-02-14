"""CLI init command for TDD Orchestrator.

Provides the top-level `init` command that bootstraps a .tdd/ directory
with config.toml, .gitignore, and a per-project database.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from .database import OrchestratorDB
from .project_config import create_default_config


@click.command("init")
@click.option(
    "--project",
    "-p",
    "project_path",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Path to the project directory",
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Project name (defaults to directory name)",
)
@click.option(
    "--language",
    "-l",
    default="python",
    help="Project language (default: python)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing .tdd/ configuration",
)
def init_command(
    project_path: str,
    name: str | None,
    language: str,
    force: bool,
) -> None:
    """Initialize a project for TDD orchestration.

    Creates a .tdd/ directory with config.toml, .gitignore,
    and an empty orchestrator database.
    """
    path = Path(project_path)

    try:
        config = create_default_config(
            path,
            name=name,
            language=language,
            force=force,
        )
    except FileExistsError:
        click.echo(
            f"Error: Project already initialized at {path / '.tdd'}. "
            "Use --force to overwrite.",
            err=True,
        )
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Initialize the database
    db_path = config.resolve_db_path(path)
    asyncio.run(_init_db(db_path))

    click.echo(f"Initialized TDD project '{config.name}' at {path}")
    click.echo(f"  Config: {path / '.tdd' / 'config.toml'}")
    click.echo(f"  Database: {db_path}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  tdd-orchestrator ingest --project . --prd <prd-file>")


async def _init_db(db_path: str | Path) -> None:
    """Initialize the project database."""
    db = OrchestratorDB(db_path)
    await db.connect()
    await db.close()
