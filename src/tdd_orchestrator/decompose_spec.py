"""CLI for app_spec decomposition.

Converts Product Requirements Documents (app_spec.txt) into TDD task
hierarchies using LLM-powered decomposition.

Usage:
    uv run python -m tdd_orchestrator.decompose_spec \
        --spec path/to/app_spec.txt \
        --prefix SF \
        --clear

Examples:
    # Decompose Salesforce integration spec
    uv run python -m tdd_orchestrator.decompose_spec \
        --spec .claude/docs/plans/salesforce-integration/app_spec.txt \
        --prefix SF \
        --clear

    # Dry-run (parse and decompose only, no DB load)
    uv run python -m tdd_orchestrator.decompose_spec \
        --spec .claude/docs/plans/salesforce-integration/app_spec.txt \
        --prefix SF \
        --dry-run

    # Use mock LLM for testing without real LLM calls
    uv run python -m tdd_orchestrator.decompose_spec \
        --spec path/to/app_spec.txt \
        --prefix TEST \
        --mock-llm \
        --dry-run

    # Production use (requires `claude login` for subscription auth)
    uv run python -m tdd_orchestrator.decompose_spec \
        --spec .claude/docs/plans/salesforce-integration/app_spec.txt \
        --prefix SF
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .decomposition import (
    AtomicityValidator,
    DecomposedTask,
    DecompositionConfig,
    LLMDecomposer,
    MockLLMClient,
    RecursiveValidator,
    SpecParser,
    TaskGenerator,
)
from .decomposition.spec_validator import SpecConformanceValidator
from .task_loader import (
    get_existing_prefixes,
    load_tdd_tasks,
    update_task_acceptance_criteria,
    update_task_depends_on,
    write_tasks_incremental,
)

if TYPE_CHECKING:
    from .decomposition import LLMClient

logger = logging.getLogger(__name__)


def _setup_mock_responses() -> dict[str, str]:
    """Set up mock LLM responses for testing.

    Returns:
        Dictionary mapping prompt substrings to mock responses.
    """
    # Mock Pass 1: Cycle extraction
    pass1_response = json.dumps(
        [
            {
                "cycle_number": 1,
                "phase": "Foundation",
                "cycle_title": "Core Setup",
                "components": ["Config", "Settings"],
                "expected_tests": "8-10",
                "module_hint": "src/core/",
            },
            {
                "cycle_number": 2,
                "phase": "Integration",
                "cycle_title": "API Integration",
                "components": ["APIClient"],
                "expected_tests": "10-15",
                "module_hint": "src/api/",
            },
        ]
    )

    # Mock Pass 2: Task breakdown
    pass2_response = json.dumps(
        [
            {
                "title": "Implement configuration loader",
                "goal": "Load and validate configuration files",
                "estimated_tests": 8,
                "estimated_lines": 50,
                "test_file": "tests/test_config.py",
                "impl_file": "src/config.py",
                "components": ["Config"],
            },
            {
                "title": "Add settings validation",
                "goal": "Validate settings against schema",
                "estimated_tests": 6,
                "estimated_lines": 40,
                "test_file": "tests/test_settings.py",
                "impl_file": "src/settings.py",
                "components": ["Settings"],
            },
        ]
    )

    # Mock Pass 3: Acceptance criteria
    pass3_response = json.dumps(
        [
            "Configuration file loads successfully from valid path",
            "Invalid configuration raises ConfigurationError",
            "Missing required fields are detected and reported",
        ]
    )

    return {
        "extract TDD cycles": pass1_response,
        "Break down this TDD cycle into": pass2_response,
        "acceptance criteria": pass3_response,
    }


def _create_llm_client(use_mock: bool) -> LLMClient:
    """Create the appropriate LLM client.

    Args:
        use_mock: If True, create a MockLLMClient with predefined responses.

    Returns:
        LLM client instance.

    Note:
        Production client uses Claude Agent SDK with subscription auth.
        Ensure you are logged in via `claude login` before using.
    """
    if use_mock:
        logger.info("Using mock LLM client")
        return MockLLMClient(responses=_setup_mock_responses())

    # For production use, use Claude Agent SDK with subscription auth
    from .decomposition import ClaudeAgentSDKClient

    logger.info("Using Claude Agent SDK client (subscription auth via `claude login`)")
    return ClaudeAgentSDKClient()


def _print_summary(
    spec_path: Path,
    prefix: str,
    tasks: list[DecomposedTask],
    metrics: object,
    validation_stats: object,
) -> None:
    """Print decomposition summary to stdout.

    Args:
        spec_path: Path to the input spec file.
        prefix: Task key prefix used.
        tasks: List of generated tasks.
        metrics: Decomposition metrics object.
        validation_stats: Recursive validation statistics.
    """
    print(f"\n{'=' * 60}")
    print("DECOMPOSITION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Input spec: {spec_path}")
    print(f"Prefix: {prefix}")
    print(f"Total tasks: {len(tasks)}")

    # Get unique phases
    phases = sorted(set(t.phase for t in tasks))
    print(f"Phases: {len(phases)} ({', '.join(str(p) for p in phases)})")
    print()

    # Show metrics
    total_llm_calls = getattr(metrics, "total_llm_calls", None)
    if total_llm_calls is not None:
        print(f"LLM calls: {total_llm_calls}")
    total_duration = getattr(metrics, "total_duration_seconds", None)
    if total_duration is not None:
        print(f"Duration: {total_duration:.1f}s")
    print()

    # Show validation stats
    split_count = getattr(validation_stats, "split_count", None)
    if split_count is not None:
        print(f"Tasks split during validation: {split_count}")
    flagged_for_review = getattr(validation_stats, "flagged_for_review", None)
    if flagged_for_review is not None:
        print(f"Tasks flagged for review: {flagged_for_review}")
    print()

    # Show first 10 tasks
    print("Tasks (first 10):")
    for task in tasks[:10]:
        print(f"  {task.task_key}: {task.title}")
        deps = ", ".join(task.depends_on) if task.depends_on else "(none)"
        print(f"    Tests: {task.estimated_tests}, Lines: {task.estimated_lines}")
        print(f"    Deps: {deps}")
    if len(tasks) > 10:
        print(f"  ... and {len(tasks) - 10} more")
    print()


def _parse_phases(phases_str: str | None) -> set[int] | None:
    """Parse comma-separated phase numbers.

    Args:
        phases_str: Comma-separated phase numbers (e.g., "15,16,17").

    Returns:
        Set of phase numbers, or None if input is None.
    """
    if phases_str is None:
        return None
    return {int(p.strip()) for p in phases_str.split(",")}


async def run_decomposition(
    spec_path: Path,
    prefix: str,
    *,
    clear_existing: bool = False,
    dry_run: bool = False,
    use_mock_llm: bool = False,
    verbose: bool = False,
    phases_filter: set[int] | None = None,
    scaffolding_ref: bool = False,
) -> int:
    """Run the full decomposition pipeline.

    Args:
        spec_path: Path to the app_spec.txt file.
        prefix: Task key prefix (e.g., SF for Salesforce).
        clear_existing: Clear existing tasks with same prefix before loading.
        dry_run: Parse and decompose only, don't load to database.
        use_mock_llm: Use mock LLM client for testing.
        verbose: Enable verbose logging.
        phases_filter: Set of phase numbers to decompose. If None, decompose all.
        scaffolding_ref: Enable MODULE API SPECIFICATION reference in prompts.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Step 1: Parse spec
    logger.info("Parsing app_spec: %s", spec_path)
    spec_parser = SpecParser()
    parsed_spec = spec_parser.parse(spec_path)
    logger.info(
        "Parsed: %d FR, %d NFR, %d AC, %d TDD cycles",
        len(parsed_spec.functional_requirements),
        len(parsed_spec.non_functional_requirements),
        len(parsed_spec.acceptance_criteria),
        len(parsed_spec.tdd_cycles),
    )

    # Filter cycles by phase if phases_filter provided
    if phases_filter:
        original_count = len(parsed_spec.tdd_cycles)
        parsed_spec.tdd_cycles = [
            c for c in parsed_spec.tdd_cycles if c.get("cycle_number", 0) in phases_filter
        ]
        logger.info(
            "Filtered to phases %s: %d cycles (from %d)",
            sorted(phases_filter),
            len(parsed_spec.tdd_cycles),
            original_count,
        )
        if not parsed_spec.tdd_cycles:
            logger.error(
                "No TDD cycles match phases %s. Available cycles: %s",
                sorted(phases_filter),
                [c.get("cycle_number", 0) for c in spec_parser.parse(spec_path).tdd_cycles],
            )
            return 1

    # Check for existing prefixes and warn about conflicts
    existing_prefixes = await get_existing_prefixes()
    if existing_prefixes:
        logger.info("Existing task prefixes in database: %s", ", ".join(existing_prefixes))
        if prefix in existing_prefixes and not clear_existing:
            logger.warning(
                "Prefix '%s' already exists! New tasks will be added (duplicates skipped). "
                "Use --clear to replace existing %s-* tasks, or choose a different prefix.",
                prefix,
                prefix,
            )

    # Clear existing tasks if requested (before decomposition for resilient writes)
    if clear_existing and not dry_run:
        from .database import get_db

        db = await get_db()
        if phases_filter:
            # Clear only specified phases
            phase_placeholders = ",".join("?" for _ in phases_filter)
            sorted_phases = tuple(sorted(phases_filter))

            # First clear attempts for tasks in those phases
            await db.execute_update(
                f"""DELETE FROM attempts WHERE task_id IN (
                    SELECT id FROM tasks WHERE phase IN ({phase_placeholders})
                )""",
                sorted_phases,
            )
            # Then clear the tasks themselves
            deleted = await db.execute_update(
                f"DELETE FROM tasks WHERE phase IN ({phase_placeholders})",
                sorted_phases,
            )
            logger.info("Cleared %d tasks from phases %s", deleted, list(sorted_phases))
        else:
            # Original behavior: clear by prefix
            from .task_loader import _clear_all_tasks

            deleted = await _clear_all_tasks(db, prefix=prefix)
            logger.info(
                "Cleared %d existing tasks with prefix '%s' before decomposition",
                deleted,
                prefix,
            )

    # Step 2: Setup LLM client
    llm_client = _create_llm_client(use_mock_llm)

    # Step 3: Define incremental write callbacks for resilience
    incremental_tasks_written = 0
    incremental_ac_updated = 0

    async def on_cycle_complete(tasks: list[DecomposedTask], cycle_number: int) -> None:
        """Write tasks to DB after each cycle completes (resilient writes)."""
        nonlocal incremental_tasks_written
        if dry_run:
            logger.debug(f"Dry-run: would write {len(tasks)} tasks from cycle {cycle_number}")
            return

        task_dicts = [t.to_dict() for t in tasks]
        written = await write_tasks_incremental(task_dicts, cycle_number)
        incremental_tasks_written += written

    async def on_ac_complete(task_key: str, acceptance_criteria: list[str]) -> None:
        """Update task AC in DB after each task's criteria is generated."""
        nonlocal incremental_ac_updated
        if dry_run:
            logger.debug(f"Dry-run: would update AC for {task_key}")
            return

        updated = await update_task_acceptance_criteria(task_key, acceptance_criteria)
        if updated:
            incremental_ac_updated += 1
            logger.info(
                f"AC updated for {task_key} ({incremental_ac_updated}/{incremental_tasks_written})"
            )

    # Step 4: Decompose with LLM (with incremental writes)
    config = DecompositionConfig(enable_scaffolding_reference=scaffolding_ref)
    decomposer = LLMDecomposer(
        client=llm_client,
        config=config,
        on_cycle_complete=on_cycle_complete,
        on_ac_complete=on_ac_complete,
        prefix=prefix,  # Generate proper SF-TDD-XX-XX keys from the start
    )

    logger.info("Decomposing with LLM (3 passes, incremental writes enabled)...")
    tasks = await decomposer.decompose(parsed_spec)
    metrics = decomposer.get_metrics()
    logger.info(
        "Generated %d tasks (LLM calls: %d, duration: %.1fs, "
        "incremental writes: %d tasks, %d AC updates)",
        len(tasks),
        metrics.total_llm_calls,
        metrics.total_duration_seconds,
        incremental_tasks_written,
        incremental_ac_updated,
    )

    # Step 4: Validate and refine (recursive)
    atomicity_validator = AtomicityValidator(config)
    recursive_validator = RecursiveValidator(
        atomicity_validator=atomicity_validator,
        llm_client=llm_client,
        config=config,
    )

    logger.info("Running recursive validation...")
    validated_tasks, validation_stats = await recursive_validator.validate_and_refine(tasks)
    logger.info(
        "Validation complete: %d tasks (splits: %d, flagged: %d)",
        validation_stats.output_tasks,
        validation_stats.split_count,
        validation_stats.flagged_for_review,
    )

    # Step 5: Calculate dependencies (keys already assigned during decomposition)
    logger.info("Calculating task dependencies...")
    generator = TaskGenerator(prefix=prefix)
    # Only calculate dependencies, don't reassign keys (they're already correct)
    final_tasks = generator._calculate_dependencies(validated_tasks)

    # Post-dependency: Detect impl_file + module_exports overlaps (deterministic)
    from .decomposition.overlap_detector import detect_overlaps

    final_tasks = detect_overlaps(final_tasks)
    overlap_count = sum(1 for t in final_tasks if t.task_type == "verify-only")
    if overlap_count:
        logger.info("Overlap detection: %d tasks marked as verify-only", overlap_count)

    # Step 5.5: Validate against spec
    if parsed_spec.module_structure.get("files") or parsed_spec.module_api:
        validator = SpecConformanceValidator()
        violations = validator.validate(
            final_tasks, parsed_spec.module_structure, parsed_spec.module_api
        )
        for v in violations:
            logger.warning(
                "Spec violation: %s %s: expected=%s actual=%s",
                v.task_key, v.field, v.expected, v.actual,
            )
        error_count = sum(1 for v in violations if v.severity == "error")
        if error_count:
            print(f"\nWARNING: {error_count} spec conformance violations found.")
            print("Tasks may have incorrect file paths. Review the warnings above.")

    # Print summary
    _print_summary(spec_path, prefix, final_tasks, metrics, validation_stats)

    if dry_run:
        logger.info("Dry-run mode: skipping database load")
        print("DRY-RUN: No database operations performed")
        return 0

    # Step 6: Update acceptance criteria for incrementally written tasks
    # and load any new tasks from validation/splitting
    logger.info("Updating acceptance criteria and loading final tasks...")

    ac_updated = 0
    deps_updated = 0
    new_tasks_loaded = 0

    for task in final_tasks:
        # Try to update AC for existing task (from incremental writes)
        if task.acceptance_criteria:
            updated = await update_task_acceptance_criteria(task.task_key, task.acceptance_criteria)
            if updated:
                ac_updated += 1
                # Also persist depends_on (calculated in Step 5)
                if task.depends_on:
                    await update_task_depends_on(task.task_key, task.depends_on)
                    deps_updated += 1
                continue

        # Task doesn't exist yet (from validation splits) - create it
        task_dict = {
            "task_key": task.task_key,
            "title": task.title,
            "goal": task.goal,
            "acceptance_criteria": task.acceptance_criteria,
            "test_file": task.test_file,
            "impl_file": task.impl_file,
            "verify_command": task.verify_command,
            "done_criteria": task.done_criteria,
            "depends_on": task.depends_on,
            "phase": task.phase,
            "sequence": task.sequence,
        }

        load_result = await load_tdd_tasks(
            [task_dict],
            clear_existing=False,  # Already cleared at start if requested
            skip_duplicates=True,
        )
        new_tasks_loaded += load_result["loaded"]

    print("\nDatabase operations complete:")
    print(f"  Incremental writes (Pass 2): {incremental_tasks_written}")
    print(f"  Incremental AC updates (Pass 3): {incremental_ac_updated}")
    print(f"  Batch AC updates (catch-up): {ac_updated}")
    print(f"  Dependencies updated: {deps_updated}")
    print(f"  New tasks (from validation): {new_tasks_loaded}")
    print(f"  Total final tasks: {len(final_tasks)}")

    return 0


