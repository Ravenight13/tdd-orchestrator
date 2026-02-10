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
from typing import TYPE_CHECKING, Any, Literal

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

MAX_TEST_FILE_CONTENT = 8000
MAX_IMPL_FILE_CONTENT = 6000
MAX_HINTS_CONTENT = 3000
MAX_SIBLING_FILES = 5
MAX_SIBLING_HINT_LINES = 10


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
    def _escape_braces(text: str) -> str:
        """Escape curly braces for safe use in str.format() templates."""
        return text.replace("{", "{{").replace("}", "}}")

    @staticmethod
    def _discover_sibling_tests(
        base_dir: Path | None,
        test_file: str,
        stage_hint: Literal["green", "red"] = "green",
    ) -> str:
        """Discover sibling test files and extract async contract hints.

        Globs test_*.py in the test file's parent directory, reads each sibling
        for `await` patterns, and builds a prompt section warning the worker
        about existing async contracts.

        Args:
            base_dir: Project root for resolving paths.
            test_file: The current task's test file (excluded from results).
            stage_hint: Controls header/description language.
                ``"green"`` (default) warns about not breaking siblings.
                ``"red"`` instructs matching existing contracts.

        Returns:
            Prompt section string (empty string if no siblings found).
        """
        if not base_dir or not test_file:
            return ""

        test_path = base_dir / test_file
        parent = test_path.parent
        if not parent.exists():
            return ""

        siblings = sorted(
            p for p in parent.glob("test_*.py")
            if p.name != test_path.name
        )
        if not siblings:
            return ""

        sections: list[str] = []
        for sib in siblings[:MAX_SIBLING_FILES]:
            rel = str(sib.relative_to(base_dir))
            hints: list[str] = []
            try:
                lines = sib.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    stripped = line.strip()
                    if "await " in stripped and len(hints) < MAX_SIBLING_HINT_LINES:
                        hints.append(f"    {stripped}")
            except OSError:
                continue

            if hints:
                hint_block = "\n".join(hints)
                sections.append(f"- `{rel}` (async contracts):\n{hint_block}")
            else:
                sections.append(f"- `{rel}`")

        sibling_list = "\n".join(sections)

        if stage_hint == "red":
            return (
                "\n## SIBLING TESTS (MATCH EXISTING CONTRACTS)\n"
                "Other test files target the SAME implementation module. "
                "These tests have already established the API contract "
                "(function signatures, sync/async, parameter names). "
                "Your tests MUST use the SAME signatures.\n"
                "If a sibling test uses `await`, your tests MUST also use "
                "`await` for that function.\n\n"
                f"{sibling_list}\n"
            )

        return (
            "\n## SIBLING TESTS (DO NOT BREAK)\n"
            "Other test files target the SAME implementation module. "
            "Your changes MUST NOT break these existing tests.\n"
            "If a sibling test uses `await`, the method MUST remain `async def`.\n\n"
            f"{sibling_list}\n"
        )

    MAX_IMPL_SIGNATURES = 30

    @staticmethod
    def _extract_impl_signatures(base_dir: Path | None, impl_file: str) -> str:
        """Extract function/class signatures from an existing implementation file.

        Reads the implementation file and extracts lines starting with ``def ``,
        ``async def ``, or ``class `` (plus preceding decorator lines).  The
        result is wrapped in a prompt section that instructs the LLM to match
        these exact signatures.

        Args:
            base_dir: Project root for resolving paths.
            impl_file: Relative path to the implementation file.

        Returns:
            Formatted prompt section, or empty string if file doesn't exist
            or contains no signatures.
        """
        raw = PromptBuilder._read_file_safe(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT, "",
        )
        if not raw:
            return ""

        lines = raw.splitlines()
        signatures: list[str] = []
        prev_line = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("def ", "async def ", "class ")):
                if prev_line.strip().startswith("@"):
                    signatures.append(prev_line)
                signatures.append(line)
                if len(signatures) >= PromptBuilder.MAX_IMPL_SIGNATURES:
                    break
            prev_line = line

        if not signatures:
            return ""

        sig_block = PromptBuilder._escape_braces("\n".join(signatures))
        return (
            "\n## EXISTING API SIGNATURES\n"
            "The implementation file already exists. Your tests MUST use "
            "these exact function signatures. Do NOT assume different "
            "parameter names, types, or sync/async.\n"
            f"```python\n{sig_block}\n```\n"
        )

    @staticmethod
    def _read_file_safe(
        base_dir: Path | None,
        relative_path: str,
        max_chars: int,
        fallback: str,
    ) -> str:
        """Read a file with truncation and fallback."""
        if not base_dir or not relative_path:
            return fallback
        file_path = (base_dir / relative_path).resolve()
        try:
            file_path.relative_to(base_dir.resolve())
        except ValueError:
            return fallback
        if not file_path.exists():
            return fallback
        try:
            raw = file_path.read_text(encoding="utf-8")
            if len(raw) > max_chars:
                return raw[:max_chars] + "\n# ... (truncated)"
            return raw
        except OSError:
            return fallback

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

        sibling_tests_section = PromptBuilder._discover_sibling_tests(
            base_dir, test_file, stage_hint="red",
        )
        existing_api_section = PromptBuilder._extract_impl_signatures(base_dir, impl_file)

        return RED_PROMPT_TEMPLATE.format(
            goal=task.get("goal", "No goal specified"),
            criteria_text=criteria_text,
            module_exports_section=module_exports_section,
            existing_api_section=existing_api_section,
            sibling_tests_section=sibling_tests_section,
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

        # --- Build test contract section ---
        test_file = task.get("test_file", "test_file.py")
        raw_test = PromptBuilder._read_file_safe(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "# (test file not available -- use test failures below)",
        )
        escaped_test = PromptBuilder._escape_braces(raw_test)

        test_contract_section = (
            "\n## TEST SOURCE CODE (the contract your implementation MUST satisfy)\n"
            f"```python\n{escaped_test}\n```\n\n"
            "Read this carefully. Your implementation MUST:\n"
            "- Match every method name, property, and function signature exactly as tested\n"
            "- Match sync vs async (if tests use `await`, implement as `async def`)\n"
            "- Return the exact types tested by assertions\n"
            "- Accept the exact parameter signatures used in test calls\n"
        )

        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria"))
        if criteria:
            criteria_lines = "\n".join(f"- {c}" for c in criteria)
            test_contract_section += (
                f"\n## ACCEPTANCE CRITERIA\n"
                f"{PromptBuilder._escape_braces(criteria_lines)}\n"
            )

        hints_raw = task.get("implementation_hints") or ""
        if isinstance(hints_raw, str) and hints_raw.strip():
            hints_text = hints_raw[:MAX_HINTS_CONTENT]
            test_contract_section += (
                f"\n## IMPLEMENTATION HINTS\n"
                f"{PromptBuilder._escape_braces(hints_text)}\n"
            )

        # --- Build existing impl section ---
        existing_impl_section = ""
        raw_impl = PromptBuilder._read_file_safe(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT, "",
        )
        if raw_impl:
            escaped_impl = PromptBuilder._escape_braces(raw_impl)
            existing_impl_section = (
                "\n## EXISTING IMPLEMENTATION (from prior task)\n"
                "This file already exists. PRESERVE all existing classes, methods, "
                "and exports while adding new functionality required by the tests.\n"
                f"```python\n{escaped_impl}\n```\n"
            )

        sibling_tests_section = PromptBuilder._discover_sibling_tests(base_dir, test_file)

        return GREEN_PROMPT_TEMPLATE.format(
            goal=task.get("goal", "No goal specified"),
            test_file=test_file,
            truncated_output=truncated_output,
            impl_file=impl_file,
            impl_file_abs=impl_file_abs,
            module_exports_section=module_exports_section,
            existing_impl_section=existing_impl_section,
            sibling_tests_section=sibling_tests_section,
            test_contract_section=test_contract_section,
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
        base_dir: Path | None = None,
    ) -> str:
        """Build GREEN prompt for retry attempt with failure context."""
        impl_file = task.get("impl_file", "")
        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria", "[]"))
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- See test file"

        truncated_failure = previous_failure[:3000] if previous_failure else "No output captured"
        truncated_test_output = test_output[:3000] if test_output else "No test output"

        # Build test contract section for retry
        test_file = task.get("test_file", "test_file.py")
        raw_test = PromptBuilder._read_file_safe(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "# (test file not available)",
        )
        escaped_test = PromptBuilder._escape_braces(raw_test)
        test_contract_section = (
            "\n### Test File Content (the contract)\n"
            f"```python\n{escaped_test}\n```\n"
        )

        sibling_tests_section = PromptBuilder._discover_sibling_tests(base_dir, test_file)

        return GREEN_RETRY_TEMPLATE.format(
            attempt=attempt,
            prev_attempt=attempt - 1,
            truncated_failure=truncated_failure,
            impl_file=impl_file,
            criteria_text=criteria_text,
            truncated_test_output=truncated_test_output,
            test_contract_section=test_contract_section,
            sibling_tests_section=sibling_tests_section,
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
                return PromptBuilder.build_green_retry(
                    task, test_output, attempt, previous_failure, base_dir=base_dir,
                )
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
