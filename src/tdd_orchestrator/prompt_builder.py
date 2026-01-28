"""Prompt builder for TDD orchestrator pipeline stages.

This module provides the PromptBuilder class that generates focused prompts
for each stage of the TDD pipeline. Each stage has a specific role:

    RED: Write failing tests that define expected behavior
    GREEN: Implement minimal code to make tests pass
    VERIFY: Run pytest, ruff, and mypy to validate implementation
    FIX: Address any issues found during verification

The prompts are designed to be single-responsibility and focused, guiding
the LLM to produce predictable, verifiable outputs at each stage.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

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
        """Parse acceptance criteria from string or list.

        Args:
            acceptance_criteria: JSON string or list of criteria.

        Returns:
            List of acceptance criteria strings.
        """
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
    def _parse_module_exports(module_exports_raw: str | list[str] | None) -> list[str]:
        """Parse module_exports from string or list.

        Args:
            module_exports_raw: JSON string or list of export names.

        Returns:
            List of export name strings.
        """
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
    def red(task: dict[str, Any]) -> str:
        """Generate prompt for RED phase (write failing tests).

        This prompt instructs the LLM to write pytest tests that define
        the expected behavior. Tests should fail initially because the
        implementation doesn't exist yet.

        Args:
            task: Task dict with keys:
                - task_key: Unique task identifier
                - title: Human-readable task title
                - goal: What this task accomplishes
                - test_file: Path to test file to create
                - acceptance_criteria: JSON list or list of testable criteria
                - module_exports: JSON list or list of export names (PLAN9)

        Returns:
            Formatted prompt string for the RED phase.
        """
        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria"))
        criteria_text = (
            "\n".join(f"- {c}" for c in criteria) if criteria else "- No criteria specified"
        )

        # Derive the import path from impl_file
        impl_file = task.get("impl_file", "impl_file.py")
        # Convert path like "src/tdd/add.py" to import path "src.tdd.add"
        import_path = impl_file.replace("/", ".").replace(".py", "")
        # Extract function name from goal (simple heuristic)
        goal = task.get("goal", "")
        func_name = goal.split()[-1].lower() if goal else "function"

        # PLAN9: Extract module_exports for import guidance
        module_exports = PromptBuilder._parse_module_exports(task.get("module_exports"))

        # PLAN9: Use module_exports if available, else fall back to heuristic
        if module_exports:
            export_names = ", ".join(module_exports)
            import_hint = f"from {import_path} import {export_names}"
        else:
            import_hint = f"from {import_path} import {func_name}"

        # PLAN9: Add section to prompt when module_exports is present
        module_exports_section = ""
        if module_exports:
            module_exports_section = f"""
## MODULE EXPORTS (from spec)
The implementation file will export the following. Write tests that import exactly these:
- Exports: {", ".join(module_exports)}
- Import: `{import_hint}`

Do NOT import from submodules. Do NOT invent new export names.
"""

        return f"""You are a test writer. Your ONLY job is to write pytest tests.

## GOAL
{task.get("goal", "No goal specified")}

## ACCEPTANCE CRITERIA
{criteria_text}
{module_exports_section}
## FILES
- **Test file to create**: {task.get("test_file", "test_file.py")}
- **Implementation will be at**: {impl_file}
- **Import path**: `{import_hint}`

## REQUIREMENTS
1. Write a pytest test class with test methods
2. Each acceptance criterion should have at least one test
3. Include edge cases (empty input, invalid input, boundary conditions)
4. Tests should FAIL initially because implementation doesn't exist
5. Use descriptive test names: test_<behavior>_when_<condition>
6. Import from the EXACT path shown above: `{import_hint}`

## STATIC REVIEW REQUIREMENTS (CRITICAL - your tests will be reviewed for these)
Your test file will be automatically checked. Tests that fail these checks will be rejected:

1. **Every test MUST have assertions** - No test function without `assert` statements
   ```python
   # WRONG - missing assertion
   def test_add():
       result = add(1, 2)
       print(result)  # No assert!

   # CORRECT
   def test_add():
       result = add(1, 2)
       assert result == 3
   ```

