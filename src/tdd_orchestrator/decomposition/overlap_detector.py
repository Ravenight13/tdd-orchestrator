"""Overlap detector for decomposed tasks.

Detects tasks targeting the same impl_file with overlapping module_exports
and marks the dependent task as verify-only to prevent RED stage failures
when the implementation already exists from a prior task.

This module is deterministic (zero LLM cost) -- it enriches tasks post-
dependency-calculation via set intersection.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .decomposer import DecomposedTask

logger = logging.getLogger(__name__)


def _task_order_key(task: "DecomposedTask") -> tuple[int, int]:
    """Return (phase, sequence) for ordering comparison."""
    return (task.phase, task.sequence)


def _exports_overlap(a: list[str], b: list[str]) -> set[str]:
    """Return the intersection of two export lists."""
    return set(a) & set(b)


def detect_overlaps(tasks: list["DecomposedTask"]) -> list["DecomposedTask"]:
    """Detect impl_file + module_exports overlaps and mark dependents.

    For each group of tasks sharing the same impl_file, checks for
    overlapping module_exports. When overlap is found, the task that
    executes later (by phase, then sequence) is marked as verify-only
    because the earlier task will have already implemented the code.

    Tasks without impl_file or module_exports are passed through unchanged.

    Args:
        tasks: List of DecomposedTask objects with depends_on populated.

    Returns:
        New list with overlapping dependent tasks marked as verify-only.
    """
    # Group by impl_file (skip empty)
    by_impl: dict[str, list[int]] = defaultdict(list)
    for i, task in enumerate(tasks):
        if task.impl_file:
            by_impl[task.impl_file].append(i)

    # Track which task indices need to become verify-only
    verify_only_indices: set[int] = set()

    for impl_file, indices in by_impl.items():
        if len(indices) < 2:
            continue  # No overlap possible with a single task

        # Compare all pairs within the group
        for a_pos in range(len(indices)):
            for b_pos in range(a_pos + 1, len(indices)):
                a_idx = indices[a_pos]
                b_idx = indices[b_pos]
                task_a = tasks[a_idx]
                task_b = tasks[b_idx]

                # Skip if either has no module_exports
                if not task_a.module_exports or not task_b.module_exports:
                    continue

                overlap = _exports_overlap(task_a.module_exports, task_b.module_exports)
                if not overlap:
                    continue

                # Determine which task is "later" in execution order
                order_a = _task_order_key(task_a)
                order_b = _task_order_key(task_b)

                if order_a == order_b:
                    # Same phase AND sequence -- parallel conflict
                    logger.warning(
                        "Parallel overlap conflict: %s and %s share impl_file=%s "
                        "with overlapping exports %s (same phase=%d, seq=%d). "
                        "Manual review recommended.",
                        task_a.task_key,
                        task_b.task_key,
                        impl_file,
                        sorted(overlap),
                        task_a.phase,
                        task_a.sequence,
                    )
                    continue

                # Mark the later task as verify-only
                if order_a < order_b:
                    later_idx = b_idx
                    later_task = task_b
                    earlier_task = task_a
                else:
                    later_idx = a_idx
                    later_task = task_a
                    earlier_task = task_b

                logger.info(
                    "Overlap detected: %s (verify-only) depends on %s "
                    "via impl_file=%s, overlapping exports=%s",
                    later_task.task_key,
                    earlier_task.task_key,
                    impl_file,
                    sorted(overlap),
                )
                verify_only_indices.add(later_idx)

    # Build result list with verify-only tasks replaced
    result: list[DecomposedTask] = []
    for i, task in enumerate(tasks):
        if i in verify_only_indices and task.task_type != "verify-only":
            result.append(replace(task, task_type="verify-only"))
        else:
            result.append(task)

    if verify_only_indices:
        logger.info(
            "Overlap detection: %d tasks marked as verify-only",
            len(verify_only_indices),
        )

    return result
