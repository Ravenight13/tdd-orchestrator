"""PRD template generator for TDD Orchestrator.

Generates opinionated PRD template files aligned with what the
decomposition parser (decomposition/parser.py) expects, so users
don't have to guess the format.
"""

from __future__ import annotations


def generate_prd_template(
    name: str,
    *,
    phases: int = 3,
    with_module_api: bool = False,
) -> str:
    """Generate a PRD template string matching the spec parser format.

    Args:
        name: Feature name for the title.
        phases: Number of phase/cycle stubs to generate.
        with_module_api: Include MODULE API SPECIFICATION section.

    Returns:
        Complete PRD template string.
    """
    sections = [
        _title_section(name),
        _functional_requirements_section(),
        _non_functional_requirements_section(),
        _acceptance_criteria_section(),
        _implementation_plan_section(phases),
        _module_structure_section(),
        _dependency_changes_section(),
    ]
    if with_module_api:
        sections.append(_module_api_section())
    return "\n\n".join(sections) + "\n"


def _title_section(name: str) -> str:
    """Generate the decorative title section."""
    title = f"{name} - [DESCRIPTION]"
    underline = "=" * len(title)
    return f"{title}\n{underline}"


def _functional_requirements_section() -> str:
    """Generate FUNCTIONAL REQUIREMENTS section with stub entries."""
    header = "FUNCTIONAL REQUIREMENTS"
    underline = "=" * len(header)
    return f"""{header}
{underline}

FR-1: [Requirement Title]
  [Describe what the system must do]
  FR-1.1: [Sub-requirement]
    [Details of sub-requirement]

FR-2: [Requirement Title]
  [Describe what the system must do]"""


def _non_functional_requirements_section() -> str:
    """Generate NON-FUNCTIONAL REQUIREMENTS section with stub entries."""
    header = "NON-FUNCTIONAL REQUIREMENTS"
    underline = "=" * len(header)
    return f"""{header}
{underline}

NFR-1: [Performance / Security / Reliability Title]
  [Describe the non-functional constraint]

NFR-2: [Performance / Security / Reliability Title]
  [Describe the non-functional constraint]"""


def _acceptance_criteria_section() -> str:
    """Generate ACCEPTANCE CRITERIA section with Gherkin stubs."""
    header = "ACCEPTANCE CRITERIA"
    underline = "=" * len(header)
    return f"""{header}
{underline}

AC-1: [Scenario Title]
  GIVEN [initial condition]
  WHEN [user action]
  THEN [expected outcome]
  AND [additional assertion]

AC-2: [Scenario Title]
  GIVEN [initial condition]
  WHEN [user action]
  THEN [expected outcome]"""


def _implementation_plan_section(phases: int) -> str:
    """Generate IMPLEMENTATION PLAN section with phase/cycle stubs."""
    header = "IMPLEMENTATION PLAN"
    underline = "=" * len(header)
    parts = [f"{header}\n{underline}"]
    for phase_num in range(1, phases + 1):
        cycle_block = _phase_block(phase_num)
        parts.append(cycle_block)
    return "\n\n".join(parts)


def _phase_block(phase_num: int) -> str:
    """Generate a single phase block with one TDD cycle stub."""
    return f"""### Phase {phase_num}: [Phase Title]

**TDD Cycle {phase_num}: [Cycle Title]**
  - [Component 1]
  - [Component 2]
  Tests: 8-10
  Module Hint: src/[module]/[file].py"""


def _module_structure_section() -> str:
    """Generate MODULE STRUCTURE section."""
    header = "MODULE STRUCTURE"
    underline = "-" * len(header)
    return f"""{header}
{underline}

src/
  [module_dir]/
    __init__.py
    [file].py"""


def _dependency_changes_section() -> str:
    """Generate DEPENDENCY CHANGES section."""
    header = "DEPENDENCY CHANGES"
    underline = "=" * len(header)
    return f"""{header}
{underline}

[project.optional-dependencies]
[extra_name] = ["package>=version"]"""


def _module_api_section() -> str:
    """Generate MODULE API SPECIFICATION section."""
    header = "MODULE API SPECIFICATION"
    underline = "=" * len(header)
    return f"""{header}
{underline}

src/[module]/[file].py:
  exports:
    - [ClassName] (class): [Description]
  import_pattern: direct
  test_import: from [module].[file] import [ClassName]"""
