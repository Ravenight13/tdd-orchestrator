"""Circular dependency detector for decomposed tasks.

Validates that the task dependency graph (depends_on -> task_key) contains
no cycles. Uses Kahn's algorithm (BFS topological sort) for detection and
DFS for cycle reporting.

This module is deterministic (zero LLM cost) -- it validates the dependency
graph post-calculation as a defensive check.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task_model import DecomposedTask

logger = logging.getLogger(__name__)


def validate_no_cycles(tasks: list["DecomposedTask"]) -> list[str]:
    """Validate that the task dependency graph has no circular dependencies.

    Uses Kahn's algorithm (BFS topological sort). If any nodes remain after
    processing all zero-in-degree nodes, cycles exist.

    Args:
        tasks: List of DecomposedTask objects with depends_on populated.

    Returns:
        List of error strings describing detected cycles. Empty if no cycles.
    """
    if not tasks:
        return []

    # Build lookup of valid task keys
    task_keys = {t.task_key for t in tasks}

    # Build adjacency list and in-degree map
    adj: dict[str, list[str]] = {t.task_key: [] for t in tasks}
    in_degree: dict[str, int] = {t.task_key: 0 for t in tasks}

    for task in tasks:
        for dep in task.depends_on:
            if dep not in task_keys:
                continue  # Skip external refs gracefully
            # Edge: dep -> task.task_key (dep must complete before task)
            adj[dep].append(task.task_key)
            in_degree[task.task_key] += 1

    # BFS: start with all zero-in-degree nodes
    queue: deque[str] = deque()
    for key, degree in in_degree.items():
        if degree == 0:
            queue.append(key)

    visited_count = 0
    while queue:
        node = queue.popleft()
        visited_count += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If all nodes visited, no cycles
    if visited_count == len(task_keys):
        return []

    # Nodes with remaining in-degree are in cycles
    remaining = {k for k, d in in_degree.items() if d > 0}
    return _find_cycle_members(adj, remaining)


def _find_cycle_members(
    adj: dict[str, list[str]], remaining: set[str]
) -> list[str]:
    """Trace cycles in the remaining nodes using DFS.

    Args:
        adj: Adjacency list for the full graph.
        remaining: Set of node keys known to be in cycles.

    Returns:
        List of formatted error strings, one per detected cycle.
    """
    errors: list[str] = []
    visited: set[str] = set()

    for start in sorted(remaining):
        if start in visited:
            continue

        # DFS to trace the cycle
        path: list[str] = []
        path_set: set[str] = set()
        node = start

        while node not in path_set:
            if node not in remaining:
                break
            path.append(node)
            path_set.add(node)
            # Follow any edge to another remaining node
            next_node = None
            for neighbor in adj[node]:
                if neighbor in remaining:
                    next_node = neighbor
                    break
            if next_node is None:
                break
            node = next_node

        if node in path_set:
            # Extract the cycle portion
            cycle_start = path.index(node)
            cycle = path[cycle_start:]
            cycle.append(node)  # Close the cycle
            visited.update(cycle[:-1])
            errors.append(" -> ".join(cycle))

    return errors
