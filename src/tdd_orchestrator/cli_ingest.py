"""CLI ingest command for TDD Orchestrator.

Thin wrapper around run_decomposition() that integrates with the
project config system. Decomposes a PRD into atomic TDD tasks and
stores them in the project's .tdd/orchestrator.db.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from .database import reset_db
from .decompose_spec import run_decomposition
from .decomposition.exceptions import DecompositionError
from .project_config import find_project_root, setup_project_context

logger = logging.getLogger(__name__)


def _parse_phases(phases_str: str | None) -> set[int] | None:
    """Parse comma-separated phase numbers.

    Args:
        phases_str: Comma-separated phase numbers (e.g., "1,2,3").

    Returns:
        Set of phase numbers, or None if input is None.

    Raises:
        click.BadParameter: If any value is not a valid integer.
    """
    if phases_str is None:
        return None
    try:
        return {int(p.strip()) for p in phases_str.split(",")}
    except ValueError as exc:
        msg = f"Invalid phase number in '{phases_str}': {exc}"
        raise click.BadParameter(msg) from exc


@click.command("ingest")
@click.option(
    "--prd",
    "-f",
    "prd_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Path to PRD/spec file",
)
@click.option(
    "--project",
    "-p",
    "project_path",
    default=None,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Project root (auto-discovered if omitted)",
)
@click.option(
    "--clear",
    is_flag=True,
    help="Clear existing tasks with same prefix",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Parse and decompose only, no DB writes",
)
@click.option(
    "--phases",
    "phases_str",
    default=None,
    help='Comma-separated phase numbers (e.g., "1,2,3")',
)
@click.option(
    "--prefix",
    default=None,
    help="Override project prefix for task keys",
)
@click.option(
    "--scaffolding-ref",
    is_flag=True,
    help="Enable MODULE API SPEC reference in prompts",
)
@click.option(
    "--mock-llm",
    is_flag=True,
    hidden=True,
    help="Use mock LLM for testing",
)
def ingest_command(
    prd_path: str,
    project_path: str | None,
    clear: bool,
    dry_run: bool,
    phases_str: str | None,
    prefix: str | None,
    scaffolding_ref: bool,
    mock_llm: bool,
) -> None:
    """Ingest a PRD and decompose into TDD tasks.

    Parses a Product Requirements Document and decomposes it into
    atomic TDD tasks using the 4-pass LLM decomposition pipeline.
    Tasks are stored in the project's .tdd/orchestrator.db.
    """
    # Resolve project root
    project_root: Path
    if project_path:
        project_root = Path(project_path)
    else:
        discovered = find_project_root()
        if discovered is None:
            click.echo(
                "Error: No .tdd/ directory found. "
                "Run 'tdd-orchestrator init' first or use --project.",
                err=True,
            )
            sys.exit(1)
        project_root = discovered

    # Parse phases
    phases_filter = _parse_phases(phases_str)

    asyncio.run(
        _run_ingest_async(
            prd_path=Path(prd_path),
            project_root=project_root,
            clear=clear,
            dry_run=dry_run,
            phases_filter=phases_filter,
            prefix_override=prefix,
            scaffolding_ref=scaffolding_ref,
            mock_llm=mock_llm,
        )
    )


async def _run_ingest_async(
    *,
    prd_path: Path,
    project_root: Path,
    clear: bool,
    dry_run: bool,
    phases_filter: set[int] | None,
    prefix_override: str | None,
    scaffolding_ref: bool,
    mock_llm: bool,
) -> None:
    """Async implementation of ingest command.

    Loads project config, resolves prefix, runs decomposition pipeline,
    and ensures DB singleton cleanup in all code paths.
    """
    try:
        config = await setup_project_context(project_root)

        # Resolve prefix: --prefix override or config value
        prefix = prefix_override if prefix_override is not None else config.tdd.prefix

        # Validate prefix (inline check matching _validate_config rules)
        if not prefix or not prefix.strip():
            click.echo("Error: prefix must not be empty", err=True)
            sys.exit(1)
        if " " in prefix or "\t" in prefix:
            click.echo(
                f"Error: prefix must not contain whitespace: '{prefix}'",
                err=True,
            )
            sys.exit(1)

        click.echo(f"Ingesting PRD: {prd_path}")
        click.echo(f"Project: {config.name} (prefix: {prefix})")

        exit_code = await run_decomposition(
            spec_path=prd_path,
            prefix=prefix,
            clear_existing=clear,
            dry_run=dry_run,
            use_mock_llm=mock_llm,
            phases_filter=phases_filter,
            scaffolding_ref=scaffolding_ref,
        )

        if exit_code != 0:
            sys.exit(exit_code)

    except DecompositionError as exc:
        click.echo(f"Decomposition error: {exc}", err=True)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(1)
    finally:
        await reset_db()
        _cleanup_sdk()


def _cleanup_sdk() -> None:
    """Best-effort SDK child process cleanup."""
    try:
        from .decomposition.llm_client import cleanup_sdk_child_processes

        cleanup_sdk_child_processes()
    except Exception:  # noqa: BLE001
        pass
