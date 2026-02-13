"""Prompt templates for LLM decomposition engine.

This module provides prompt templates for the four-pass decomposition:
- Pass 1: Extract TDD cycles from PRD
- Pass 2: Break cycles into atomic tasks
- Pass 3: Generate acceptance criteria for tasks
- Pass 4: Generate implementation hints for medium/high complexity tasks
- Re-decomposition: Split oversized tasks into smaller subtasks

IMPORTANT: Avoid XML-style angle brackets in prompts. The Claude Agent SDK CLI
interprets <tag> patterns specially, causing empty responses. Use neutral
delimiters instead (=== SECTION ===, --- ID ---).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import DecompositionConfig, DEFAULT_DECOMPOSITION_CONFIG
from .utils import sanitize_for_llm

if TYPE_CHECKING:
    from .task_model import DecomposedTask

# =============================================================================
# PASS 1: Phase/Cycle Extraction
# =============================================================================

PHASE_EXTRACTION_PROMPT = """You are a TDD task decomposition expert. Analyze this PRD and extract TDD cycles.

Each TDD cycle should:
- Focus on a single cohesive feature or capability
- Be implementable in 1-2 sessions (2-4 hours)
- Have clear boundaries and dependencies
- Include 5-20 tests when fully implemented

XML Element Guidance (if present in PRD):
- Look for <dependencies> section defining a DAG of task relationships
- Use dependency relationships (e.g., "FR-2 depends on FR-1") to inform phase ordering
- Tasks with no dependencies should be scheduled in early phases
- Tasks with many dependents are foundational; prioritize them early
- If no <dependencies> section exists, infer logical ordering from requirements
- Look for <assumptions> section with assumption elements
- Extract assumptions with confidence levels (high/medium/low)
- Flag assumptions with confidence="low" or "NEEDS CONFIRMATION" as BLOCKING
- Map assumption impacts (e.g., impacts="FR-1, FR-2") to relevant cycles
- If blocking assumptions exist, note them in the returned cycles JSON


PRD Content:
{app_spec_content}

Return a JSON array of TDD cycles. Each cycle should have:
- cycle_number: Sequential number starting from 1
- phase: High-level phase name (e.g., "Foundation", "Core Features", "Integration")
- cycle_title: Brief descriptive title for the cycle
- components: Array of component names to implement
- expected_tests: String like "8-10" indicating expected test count range
- module_hint: Path hint for where implementation should go
- dependencies: Array of cycle_numbers this cycle depends on (use [] if none)
- blocking_assumptions: Array of assumption IDs that block this cycle (use [] if none)

Example format:
[
  {{
    "cycle_number": 1,
    "phase": "Foundation",
    "cycle_title": "Configuration and Environment Setup",
    "components": ["ConfigLoader", "EnvironmentValidator"],
    "expected_tests": "8-10",
    "module_hint": "src/config/",
    "dependencies": [],
    "blocking_assumptions": ["A-4", "A-6"]
  }}
]"""


# =============================================================================
# PASS 2: Task Breakdown
# =============================================================================

TASK_BREAKDOWN_PROMPT = """You are a TDD task breakdown expert. Decompose this TDD cycle into atomic tasks.

Each atomic task must:
- Be completable in one RED-GREEN-REFACTOR cycle (30-60 minutes)
- Have exactly 5-20 tests
- Produce less than 100 lines of implementation
- Focus on a single responsibility
- Be independently testable

TDD Cycle Details:
- Cycle Number: {cycle_number}
- Cycle Title: {cycle_title}
- Phase: {phase}
- Components: {components}
- Expected Tests: {expected_tests}
- Module Hint: {module_hint}

Additional Context from PRD:
{context}
{module_api_section}
FILE PATH RULES (CRITICAL):
- impl_file MUST be a single .py module file (e.g., "src/auth/cache.py")
- impl_file MUST use the Module Hint as its base directory (e.g., if Module Hint is "src/htmx/", impl_file should be "src/htmx/component_name.py")
- Do NOT specify package directories (folders that would contain __init__.py)
- The verification system checks for the EXACT file path - no variations allowed
- Example: "src/auth/token_cache.py" is correct, "src/auth/token_cache/" is WRONG

{valid_path_prefixes}

INTEGRATION-BOUNDARY DETECTION (overrides Phase-based classification):

If a task involves ANY of these component types, classify as integration
regardless of Phase name:
- Route handlers / API endpoints (FastAPI, Flask, Django views)
- Database query methods (methods that execute SQL or ORM queries)
- External service clients (HTTP clients, SDK wrappers)
- Message queue consumers/producers

