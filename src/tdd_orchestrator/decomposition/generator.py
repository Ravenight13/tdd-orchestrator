"""Task Generator for assigning keys and calculating dependencies.

This module implements the TaskGenerator class which assigns task keys,
calculates dependencies based on phase ordering, and provides utility
functions for file path generation.

Public API:
    - TaskGenerator: Generate task keys and dependencies for decomposed tasks
    - camel_to_snake: Convert PascalCase/camelCase to snake_case
    - generate_file_paths: Generate test and implementation file paths
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task_model import DecomposedTask


def camel_to_snake(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case.

    Handles consecutive uppercase letters (acronyms) properly by treating
    them as a single unit until the last uppercase letter before a lowercase.

    Args:
        name: A string in PascalCase or camelCase format.

    Returns:
        The string converted to snake_case.

    Examples:
        >>> camel_to_snake("SalesforceSettings")
        'salesforce_settings'
        >>> camel_to_snake("JWTBearer")
        'jwt_bearer'
        >>> camel_to_snake("APIClient")
        'api_client'
        >>> camel_to_snake("OAuth2Handler")
        'oauth2_handler'
        >>> camel_to_snake("simple")
        'simple'
        >>> camel_to_snake("ABC")
        'abc'
    """
    if not name:
        return ""

    # Step 1: Handle transitions from uppercase sequence (2+ chars) to lowercase
    # e.g., "APIClient" -> "API_Client", "JWTBearer" -> "JWT_Bearer"
    # The pattern [A-Z]{2,} matches 2+ uppercase, then split before final uppercase + lowercase
    result = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1_\2", name)

    # Step 2: Handle transitions from lowercase/digit to uppercase
    # e.g., "salesforceSettings" -> "salesforce_Settings", "OAuth2Handler" -> "OAuth2_Handler"
    result = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", result)

    return result.lower()


def generate_file_paths(
    component: str,
    module_base: str,
    test_base: str = "tests/unit",
) -> tuple[str, str]:
    """Generate test_file and impl_file paths from component name.

    Creates standardized file paths for test and implementation files
    based on the component name and module base path.

    Args:
        component: Primary component name (e.g., "SalesforceSettings").
        module_base: Base path for implementation (e.g., "src/integrations/salesforce").
        test_base: Base path for tests (default: "tests/unit").

    Returns:
        A tuple of (test_file, impl_file) paths.

    Examples:
        >>> generate_file_paths("SalesforceSettings", "src/integrations/salesforce")
        ('tests/unit/salesforce/test_salesforce_settings.py',
         'src/integrations/salesforce/salesforce_settings.py')

        >>> generate_file_paths("JWTBearer", "src/auth")
        ('tests/unit/auth/test_jwt_bearer.py',
         'src/auth/jwt_bearer.py')
    """
    # Convert component name to snake_case for file naming
    snake_name = camel_to_snake(component)

    # Normalize module_base by stripping trailing slashes
    module_base = module_base.rstrip("/")

    # Extract the last directory from module_base for test organization
    # e.g., "src/integrations/salesforce" -> "salesforce"
    module_parts = module_base.split("/")
    module_name = module_parts[-1] if module_parts else "unknown"

    # Build file paths
    test_file = f"{test_base}/{module_name}/test_{snake_name}.py"
    impl_file = f"{module_base}/{snake_name}.py"

    return test_file, impl_file


