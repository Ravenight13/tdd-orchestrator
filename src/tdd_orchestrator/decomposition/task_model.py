"""Data model for decomposed TDD tasks.

This module contains the DecomposedTask dataclass and related types that are
used across the decomposition pipeline. Extracted from decomposer.py to
separate data models from orchestration logic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .exceptions import DecompositionError


class LLMDecompositionError(DecompositionError):
    """Raised when LLM decomposition fails."""

    pass


# Callback type for incremental task writes after each cycle completes
OnCycleCompleteCallback = Callable[[list["DecomposedTask"], int], Awaitable[None]]

# Callback type for incremental AC writes after each task's AC is generated
OnACCompleteCallback = Callable[[str, list[str]], Awaitable[None]]


@dataclass
class DecomposedTask:
    """A fully decomposed task ready for TDD execution.

    Represents an atomic unit of work that can be completed in a single
    RED-GREEN-REFACTOR TDD cycle.

    Attributes:
        task_key: Unique identifier for the task (e.g., "TASK-001").
        title: Clear action-oriented title.
        goal: One sentence describing what this task accomplishes.
        estimated_tests: Expected number of tests (5-20).
        estimated_lines: Expected lines of implementation (<100).
        test_file: Relative path for the test file.
        impl_file: Relative path for the implementation file.
        components: List of component names (max 3).
        acceptance_criteria: List of testable acceptance criteria.
        phase: Phase number (from Pass 1 cycle extraction).
        sequence: Sequence number within the phase.
        depends_on: List of task keys this task depends on.
        parent_task_key: Parent task key if this is a subtask.
        recursion_depth: Depth of decomposition (0 = top-level).
        error_codes: List of expected error codes this task should handle.
        blocking_assumption: Assumption that blocks implementation if unresolved.
        verify_command: Shell command to verify task completion.
        done_criteria: Human-readable success criteria.
    """

    task_key: str
    title: str
    goal: str
    estimated_tests: int
    estimated_lines: int
    test_file: str
    impl_file: str
    components: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    phase: int = 0
    sequence: int = 0
    depends_on: list[str] = field(default_factory=list)
    parent_task_key: str | None = None
    recursion_depth: int = 0
    error_codes: list[str] = field(default_factory=list)
    blocking_assumption: str | None = None
    verify_command: str = ""
    done_criteria: str = ""
    complexity: str = "medium"  # "low" | "medium" | "high"
    implementation_hints: str = ""  # Markdown hints from Pass 4
    module_exports: list[str] = field(default_factory=list)  # PLAN9: Export names for this module
    import_pattern: str = "direct"  # PLAN9: How to import (direct, namespace, factory)
    task_type: str = "implement"  # "implement" | "verify-only"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary containing all task fields.
        """
        return {
            "task_key": self.task_key,
            "title": self.title,
            "goal": self.goal,
            "estimated_tests": self.estimated_tests,
            "estimated_lines": self.estimated_lines,
            "test_file": self.test_file,
            "impl_file": self.impl_file,
            "components": self.components,
            "acceptance_criteria": self.acceptance_criteria,
            "phase": self.phase,
            "sequence": self.sequence,
            "depends_on": self.depends_on,
            "parent_task_key": self.parent_task_key,
            "recursion_depth": self.recursion_depth,
            "error_codes": self.error_codes,
            "blocking_assumption": self.blocking_assumption,
            "verify_command": self.verify_command,
            "done_criteria": self.done_criteria,
            "complexity": self.complexity,
            "implementation_hints": self.implementation_hints,
            "module_exports": self.module_exports,
            "import_pattern": self.import_pattern,
            "task_type": self.task_type,
        }