For integration-boundary tasks:
- test_type: "integration"
- verify_command: Must point to integration test file (tests/integration/...)
- done_criteria: MUST include "against real database with seeded data" or
  "against test server with real dependencies"
- impl_file: The actual route/DB file in src/ (do NOT set equal to test_file)

TEST TYPE CLASSIFICATION (CRITICAL):

Determine the test type based on the Phase name (unless overridden by
INTEGRATION-BOUNDARY DETECTION above):
- Phase contains "Foundation", "Core", "Unit" → test_type: "unit"
- Phase contains "Integration" → test_type: "integration"
- Phase contains "E2E", "End-to-End", "Acceptance" → test_type: "e2e"

UNIT TEST RULES (default):
- test_file: "tests/unit/{{module}}/test_{{component}}.py"
- impl_file: New implementation file in src/
- estimated_tests: 5-20
- No special dependencies required

INTEGRATION TEST RULES:
- test_file: "tests/integration/test_{{feature}}_{{aspect}}.py" (UNIQUE per task - no sharing)
- impl_file: Set EQUAL TO test_file (the test IS the deliverable for integration tasks)
- estimated_tests: 3-8 (fewer but more complex tests)
- MUST include "depends_on" array with task_keys of unit tests that create tested components
- Auto-set complexity to "high"

E2E TEST RULES:
- test_file: "tests/e2e/test_{{user_flow}}.py" (UNIQUE per task)
- impl_file: Set EQUAL TO test_file (the test IS the deliverable for e2e tasks)
- estimated_tests: 2-5 (fewest but most comprehensive)
- MUST depend on multiple integration test tasks
- Auto-set complexity to "high"

ANTI-PATTERNS TO AVOID:
- Multiple tasks sharing the same test_file (each task = unique test file)
- Integration tests with impl_file NOT equal to test_file
- Integration tests without depends_on linking to related unit tests
- Creating src/ files in integration/e2e test impl_file (use test_file path instead)

Return a JSON array of 3-5 atomic tasks. Each task should have:
- title: Clear action-oriented title
- goal: One sentence describing what this task accomplishes
- verify_command: A shell command to verify task completion (e.g., "uv run pytest tests/unit/config/test_loader.py -v")
- done_criteria: A clear, testable statement of what "done" means (e.g., "All tests pass and code is formatted with ruff")
- estimated_tests: Integer between 5-20
- estimated_lines: Integer less than 100
- test_file: Relative path for the test file
- impl_file: Relative path for the implementation file
- components: Array of component names (max 3)
- error_codes: Array of relevant error codes (e.g., ERR-AUTH-001) - use empty array if none
- blocking_assumption: Assumption ID if task depends on unverified assumption (omit if none)
- module_exports: Array of exact export names this module should provide (from MODULE API SPECIFICATION if available, or infer from components)

Example format:
[
  {{
    "title": "Implement configuration file loading",
    "goal": "Load and validate YAML configuration files with schema enforcement",
    "verify_command": "uv run pytest tests/unit/config/test_loader.py -v",
    "done_criteria": "All configuration tests pass, valid YAML files load successfully with schema validation, and invalid files raise appropriate errors",
    "estimated_tests": 8,
    "estimated_lines": 45,
    "test_file": "tests/unit/config/test_loader.py",
    "impl_file": "src/config/loader.py",
    "components": ["ConfigLoader"],
    "error_codes": ["ERR-CFG-001", "ERR-CFG-002"],
    "blocking_assumption": "A-4",
    "module_exports": ["ConfigLoader", "load_config", "ConfigError"]
  }}
]"""


# =============================================================================
# PASS 3: Acceptance Criteria Generation
# =============================================================================

AC_GENERATION_PROMPT = """You are a TDD acceptance criteria expert. Generate testable acceptance criteria.

Each acceptance criterion must:
- Be specific and measurable
- Directly translate to a test case
- Focus on behavior, not implementation
- Use clear "GIVEN/WHEN/THEN" or imperative language

Task Details:
- Title: {task_title}
- Goal: {task_goal}
- Test File: {test_file}
- Implementation File: {impl_file}
- Components: {components}
- Estimated Tests: {estimated_tests}

Relevant Requirements from PRD:
{requirements_context}

## TEST CONTEXT RULES

If test_file path contains "integration/" or task involves route handlers/DB methods:
- Criteria MUST reference "seeded test database" or "test server"
- Use "GIVEN a test database seeded with..." not "GIVEN a mocked..."
- Specify exact seed data counts: "GIVEN 5 circuits (3 closed, 2 open)"
- Example: "GIVEN test DB with 3 tasks, GET /tasks returns list of 3 TaskResponse items"

