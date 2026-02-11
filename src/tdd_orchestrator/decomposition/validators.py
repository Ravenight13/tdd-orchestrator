"""Recursive validation loop for atomicity enforcement.

This module implements the recursive validation loop that ensures 100% atomicity
compliance by automatically re-decomposing oversized tasks using LLM calls.

Public API:
    - ValidationResult: Result of atomicity validation for a single task
    - AtomicityValidator: Validates task atomicity constraints
    - RecursiveValidationStats: Statistics from recursive validation
    - RecursiveValidator: Recursive task validation and re-decomposition engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import DecompositionConfig
from .llm_client import LLMClient, LLMResponseParseError, parse_json_response
from .prompts import format_re_decomposition_prompt

if TYPE_CHECKING:
    from .task_model import DecomposedTask

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of atomicity validation for a single task.

    Attributes:
        is_valid: Whether the task passes all atomicity constraints.
        violations: List of specific constraint violations found.
        task: The task that was validated.
    """

    is_valid: bool
    violations: list[str]
    task: DecomposedTask


@dataclass
class RecursiveValidationStats:
    """Statistics from recursive validation.

    Tracks metrics about the validation and re-decomposition process.

    Attributes:
        input_tasks: Number of tasks received for validation.
        output_tasks: Number of tasks after validation (may be more due to splits).
        passed_validation: Number of tasks that passed validation without splitting.
        split_count: Number of tasks that were split during validation.
        flagged_for_review: Number of tasks flagged for manual review (max depth).
        max_depth_reached: Maximum recursion depth reached during validation.
    """

    input_tasks: int = 0
    output_tasks: int = 0
    passed_validation: int = 0
    split_count: int = 0
    flagged_for_review: int = 0
    max_depth_reached: int = 0


class AtomicityValidator:
    """Validates task atomicity constraints.

    Checks tasks against configured atomicity rules:
    - Test count within min/max bounds (5-20)
    - Implementation lines under max (100)
    - Component count under max (3)
    - Acceptance criteria count within min/max bounds (2-5)

    Example:
        >>> validator = AtomicityValidator(config)
        >>> result = validator.validate(task)
        >>> if not result.is_valid:
        ...     print(f"Violations: {result.violations}")
    """

    def __init__(self, config: DecompositionConfig) -> None:
        """Initialize the validator with configuration.

        Args:
            config: DecompositionConfig with atomicity constraints.
        """
        self.config = config

    def validate(self, task: DecomposedTask) -> ValidationResult:
        """Validate a single task against atomicity constraints.

        Checks:
        - min_tests <= estimated_tests <= max_tests (5-20)
        - estimated_lines <= max_lines (100)
        - len(components) <= max_components (3)
        - min_criteria <= len(acceptance_criteria) <= max_criteria (2-5)

        Args:
            task: The DecomposedTask to validate.

        Returns:
            ValidationResult with is_valid flag and list of violations.
        """
        violations: list[str] = []

        # Check test count bounds
        if task.estimated_tests < self.config.min_tests:
            violations.append(
                f"Too few tests: {task.estimated_tests} < {self.config.min_tests} minimum"
            )
        if task.estimated_tests > self.config.max_tests:
            violations.append(
                f"Too many tests: {task.estimated_tests} > {self.config.max_tests} maximum"
            )

        # Check lines limit
        if task.estimated_lines > self.config.max_lines:
            violations.append(
                f"Too many lines: {task.estimated_lines} > {self.config.max_lines} maximum"
            )

        # Check component count
        if len(task.components) > self.config.max_components:
            violations.append(
                f"Too many components: {len(task.components)} > {self.config.max_components} maximum"
            )

        # Check acceptance criteria count
        ac_count = len(task.acceptance_criteria)
        if ac_count > 0:  # Only check if AC is populated
            if ac_count < self.config.min_criteria:
                violations.append(
                    f"Too few acceptance criteria: {ac_count} < {self.config.min_criteria} minimum"
                )
            if ac_count > self.config.max_criteria:
                violations.append(
                    f"Too many acceptance criteria: {ac_count} > {self.config.max_criteria} maximum"
                )

        is_valid = len(violations) == 0
        return ValidationResult(is_valid=is_valid, violations=violations, task=task)

    def validate_all(self, tasks: list[DecomposedTask]) -> list[ValidationResult]:
        """Validate all tasks, return results for each.

        Args:
            tasks: List of DecomposedTask objects to validate.

        Returns:
            List of ValidationResult objects, one per input task.
        """
        return [self.validate(task) for task in tasks]


