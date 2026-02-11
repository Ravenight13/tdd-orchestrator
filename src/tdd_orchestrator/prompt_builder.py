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

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .prompt_enrichment import (
    MAX_HINTS_CONTENT,
    MAX_IMPL_FILE_CONTENT,
    MAX_ISSUES_OUTPUT,
    MAX_TEST_FILE_CONTENT,
    MAX_TEST_OUTPUT,
    build_code_section,
    discover_sibling_tests,
    escape_braces,
    extract_impl_signatures,
    parse_criteria,
    parse_module_exports,
    read_conftest,
    read_file_safe,
    safe_absolute_path,
    to_import_path,
)
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

    # Keep backward-compatible aliases for any external code referencing these
    _parse_criteria = staticmethod(parse_criteria)
    _parse_module_exports = staticmethod(parse_module_exports)
    _to_import_path = staticmethod(to_import_path)
    _escape_braces = staticmethod(escape_braces)
    _read_file_safe = staticmethod(read_file_safe)
    _discover_sibling_tests = staticmethod(discover_sibling_tests)
    _read_conftest = staticmethod(read_conftest)
    _extract_impl_signatures = staticmethod(extract_impl_signatures)

    @staticmethod
    def red(task: dict[str, Any], base_dir: Path | None = None) -> str:
        """Generate prompt for RED phase (write failing tests)."""
        criteria = parse_criteria(task.get("acceptance_criteria"))
        criteria_text = (
            "\n".join(f"- {c}" for c in criteria) if criteria else "- No criteria specified"
        )

        impl_file = task.get("impl_file", "impl_file.py")
        import_path = to_import_path(impl_file)
        goal = task.get("goal", "")
        words = goal.split()
        func_name = words[-1].lower() if words else "function"

        module_exports = parse_module_exports(task.get("module_exports"))
        if module_exports:
            export_names = ", ".join(module_exports)
            import_hint = f"from {import_path} import {export_names}"
        else:
            import_hint = f"from {import_path} import {func_name}"

        module_exports_section = ""
        if module_exports:
            escaped_exports = [escape_braces(e) for e in module_exports]
            module_exports_section = (
                f"\n## MODULE EXPORTS (from spec)\n"
                f"The implementation file will export the following. "
                f"Write tests that import exactly these:\n"
                f"- Exports: {', '.join(escaped_exports)}\n"
                f"- Import: `{escape_braces(import_hint)}`\n\n"
                f"Do NOT import from submodules. Do NOT invent new export names.\n"
            )

        test_file = task.get("test_file", "test_file.py")
        test_file_abs = safe_absolute_path(base_dir, test_file)

        sibling_tests_section = discover_sibling_tests(
            base_dir, test_file, stage_hint="red",
        )
        existing_api_section = extract_impl_signatures(base_dir, impl_file)
        conftest_section = read_conftest(base_dir, test_file)

        return RED_PROMPT_TEMPLATE.format(
            goal=escape_braces(task.get("goal", "No goal specified")),
            criteria_text=escape_braces(criteria_text),
            module_exports_section=module_exports_section,
            existing_api_section=existing_api_section,
            sibling_tests_section=sibling_tests_section,
            conftest_section=conftest_section,
            test_file=escape_braces(test_file),
            impl_file=escape_braces(impl_file),
            import_hint=escape_braces(import_hint),
            import_convention=IMPORT_CONVENTION,
            static_review_instructions=STATIC_REVIEW_INSTRUCTIONS,
            test_file_abs=escape_braces(test_file_abs),
        )

    @staticmethod
    def green(task: dict[str, Any], test_output: str, base_dir: Path | None = None) -> str:
        """Generate prompt for GREEN phase (write implementation)."""
        truncated_output = test_output[:MAX_TEST_OUTPUT] if test_output else "No test output available"

        module_exports = parse_module_exports(task.get("module_exports"))
        impl_file = task.get("impl_file", "impl_file.py")
        import_path = to_import_path(impl_file)

        module_exports_section = ""
        if module_exports:
            escaped_exports = [escape_braces(e) for e in module_exports]
            exports_list = "\n".join(f"- {e}" for e in escaped_exports)
            escaped_import = escape_braces(
                f"from {import_path} import {', '.join(module_exports)}"
            )
            module_exports_section = (
                f"\n## REQUIRED MODULE EXPORTS\n"
                f"Your implementation MUST export the following at module level:\n"
                f"{exports_list}\n\n"
                f"These must be importable via:\n"
                f"```python\n"
                f"{escaped_import}\n"
                f"```\n\n"
                f"## CONSTRAINTS\n"
                f"- Do NOT create a package directory (no __init__.py)\n"
                f"- Do NOT create nested namespaces\n"
                f"- ALL exports must be defined at module level\n"
                f"- If multiple classes, define them all in the single file\n"
            )

        impl_file_abs = safe_absolute_path(base_dir, impl_file)

        # --- Build test contract section ---
        test_file = task.get("test_file", "test_file.py")
        raw_test = read_file_safe(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "# (test file not available -- use test failures below)",
        )
        escaped_test = escape_braces(raw_test)

        test_contract_section = (
            "\n## TEST SOURCE CODE (the contract your implementation MUST satisfy)\n"
            f"```python\n{escaped_test}\n```\n\n"
            "Read this carefully. Your implementation MUST:\n"
            "- Match every method name, property, and function signature exactly as tested\n"
            "- Match sync vs async (if tests use `await`, implement as `async def`)\n"
            "- Return the exact types tested by assertions\n"
            "- Accept the exact parameter signatures used in test calls\n"
        )

        criteria = parse_criteria(task.get("acceptance_criteria"))
        if criteria:
            criteria_lines = "\n".join(f"- {c}" for c in criteria)
            test_contract_section += (
                f"\n## ACCEPTANCE CRITERIA\n"
                f"{escape_braces(criteria_lines)}\n"
            )

        hints_raw = task.get("implementation_hints") or ""
        if isinstance(hints_raw, str) and hints_raw.strip():
            hints_text = hints_raw[:MAX_HINTS_CONTENT]
            test_contract_section += (
                f"\n## IMPLEMENTATION HINTS\n"
                f"{escape_braces(hints_text)}\n"
            )

        # --- Build existing impl section ---
        existing_impl_section = build_code_section(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT,
            "EXISTING IMPLEMENTATION (from prior task)",
            "This file already exists. PRESERVE all existing classes, methods, "
            "and exports while adding new functionality required by the tests.",
        )

        sibling_tests_section = discover_sibling_tests(base_dir, test_file)
        conftest_section = read_conftest(base_dir, test_file)

        return GREEN_PROMPT_TEMPLATE.format(
            goal=escape_braces(task.get("goal", "No goal specified")),
            test_file=escape_braces(test_file),
            truncated_output=escape_braces(truncated_output),
            impl_file=escape_braces(impl_file),
            impl_file_abs=escape_braces(impl_file_abs),
            module_exports_section=module_exports_section,
            existing_impl_section=existing_impl_section,
            sibling_tests_section=sibling_tests_section,
            conftest_section=conftest_section,
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
        criteria = parse_criteria(task.get("acceptance_criteria", "[]"))
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- See test file"

        truncated_failure = previous_failure[:MAX_TEST_OUTPUT] if previous_failure else "No output captured"
        truncated_test_output = test_output[:MAX_TEST_OUTPUT] if test_output else "No test output"

        # Build test contract section for retry
        test_file = task.get("test_file", "test_file.py")
        raw_test = read_file_safe(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "# (test file not available)",
        )
        escaped_test = escape_braces(raw_test)
        test_contract_section = (
            "\n### Test File Content (the contract)\n"
            f"```python\n{escaped_test}\n```\n"
        )

        # Module exports
        module_exports = parse_module_exports(task.get("module_exports"))
        import_path = to_import_path(impl_file)
        module_exports_section = ""
        if module_exports:
            escaped_exports = [escape_braces(e) for e in module_exports]
            exports_list = "\n".join(f"- {e}" for e in escaped_exports)
            escaped_import = escape_braces(
                f"from {import_path} import {', '.join(module_exports)}"
            )
            module_exports_section = (
                f"\n## REQUIRED MODULE EXPORTS\n"
                f"Your implementation MUST export the following at module level:\n"
                f"{exports_list}\n\n"
                f"Import: `{escaped_import}`\n"
            )

        # Existing implementation
        existing_impl_section = build_code_section(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT,
            "EXISTING IMPLEMENTATION",
            "Read this carefully before making changes:",
        )

        sibling_tests_section = discover_sibling_tests(base_dir, test_file)
        conftest_section = read_conftest(base_dir, test_file)

        return GREEN_RETRY_TEMPLATE.format(
            attempt=attempt,
            prev_attempt=attempt - 1,
            truncated_failure=escape_braces(truncated_failure),
            impl_file=escape_braces(impl_file),
            criteria_text=escape_braces(criteria_text),
            truncated_test_output=escape_braces(truncated_test_output),
            test_contract_section=test_contract_section,
            module_exports_section=module_exports_section,
            existing_impl_section=existing_impl_section,
            sibling_tests_section=sibling_tests_section,
            conftest_section=conftest_section,
            import_convention=IMPORT_CONVENTION,
        )

    @staticmethod
    def verify(task: dict[str, Any]) -> str:
        """Generate prompt for VERIFY phase (run quality checks)."""
        return VERIFY_PROMPT_TEMPLATE.format(
            title=escape_braces(task.get("title", "Unknown task")),
            task_key=escape_braces(task.get("task_key", "UNKNOWN")),
            test_file=escape_braces(task.get("test_file", "test_file.py")),
            impl_file=escape_braces(task.get("impl_file", "impl_file.py")),
        )

    @staticmethod
    def fix(
        task: dict[str, Any],
        issues: list[dict[str, Any]],
        base_dir: Path | None = None,
    ) -> str:
        """Generate prompt for FIX phase (address issues)."""
        issues_parts = []
        for i in issues:
            if "tool" in i and "output" in i:
                tool = i["tool"].upper()
                output = i["output"][:MAX_ISSUES_OUTPUT]
                issues_parts.append(f"### {tool} ERRORS:\n```\n{output}\n```")
            else:
                severity = i.get("severity", "unknown").upper()
                line = i.get("line", "?")
                desc = i.get("description", "No description")
                issues_parts.append(f"- [{severity}] Line {line}: {desc}")

        issues_text = "\n\n".join(issues_parts) if issues_parts else "- No issues specified"

        impl_file = task.get("impl_file", "impl_file.py")
        test_file = task.get("test_file", "test_file.py")

        # Read test file content
        test_content_section = build_code_section(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "TEST CONTRACT",
            "These are the tests your implementation must satisfy:",
        )

        # Read impl file content
        impl_content_section = build_code_section(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT,
            "CURRENT IMPLEMENTATION",
        )

        # Acceptance criteria
        criteria_section = ""
        criteria = parse_criteria(task.get("acceptance_criteria"))
        if criteria:
            criteria_lines = "\n".join(f"- {c}" for c in criteria)
            criteria_section = f"\n## ACCEPTANCE CRITERIA\n{escape_braces(criteria_lines)}\n"

        # Module exports
        module_exports_section = ""
        module_exports = parse_module_exports(task.get("module_exports"))
        if module_exports:
            exports_list = ", ".join(escape_braces(e) for e in module_exports)
            module_exports_section = (
                f"\n## MODULE EXPORTS\n"
                f"The implementation must export: {exports_list}\n"
            )

        # Sibling tests
        sibling_tests_section = discover_sibling_tests(base_dir, test_file)

        # Conftest
        conftest_section = read_conftest(base_dir, test_file)

        return FIX_PROMPT_TEMPLATE.format(
            goal=escape_braces(task.get("goal", "No goal specified")),
            impl_file=escape_braces(impl_file),
            issues_text=escape_braces(issues_text),
            test_content_section=test_content_section,
            impl_content_section=impl_content_section,
            criteria_section=criteria_section,
            module_exports_section=module_exports_section,
            sibling_tests_section=sibling_tests_section,
            conftest_section=conftest_section,
        )

    @staticmethod
    def red_fix(
        task: dict[str, Any],
        issues: list[dict[str, Any]],
        base_dir: Path | None = None,
    ) -> str:
        """Generate prompt for RED_FIX phase (fix static review issues in tests)."""
        issues_text = "\n".join(
            f"- [{i.get('severity', 'error').upper()}] Line {i.get('line_number', '?')}: "
            f"{i.get('message', 'No description')}\n"
            f"  Code: `{i.get('code_snippet', '')}`"
            for i in issues
        )

        goal = task.get("goal", "")
        goal_section = f"\n## TASK GOAL\n{escape_braces(goal)}\n" if goal else ""

        criteria = parse_criteria(task.get("acceptance_criteria"))
        criteria_section = ""
        if criteria:
            criteria_lines = "\n".join(f"- {c}" for c in criteria)
            criteria_section = f"\n## ACCEPTANCE CRITERIA\n{escape_braces(criteria_lines)}\n"

        impl_file = task.get("impl_file", "impl_file.py")
        import_hint = to_import_path(impl_file)

        # Enrichments requiring base_dir
        conftest_section = read_conftest(base_dir, task.get("test_file", ""))
        sibling_tests_section = discover_sibling_tests(
            base_dir, task.get("test_file", ""), stage_hint="red",
        )
        existing_api_section = extract_impl_signatures(base_dir, impl_file)

        return RED_FIX_PROMPT_TEMPLATE.format(
            task_key=escape_braces(task.get("task_key", "UNKNOWN")),
            test_file=escape_braces(task.get("test_file", "test_file.py")),
            issues_text=escape_braces(issues_text),
            goal_section=goal_section,
            criteria_section=criteria_section,
            import_hint=escape_braces(import_hint),
            conftest_section=conftest_section,
            sibling_tests_section=sibling_tests_section,
            existing_api_section=existing_api_section,
        )

    @staticmethod
    def refactor(
        task: dict[str, Any],
        refactor_reasons: list[str],
        base_dir: Path | None = None,
    ) -> str:
        """Generate prompt for REFACTOR phase (code quality cleanup)."""
        reasons_text = (
            "\n".join(f"- {r}" for r in refactor_reasons)
            if refactor_reasons
            else "- No specific issues identified"
        )

        impl_file = task.get("impl_file", "impl_file.py")
        test_file = task.get("test_file", "test_file.py")

        # Read current implementation
        impl_content_section = build_code_section(
            base_dir, impl_file, MAX_IMPL_FILE_CONTENT,
            "CURRENT IMPLEMENTATION",
        )

        # Read test content
        test_content_section = build_code_section(
            base_dir, test_file, MAX_TEST_FILE_CONTENT,
            "TEST CONTRACT",
            "These tests must continue to pass after refactoring:",
        )

        # Acceptance criteria
        criteria_section = ""
        criteria = parse_criteria(task.get("acceptance_criteria"))
        if criteria:
            criteria_lines = "\n".join(f"- {c}" for c in criteria)
            criteria_section = f"\n## ACCEPTANCE CRITERIA\n{escape_braces(criteria_lines)}\n"

        # Module exports
        module_exports_section = ""
        module_exports = parse_module_exports(task.get("module_exports"))
        if module_exports:
            exports_list = ", ".join(escape_braces(e) for e in module_exports)
            module_exports_section = (
                f"\n## MODULE EXPORTS (must be preserved)\n"
                f"The implementation must continue to export: {exports_list}\n"
            )

        # Discover sibling tests
        sibling_tests_section = discover_sibling_tests(base_dir, test_file)
        if sibling_tests_section:
            sibling_tests_section += (
                "\nRefactoring must not change behavior observed by these tests.\n"
            )

        return REFACTOR_PROMPT_TEMPLATE.format(
            title=escape_braces(task.get("title", "Unknown task")),
            task_key=escape_braces(task.get("task_key", "UNKNOWN")),
            impl_file=escape_braces(impl_file),
            test_file=escape_braces(test_file),
            reasons_text=escape_braces(reasons_text),
            impl_content_section=impl_content_section,
            test_content_section=test_content_section,
            criteria_section=criteria_section,
            module_exports_section=module_exports_section,
            sibling_tests_section=sibling_tests_section,
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
            return PromptBuilder.fix(task, issues, base_dir=base_dir)

        if stage == StageEnum.REFACTOR:
            refactor_reasons = kwargs.get("refactor_reasons")
            if refactor_reasons is None:
                msg = "REFACTOR stage requires 'refactor_reasons' argument"
                raise ValueError(msg)
            return PromptBuilder.refactor(task, refactor_reasons, base_dir=base_dir)

        if stage == StageEnum.RED_FIX:
            issues = kwargs.get("issues")
            if issues is None:
                msg = "RED_FIX stage requires 'issues' argument"
                raise ValueError(msg)
            return PromptBuilder.red_fix(task, issues, base_dir=base_dir)

        msg = f"Unsupported stage: {stage}"
        raise ValueError(msg)