If test_file path contains "unit/" and no DB/route involvement:
- Mocks are acceptable: "GIVEN mocked api_client.get() returns 200..."
- Focus on isolated component behavior

Include criteria for:
- Happy path scenarios
- Error paths (reference error codes like ERR-AUTH-001 if applicable)
- Edge cases

## CRITICAL CONSISTENCY RULES

Before finalizing acceptance criteria, verify ALL of the following:

1. **Mutual Satisfiability**: All criteria must be satisfiable by a SINGLE implementation.
   - If two criteria have the same function inputs, they MUST expect the same output
   - BAD: "brand='Direct' returns True" AND "brand='Direct' returns False"
   - GOOD: "brand='Enabled' returns True" AND "brand='Disabled' returns False"

2. **Configuration-Dependent Behavior**: If behavior varies based on state/config:
   - Specify WHERE configuration is stored (env var, config file, database, fixture)
   - Specify HOW tests will set up different states (pytest fixtures, mocking, parametrization)
   - Example: "GIVEN feature_flags fixture sets brand='Direct' to enabled..."

3. **No Implicit State**: Never assume external state exists without defining it
   - BAD: "GIVEN a brand with flag set to true" (where is this flag?)
   - GOOD: "GIVEN conftest.py fixture sets FEATURE_FLAGS['Direct']['upload']=True"

4. **Self-Check**: Before returning criteria, ask: "Can ONE implementation pass ALL these tests simultaneously?"
   - If answer is "no" or "depends on state", criteria need fixtures/mocking defined


Return a JSON array of {min_criteria}-{max_criteria} acceptance criteria strings.
Each should be a specific, testable statement that could become a test case.

Example format:
[
  "Loading a valid YAML file returns a populated config object",
  "Loading a non-existent file raises ConfigNotFoundError with code ERR-CFG-001",
  "Loading a file with invalid YAML raises ConfigParseError with code ERR-CFG-002",
  "Config values are accessible via dot notation (config.database.host)",
  "Environment variables override file values when prefixed with APP_"
]"""


# =============================================================================
# PASS 4: Implementation Hints Generation
# =============================================================================

IMPLEMENTATION_HINTS_PROMPT = """You are a senior developer providing implementation guidance.

Task Details:
- Title: {task_title}
- Goal: {task_goal}
- Implementation File: {impl_file}
- Acceptance Criteria: {acceptance_criteria}

Complexity: {complexity}

For HIGH complexity tasks, provide:
1. Required Libraries: Specific packages to use (with import statements)
2. Code Patterns: Key function signatures and patterns
3. Common Pitfalls: Mistakes to avoid
4. Reference Examples: Brief code snippets showing the pattern

For MEDIUM complexity, provide:
1. Libraries: Package names only
2. Key Pattern: One code snippet

For LOW complexity, return empty hints (no guidance needed).

Return JSON:
{{
  "hints": "markdown string with implementation guidance",
  "libraries": ["lib1", "lib2"],
  "complexity_confirmed": "high|medium|low"
}}"""


# =============================================================================
# RECURSIVE RE-DECOMPOSITION: Split Oversized Tasks
# =============================================================================

RE_DECOMPOSITION_PROMPT = """You are a TDD task decomposition expert. Split an oversized task into smaller subtasks.

ATOMICITY RULES:
- Each subtask: 5-20 tests
- Each subtask: <100 lines of code
- Each subtask: <=3 components
- Single responsibility principle

Oversized Task Details:
- Task Key: {task_key}
- Title: {title}
- Goal: {goal}
- Estimated Tests: {estimated_tests}
- Estimated Lines: {estimated_lines}
- Components: {components}

Violations: {violations}
Split Strategy: {strategy}

Return a JSON array of 2-3 atomic subtasks. Each subtask should have:
- title: Clear action-oriented title
- goal: One sentence describing what this subtask accomplishes
- verify_command: A shell command to verify subtask completion
- done_criteria: A clear, testable statement of what "done" means
- estimated_tests: Integer between 5-20
- estimated_lines: Integer less than 100
- components: Array of component names (max 3)
- test_file: Relative path for the test file
- impl_file: Relative path for the implementation file