async def main() -> int:
    """Main entry point for CLI.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Decompose app_spec into TDD tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="Path to app_spec.txt file",
    )
    parser.add_argument(
        "--prefix",
        required=True,
        help="Task key prefix (e.g., SF for Salesforce)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing tasks with SAME PREFIX before loading (e.g., --prefix HTMX --clear only deletes HTMX-* tasks)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and decompose only, don't load to database",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM client (for testing without API)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--phases",
        type=str,
        default=None,
        help="Comma-separated phase numbers to decompose (e.g., '15,16,17'). If omitted, all phases.",
    )
    parser.add_argument(
        "--scaffolding-ref",
        action="store_true",
        help="Enable MODULE API SPECIFICATION reference in decomposition prompts",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Validate spec file exists
    if not args.spec.exists():
        logger.error("Spec file not found: %s", args.spec)
        return 1

    try:
        return await run_decomposition(
            spec_path=args.spec,
            prefix=args.prefix,
            clear_existing=args.clear,
            dry_run=args.dry_run,
            use_mock_llm=args.mock_llm,
            verbose=args.verbose,
            phases_filter=_parse_phases(args.phases),
            scaffolding_ref=args.scaffolding_ref,
        )

    except Exception as e:
        logger.exception("Decomposition failed: %s", e)
        return 1


async def _run_with_cleanup() -> int:
    """Run main and cleanup resources on exit.

    The Claude Agent SDK spawns background tasks and OS subprocesses that survive
    generator cleanup. This wrapper ensures:
    1. All pending asyncio tasks are cancelled
    2. Any lingering Claude CLI child processes are terminated

    IMPORTANT: Cleanup happens ONCE at CLI exit, not per-SDK-call.
    Per-call cleanup would kill parallel SDK queries prematurely.

    Returns:
        Exit code from main().
    """
    try:
        return await main()
    finally:
        # Cancel all pending asyncio tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Kill any lingering SDK child processes (call ONCE at exit)
        from .decomposition.llm_client import cleanup_sdk_child_processes

        cleanup_sdk_child_processes()

        # Force immediate exit to avoid asyncio/anyio cleanup deadlocks
        # The SDK uses anyio task groups that deadlock during normal shutdown
        import os

        os._exit(0)


def cli_main() -> None:
    """Entry point for CLI invocation.

    Uses _run_with_cleanup() which handles asyncio task cancellation,
    SDK child process cleanup, and os._exit() to prevent hanging.
    """
    sys.exit(asyncio.run(_run_with_cleanup()))


if __name__ == "__main__":
    cli_main()
