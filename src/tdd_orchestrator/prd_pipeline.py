"""End-to-end PRD pipeline: ingest, decompose, TDD, open PR.

Orchestrates the full pipeline from PRD file to completed TDD execution
with optional GitHub PR creation. Chains existing components:
- GitCoordinator for branch creation
- run_decomposition() for PRD decomposition
- WorkerPool for parallel TDD execution
- gh CLI for PR creation
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .database import OrchestratorDB, get_db, reset_db
from .decompose_spec import run_decomposition
from .git_coordinator import GitCoordinator
from .project_config import setup_project_context
from .worker_pool import PoolResult, WorkerConfig, WorkerPool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrdPipelineConfig:
    """All inputs for a run-prd pipeline execution."""

    prd_path: Path
    project_root: Path
    db_path: Path
    prefix: str
    branch_name: str
    base_branch: str
    workers: int
    max_invocations: int
    create_pr: bool
    pr_title: str | None = None
    dry_run: bool = False
    clear_existing: bool = False
    use_mock_llm: bool = False
    phases_filter: set[int] | None = None
    scaffolding_ref: bool = False
    single_branch: bool = True
    enable_phase_gates: bool = True


@dataclass
class PrdPipelineResult:
    """Outcome of a run-prd pipeline execution."""

    decomposition_exit_code: int = 1
    task_count: int = 0
    pool_result: PoolResult | None = None
    pr_url: str | None = None
    stage_reached: str = "init"
    error_message: str | None = None


def sanitize_branch_name(name: str) -> str:
    """Sanitize a string for use as a git branch name.

    - Lowercases input
    - Replaces non-alphanumeric chars (except / and -) with hyphens
    - Collapses consecutive hyphens
    - Strips leading/trailing hyphens per segment (split on /)

    Args:
        name: Raw branch name candidate.

    Returns:
        Sanitized branch name safe for git.
    """
    result = name.lower()
    # Replace anything that isn't alphanumeric, /, or - with a hyphen
    result = re.sub(r"[^a-z0-9/\-]", "-", result)
    # Collapse consecutive hyphens
    result = re.sub(r"-{2,}", "-", result)
    # Strip leading/trailing hyphens per segment
    segments = result.split("/")
    segments = [seg.strip("-") for seg in segments]
    # Remove empty segments
    segments = [seg for seg in segments if seg]
    return "/".join(segments)


def derive_branch_name(prd_path: Path) -> str:
    """Derive a feature branch name from a PRD file path.

    Strips common extensions (.md, .txt) and prefixes with feat/.

    Args:
        prd_path: Path to the PRD file.

    Returns:
        Branch name like "feat/user-auth".
    """
    stem = prd_path.stem
    return f"feat/{sanitize_branch_name(stem)}"


async def _check_gh_available() -> bool:
    """Check if the GitHub CLI (gh) is available.

    Returns:
        True if gh is installed and runnable.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh", "--version",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except FileNotFoundError:
        return False
    except OSError:
        return False