Example format:
[
  {{"title": "...", "goal": "...", "verify_command": "uv run pytest tests/unit/.../test_*.py -v", "done_criteria": "All subtask tests pass and implementation is complete", "estimated_tests": 10, "estimated_lines": 50, "components": [...], "test_file": "...", "impl_file": "..."}}
]"""


# =============================================================================
# Helper Functions
# =============================================================================


def _format_module_api_context(module_api: dict[str, dict[str, Any]]) -> str:
    """Format MODULE_API_SPECIFICATION for inclusion in prompt.

    PLAN9: Provides export context for task breakdown.

    Args:
        module_api: Dictionary mapping module paths to their specifications.
            Each spec should have 'exports' (list of export names) and
            optionally 'test_import' (example import statement).

    Returns:
        Formatted string for inclusion in prompt, or empty string if no data.
    """
    if not module_api:
        return ""

    lines = ["", "## Module API Specification", ""]
    lines.append("Use these exact exports when generating task specifications:")
    lines.append("")

    for module_path, spec in module_api.items():
        exports = spec.get("exports", [])
        test_import = spec.get("test_import", "")

        if exports:
            export_list = ", ".join(exports)
            lines.append(f"**{module_path}**: exports `{export_list}`")
            if test_import:
                lines.append(f"  - Test import: `{test_import}`")

    lines.append("")
    lines.append(
        "When generating tasks for these modules, include the `module_exports` "
        "field with the exact export names listed above."
    )
    lines.append("")

    return "\n".join(lines)


def _build_valid_prefixes(
    module_hint: str, module_structure: dict[str, Any] | None = None
) -> str:
    """Build dynamic VALID PATH PREFIXES section from spec data.

    Extracts unique directory prefixes from the module_structure's files list,
    always includes the module_hint, and falls back to "src/" if no data.

    Args:
        module_hint: Path hint for where implementation should go.
        module_structure: Dictionary with optional 'files' list of file paths.

    Returns:
        Formatted string for inclusion in the TASK_BREAKDOWN_PROMPT.
    """
    impl_prefixes: set[str] = set()

    # Extract directory prefixes from module_structure files
    if module_structure and module_structure.get("files"):
        for file_path in module_structure["files"]:
            # Get directory portion: "src/tdd_orchestrator/api/routes.py" -> "src/tdd_orchestrator/api/"
            parts = str(file_path).rsplit("/", 1)
            if len(parts) == 2:
                impl_prefixes.add(parts[0] + "/")

    # Always include the module_hint if it looks like a path
    if module_hint and "/" in module_hint:
        # Ensure trailing slash
        hint = module_hint if module_hint.endswith("/") else module_hint + "/"
        impl_prefixes.add(hint)

    # Fallback: generic src/ prefix
    if not impl_prefixes:
        impl_prefixes.add("src/")

    sorted_prefixes = sorted(impl_prefixes)
    impl_line = ", ".join(f'"{p}"' for p in sorted_prefixes)

    lines = [
        "VALID PATH PREFIXES (use these only):",
        f"- impl_file: {impl_line}",
        '- test_file: "tests/unit/", "tests/integration/", "tests/acceptance/"',
        "",
        "INVALID PREFIXES (never use these):",
        '- "app/" (use "src/" instead)',
        '- "backend/tests/" (use "tests/" without backend prefix)',
        '- "backend/src/" (use "src/" without backend prefix)',
    ]

    return "\n".join(lines)


def format_phase_extraction_prompt(app_spec_content: str) -> str:
    """Format the phase extraction prompt with the PRD content.

    Sanitizes the spec content to remove XML-like tags that cause empty SDK responses.

    Args:
        app_spec_content: Raw content from app_spec.txt file.

    Returns:
        Formatted prompt string ready for LLM.
    """
    # Sanitize content to remove XML-like tags that confuse the SDK
    sanitized_content = sanitize_for_llm(app_spec_content)
    return PHASE_EXTRACTION_PROMPT.format(app_spec_content=sanitized_content)


def format_task_breakdown_prompt(
    cycle_number: int,
    cycle_title: str,
    phase: str,
    components: list[str],
    expected_tests: str,
    module_hint: str,
    context: str,
    module_api: dict[str, dict[str, Any]] | None = None,
    module_structure: dict[str, Any] | None = None,
    config: DecompositionConfig | None = None,
) -> str:
    """Format the task breakdown prompt with cycle details.

    Sanitizes the context to remove XML-like tags that cause empty SDK responses.

    Args:
        cycle_number: Sequential cycle number.
        cycle_title: Title of the TDD cycle.
        phase: High-level phase name.
        components: List of component names.
        expected_tests: Expected test count range (e.g., "8-10").
        module_hint: Path hint for implementation.
        context: Additional context from the PRD.
        module_api: PLAN9 - Dictionary mapping module paths to their export
            specifications. Used to provide exact export names for task generation.
        module_structure: Dictionary with optional 'files' list for path prefix extraction.
        config: Decomposition configuration. If None, uses default config.

    Returns:
        Formatted prompt string ready for LLM.
    """
    if config is None:
        config = DEFAULT_DECOMPOSITION_CONFIG

    # Sanitize context to remove XML-like tags
    sanitized_context = sanitize_for_llm(context)

    # PLAN9: Add module API context if scaffolding reference is enabled
    module_api_section = ""
    if config.enable_scaffolding_reference and module_api:
        module_api_section = _format_module_api_context(module_api)

    # Build dynamic path prefixes from spec data
    valid_path_prefixes = _build_valid_prefixes(module_hint, module_structure)

    return TASK_BREAKDOWN_PROMPT.format(
        cycle_number=cycle_number,
        cycle_title=cycle_title,
        phase=phase,
        components=", ".join(components),
        expected_tests=expected_tests,
        module_hint=module_hint,
        context=sanitized_context,
        module_api_section=module_api_section,
        valid_path_prefixes=valid_path_prefixes,
    )


def format_ac_generation_prompt(
    task_title: str,
    task_goal: str,
    test_file: str,
    impl_file: str,
    components: list[str],
    estimated_tests: int,
    requirements_context: str,
    min_criteria: int,
    max_criteria: int,
) -> str:
    """Format the acceptance criteria generation prompt.

    Sanitizes the requirements context to remove XML-like tags that cause empty SDK responses.

    Args:
        task_title: Title of the atomic task.
        task_goal: Goal statement for the task.
        test_file: Path to the test file.
        impl_file: Path to the implementation file.
        components: List of component names.
        estimated_tests: Expected number of tests.
        requirements_context: Relevant requirements from PRD.
        min_criteria: Minimum number of criteria to generate.
        max_criteria: Maximum number of criteria to generate.

    Returns:
        Formatted prompt string ready for LLM.
    """
    # Sanitize requirements context to remove XML-like tags
    sanitized_requirements = sanitize_for_llm(requirements_context)
    return AC_GENERATION_PROMPT.format(
        task_title=task_title,
        task_goal=task_goal,
        test_file=test_file,
        impl_file=impl_file,
        components=", ".join(components),
        estimated_tests=estimated_tests,
        requirements_context=sanitized_requirements,
        min_criteria=min_criteria,
        max_criteria=max_criteria,
    )


def format_implementation_hints_prompt(
    task_title: str,
    task_goal: str,
    impl_file: str,
    acceptance_criteria: list[str],
    complexity: str,
) -> str:
    """Format the implementation hints prompt for Pass 4.

    For HIGH complexity tasks, the prompt requests detailed implementation
    guidance including libraries with imports, code patterns, common pitfalls,
    and reference examples.

    For MEDIUM complexity tasks, the prompt requests just library names and
    one key code snippet.

    For LOW complexity tasks, the model should return empty hints.

    Args:
        task_title: Title of the atomic task.
        task_goal: Goal statement for the task.
        impl_file: Path to the implementation file.
        acceptance_criteria: List of acceptance criteria strings.
        complexity: Detected complexity level ("low", "medium", or "high").

    Returns:
        Formatted prompt string ready for LLM. Returns empty string for
        LOW complexity tasks since no hints are needed.
    """
    # Skip hint generation for low complexity tasks
    if complexity.lower() == "low":
        return ""

    return IMPLEMENTATION_HINTS_PROMPT.format(
        task_title=task_title,
        task_goal=task_goal,
        impl_file=impl_file,
        acceptance_criteria="\n".join(f"- {ac}" for ac in acceptance_criteria),
        complexity=complexity.upper(),
    )


def format_re_decomposition_prompt(
    task: "DecomposedTask",
    violations: list[str],
    strategy: str,
) -> str:
    """Format the re-decomposition prompt for splitting oversized tasks.

    Args:
        task: The DecomposedTask that failed validation.
        violations: List of atomicity violation messages.
        strategy: The split strategy to use (by_component, by_tests, by_size, balanced).

    Returns:
        Formatted prompt string ready for LLM.
    """
    return RE_DECOMPOSITION_PROMPT.format(
        task_key=task.task_key or "UNKNOWN",
        title=task.title,
        goal=task.goal,
        estimated_tests=task.estimated_tests,
        estimated_lines=task.estimated_lines,
        components=", ".join(task.components),
        violations="; ".join(violations),
        strategy=strategy,
    )
