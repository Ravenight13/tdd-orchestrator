"""PLAN9: Validation utilities for MODULE_API_SPECIFICATION.

Security validation for export names and module paths to prevent
prompt injection and ensure safe database storage.
"""

from __future__ import annotations

import re

# Valid Python identifier pattern
VALID_EXPORT_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Valid module path pattern (relative .py file, no parent refs)
VALID_MODULE_PATH = re.compile(r"^src/[\w/]+\.py$")


def validate_export_name(name: str) -> tuple[bool, str]:
    """Validate export name follows Python identifier rules.

    Args:
        name: Export name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Export name cannot be empty"

    if not VALID_EXPORT_NAME.match(name):
        return False, f"Invalid export name: {name} (must be valid Python identifier)"

    if len(name) > 255:
        return False, f"Export name too long: {len(name)} chars (max 255)"

    return True, ""


def validate_module_path(path: str) -> tuple[bool, str]:
    """Validate module path is safe and correct format.

    Args:
        path: Module path to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Module path cannot be empty"

    # Reject absolute paths
    if path.startswith("/"):
        return False, f"Module path must be relative: {path}"

    # Reject parent directory references
    if ".." in path:
        return False, f"Module path cannot contain parent refs: {path}"

    # Must be a .py file
    if not path.endswith(".py"):
        return False, f"Module path must end with .py: {path}"

    # Must match expected pattern
    if not VALID_MODULE_PATH.match(path):
        return False, f"Module path format invalid: {path}"

    if len(path) > 500:
        return False, f"Module path too long: {len(path)} chars (max 500)"

    return True, ""


def sanitize_export_description(desc: str) -> str:
    """Sanitize export description for safe use in prompts.

    Removes shell metacharacters and limits length.

    Args:
        desc: Description to sanitize

    Returns:
        Sanitized description string
    """
    if not desc:
        return ""

    # Strip shell metacharacters
    dangerous_chars = [";", "|", "&", "$", "(", ")", "<", ">", "`", "\\"]
    for char in dangerous_chars:
        desc = desc.replace(char, "")

    # Limit length
    max_len = 1000
    if len(desc) > max_len:
        desc = desc[:max_len] + "..."

    return desc.strip()


def validate_module_api(api_spec: dict[str, dict]) -> list[str]:
    """Validate entire MODULE_API_SPECIFICATION for security issues.

    Args:
        api_spec: Dictionary mapping module paths to their specifications

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    for module_path, spec in api_spec.items():
        # Validate module path
        is_valid, error = validate_module_path(module_path)
        if not is_valid:
            errors.append(error)
            continue

        # Validate exports
        exports = spec.get("exports", [])
        for export_name in exports:
            is_valid, error = validate_export_name(export_name)
            if not is_valid:
                errors.append(f"{module_path}: {error}")

    return errors