async def _create_pull_request(
    base_dir: Path,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> tuple[bool, str | None]:
    """Create a GitHub PR using the gh CLI.

    Uses list-form subprocess args (no shell=True) for safety.

    Args:
        base_dir: Repository root directory.
        branch: Head branch name.
        base_branch: Base branch for the PR.
        title: PR title.
        body: PR body (markdown).

    Returns:
        (success, pr_url) tuple. pr_url is None on failure.
    """
    cmd = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base_branch,
        "--head", branch,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            pr_url = stdout.decode().strip()
            return True, pr_url
        logger.error("gh pr create failed: %s", stderr.decode())
        return False, None
    except FileNotFoundError:
        logger.error("gh CLI not found")
        return False, None
    except OSError as exc:
        logger.error("Failed to run gh: %s", exc)
        return False, None


def _generate_pr_body(
    prd_path: Path,
    task_count: int,
    pool_result: PoolResult,
) -> str:
    """Generate markdown PR body with pipeline results.

    Args:
        prd_path: Path to the PRD file.
        task_count: Number of tasks decomposed.
        pool_result: Worker pool execution results.

    Returns:
        Markdown string for PR body.
    """
    lines = [
        "## Summary",
        "",
        f"Automated TDD pipeline from PRD: `{prd_path.name}`",
        "",
        "## Pipeline Results",
        "",
        f"- **Tasks decomposed**: {task_count}",
        f"- **Tasks completed**: {pool_result.tasks_completed}",
        f"- **Tasks failed**: {pool_result.tasks_failed}",
        f"- **Total invocations**: {pool_result.total_invocations}",
        "",
    ]

    if pool_result.worker_stats:
        lines.append("## Worker Statistics")
        lines.append("")
        for ws in pool_result.worker_stats:
            lines.append(
                f"- Worker {ws.worker_id}: "
                f"{ws.tasks_completed} completed, "
                f"{ws.tasks_failed} failed, "
                f"{ws.invocations} invocations"
            )
        lines.append("")

    if pool_result.stopped_reason:
        lines.append(f"**Stopped**: {pool_result.stopped_reason}")
        lines.append("")

    lines.append("---")
    lines.append("Generated by TDD Orchestrator `run-prd` pipeline")
    return "\n".join(lines)


async def run_prd_pipeline(config: PrdPipelineConfig) -> PrdPipelineResult:
    """Run the full PRD-to-TDD pipeline.

    Stages:
    1. Create feature branch (skip in dry-run)
    2. Decompose PRD into tasks
    3. Execute TDD via WorkerPool (skip in dry-run)
    4. Create GitHub PR (optional, on success)

    Args:
        config: Pipeline configuration.

    Returns:
        PrdPipelineResult with stage outcomes.
    """
    result = PrdPipelineResult()
    git = GitCoordinator(config.project_root)
    explicit_db: OrchestratorDB | None = None

    try:
        # Early check: gh available if --create-pr
        if config.create_pr and not config.dry_run:
            if not await _check_gh_available():
                result.error_message = (
                    "GitHub CLI (gh) not found. Install it or remove --create-pr."
                )
                return result

        # Stage 1: Create feature branch
        if not config.dry_run:
            result.stage_reached = "branch"
            await git.create_feature_branch(
                branch_name=config.branch_name,
                base_branch=config.base_branch,
                use_local=True,
            )
            logger.info("Created feature branch: %s", config.branch_name)

        # Stage 2: Decompose PRD
        result.stage_reached = "decompose"
        await setup_project_context(config.project_root)

        exit_code = await run_decomposition(
            spec_path=config.prd_path,
            prefix=config.prefix,
            clear_existing=config.clear_existing,
            dry_run=config.dry_run,
            use_mock_llm=config.use_mock_llm,
            phases_filter=config.phases_filter,
            scaffolding_ref=config.scaffolding_ref,
        )
        result.decomposition_exit_code = exit_code

        if exit_code != 0:
            result.error_message = "Decomposition failed"
            return result

        # Get task count from singleton before resetting
        db = await get_db()
        rows = await db.execute_query(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status = ?", ("pending",)
        )
        result.task_count = int(rows[0]["cnt"]) if rows else 0

        # Reset singleton before explicit DB
        await reset_db()
        _cleanup_sdk_processes()

        if config.dry_run:
            result.stage_reached = "done"
            return result

        # Stage 3: Execute TDD via WorkerPool
        result.stage_reached = "execute"
        explicit_db = OrchestratorDB(config.db_path)
        await explicit_db.connect()

        worker_config = WorkerConfig(
            max_workers=config.workers,
            max_invocations_per_session=config.max_invocations,
            budget_warning_threshold=int(config.max_invocations * 0.8),
            use_local_branches=True,
            single_branch_mode=config.single_branch,
            git_stash_enabled=False,
            enable_phase_gates=config.enable_phase_gates,
        )

        pool = WorkerPool(
            db=explicit_db,
            base_dir=config.project_root,
            config=worker_config,
        )
        result.pool_result = await pool.run_all_phases()
        await explicit_db.close()
        explicit_db = None

        # Stage 4: Create PR (optional, on success)
        if config.create_pr and result.pool_result is not None:
            if result.pool_result.tasks_failed == 0:
                result.stage_reached = "pr"
                pr_title = config.pr_title or f"feat: {config.prd_path.stem}"
                pr_body = _generate_pr_body(
                    config.prd_path, result.task_count, result.pool_result,
                )

                # Push branch first
                await git.push_branch(config.branch_name)

                success, pr_url = await _create_pull_request(
                    base_dir=config.project_root,
                    branch=config.branch_name,
                    base_branch=config.base_branch,
                    title=pr_title,
                    body=pr_body,
                )
                if success:
                    result.pr_url = pr_url
            else:
                logger.warning(
                    "Skipping PR creation: %d tasks failed",
                    result.pool_result.tasks_failed,
                )

        result.stage_reached = "done"
        return result

    except subprocess.CalledProcessError as exc:
        result.error_message = f"Git operation failed: {exc.stderr or exc}"
        logger.error("Pipeline failed at stage %s: %s", result.stage_reached, exc)
        return result
    except Exception as exc:
        result.error_message = str(exc)
        logger.error("Pipeline failed at stage %s: %s", result.stage_reached, exc)
        return result
    finally:
        # Cleanup explicit DB if still open
        if explicit_db is not None:
            try:
                await explicit_db.close()
            except Exception:  # noqa: BLE001
                pass
        # Cleanup singleton if still active
        try:
            await reset_db()
        except Exception:  # noqa: BLE001
            pass
        _cleanup_sdk_processes()


def _cleanup_sdk_processes() -> None:
    """Best-effort SDK child process cleanup."""
    try:
        from .decomposition.llm_client import cleanup_sdk_child_processes

        cleanup_sdk_child_processes()
    except Exception:  # noqa: BLE001
        pass
