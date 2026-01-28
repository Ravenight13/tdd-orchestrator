"""Configuration for LLM decomposition engine.

This module defines configuration dataclasses for the three-pass decomposition
pipeline including limits for task generation, acceptance criteria, and recursion.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DecompositionConfig:
    """Configuration for the LLM decomposition pipeline.

    Controls the behavior of the three-pass decomposition process including
    limits on task complexity, recursion depth, and acceptance criteria counts.

    Attributes:
        max_recursion_depth: Maximum depth for recursive task decomposition.
        min_tests: Minimum expected tests per atomic task.
        max_tests: Maximum expected tests per atomic task.
        max_lines: Maximum implementation lines per atomic task.
        min_criteria: Minimum acceptance criteria per task.
        max_criteria: Maximum acceptance criteria per task.
        max_components: Maximum components per atomic task.
        enable_parallel_calls: Enable parallel LLM calls for Pass 2/3.
        max_cycles_per_spec: Maximum TDD cycles to extract in Pass 1.
        max_tasks_per_cycle: Maximum tasks to generate per cycle in Pass 2.
        max_concurrent_llm_calls: Maximum concurrent LLM calls (prevents throttling).
        max_retry_attempts: Maximum retry attempts for failed LLM calls.
        max_total_llm_calls: Hard limit on total LLM calls to prevent runaway.
    """

    max_recursion_depth: int = 3
    min_tests: int = 5
    max_tests: int = 20
    max_lines: int = 100
    min_criteria: int = 2
    max_criteria: int = 5
    max_components: int = 3
    enable_parallel_calls: bool = True
    max_cycles_per_spec: int = 20
    max_tasks_per_cycle: int = 5
    max_concurrent_llm_calls: int = 4
    max_retry_attempts: int = 2
    max_total_llm_calls: int = 100  # Hard limit to prevent runaway

    # PLAN9: Scaffolding reference feature flag
    enable_scaffolding_reference: bool = False


@dataclass
class DecompositionMetrics:
    """Metrics collected during decomposition.

    Tracks performance and quality metrics for the decomposition process.

    Attributes:
        total_llm_calls: Total number of LLM API calls made.
        pass1_cycles_extracted: Number of TDD cycles extracted in Pass 1.
        pass2_tasks_generated: Number of tasks generated in Pass 2.
        pass3_ac_generated: Total acceptance criteria generated in Pass 3.
        total_duration_seconds: Total time for decomposition.
        errors: List of error messages encountered during decomposition.
    """

    total_llm_calls: int = 0
    pass1_cycles_extracted: int = 0
    pass2_tasks_generated: int = 0
    pass3_ac_generated: int = 0
    total_duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


# Default configuration instance for convenience
DEFAULT_DECOMPOSITION_CONFIG = DecompositionConfig()
