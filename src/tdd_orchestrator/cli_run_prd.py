"""CLI run-prd command for TDD Orchestrator.

End-to-end pipeline: ingest PRD, decompose into tasks, run TDD
execution, and optionally create a GitHub PR.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from .database import reset_db
from .prd_pipeline import (
    PrdPipelineConfig,
    PrdPipelineResult,
    derive_branch_name,
    run_prd_pipeline,
)
from .project_config import find_project_root, load_project_config

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


@click.command("run-prd")
@click.argument(
    "prd_file",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
)
@click.option(
    "--project", "-p",
    "project_path",
    default=None,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Project root (auto-discovered if omitted)",
)
@click.option(
    "--workers", "-w",
    default=None,
    type=int,
    help="Parallel workers (from config or default 2)",
)
@click.option(
    "--branch", "-b",
    default=None,
    help="Feature branch name (auto-generated from PRD filename)",
)
@click.option(
    "--create-pr",
    is_flag=True,
    help="Create GitHub PR on success",
)
@click.option(
    "--pr-title",
    default=None,
    help="PR title (auto-generated if omitted)",
)
@click.option(
    "--prefix",
    default=None,
    help="Task key prefix override",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Decompose only, skip execution and branch creation",
)
@click.option(
    "--clear",
    is_flag=True,
    help="Clear existing tasks with same prefix",
)
@click.option(
    "--max-invocations",
    default=100,
    type=int,
    help="API budget limit (default: 100)",
)
@click.option(
    "--scaffolding-ref",
    is_flag=True,
    help="Enable module API spec reference",
)
@click.option(
    "--phases",
    "phases_str",
    default=None,
    help="Comma-separated phase filter",
)
@click.option(
    "--no-phase-gates",
    is_flag=True,
    help="Disable phase gate validation between phases",
)
@click.option(
    "--mock-llm",
    is_flag=True,
    hidden=True,
    help="Use mock LLM (for testing)",
)
def run_prd_command(
    prd_file: str,
    project_path: str | None,
    workers: int | None,
    branch: str | None,
    create_pr: bool,
    pr_title: str | None,
    prefix: str | None,
    dry_run: bool,
    clear: bool,
    max_invocations: int,
    scaffolding_ref: bool,
    phases_str: str | None,
    no_phase_gates: bool,
    mock_llm: bool,
) -> None:
    """Run end-to-end PRD pipeline: ingest, decompose, TDD, open PR.

    PRD_FILE is the path to the Product Requirements Document.
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

    # Load config for defaults
    try:
        config = load_project_config(project_root)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(1)

    # Resolve values from flags / config / defaults
    resolved_workers = workers if workers is not None else config.tdd.max_workers
    resolved_prefix = prefix if prefix is not None else config.tdd.prefix
    prd_path = Path(prd_file)
    resolved_branch = branch if branch is not None else derive_branch_name(prd_path)
    phases_filter = _parse_phases(phases_str)

    pipeline_config = PrdPipelineConfig(
        prd_path=prd_path,
        project_root=project_root,
        db_path=config.resolve_db_path(project_root),
        prefix=resolved_prefix,
        branch_name=resolved_branch,
        base_branch=config.git.base_branch,
        workers=resolved_workers,
        max_invocations=max_invocations,
        create_pr=create_pr,
        pr_title=pr_title,
        dry_run=dry_run,
        clear_existing=clear,
        use_mock_llm=mock_llm,
        phases_filter=phases_filter,
        scaffolding_ref=scaffolding_ref,
        single_branch=True,
        enable_phase_gates=not no_phase_gates,
    )

    asyncio.run(_run_prd_async(pipeline_config))


async def _run_prd_async(config: PrdPipelineConfig) -> None:
    """Async wrapper for the pipeline with cleanup.

    Args:
        config: Pipeline configuration.
    """
    try:
        click.echo(f"PRD Pipeline: {config.prd_path.name}")
        click.echo(f"Project: {config.project_root}")
        click.echo(f"Branch: {config.branch_name}")
        if config.dry_run:
            click.echo("Mode: DRY RUN (decompose only)")
        click.echo()

        result = await run_prd_pipeline(config)
        _print_prd_results(result)

        if result.error_message:
            sys.exit(1)
        if result.pool_result and result.pool_result.tasks_failed > 0:
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Pipeline error: {exc}", err=True)
        sys.exit(1)
    finally:
        await reset_db()
        _cleanup_sdk()


def _print_prd_results(result: PrdPipelineResult) -> None:
    """Print pipeline results to console.

    Args:
        result: Pipeline execution results.
    """
    click.echo("\n" + "=" * 50)
    click.echo("PRD Pipeline Results")
    click.echo("=" * 50)

    # Decomposition
    status = "OK" if result.decomposition_exit_code == 0 else "FAILED"
    click.echo(f"Decomposition: {status}")
    if result.task_count > 0:
        click.echo(f"Tasks created: {result.task_count}")

    # Execution
    if result.pool_result is not None:
        click.echo("\nExecution:")
        click.echo(f"  Tasks completed: {result.pool_result.tasks_completed}")
        click.echo(f"  Tasks failed: {result.pool_result.tasks_failed}")
        click.echo(f"  Total invocations: {result.pool_result.total_invocations}")

        if result.pool_result.worker_stats:
            click.echo("\n  Worker Statistics:")
            for ws in result.pool_result.worker_stats:
                click.echo(
                    f"    Worker {ws.worker_id}: "
                    f"{ws.tasks_completed} completed, "
                    f"{ws.tasks_failed} failed, "
                    f"{ws.invocations} invocations"
                )

        if result.pool_result.stopped_reason:
            click.echo(f"\n  Stopped: {result.pool_result.stopped_reason}")

    # PR
    if result.pr_url:
        click.echo(f"\nPR created: {result.pr_url}")

    # Error
    if result.error_message:
        click.echo(f"\nError: {result.error_message}")

    click.echo(f"\nStage reached: {result.stage_reached}")


def _cleanup_sdk() -> None:
    """Best-effort SDK child process cleanup."""
    try:
        from .decomposition.llm_client import cleanup_sdk_child_processes

        cleanup_sdk_child_processes()
    except Exception:  # noqa: BLE001
        pass