class RecursiveValidator:
    """Recursive task validation and re-decomposition engine.

    When tasks fail atomicity validation, this validator automatically
    re-decomposes them into smaller subtasks using LLM calls, up to
    max_recursion_depth levels.

    Tasks that exceed max_recursion_depth are flagged for manual review
    rather than being split further.

    Example:
        >>> validator = RecursiveValidator(atomicity_validator, llm_client, config)
        >>> tasks, stats = await validator.validate_and_refine(tasks)
        >>> print(f"Split {stats.split_count} tasks, flagged {stats.flagged_for_review}")
    """

    def __init__(
        self,
        atomicity_validator: AtomicityValidator,
        llm_client: LLMClient,
        config: DecompositionConfig,
    ) -> None:
        """Initialize the recursive validator.

        Args:
            atomicity_validator: AtomicityValidator for checking constraints.
            llm_client: LLMClient for making re-decomposition calls.
            config: DecompositionConfig with recursion limits.
        """
        self.atomicity_validator = atomicity_validator
        self.llm_client = llm_client
        self.config = config
        self._subtask_counter: dict[str, int] = {}

    async def validate_and_refine(
        self,
        tasks: list[DecomposedTask],
        current_depth: int = 0,
    ) -> tuple[list[DecomposedTask], RecursiveValidationStats]:
        """Recursively validate and refine tasks.

        For each task:
        1. Validate against atomicity constraints
        2. If valid, add to output
        3. If invalid and depth < max, re-decompose via LLM and recurse
        4. If invalid and depth >= max, flag for review

        Args:
            tasks: Tasks to validate.
            current_depth: Current recursion level (internal use).

        Returns:
            Tuple of (validated_tasks, stats).
        """
        stats = RecursiveValidationStats(input_tasks=len(tasks))
        validated_tasks: list[DecomposedTask] = []

        for task in tasks:
            result = self.atomicity_validator.validate(task)

            if result.is_valid:
                # Task passes validation
                validated_tasks.append(task)
                stats.passed_validation += 1
                logger.debug(f"Task {task.task_key} passed validation")
            elif current_depth >= self.config.max_recursion_depth:
                # Max depth reached, flag for review
                validated_tasks.append(task)
                stats.flagged_for_review += 1
                stats.max_depth_reached = max(stats.max_depth_reached, current_depth)
                logger.warning(
                    f"Task {task.task_key} flagged for review (max depth {current_depth}): "
                    f"{result.violations}"
                )
            else:
                # Split the task
                logger.info(
                    f"Splitting task {task.task_key} at depth {current_depth}: {result.violations}"
                )
                subtasks = await self._split_task(task, result.violations)
                stats.split_count += 1

                # Recursively validate subtasks
                refined_subtasks, sub_stats = await self.validate_and_refine(
                    subtasks, current_depth + 1
                )

                # Merge stats
                validated_tasks.extend(refined_subtasks)
                stats.passed_validation += sub_stats.passed_validation
                stats.split_count += sub_stats.split_count
                stats.flagged_for_review += sub_stats.flagged_for_review
                stats.max_depth_reached = max(
                    stats.max_depth_reached, sub_stats.max_depth_reached, current_depth + 1
                )

        stats.output_tasks = len(validated_tasks)
        return validated_tasks, stats

    async def _split_task(
        self,
        task: DecomposedTask,
        violations: list[str],
    ) -> list[DecomposedTask]:
        """Split an oversized task into 2-3 subtasks using LLM.

        Args:
            task: The task that failed validation.
            violations: List of atomicity violations.

        Returns:
            List of 2-3 smaller subtasks.
        """
        # Import here to avoid circular imports
        from .task_model import DecomposedTask as TaskClass

        strategy = self._select_split_strategy(task, violations)

        prompt = format_re_decomposition_prompt(task, violations, strategy)

        try:
            response = await self.llm_client.send_message(prompt)
            subtask_data = parse_json_response(response)
        except LLMResponseParseError as e:
            logger.error(f"Failed to parse LLM response for split: {e}")
            # Return original task if split fails
            return [task]

        if not isinstance(subtask_data, list) or len(subtask_data) == 0:
            logger.warning(f"LLM returned invalid subtask data: {subtask_data}")
            return [task]

        # Create subtasks with proper lineage
        subtasks: list[DecomposedTask] = []
        parent_key = task.task_key or "UNKNOWN"

        for i, data in enumerate(subtask_data[:3]):  # Limit to 3 subtasks
            # Generate subtask key suffix
            suffix = self._get_subtask_suffix(parent_key)

            subtask = TaskClass(
                task_key=f"{parent_key}-{suffix}",
                title=data.get("title", f"Subtask {i + 1}"),
                goal=data.get("goal", ""),
                estimated_tests=data.get("estimated_tests", self.config.min_tests),
                estimated_lines=data.get("estimated_lines", 50),
                test_file=data.get("test_file", task.test_file),
                impl_file=data.get("impl_file", task.impl_file),
                components=data.get("components", task.components[:1]),
                acceptance_criteria=task.acceptance_criteria,  # Inherit from parent
                phase=task.phase,
                sequence=task.sequence,
                depends_on=task.depends_on.copy(),
                parent_task_key=parent_key,
                recursion_depth=task.recursion_depth + 1,
            )
            subtasks.append(subtask)

        logger.info(f"Split {parent_key} into {len(subtasks)} subtasks")
        return subtasks

    def _get_subtask_suffix(self, parent_key: str) -> str:
        """Get the next suffix letter for a subtask.

        Tracks how many subtasks have been created for each parent
        and returns the appropriate letter suffix (A, B, C, etc.).

        Args:
            parent_key: The parent task key.

        Returns:
            Suffix letter (A, B, C, etc.).
        """
        if parent_key not in self._subtask_counter:
            self._subtask_counter[parent_key] = 0

        count = self._subtask_counter[parent_key]
        self._subtask_counter[parent_key] += 1

        if count < 26:
            return chr(ord("A") + count)
        else:
            # For extreme cases, use double letters (AA, AB, etc.)
            return chr(ord("A") + (count // 26) - 1) + chr(ord("A") + (count % 26))

    def _select_split_strategy(
        self,
        task: DecomposedTask,
        violations: list[str],
    ) -> str:
        """Select split strategy based on violation type.

        Analyzes the violations to determine the best strategy for
        splitting the task.

        Strategies:
        - 'by_component': Split if too many components
        - 'by_tests': Split if too many tests
        - 'by_size': Split if too many lines
        - 'balanced': Default balanced split

        Args:
            task: The task that failed validation.
            violations: List of violation messages.

        Returns:
            Strategy name string.
        """
        violations_text = " ".join(violations).lower()

        if "too many components" in violations_text:
            return "by_component"
        elif "too many tests" in violations_text:
            return "by_tests"
        elif "too many lines" in violations_text:
            return "by_size"
        else:
            return "balanced"

    def reset_counters(self) -> None:
        """Reset subtask counters for fresh validation run."""
        self._subtask_counter.clear()