2. **Assertions must be meaningful** - No empty assertions like `assert result`
   ```python
   # WRONG - empty assertion
   assert result  # What should it equal?

   # CORRECT - explicit expectation
   assert result == expected_value
   assert result is not None
   assert len(result) == 3
   ```

3. **Guard against None in lambdas/comprehensions**
   ```python
   # WRONG - will fail if c is None
   lambda c: [x for x in c]

   # CORRECT - None guard
   lambda c: [x for x in c] if c else []
   ```

4. **Guard method calls on potentially None values**
   ```python
   # WRONG - unguarded method call
   result.lower()

   # CORRECT - guarded
   result.lower() if result else ""
   ```

5. **No TODO/FIXME comments** - Complete your implementation
6. **No print statements** - Use assertions instead
7. **No bare except clauses** - Use specific exceptions

## IMPORTANT
- ONLY create the test file at the EXACT path: {task.get("test_file", "test_file.py")}
- Do NOT write any implementation code
- Do NOT create any other files
- Tests should fail with ImportError or NameError (function doesn't exist)
- Use the EXACT import path: `{import_hint}`

Write the test file now using the Write tool."""

    @staticmethod
    def green(task: dict[str, Any], test_output: str) -> str:
        """Generate prompt for GREEN phase (write implementation).

        This prompt instructs the LLM to write minimal implementation code
        that makes all tests pass. The focus is on making tests pass,
        not on perfect code.

        Args:
            task: Task dict with keys:
                - task_key: Unique task identifier
                - title: Human-readable task title
                - goal: What this task accomplishes
                - test_file: Path to test file
                - impl_file: Path to implementation file to create
                - module_exports: JSON list or list of export names (PLAN9)

            test_output: Output from running pytest showing failures.

        Returns:
            Formatted prompt string for the GREEN phase.
        """
        # Truncate test output to avoid context overflow
        truncated_output = test_output[:3000] if test_output else "No test output available"

        # PLAN9: Extract module_exports
        module_exports = PromptBuilder._parse_module_exports(task.get("module_exports"))

        # Derive import path from impl_file for export requirements section
        impl_file = task.get("impl_file", "impl_file.py")
        import_path = impl_file.replace("/", ".").replace(".py", "")

        # PLAN9: Add export requirements section when module_exports is present
        module_exports_section = ""
        if module_exports:
            exports_list = "\n".join(f"- {e}" for e in module_exports)
            module_exports_section = f"""
## REQUIRED MODULE EXPORTS
Your implementation MUST export the following at module level:
{exports_list}

These must be importable via:
```python
from {import_path} import {", ".join(module_exports)}
```

## CONSTRAINTS
- Do NOT create a package directory (no __init__.py)
- Do NOT create nested namespaces
- ALL exports must be defined at module level
- If multiple classes, define them all in the single file
"""

        return f"""You are an implementer. Your ONLY job is to make the tests pass.

## GOAL
{task.get("goal", "No goal specified")}

## TEST FILE
{task.get("test_file", "test_file.py")}

## CURRENT TEST FAILURES
```
{truncated_output}
```

## OUTPUT FILE (EXACT PATH REQUIRED)
You MUST create the implementation file at EXACTLY this path:

**Full path**: `{impl_file}`

⚠️ CRITICAL:
- Use the EXACT path shown above with the Write tool
- Do NOT modify the path in any way
- Do NOT create subdirectories or packages
- The path is relative to the repository root
{module_exports_section}
## CRITICAL FILE STRUCTURE CONSTRAINT
- Create a SINGLE MODULE FILE at the EXACT path shown above
- Do NOT create a package directory (folder with __init__.py)
- Do NOT create multiple files or subdirectories
- The verification system will FAIL if the exact file path doesn't exist
- If you need multiple classes, put them ALL in the single module file
- Example: If impl_file is "src/frontend/htmx/button.py", create EXACTLY that file
- WRONG: Creating "frontend/htmx/button.py" (missing src/)
- WRONG: Creating "src/frontend/htmx/button/__init__.py" (package instead of module)

## REQUIREMENTS
1. Write MINIMAL code to pass all tests
2. Follow the test assertions exactly
3. Do NOT add extra functionality beyond what tests require
4. Do NOT modify the test file
5. Include FULL TYPE ANNOTATIONS on ALL:
   - Function parameters
   - Function return types (including `-> None` for void functions)
   - Class attributes in __init__
   - Variables that mypy cannot infer

## TYPE ANNOTATIONS (MANDATORY - mypy strict mode)
Your code will be verified with mypy in strict mode. ALL of these must have type annotations:

1. **Function parameters and return types**:
```python
# WRONG
def process(data):
    return data.upper()

# CORRECT
def process(data: str) -> str:
    return data.upper()
```

2. **Class attributes**:
```python
# WRONG
class Button:
    def __init__(self, label):
        self.label = label

# CORRECT
class Button:
    def __init__(self, label: str) -> None:
        self.label: str = label
```

3. **Optional and Union types**:
```python
# WRONG
def find(items, default=None):
    return items[0] if items else default

# CORRECT
from typing import Optional, TypeVar
T = TypeVar('T')
def find(items: list[T], default: T | None = None) -> T | None:
    return items[0] if items else default
```

4. **Dictionary and List types**:
```python
# WRONG
def get_config():
    return {{"key": "value"}}

# CORRECT
def get_config() -> dict[str, str]:
    return {{"key": "value"}}
```

⚠️ If you see mypy errors like "missing type annotation", add the annotation BEFORE submitting.

## IMPORTANT
- ONLY create/modify the implementation file
- Focus on making tests pass, nothing more
- If tests expect specific behavior, implement exactly that
- ALL functions MUST have type annotations (mypy strict mode is enabled)

Write the implementation now using the Write tool."""

    @staticmethod
    def build_green_retry(
        task: dict[str, Any],
        test_output: str,
        attempt: int,
        previous_failure: str,
    ) -> str:
        """Build GREEN prompt for retry attempt with failure context.

        Key insight from Ralph Wiggum: The LLM sees its previous work via
        file contents, but explicitly providing failure details in the
        prompt accelerates convergence.

        Args:
            task: Task dict with impl_file, acceptance_criteria, etc.
            test_output: Original test output from RED stage.
            attempt: Current attempt number (2, 3, etc.).
            previous_failure: Test failure output from previous attempt.

        Returns:
            Formatted retry prompt with failure analysis guidance.
        """
        impl_file = task.get("impl_file", "")
        criteria = PromptBuilder._parse_criteria(task.get("acceptance_criteria", "[]"))
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- See test file"

        # Truncate previous failure to prevent context overflow
        truncated_failure = previous_failure[:3000] if previous_failure else "No output captured"
        truncated_test_output = test_output[:3000] if test_output else "No test output"

        return f"""## GREEN Stage - Retry Attempt {attempt}

Your previous implementation attempt FAILED. The tests are not passing.

### Test Failure Output (from attempt {attempt - 1})
```
{truncated_failure}
```

### What Went Wrong
Review the test output above. Common issues include:
- Missing imports
- Incorrect return types
- Logic errors in the implementation
- Edge cases not handled

### Your Task
1. READ the existing implementation file: {impl_file}
2. ANALYZE the test failure output above
3. FIX the implementation to make ALL tests pass
4. The tests are correct - do not modify them

### Acceptance Criteria
{criteria_text}

### Important
- Focus on fixing the SPECIFIC failures shown above
- Do not start over - iterate on your existing code
- Try a DIFFERENT approach if the same fix keeps failing
- Run the tests after making changes to verify they pass

### Original Test Output (RED stage)
```
{truncated_test_output}
```
"""

    @staticmethod
    def verify(task: dict[str, Any]) -> str:
        """Generate prompt for VERIFY phase (run quality checks).

        This prompt instructs the LLM to run verification tools (pytest,
        ruff, mypy) and report the results. The VERIFY phase validates
        that the implementation meets quality standards.

        Args:
            task: Task dict with keys:
                - task_key: Unique task identifier
                - title: Human-readable task title
                - test_file: Path to test file
                - impl_file: Path to implementation file

        Returns:
            Formatted prompt string for the VERIFY phase.
        """
        return f"""You are a code verifier. Run quality checks on the implementation.

## TASK
{task.get("title", "Unknown task")} ({task.get("task_key", "UNKNOWN")})

## FILES TO VERIFY
- Test file: {task.get("test_file", "test_file.py")}
- Implementation: {task.get("impl_file", "impl_file.py")}

## VERIFICATION STEPS
1. Run pytest on the test file
2. Run ruff check on the implementation file
3. Run mypy on the implementation file

## REQUIREMENTS
1. Execute each verification tool
2. Capture the output from each tool
3. Report any failures or issues found

## OUTPUT FORMAT
After running all checks, summarize:
- pytest: PASS/FAIL (X tests passed, Y failed)
- ruff: PASS/FAIL (X issues found)
- mypy: PASS/FAIL (X errors found)

Run the verification checks now using the Bash tool."""

    @staticmethod
    def fix(task: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        """Generate prompt for FIX phase (address issues).

        This prompt instructs the LLM to fix specific issues found during
        verification. Each issue is listed with severity and description
        to guide the fixes.

        Args:
            task: Task dict with keys:
                - task_key: Unique task identifier
                - title: Human-readable task title
                - goal: What this task accomplishes
                - impl_file: Path to implementation file

            issues: List of issue dicts, each with:
                - severity: critical/major/minor
                - description: What needs to be fixed
                - line: Optional line number

        Returns:
            Formatted prompt string for the FIX phase.
        """
        # Format issues - handle both old format (severity/description) and new format (tool/output)
        issues_parts = []
        for i in issues:
            if "tool" in i and "output" in i:
                # New format from CodeVerifier: {"tool": "mypy", "output": "..."}
                tool = i["tool"].upper()
                output = i["output"][:1000]  # Truncate long outputs
                issues_parts.append(f"### {tool} ERRORS:\n```\n{output}\n```")
            else:
                # Old format: {"severity": "...", "description": "...", "line": ...}
                severity = i.get("severity", "unknown").upper()
                line = i.get("line", "?")
                desc = i.get("description", "No description")
                issues_parts.append(f"- [{severity}] Line {line}: {desc}")

        issues_text = "\n\n".join(issues_parts) if issues_parts else "- No issues specified"

        return f"""You are a code fixer. Fix the identified issues in this implementation.

## GOAL
{task.get("goal", "No goal specified")}

## IMPLEMENTATION FILE
{task.get("impl_file", "impl_file.py")}

## ISSUES TO FIX
{issues_text}

## COMMON FIXES

### For mypy "missing type annotation" errors:
```python
# BEFORE (wrong)
def func(a, b):
    return a + b

# AFTER (correct)
def func(a: int, b: int) -> int:
    return a + b
```

### For ruff import errors:
- Add missing imports at the top of the file
- Remove unused imports

### For ruff formatting errors:
- Fix line length (max 88 chars)
- Add missing blank lines between functions

## REQUIREMENTS
1. Fix ALL issues listed above
2. Do NOT break existing functionality (tests must still pass)
3. Do NOT add new features
4. Keep changes minimal and focused
5. Ensure ALL functions have type annotations

## IMPORTANT
- ONLY modify the implementation file
- Each fix should address a specific issue
- Preserve existing behavior that isn't broken
- After fixing, the code must pass pytest, ruff, AND mypy

Fix the issues now using the Edit tool."""

    @staticmethod
    def red_fix(task: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        """Generate prompt for RED_FIX phase (fix static review issues in tests).

        This prompt instructs the LLM to fix specific static review issues
        found in the RED stage test file. The key constraint is to fix
        ONLY the flagged issues without changing test behavior.

        Args:
            task: Task dict with keys:
                - task_key: Unique task identifier
                - test_file: Path to test file to fix

            issues: List of issue dicts, each with:
                - pattern: The check that failed (e.g., "missing_assertion")
                - line_number: Line where issue was found
                - message: Human-readable description
                - severity: "error" or "warning"
                - code_snippet: The offending code

        Returns:
            Formatted prompt string for the RED_FIX phase.
        """
        # Format issues for the prompt
        issues_text = "\n".join(
            f"- [{i.get('severity', 'error').upper()}] Line {i.get('line_number', '?')}: "
            f"{i.get('message', 'No description')}\n"
            f"  Code: `{i.get('code_snippet', '')}`"
            for i in issues
        )

        return f"""You are a test fixer. Fix the static review issues in this test file.

## TASK
{task.get("task_key", "UNKNOWN")} - Fix static review issues

## TEST FILE TO FIX
{task.get("test_file", "test_file.py")}

## ISSUES TO FIX
{issues_text}

## CONSTRAINTS (CRITICAL)
1. **ONLY fix the specific lines flagged** - do not change test behavior
2. **PRESERVE test intent** - tests should still fail (no implementation exists)
3. **DO NOT modify assertions** unless the assertion itself is the issue
4. **DO NOT add implementation code** - this is test-only
5. **DO NOT delete test functions** - fix them instead

## COMMON FIXES

### For "missing_assertion" errors:
```python
# BEFORE (wrong - no assertion)
def test_something():
    result = calculate(5)
    print(result)  # Forgot assert!

# AFTER (correct)
def test_something():
    result = calculate(5)
    assert result == expected_value
```

### For "empty_assertion" warnings:
```python
# BEFORE (wrong - meaningless assertion)
def test_something():
    result = calculate(5)
    assert result  # What should it equal?

# AFTER (correct)
def test_something():
    result = calculate(5)
    assert result == 10
```

### For lambda iteration issues:
```python
# BEFORE (wrong - no None guard)
lambda c: [x for x in c]

# AFTER (correct)
lambda c: [x for x in c] if c else []
```

## EXPECTED OUTCOME
- All flagged issues resolved
- Test file still fails when run (expected - RED stage)
- No new issues introduced

Fix the issues now using the Edit tool."""

    @staticmethod
    def build(stage: Stage, task: dict[str, Any], **kwargs: Any) -> str:
        """Dispatcher method to build prompts for any stage.

        This method routes to the appropriate stage-specific prompt builder
        based on the stage enum value.

        Args:
            stage: The TDD pipeline stage (RED, GREEN, VERIFY, FIX, RED_FIX).
            task: Task dict containing task metadata.
            **kwargs: Additional arguments for specific stages:
                - test_output: Required for GREEN stage
                - issues: Required for FIX and RED_FIX stages

        Returns:
            Formatted prompt string for the specified stage.

        Raises:
            ValueError: If the stage is not supported or required kwargs missing.
        """
        # Import here to avoid circular import
        from .models import Stage as StageEnum

        if stage == StageEnum.RED:
            return PromptBuilder.red(task)

        if stage == StageEnum.GREEN:
            test_output = kwargs.get("test_output")
            if test_output is None:
                msg = "GREEN stage requires 'test_output' argument"
                raise ValueError(msg)

            # Route to retry prompt for attempts > 1
            attempt = kwargs.get("attempt", 1)
            if attempt > 1:
                previous_failure = kwargs.get("previous_failure", "")
                return PromptBuilder.build_green_retry(task, test_output, attempt, previous_failure)
            return PromptBuilder.green(task, test_output)

        if stage == StageEnum.VERIFY or stage == StageEnum.RE_VERIFY:
            return PromptBuilder.verify(task)

        if stage == StageEnum.FIX:
            issues = kwargs.get("issues")
            if issues is None:
                msg = "FIX stage requires 'issues' argument"
                raise ValueError(msg)
            return PromptBuilder.fix(task, issues)

        if stage == StageEnum.RED_FIX:
            issues = kwargs.get("issues")
            if issues is None:
                msg = "RED_FIX stage requires 'issues' argument"
                raise ValueError(msg)
            return PromptBuilder.red_fix(task, issues)

        msg = f"Unsupported stage: {stage}"
        raise ValueError(msg)
