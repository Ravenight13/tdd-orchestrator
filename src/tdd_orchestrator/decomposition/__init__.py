"""Decomposition module for app spec parsing and task generation.

This module provides tools for parsing app_spec.txt files and decomposing
them into structured tasks for TDD orchestration.

Public API:
    Phase 1 (Parser):
    - ParsedSpec: Dataclass containing parsed specification components
    - SpecParser: Parser for extracting structured data from spec files

    Phase 2 (LLM Decomposition):
    - DecompositionConfig: Configuration for decomposition pipeline
    - DecomposedTask: Atomic task ready for TDD execution
    - LLMDecomposer: Three-pass decomposition engine
    - LLMClient: Protocol for LLM client abstraction
    - MockLLMClient: Mock client for testing

    Phase 3 (Task Generation):
    - TaskGenerator: Assign task keys and calculate dependencies
    - camel_to_snake: Convert PascalCase/camelCase to snake_case
    - generate_file_paths: Generate test and implementation file paths

    Phase 4 (Recursive Validation):
    - AtomicityValidator: Validate task atomicity constraints
    - RecursiveValidator: Recursive validation and re-decomposition engine
    - ValidationResult: Result of atomicity validation
    - RecursiveValidationStats: Statistics from recursive validation

    Exceptions:
    - DecompositionError: Base exception for decomposition errors
    - SpecParseError: Raised when parsing fails
    - LLMDecompositionError: Raised when LLM decomposition fails
"""

from __future__ import annotations

from .config import DecompositionConfig, DecompositionMetrics
from .decomposer import (
    DecomposedTask,
    LLMDecomposer,
    LLMDecompositionError,
    OnCycleCompleteCallback,
)
from .exceptions import DecompositionError, SpecParseError
from .generator import TaskGenerator, camel_to_snake, generate_file_paths
from .llm_client import (
    ClaudeAgentSDKClient,
    LLMClient,
    LLMClientError,
    LLMResponseParseError,
    MockLLMClient,
    SubscriptionErrorSimulator,
)
from .parser import ParsedSpec, SpecParser
from .prerequisites import generate_prerequisite_tasks
from .validators import (
    AtomicityValidator,
    RecursiveValidationStats,
    RecursiveValidator,
    ValidationResult,
)

__all__ = [
    # Parser (Phase 1)
    "ParsedSpec",
    "SpecParser",
    # Config (Phase 2)
    "DecompositionConfig",
    "DecompositionMetrics",
    # Decomposer (Phase 2)
    "DecomposedTask",
    "LLMDecomposer",
    "OnCycleCompleteCallback",
    # Generator (Phase 3)
    "TaskGenerator",
    "camel_to_snake",
    "generate_file_paths",
    # Validators (Phase 4)
    "AtomicityValidator",
    "RecursiveValidator",
    "ValidationResult",
    "RecursiveValidationStats",
    # LLM Client (Phase 2)
    "LLMClient",
    "MockLLMClient",
    "ClaudeAgentSDKClient",
    "SubscriptionErrorSimulator",
    # Prerequisites
    "generate_prerequisite_tasks",
    # Exceptions
    "DecompositionError",
    "SpecParseError",
    "LLMDecompositionError",
    "LLMClientError",
    "LLMResponseParseError",
]