class TaskGenerator:
    """Generate task keys and dependencies for decomposed tasks.

    Assigns unique task keys in the format {PREFIX}-TDD-{PHASE:02d}-{SEQ:02d}
    and calculates dependencies based on phase ordering.

    Attributes:
        prefix: Task key prefix (e.g., "SF" for Salesforce).

    Example:
        >>> generator = TaskGenerator(prefix="SF")
        >>> tasks = generator.generate(decomposed_tasks)
        >>> # Tasks now have task_key and depends_on populated
    """

    def __init__(self, prefix: str = "TASK") -> None:
        """Initialize the generator with a task key prefix.

        Args:
            prefix: Prefix for task keys (e.g., "SF" for Salesforce).
                   Defaults to "TASK".
        """
        self.prefix = prefix

    def generate(self, tasks: list[DecomposedTask]) -> list[DecomposedTask]:
        """Assign task_keys and calculate depends_on for all tasks.

        This is the main entry point. It sorts tasks by phase and sequence,
        assigns unique task keys, and calculates dependencies based on
        phase ordering rules.

        Args:
            tasks: List of DecomposedTask objects from LLMDecomposer.

        Returns:
            New list of tasks with task_key and depends_on populated.
            Original tasks are not modified.
        """
        if not tasks:
            return []

        # Sort tasks by (phase, sequence) for consistent ordering
        sorted_tasks = sorted(tasks, key=lambda t: (t.phase, t.sequence))

        # Assign task keys first
        keyed_tasks = self._assign_task_keys(sorted_tasks)

        # Then calculate dependencies
        return self._calculate_dependencies(keyed_tasks)

    def _assign_task_keys(self, tasks: list[DecomposedTask]) -> list[DecomposedTask]:
        """Assign unique task_keys to all tasks.

        Key format: {PREFIX}-TDD-{PHASE:02d}-{SEQ:02d}
        Split tasks: {PREFIX}-TDD-{PHASE:02d}-{SEQ:02d}-{A|B|C}

        Args:
            tasks: List of sorted tasks.

        Returns:
            New list with task_key populated.
        """
        result: list[DecomposedTask] = []

        for task in tasks:
            # Generate base task key
            base_key = f"{self.prefix}-TDD-{task.phase:02d}-{task.sequence:02d}"

            # Handle split tasks (from recursive validation)
            # Split tasks have a parent_task_key set
            if task.parent_task_key:
                # Extract suffix letter based on recursion depth
                suffix = self._get_split_suffix(task, result)
                task_key = f"{base_key}-{suffix}"
            else:
                task_key = base_key

            # Create new task with key assigned (immutable update)
            result.append(replace(task, task_key=task_key))

        return result

    def _get_split_suffix(self, task: DecomposedTask, existing_tasks: list[DecomposedTask]) -> str:
        """Get the suffix letter for a split task.

        Counts existing tasks with the same parent and phase/sequence
        to determine the next suffix letter (A, B, C, etc.).

        Args:
            task: The task needing a suffix.
            existing_tasks: Tasks already processed (with keys assigned).

        Returns:
            Suffix letter (A, B, C, etc.) or compound suffix (A-A, A-B).
        """
        # Count siblings (same parent and phase/sequence)
        sibling_count = sum(
            1
            for t in existing_tasks
            if t.parent_task_key == task.parent_task_key
            and t.phase == task.phase
            and t.sequence == task.sequence
        )

        # Generate suffix: A=0, B=1, C=2, etc.
        if sibling_count < 26:
            return chr(ord("A") + sibling_count)
        else:
            # For extreme cases, use double letters
            return chr(ord("A") + (sibling_count // 26) - 1) + chr(ord("A") + (sibling_count % 26))

    def _calculate_dependencies(self, tasks: list[DecomposedTask]) -> list[DecomposedTask]:
        """Calculate depends_on based on phase ordering.

        Dependency Rules:
        1. Phase 0 tasks have no dependencies (depends_on = [])
        2. Phase N tasks depend on ALL tasks in Phase N-1
        3. Within a phase: no cross-dependencies (parallel execution)

        Args:
            tasks: List of tasks with task_keys assigned.

        Returns:
            New list with depends_on populated.
        """
        # Group tasks by phase for dependency calculation
        tasks_by_phase: dict[int, list[str]] = {}
        for task in tasks:
            phase = task.phase
            if phase not in tasks_by_phase:
                tasks_by_phase[phase] = []
            tasks_by_phase[phase].append(task.task_key)

        # Build result with dependencies
        result: list[DecomposedTask] = []

        for task in tasks:
            phase = task.phase

            if phase == 0:
                # Phase 0 tasks have no dependencies
                depends_on: list[str] = []
            else:
                # Phase N depends on ALL tasks in Phase N-1
                prev_phase = phase - 1
                depends_on = tasks_by_phase.get(prev_phase, []).copy()

            result.append(replace(task, depends_on=depends_on))

        return result

    def generate_with_file_paths(
        self,
        tasks: list[DecomposedTask],
        module_base: str,
        test_base: str = "tests/unit",
    ) -> list[DecomposedTask]:
        """Generate task keys, dependencies, and file paths in one pass.

        Convenience method that combines generate() with file path generation
        for tasks that don't already have test_file/impl_file set.

        Args:
            tasks: List of DecomposedTask objects.
            module_base: Base path for implementation files.
            test_base: Base path for test files.

        Returns:
            Tasks with task_key, depends_on, test_file, and impl_file populated.
        """
        # First assign keys and dependencies
        keyed_tasks = self.generate(tasks)

        # Then fill in missing file paths
        result: list[DecomposedTask] = []
        for task in keyed_tasks:
            if not task.test_file or not task.impl_file:
                # Use first component for file naming, or task title
                component = task.components[0] if task.components else task.title
                # Clean up component name (remove spaces, etc.)
                component = component.replace(" ", "")
                test_file, impl_file = generate_file_paths(component, module_base, test_base)
                result.append(
                    replace(
                        task,
                        test_file=task.test_file or test_file,
                        impl_file=task.impl_file or impl_file,
                    )
                )
            else:
                result.append(task)

        return result
