"""Prompt template constants for TDD pipeline stages.

Extracted from prompt_builder.py to keep that module focused on
formatting logic and dispatch. Each template uses str.format()
placeholders for dynamic content.
"""

from __future__ import annotations

# =============================================================================
# Shared instruction blocks (deduplicated across templates)
# =============================================================================

TYPE_ANNOTATION_INSTRUCTIONS = """## TYPE ANNOTATIONS (MANDATORY - mypy strict mode)
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

⚠️ If you see mypy errors like "missing type annotation", add the annotation BEFORE submitting."""

STATIC_REVIEW_INSTRUCTIONS = """## STATIC REVIEW REQUIREMENTS (CRITICAL - your tests will be reviewed for these)
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
7. **No bare except clauses** - Use specific exceptions"""

FILE_STRUCTURE_CONSTRAINT = """## CRITICAL FILE STRUCTURE CONSTRAINT
- Create a SINGLE MODULE FILE at the EXACT path shown above
- Do NOT create a package directory (folder with __init__.py)
- Do NOT create multiple files or subdirectories
- The verification system will FAIL if the exact file path doesn't exist
- If you need multiple classes, put them ALL in the single module file
- Example: If impl_file is "src/frontend/htmx/button.py", create EXACTLY that file
- WRONG: Creating "frontend/htmx/button.py" (missing src/)
- WRONG: Creating "src/frontend/htmx/button/__init__.py" (package instead of module)"""

# =============================================================================
# RED stage template
# =============================================================================

RED_PROMPT_TEMPLATE = """You are a test writer. Your ONLY job is to write pytest tests.

## GOAL
{goal}

## ACCEPTANCE CRITERIA
{criteria_text}
{module_exports_section}
## FILES
- **Test file to create**: {test_file}
- **Implementation will be at**: {impl_file}
- **Import path**: `{import_hint}`

## REQUIREMENTS
1. Write a pytest test class with test methods
2. Each acceptance criterion should have at least one test
3. Include edge cases (empty input, invalid input, boundary conditions)
4. Tests should FAIL initially because implementation doesn't exist
5. Use descriptive test names: test_<behavior>_when_<condition>
6. Import from the EXACT path shown above: `{import_hint}`

{static_review_instructions}

## IMPORTANT
- ONLY create the test file at the EXACT path: {test_file}
- Do NOT write any implementation code
- Do NOT create any other files
- Tests should fail with ImportError or NameError (function doesn't exist)
- Use the EXACT import path: `{import_hint}`

Write the test file now using the Write tool."""

# =============================================================================
# GREEN stage template
# =============================================================================

GREEN_PROMPT_TEMPLATE = """You are an implementer. Your ONLY job is to make the tests pass.

## GOAL
{goal}

## TEST FILE
{test_file}

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
{file_structure_constraint}

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

{type_annotation_instructions}

## IMPORTANT
- ONLY create/modify the implementation file
- Focus on making tests pass, nothing more
- If tests expect specific behavior, implement exactly that
- ALL functions MUST have type annotations (mypy strict mode is enabled)

Write the implementation now using the Write tool."""

# =============================================================================
# GREEN RETRY template
# =============================================================================

GREEN_RETRY_TEMPLATE = """## GREEN Stage - Retry Attempt {attempt}

Your previous implementation attempt FAILED. The tests are not passing.

### Test Failure Output (from attempt {prev_attempt})
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

# =============================================================================
# VERIFY stage template
# =============================================================================

VERIFY_PROMPT_TEMPLATE = """You are a code verifier. Run quality checks on the implementation.

## TASK
{title} ({task_key})

## FILES TO VERIFY
- Test file: {test_file}
- Implementation: {impl_file}

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

# =============================================================================
# FIX stage template
# =============================================================================

FIX_PROMPT_TEMPLATE = """You are a code fixer. Fix the identified issues in this implementation.

## GOAL
{goal}

## IMPLEMENTATION FILE
{impl_file}

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

# =============================================================================
# RED_FIX stage template
# =============================================================================

RED_FIX_PROMPT_TEMPLATE = """You are a test fixer. Fix the static review issues in this test file.

## TASK
{task_key} - Fix static review issues

## TEST FILE TO FIX
{test_file}

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

# =============================================================================
# REFACTOR stage template
# =============================================================================

REFACTOR_PROMPT_TEMPLATE = """You are a code refactorer. Improve the code quality without changing behavior.

## TASK
{title} ({task_key})

## FILES
- Implementation: {impl_file}
- Test file: {test_file}

## ISSUES TO ADDRESS
{reasons_text}

## REQUIREMENTS
1. Read the implementation file and understand its structure
2. Address ONLY the specific issues listed above
3. If splitting a file, create new modules and update imports
4. Preserve the public API (same exports, same function signatures)
5. Do NOT add new functionality
6. Do NOT modify the test file
7. Run tests after changes to verify nothing broke

## CONSTRAINTS
- Keep ALL files under 800 lines (hard limit)
- Aim for 200-400 lines per file (ideal range)
- Maintain type annotations (mypy strict mode)
- Do NOT change function signatures or return types
- Do NOT rename public functions or classes

## APPROACH
- For long files: split by responsibility into focused modules
- For long functions: extract helper functions with clear names
- For classes with many methods: consider splitting into mixins or helper classes
- Always update imports in all affected files after splitting

Make the refactoring changes now using the Edit tool."""
