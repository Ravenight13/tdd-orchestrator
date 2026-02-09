"""Prompt builder for TDD orchestrator pipeline stages.

This module provides the PromptBuilder class that generates focused prompts
for each stage of the TDD pipeline. Each stage has a specific role:

    RED: Write failing tests that define expected behavior
    GREEN: Implement minimal code to make tests pass
    VERIFY: Run pytest, ruff, and mypy to validate implementation
    FIX: Address any issues found during verification
    REFACTOR: Improve code quality (file size, structure)

The prompts are designed to be single-responsibility and focused, guiding
the LLM to produce predictable, verifiable outputs at each stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .prompt_templates import (
    FILE_STRUCTURE_CONSTRAINT,
    FIX_PROMPT_TEMPLATE,
    GREEN_PROMPT_TEMPLATE,
    GREEN_RETRY_TEMPLATE,
    IMPORT_CONVENTION,
    RED_FIX_PROMPT_TEMPLATE,
    RED_PROMPT_TEMPLATE,
    REFACTOR_PROMPT_TEMPLATE,
    STATIC_REVIEW_INSTRUCTIONS,
    TYPE_ANNOTATION_INSTRUCTIONS,
    VERIFY_PROMPT_TEMPLATE,
)

if TYPE_CHECKING:
    from .models import Stage


class PromptBuilder:
    """Build focused prompts for each TDD pipeline stage.

    This class provides static methods to generate stage-specific prompts
    that guide the LLM through the TDD workflow. Each method produces a
    prompt tailored to that stage's specific responsibilities.

    Usage:
        # Generate prompts for each stage
        red_prompt = PromptBuilder.red(task)
        green_prompt = PromptBuilder.green(task, test_output)
        verify_prompt = PromptBuilder.verify(task)
        fix_prompt = PromptBuilder.fix(task, issues)
        red_fix_prompt = PromptBuilder.red_fix(task, issues)

        # Or use the dispatcher
        prompt = PromptBuilder.build(Stage.RED, task)
    """

    @staticmethod
    def _parse_criteria(acceptance_criteria: str | list[str] | None) -> list[str]:
        """Parse acceptance criteria from string or list."""
        if acceptance_criteria is None:
            return []
        if isinstance(acceptance_criteria, list):
            return acceptance_criteria
        try:
            parsed = json.loads(acceptance_criteria)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _to_import_path(file_path: str) -> str:
        """Convert a file path to a Python import path, stripping src layout prefix."""
        import_path = file_path.replace("/", ".").replace(".py", "")
        if import_path.startswith("src."):
            import_path = import_path[4:]
        return import_path

    @staticmethod
    def _parse_module_exports(module_exports_raw: str | list[str] | None) -> list[str]:
        """Parse module_exports from string or list."""
        if module_exports_raw is None:
            return []
        if isinstance(module_exports_raw, list):
            return module_exports_raw
        try:
            parsed = json.loads(module_exports_raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def red(task: dict[str, Any], base_dir: Path | None = None) -> str:
        """Generate prompt for RED phase (write failing tests)."""
        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria"))
        criteria_text = (
            "\n".join(f"- {c}" for c in criteria) if criteria else "- No criteria specified"
        )

        impl_file = task.get("impl_file", "impl_file.py")
        import_path = PromptBuilder._to_import_path(impl_file)
        goal = task.get("goal", "")
        func_name = goal.split()[-1].lower() if goal else "function"

        module_exports = PromptBuilder._parse_module_exports(task.get("module_exports"))
        if module_exports:
            export_names = ", ".join(module_exports)
            import_hint = f"from {import_path} import {export_names}"
        else:
            import_hint = f"from {import_path} import {func_name}"

        module_exports_section = ""
        if module_exports:
            module_exports_section = (
                f"\n## MODULE EXPORTS (from spec)\n"
                f"The implementation file will export the following. "
                f"Write tests that import exactly these:\n"
                f"- Exports: {', '.join(module_exports)}\n"
                f"- Import: `{import_hint}`\n\n"
                f"Do NOT import from submodules. Do NOT invent new export names.\n"
            )

        test_file = task.get("test_file", "test_file.py")
        test_file_abs = str(base_dir / test_file) if base_dir else test_file

        return RED_PROMPT_TEMPLATE.format(
            goal=task.get("goal", "No goal specified"),
            criteria_text=criteria_text,
            module_exports_section=module_exports_section,
            test_file=test_file,
            impl_file=impl_file,
            import_hint=import_hint,
            import_convention=IMPORT_CONVENTION,
            static_review_instructions=STATIC_REVIEW_INSTRUCTIONS,
            test_file_abs=test_file_abs,
        )

    @staticmethod
    def green(task: dict[str, Any], test_output: str, base_dir: Path | None = None) -> str:
        """Generate prompt for GREEN phase (write implementation)."""
        truncated_output = test_output[:3000] if test_output else "No test output available"

        module_exports = PromptBuilder._parse_module_exports(task.get("module_exports"))
        impl_file = task.get("impl_file", "impl_file.py")
        import_path = PromptBuilder._to_import_path(impl_file)

        module_exports_section = ""
        if module_exports:
            exports_list = "\n".join(f"- {e}" for e in module_exports)
            module_exports_section = (
                f"\n## REQUIRED MODULE EXPORTS\n"
                f"Your implementation MUST export the following at module level:\n"
                f"{exports_list}\n\n"
                f"These must be importable via:\n"
                f"```python\n"
                f"from {import_path} import {', '.join(module_exports)}\n"
                f"```\n\n"
                f"## CONSTRAINTS\n"
                f"- Do NOT create a package directory (no __init__.py)\n"
                f"- Do NOT create nested namespaces\n"
                f"- ALL exports must be defined at module level\n"
                f"- If multiple classes, define them all in the single file\n"
            )

        impl_file_abs = str(base_dir / impl_file) if base_dir else impl_file

        return GREEN_PROMPT_TEMPLATE.format(
            goal=task.get("goal", "No goal specified"),
            test_file=task.get("test_file", "test_file.py"),
            truncated_output=truncated_output,
            impl_file=impl_file,
            impl_file_abs=impl_file_abs,
            module_exports_section=module_exports_section,
            file_structure_constraint=FILE_STRUCTURE_CONSTRAINT,
            import_convention=IMPORT_CONVENTION,
            type_annotation_instructions=TYPE_ANNOTATION_INSTRUCTIONS,
        )

    @staticmethod
    def build_green_retry(
        task: dict[str, Any],
        test_output: str,
        attempt: int,
        previous_failure: str,
    ) -> str:
        """Build GREEN prompt for retry attempt with failure context."""
        impl_file = task.get("impl_file", "")
        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria", "[]"))
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- See test file"

        truncated_failure = previous_failure[:3000] if previous_failure else "No output captured"
        truncated_test_output = test_output[:3000] if test_output else "No test output"

        return GREEN_RETRY_TEMPLATE.format(
            attempt=attempt,
            prev_attempt=attempt - 1,
            truncated_failure=truncated_failure,
            impl_file=impl_file,
            criteria_text=criteria_text,
            truncated_test_output=truncated_test_output,
            import_convention=IMPORT_CONVENTION,
        )

    @staticmethod
    def verify(task: dict[str, Any]) -> str:
        """Generate prompt for VERIFY phase (run quality checks)."""
        return VERIFY_PROMPT_TEMPLATE.format(
            title=task.get("title", "Unknown task"),
            task_key=task.get("task_key", "UNKNOWN"),
            test_file=task.get("test_file", "test_file.py"),
            impl_file=task.get("impl_file", "impl_file.py"),
        )

    @staticmethod
    def fix(task: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        """Generate prompt for FIX phase (address issues)."""
        issues_parts = []
        for i in issues:
            if "tool" in i and "output" in i:
                tool = i["tool"].upper()
                output = i["output"][:1000]
                issues_parts.append(f"### {tool} ERRORS:\n```\n{output}\n```")
            else:
                severity = i.get("severity", "unknown").upper()
                line = i.get("line", "?")
                desc = i.get("description", "No description")
                issues_parts.append(f"- [{severity}] Line {line}: {desc}")

        issues_text = "\n\n".join(issues_parts) if issues_parts else "- No issues specified"

        return FIX_PROMPT_TEMPLATE.format(
            goal=task.get("goal", "No goal specified"),
            impl_file=task.get("impl_file", "impl_file.py"),
            issues_text=issues_text,
        )

    @staticmethod
    def red_fix(task: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        """Generate prompt for RED_FIX phase (fix static review issues in tests)."""
        issues_text = "\n".join(
            f"- [{i.get('severity', 'error').upper()}] Line {i.get('line_number', '?')}: "
            f"{i.get('message', 'No description')}\n"
            f"  Code: `{i.get('code_snippet', '')}`"
            for i in issues
        )

        return RED_FIX_PROMPT_TEMPLATE.format(
            task_key=task.get("task_key", "UNKNOWN"),
            test_file=task.get("test_file", "test_file.py"),
            issues_text=issues_text,
        )

    @staticmethod
    def refactor(task: dict[str, Any], refactor_reasons: list[str]) -> str:
        """Generate prompt for REFACTOR phase (code quality cleanup)."""
        reasons_text = "\n".join(f"- {r}" for r in refactor_reasons) if refactor_reasons else "- No specific issues identified"

        return REFACTOR_PROMPT_TEMPLATE.format(
            title=task.get("title", "Unknown task"),
            task_key=task.get("task_key", "UNKNOWN"),
            impl_file=task.get("impl_file", "impl_file.py"),
            test_file=task.get("test_file", "test_file.py"),
            reasons_text=reasons_text,
        )

    @staticmethod
    def build(stage: Stage, task: dict[str, Any], **kwargs: Any) -> str:
        """Dispatcher method to build prompts for any stage."""
        from .models import Stage as StageEnum

        base_dir: Path | None = kwargs.pop("base_dir", None)

        if stage == StageEnum.RED:
            return PromptBuilder.red(task, base_dir=base_dir)

        if stage == StageEnum.GREEN:
            test_output = kwargs.get("test_output")
            if test_output is None:
                msg = "GREEN stage requires 'test_output' argument"
                raise ValueError(msg)

            attempt = kwargs.get("attempt", 1)
            if attempt > 1:
                previous_failure = kwargs.get("previous_failure", "")
                return PromptBuilder.build_green_retry(task, test_output, attempt, previous_failure)
            return PromptBuilder.green(task, test_output, base_dir=base_dir)

        if stage == StageEnum.VERIFY or stage == StageEnum.RE_VERIFY:
            return PromptBuilder.verify(task)

        if stage == StageEnum.FIX:
            issues = kwargs.get("issues")
            if issues is None:
                msg = "FIX stage requires 'issues' argument"
                raise ValueError(msg)
            return PromptBuilder.fix(task, issues)

        if stage == StageEnum.REFACTOR:
            refactor_reasons = kwargs.get("refactor_reasons")
            if refactor_reasons is None:
                msg = "REFACTOR stage requires 'refactor_reasons' argument"
                raise ValueError(msg)
            return PromptBuilder.refactor(task, refactor_reasons)

        if stage == StageEnum.RED_FIX:
            issues = kwargs.get("issues")
            if issues is None:
                msg = "RED_FIX stage requires 'issues' argument"
                raise ValueError(msg)
            return PromptBuilder.red_fix(task, issues)

        msg = f"Unsupported stage: {stage}"
        raise ValueError(msg)
