"""LLM Decomposer for four-pass spec decomposition.

This module implements the LLMDecomposer class which transforms a ParsedSpec
into a list of DecomposedTask objects through four LLM passes:
- Pass 1: Extract TDD cycles from the PRD
- Pass 2: Break each cycle into atomic tasks (parallel)
- Pass 3: Generate acceptance criteria for each task (parallel)
- Pass 4: Generate implementation hints for medium/high complexity tasks (parallel)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .config import DecompositionConfig, DecompositionMetrics
from .exceptions import DecompositionError
from .llm_client import LLMClient, LLMClientError, LLMResponseParseError, parse_json_response
from .prompts import (
    format_ac_generation_prompt,
    format_implementation_hints_prompt,
    format_phase_extraction_prompt,
    format_task_breakdown_prompt,
)
from ..complexity_detector import ComplexityResult, detect_complexity

if TYPE_CHECKING:
    from .parser import ParsedSpec

# Callback type for incremental task writes after each cycle completes
OnCycleCompleteCallback = Callable[[list["DecomposedTask"], int], Awaitable[None]]

# Callback type for incremental AC writes after each task's AC is generated
OnACCompleteCallback = Callable[[str, list[str]], Awaitable[None]]

logger = logging.getLogger(__name__)


class LLMDecompositionError(DecompositionError):
    """Raised when LLM decomposition fails."""

    pass


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
        }


class LLMDecomposer:
    """Four-pass LLM decomposer for spec-to-task transformation.

    Takes a ParsedSpec and decomposes it into atomic DecomposedTask objects
    through four LLM passes:

    Pass 1 (Sequential): Extract TDD cycles from the PRD
    Pass 2 (Parallel): Break each cycle into 3-5 atomic tasks
    Pass 3 (Parallel): Generate acceptance criteria for each task
    Pass 4 (Parallel): Generate implementation hints for medium/high complexity tasks
    """

    def __init__(
        self,
        client: LLMClient,
        config: DecompositionConfig | None = None,
        on_cycle_complete: OnCycleCompleteCallback | None = None,
        on_ac_complete: OnACCompleteCallback | None = None,
        prefix: str = "TASK",
    ) -> None:
        """Initialize the decomposer with an LLM client.

        Args:
            client: LLM client implementing the LLMClient protocol.
            config: Optional configuration (uses defaults if not provided).
            on_cycle_complete: Optional async callback invoked after each cycle
                completes in Pass 2. Receives (tasks, cycle_number) for incremental
                database writes. Tasks at this point have no acceptance criteria yet.
            on_ac_complete: Optional async callback invoked after each task's
                acceptance criteria is generated in Pass 3. Receives (task_key,
                acceptance_criteria) for incremental database updates.
            prefix: Task key prefix (e.g., "SF" for Salesforce). Used to generate
                proper task keys from the start: {prefix}-TDD-{phase:02d}-{seq:02d}
        """
        self.client = client
        self.config = config or DecompositionConfig()
        self.metrics = DecompositionMetrics()
        self._prefix = prefix
        self._phase_sequence: dict[int, int] = {}  # Track sequence per phase
        self._total_llm_calls = 0
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_llm_calls)
        self._on_cycle_complete = on_cycle_complete
        self._on_ac_complete = on_ac_complete

    def _generate_task_key(self, phase: int) -> str:
        """Generate a unique task key for the given phase.

        Args:
            phase: The phase (cycle) number for this task.

        Returns:
            Task key in format "{PREFIX}-TDD-{PHASE:02d}-{SEQ:02d}".
        """
        # Initialize or increment sequence for this phase
        if phase not in self._phase_sequence:
            self._phase_sequence[phase] = 0
        self._phase_sequence[phase] += 1
        seq = self._phase_sequence[phase]
        return f"{self._prefix}-TDD-{phase:02d}-{seq:02d}"

    def _check_llm_limit(self) -> None:
        """Check if LLM call limit exceeded.

        Raises:
            LLMClientError: If total LLM calls exceed configured limit.
        """
        self._total_llm_calls += 1
        if self._total_llm_calls > self.config.max_total_llm_calls:
            raise LLMClientError(
                f"LLM call limit exceeded: {self._total_llm_calls} > {self.config.max_total_llm_calls}"
            )

    async def decompose(self, parsed_spec: ParsedSpec) -> list[DecomposedTask]:
        """Decompose a parsed spec into atomic tasks.

        This is the main entry point for decomposition. It runs four passes:
        1. Extract TDD cycles from the PRD
        2. Break each cycle into atomic tasks (parallel)
        3. Generate acceptance criteria for each task (parallel)
        4. Generate implementation hints for medium/high complexity tasks (parallel)

        Args:
            parsed_spec: ParsedSpec from the spec parser.

        Returns:
            List of DecomposedTask objects ready for TDD execution.

        Raises:
            LLMDecompositionError: If decomposition fails.
        """
        start_time = time.time()
        self._phase_sequence = {}  # Reset sequence tracking for new decomposition

        try:
            # Pass 1: Extract TDD cycles
            logger.info("Pass 1: Extracting TDD cycles from spec")
            cycles = await self._extract_cycles(parsed_spec)
            self.metrics.pass1_cycles_extracted = len(cycles)
            logger.info(f"Pass 1 complete: {len(cycles)} cycles extracted")

            # Pass 2: Break cycles into tasks (parallel)
            logger.info("Pass 2: Breaking cycles into atomic tasks")
            all_tasks = await self._break_all_cycles(cycles, parsed_spec)
            self.metrics.pass2_tasks_generated = len(all_tasks)
            logger.info(f"Pass 2 complete: {len(all_tasks)} tasks generated")

            # Pass 3: Generate acceptance criteria (parallel)
            logger.info("Pass 3: Generating acceptance criteria")
            tasks = await self._generate_all_ac(all_tasks, parsed_spec)
            self.metrics.pass3_ac_generated = sum(len(t.acceptance_criteria) for t in tasks)
            logger.info(f"Pass 3 complete: {self.metrics.pass3_ac_generated} criteria generated")

            # Pass 4: Generate implementation hints for medium/high complexity tasks
            logger.info("Pass 4: Generating implementation hints")
            tasks = await self._generate_all_hints(tasks)
            hints_count = sum(1 for t in tasks if t.implementation_hints)
            logger.info(f"Pass 4 complete: {hints_count} tasks received hints")

            self.metrics.total_duration_seconds = time.time() - start_time
            return tasks

        except Exception as e:
            self.metrics.errors.append(str(e))
            logger.error(f"Decomposition failed: {e}")
            raise LLMDecompositionError(f"Decomposition failed: {e}") from e

    async def _extract_cycles(self, spec: ParsedSpec) -> list[dict[str, Any]]:
        """Pass 1: Extract TDD cycles from the PRD.

        If the spec already has TDD cycles extracted by the parser, use them
        directly without an LLM call. This avoids sending large specs (92KB+)
        to the LLM which can overwhelm the SDK.

        Args:
            spec: ParsedSpec containing the raw PRD content.

        Returns:
            List of cycle dictionaries with cycle_number, phase, title, etc.
        """
        # If spec already has TDD cycles extracted, use them directly (no LLM needed)
        existing_cycles = spec.tdd_cycles
        if existing_cycles:
            logger.info(
                f"Using {len(existing_cycles)} pre-extracted cycles from spec (skipping LLM Pass 1)"
            )
            # Limit cycles to max configured
            return existing_cycles[: self.config.max_cycles_per_spec]

        # Only use LLM if no cycles were extracted by parser
        # Note: Large specs (>50KB) may cause empty responses from SDK
        if len(spec.raw_content) > 50000:
            logger.warning(
                f"Spec is {len(spec.raw_content):,} chars - too large for LLM extraction. "
                "Add TDD Cycle definitions to the TESTING STRATEGY section of your spec."
            )
            raise LLMDecompositionError(
                f"Spec too large ({len(spec.raw_content):,} chars) and no pre-extracted cycles. "
                "Add 'TDD Cycle N: Title' entries to your spec's TESTING STRATEGY section."
            )

        prompt = format_phase_extraction_prompt(spec.raw_content)
        self._check_llm_limit()
        self.metrics.total_llm_calls += 1

        response = await self.client.send_message(prompt)

        try:
            cycles = parse_json_response(response)
        except LLMResponseParseError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            raise LLMDecompositionError(f"Pass 1 failed: {e}") from e

        if not isinstance(cycles, list):
            raise LLMDecompositionError(f"Pass 1 expected list, got {type(cycles).__name__}")

        # Limit cycles to max configured
        cycles = cycles[: self.config.max_cycles_per_spec]

        return cycles

    async def _break_all_cycles(
        self, cycles: list[dict[str, Any]], spec: ParsedSpec
    ) -> list[dict[str, Any]]:
        """Break all cycles into tasks, optionally in parallel with concurrency limiting.

        Args:
            cycles: List of cycle dictionaries from Pass 1.
            spec: ParsedSpec for additional context.

        Returns:
            List of task dictionaries with phase and sequence assigned.
        """
        if self.config.enable_parallel_calls:
            # Run Pass 2 in parallel with concurrency limiting
            coroutines = [self._break_cycle_with_semaphore(cycle, spec) for cycle in cycles]
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            all_tasks: list[dict[str, Any]] = []
            failed_cycles: list[tuple[int, dict[str, Any]]] = []

            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.warning(f"Cycle {i + 1} breakdown failed: {result}")
                    self.metrics.errors.append(f"Cycle {i + 1}: {result}")
                    failed_cycles.append((i, cycles[i]))
                else:
                    # result is list[dict[str, Any]] when not an exception
                    all_tasks.extend(result)

            # Retry failed cycles sequentially
            if failed_cycles:
                logger.info(f"Retrying {len(failed_cycles)} failed cycles")
                for cycle_num, cycle in failed_cycles:
                    for attempt in range(self.config.max_retry_attempts):
                        try:
                            tasks = await self._break_cycle(cycle, spec)
                            all_tasks.extend(tasks)
                            logger.info(f"Cycle {cycle_num + 1} succeeded on retry {attempt + 1}")
                            break
                        except Exception as e:
                            logger.warning(f"Cycle {cycle_num + 1} retry {attempt + 1} failed: {e}")
                            if attempt == self.config.max_retry_attempts - 1:
                                self.metrics.errors.append(
                                    f"Cycle {cycle_num + 1} failed after {self.config.max_retry_attempts} retries"
                                )

            return all_tasks
        else:
            # Sequential execution
            all_tasks = []
            for cycle in cycles:
                tasks = await self._break_cycle(cycle, spec)
                all_tasks.extend(tasks)
            return all_tasks

    async def _break_cycle_with_semaphore(
        self, cycle: dict[str, Any], spec: ParsedSpec
    ) -> list[dict[str, Any]]:
        """Break a cycle with semaphore-controlled concurrency.

        Args:
            cycle: Cycle dictionary from Pass 1.
            spec: ParsedSpec for additional context.

        Returns:
            List of task dictionaries for this cycle.
        """
        async with self._semaphore:
            return await self._break_cycle(cycle, spec)

    async def _break_cycle(self, cycle: dict[str, Any], spec: ParsedSpec) -> list[dict[str, Any]]:
        """Pass 2: Break a single cycle into atomic tasks.

        Args:
            cycle: Cycle dictionary from Pass 1.
            spec: ParsedSpec for additional context.

        Returns:
            List of task dictionaries for this cycle.
        """
        cycle_number = cycle.get("cycle_number", 0)
        cycle_title = cycle.get("cycle_title", cycle.get("title", "Unnamed Cycle"))
        phase = cycle.get("phase", "")
        components = cycle.get("components", [])
        expected_tests = cycle.get("expected_tests", "5-10")
        module_hint = cycle.get("module_hint", "")

        # Build context from spec's functional requirements
        context_parts = []
        for fr in spec.functional_requirements[:5]:  # Limit context size
            context_parts.append(f"- {fr.get('id', '')}: {fr.get('title', '')}")

        context = "\n".join(context_parts) if context_parts else "No additional context"

        prompt = format_task_breakdown_prompt(
            cycle_number=cycle_number,
            cycle_title=cycle_title,
            phase=phase,
            components=components,
            expected_tests=expected_tests,
            module_hint=module_hint,
            context=context,
            module_api=spec.module_api if self.config.enable_scaffolding_reference else None,
            module_structure=spec.module_structure,
            config=self.config,
        )

        self._check_llm_limit()
        self.metrics.total_llm_calls += 1
        response = await self.client.send_message(prompt)

        try:
            tasks = parse_json_response(response)
        except LLMResponseParseError as e:
            logger.warning(f"Failed to parse cycle {cycle_number} breakdown: {e}")
            raise LLMDecompositionError(f"Pass 2 failed for cycle {cycle_number}: {e}")

        if not isinstance(tasks, list):
            raise LLMDecompositionError(
                f"Pass 2 expected list for cycle {cycle_number}, got {type(tasks).__name__}"
            )

        # Limit tasks per cycle
        tasks = tasks[: self.config.max_tasks_per_cycle]

        # Add phase and sequence info
        for i, task in enumerate(tasks):
            task["phase"] = cycle_number
            task["sequence"] = i + 1

        # Call incremental callback if provided (for resilient DB writes)
        if self._on_cycle_complete is not None:
            # Create DecomposedTask objects without AC (will be added in Pass 3)
            decomposed_tasks = [self._create_decomposed_task(t, []) for t in tasks]
            # Copy generated task_key back to original dicts for Pass 3 AC updates
            for task, dt in zip(tasks, decomposed_tasks):
                task["task_key"] = dt.task_key
            await self._on_cycle_complete(decomposed_tasks, cycle_number)
            logger.debug(f"Callback invoked for cycle {cycle_number}: {len(tasks)} tasks")

        return tasks

    async def _generate_all_ac(
        self, tasks: list[dict[str, Any]], spec: ParsedSpec
    ) -> list[DecomposedTask]:
        """Generate acceptance criteria for all tasks, optionally in parallel with concurrency limiting.

        Args:
            tasks: List of task dictionaries from Pass 2.
            spec: ParsedSpec for additional context.

        Returns:
            List of fully populated DecomposedTask objects.
        """
        if self.config.enable_parallel_calls:
            # Run Pass 3 in parallel with concurrency limiting
            coroutines = [self._generate_ac_with_semaphore(task, spec) for task in tasks]
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            decomposed_tasks: list[DecomposedTask] = []
            failed_tasks: list[tuple[int, dict[str, Any]]] = []

            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.warning(f"Task {i + 1} AC generation failed: {result}")
                    self.metrics.errors.append(f"Task {i + 1}: {result}")
                    failed_tasks.append((i, tasks[i]))
                    # Create task without AC on initial failure
                    decomposed_tasks.append(self._create_decomposed_task(tasks[i], []))
                else:
                    # result is DecomposedTask when not an exception
                    decomposed_tasks.append(result)

            # Retry failed tasks sequentially
            if failed_tasks:
                logger.info(f"Retrying {len(failed_tasks)} failed AC generations")
                for task_idx, task in failed_tasks:
                    for attempt in range(self.config.max_retry_attempts):
                        try:
                            decomposed_task = await self._generate_ac(task, spec)
                            # Replace the failed task with the successful one
                            decomposed_tasks[task_idx] = decomposed_task
                            logger.info(f"Task {task_idx + 1} AC succeeded on retry {attempt + 1}")
                            break
                        except Exception as e:
                            logger.warning(
                                f"Task {task_idx + 1} AC retry {attempt + 1} failed: {e}"
                            )
                            if attempt == self.config.max_retry_attempts - 1:
                                self.metrics.errors.append(
                                    f"Task {task_idx + 1} AC failed after {self.config.max_retry_attempts} retries"
                                )

            return decomposed_tasks
        else:
            # Sequential execution
            decomposed_tasks = []
            for task in tasks:
                decomposed_task = await self._generate_ac(task, spec)
                decomposed_tasks.append(decomposed_task)
            return decomposed_tasks

    async def _generate_ac_with_semaphore(
        self, task: dict[str, Any], spec: ParsedSpec
    ) -> DecomposedTask:
        """Generate AC with semaphore-controlled concurrency.

        Args:
            task: Task dictionary from Pass 2.
            spec: ParsedSpec for additional context.

        Returns:
            Fully populated DecomposedTask.
        """
        async with self._semaphore:
            return await self._generate_ac(task, spec)

    async def _generate_ac(self, task: dict[str, Any], spec: ParsedSpec) -> DecomposedTask:
        """Pass 3: Generate acceptance criteria for a single task.

        Args:
            task: Task dictionary from Pass 2.
            spec: ParsedSpec for additional context.

        Returns:
            Fully populated DecomposedTask.
        """
        task_title = task.get("title", "Unnamed Task")
        task_goal = task.get("goal", "")
        test_file = task.get("test_file", "")
        impl_file = task.get("impl_file", "")
        components = task.get("components", [])
        estimated_tests = task.get("estimated_tests", self.config.min_tests)

        # Build requirements context from spec
        context_parts = []
        for ac in spec.acceptance_criteria[:3]:  # Limit context
            if ac.get("gherkin"):
                context_parts.append(ac["gherkin"])

        requirements_context = (
            "\n\n".join(context_parts) if context_parts else "No specific requirements"
        )

        prompt = format_ac_generation_prompt(
            task_title=task_title,
            task_goal=task_goal,
            test_file=test_file,
            impl_file=impl_file,
            components=components,
            estimated_tests=estimated_tests,
            requirements_context=requirements_context,
            min_criteria=self.config.min_criteria,
            max_criteria=self.config.max_criteria,
        )

        self._check_llm_limit()
        self.metrics.total_llm_calls += 1
        response = await self.client.send_message(prompt)

        try:
            criteria = parse_json_response(response)
        except LLMResponseParseError as e:
            logger.warning(f"Failed to parse AC for '{task_title}': {e}")
            criteria = []

        if not isinstance(criteria, list):
            logger.warning(f"AC response not a list for '{task_title}'")
            criteria = []

        # Validate criteria are strings
        criteria = [str(c) for c in criteria if c][: self.config.max_criteria]

        # Detect logical contradictions in acceptance criteria
        contradictions = self._detect_ac_contradictions(criteria)
        if contradictions:
            # Log warning but don't block - let downstream catch it
            logger.warning(
                f"Potential AC contradictions detected for task {task.get('task_key', 'unknown')}: "
                f"{contradictions}"
            )

        decomposed_task = self._create_decomposed_task(task, criteria)

        # Call incremental AC callback if provided (for real-time DB updates)
        if self._on_ac_complete is not None and criteria:
            try:
                await self._on_ac_complete(decomposed_task.task_key, criteria)
                logger.debug(
                    f"AC callback invoked for {decomposed_task.task_key}: {len(criteria)} criteria"
                )
            except Exception as e:
                # Log warning but don't stop execution - AC update failure shouldn't block
                logger.warning(f"AC callback failed for {decomposed_task.task_key}: {e}")

        return decomposed_task

    async def _generate_all_hints(self, tasks: list[DecomposedTask]) -> list[DecomposedTask]:
        """Generate implementation hints for all medium/high complexity tasks.

        Args:
            tasks: List of DecomposedTask objects from Pass 3.

        Returns:
            List of DecomposedTask objects with hints populated for non-low complexity.
        """
        if self.config.enable_parallel_calls:
            # Run Pass 4 in parallel with concurrency limiting
            coroutines = [self._generate_hints_with_semaphore(task) for task in tasks]
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.warning(f"Hints generation failed for {tasks[i].task_key}: {result}")
                    self.metrics.errors.append(f"Hints for {tasks[i].task_key}: {result}")
                elif result:  # Non-empty hints
                    tasks[i] = replace(tasks[i], implementation_hints=result)

            return tasks
        else:
            # Sequential execution
            for i, task in enumerate(tasks):
                hints = await self._generate_hints(task)
                if hints:
                    tasks[i] = replace(task, implementation_hints=hints)
            return tasks

    async def _generate_hints_with_semaphore(self, task: DecomposedTask) -> str:
        """Generate hints with semaphore-controlled concurrency.

        Args:
            task: DecomposedTask from Pass 3.

        Returns:
            Markdown string with implementation hints, or empty string.
        """
        async with self._semaphore:
            return await self._generate_hints(task)

    async def _generate_hints(self, task: DecomposedTask) -> str:
        """Pass 4: Generate implementation hints for a task.

        Args:
            task: DecomposedTask from Pass 3.

        Returns:
            Markdown string with implementation hints, or empty string for low complexity.
        """
        # Skip LLM call for low complexity tasks
        if task.complexity == "low":
            return ""

        prompt = format_implementation_hints_prompt(
            task_title=task.title,
            task_goal=task.goal,
            impl_file=task.impl_file,
            acceptance_criteria=task.acceptance_criteria,
            complexity=task.complexity,
        )

        # Skip if prompt is empty (format_implementation_hints_prompt returns "" for low)
        if not prompt:
            return ""

        self._check_llm_limit()
        self.metrics.total_llm_calls += 1
        response = await self.client.send_message(prompt)

        try:
            result = parse_json_response(response)
            return result.get("hints", "") if isinstance(result, dict) else ""
        except LLMResponseParseError:
            return ""

    def _detect_ac_contradictions(self, criteria: list[str]) -> list[str]:
        """Detect logically contradictory acceptance criteria.

        Finds criteria where the same WHEN condition expects different THEN results.

        Args:
            criteria: List of acceptance criteria strings in GIVEN/WHEN/THEN format

        Returns:
            List of contradiction descriptions, empty if none found
        """
        contradictions: list[str] = []
        when_then_map: dict[
            str, list[tuple[str, str]]
        ] = {}  # when_clause -> [(then_clause, full_ac)]

        for ac in criteria:
            # Extract WHEN and THEN clauses
            when_match = re.search(r"WHEN\s+(.+?)\s+THEN", ac, re.IGNORECASE | re.DOTALL)
            then_match = re.search(r"THEN\s+(.+?)(?:$|GIVEN|WHEN)", ac, re.IGNORECASE | re.DOTALL)

            if when_match and then_match:
                when_clause = when_match.group(1).strip().lower()
                then_clause = then_match.group(1).strip().lower()

                # Normalize the WHEN clause (remove extra whitespace)
                when_normalized = " ".join(when_clause.split())

                if when_normalized not in when_then_map:
                    when_then_map[when_normalized] = []
                when_then_map[when_normalized].append((then_clause, ac))

        # Check for contradictions: same WHEN with different THEN
        for when_clause, then_list in when_then_map.items():
            if len(then_list) > 1:
                # Check if THEN clauses are contradictory (e.g., "true" vs "false")
                then_clauses = [t[0] for t in then_list]

                # Simple contradiction detection: "returns true" vs "returns false"
                has_true = any("true" in t and "return" in t for t in then_clauses)
                has_false = any("false" in t and "return" in t for t in then_clauses)

                if has_true and has_false:
                    contradictions.append(
                        f"Contradictory expectations for '{when_clause[:50]}...': "
                        f"some criteria expect True, others expect False"
                    )

        return contradictions

    def _create_decomposed_task(
        self, task: dict[str, Any], acceptance_criteria: list[str]
    ) -> DecomposedTask:
        """Create a DecomposedTask from a task dictionary.

        Detects task complexity using multi-factor scoring (title, acceptance
        criteria, and implementation file path) and stores the result.

        Args:
            task: Task dictionary from Pass 2.
            acceptance_criteria: List of acceptance criteria strings.

        Returns:
            DecomposedTask instance with complexity detected.
        """
        phase = task.get("phase", 0)
        # Preserve existing task_key (from Pass 2) or generate new one (for splits)
        existing_key = task.get("task_key")
        task_key = existing_key if existing_key else self._generate_task_key(phase)

        # Detect complexity using multi-factor scoring
        title = task.get("title", "Unnamed Task")
        impl_file = task.get("impl_file", "")
        complexity_result: ComplexityResult = detect_complexity(
            title=title,
            acceptance_criteria=acceptance_criteria,
            impl_file=impl_file,
        )

        return DecomposedTask(
            task_key=task_key,
            title=title,
            goal=task.get("goal", ""),
            estimated_tests=task.get("estimated_tests", self.config.min_tests),
            estimated_lines=task.get("estimated_lines", 50),
            test_file=task.get("test_file", ""),
            impl_file=impl_file,
            components=task.get("components", []),
            acceptance_criteria=acceptance_criteria,
            phase=phase,
            sequence=task.get("sequence", 0),
            parent_task_key=task.get("parent_task_key"),
            recursion_depth=task.get("recursion_depth", 0),
            error_codes=task.get("error_codes", []),
            blocking_assumption=task.get("blocking_assumption"),
            verify_command=task.get("verify_command", ""),
            done_criteria=task.get("done_criteria", ""),
            complexity=complexity_result.level,
            module_exports=task.get("module_exports", []),
            import_pattern=task.get("import_pattern", "direct"),
        )

    def get_metrics(self) -> DecompositionMetrics:
        """Get decomposition metrics.

        Returns:
            DecompositionMetrics containing execution statistics.
        """
        return self.metrics
