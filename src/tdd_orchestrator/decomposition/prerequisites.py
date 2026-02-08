"""Prerequisite task generation from spec metadata.

Deterministic (no LLM calls) generation of Phase 0 setup tasks from parsed
spec sections like DEPENDENCY CHANGES and MODULE STRUCTURE. These tasks must
complete before implementation tasks in Phase 1+ can begin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .decomposer import DecomposedTask
    from .parser import ParsedSpec


def generate_prerequisite_tasks(
    spec: ParsedSpec,
    task_key_generator: Any,
) -> list[DecomposedTask]:
    """Generate Phase 0 prerequisite tasks from spec metadata.

    Detects dependency changes and new package directories from the parsed spec
    and creates setup tasks that must run before any implementation tasks.

    Args:
        spec: ParsedSpec with dependency_changes and module_structure.
        task_key_generator: Callable(phase: int) -> str that generates unique task keys.

    Returns:
        List of Phase 0 DecomposedTask objects (may be empty).
    """
    prereqs: list[DecomposedTask] = []

    prereqs.extend(_generate_dependency_task(spec, task_key_generator))
    prereqs.extend(_generate_scaffold_task(spec, task_key_generator))

    return prereqs


def _generate_dependency_task(
    spec: ParsedSpec,
    task_key_generator: Any,
) -> list[DecomposedTask]:
    """Generate a task for adding dependencies to pyproject.toml.

    Args:
        spec: ParsedSpec with dependency_changes field.
        task_key_generator: Callable(phase: int) -> str.

    Returns:
        List with zero or one DecomposedTask.
    """
    from .decomposer import DecomposedTask

    dep = spec.dependency_changes
    if not dep or not dep.get("packages"):
        return []

    extra_name: str = dep.get("extra_name", "new")
    packages: list[str] = dep["packages"]
    pkg_list = ", ".join(packages[:5])
    if len(packages) > 5:
        pkg_list += f" (+{len(packages) - 5} more)"

    # Extract base package name from first package specifier
    first_pkg = packages[0].split(">")[0].split("<")[0].split("=")[0].split("[")[0]

    task_key: str = task_key_generator(0)
    return [DecomposedTask(
        task_key=task_key,
        title=f"Add [{extra_name}] optional dependencies to pyproject.toml",
        goal=f"Add {pkg_list} to pyproject.toml [project.optional-dependencies] and install",
        estimated_tests=3,
        estimated_lines=20,
        test_file=f"tests/unit/test_{extra_name}_dependency_setup.py",
        impl_file="pyproject.toml",
        components=["pyproject.toml", "dependencies"],
        acceptance_criteria=[
            f"pyproject.toml has [{extra_name}] extra with {len(packages)} packages",
            f"pip install -e '.[{extra_name}]' succeeds without errors",
            f"import of first package ({first_pkg}) succeeds",
        ],
        phase=0,
        sequence=1,
        depends_on=[],
        complexity="low",
        verify_command=f".venv/bin/pip install -e '.[{extra_name}]'",
        done_criteria=f"All [{extra_name}] packages installable",
    )]


def _generate_scaffold_task(
    spec: ParsedSpec,
    task_key_generator: Any,
) -> list[DecomposedTask]:
    """Generate a task for creating package directory structure.

    Args:
        spec: ParsedSpec with module_structure field.
        task_key_generator: Callable(phase: int) -> str.

    Returns:
        List with zero or one DecomposedTask.
    """
    from .decomposer import DecomposedTask

    mod = spec.module_structure
    base_path: str = mod.get("base_path", "") if mod else ""
    if not base_path:
        return []

    # Convert filesystem path to Python package for imports
    package_path = base_path.replace("/", ".")
    task_key: str = task_key_generator(0)
    files: list[str] = mod.get("files", [])
    file_count = len(files)

    criteria = [
        f"Directory {base_path}/ exists",
        f"{base_path}/__init__.py exists and is importable",
        f"Package {package_path} is importable",
    ]
    if file_count:
        criteria.append(f"{file_count} module files listed in spec")

    return [DecomposedTask(
        task_key=task_key,
        title=f"Create {base_path} package structure with __init__.py files",
        goal=f"Create directory tree and __init__.py files for {base_path}",
        estimated_tests=3,
        estimated_lines=15,
        test_file="tests/unit/test_package_structure.py",
        impl_file=f"{base_path}/__init__.py",
        components=[base_path, "__init__.py"],
        acceptance_criteria=criteria,
        phase=0,
        sequence=2,
        depends_on=[],
        complexity="low",
        verify_command=f"python -c 'import {package_path}'",
        done_criteria=f"Package {base_path} importable",
    )]
