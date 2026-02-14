"""Project configuration for TDD Orchestrator.

Manages per-project .tdd/ directory with config.toml, .gitignore,
and project-scoped database. Provides discovery via find_project_root()
and integration via setup_project_context().
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_TDD_DIR = ".tdd"
_CONFIG_FILE = "config.toml"
_DB_FILE = "orchestrator.db"

_GITIGNORE_CONTENT = """\
orchestrator.db
*.db-journal
*.db-wal
*.db-shm
"""


@dataclass(frozen=True)
class TDDConfig:
    """TDD-specific configuration."""

    prefix: str = "TDD"
    max_workers: int = 2


@dataclass(frozen=True)
class GitConfig:
    """Git-related configuration."""

    base_branch: str = "main"


@dataclass(frozen=True)
class ProjectConfig:
    """Per-project TDD Orchestrator configuration.

    Loaded from .tdd/config.toml via load_project_config().
    """

    name: str
    language: str = "python"
    source_root: str = "src"
    test_root: str = "tests"
    tdd: TDDConfig = field(default_factory=TDDConfig)
    git: GitConfig = field(default_factory=GitConfig)

    def resolve_db_path(self, project_root: Path) -> Path:
        """Resolve absolute path to the project database."""
        return project_root.resolve() / _TDD_DIR / _DB_FILE


def load_project_config(project_path: Path) -> ProjectConfig:
    """Load config from .tdd/config.toml.

    Args:
        project_path: Path to the project root directory.

    Returns:
        Parsed ProjectConfig.

    Raises:
        FileNotFoundError: If .tdd/config.toml is missing.
        ValueError: On invalid, empty, or corrupt TOML.
    """
    config_file = project_path / _TDD_DIR / _CONFIG_FILE
    if not config_file.exists():
        msg = f"Project config not found: {config_file}"
        raise FileNotFoundError(msg)

    content = config_file.read_text(encoding="utf-8")
    if not content.strip():
        msg = f"Config file is empty: {config_file}"
        raise ValueError(msg)

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in {config_file}: {exc}"
        raise ValueError(msg) from exc

    return _parse_config(data)


def _parse_config(data: dict[str, object]) -> ProjectConfig:
    """Parse raw TOML data into a ProjectConfig.

    Unknown fields are silently ignored for forward compatibility.
    """
    project = data.get("project", {})
    if not isinstance(project, dict):
        msg = "[project] section must be a table"
        raise ValueError(msg)

    tdd_data = data.get("tdd", {})
    if not isinstance(tdd_data, dict):
        msg = "[tdd] section must be a table"
        raise ValueError(msg)

    git_data = data.get("git", {})
    if not isinstance(git_data, dict):
        msg = "[git] section must be a table"
        raise ValueError(msg)

    name = project.get("name")
    if not isinstance(name, str) or not name:
        msg = "project.name is required and must be a non-empty string"
        raise ValueError(msg)

    config = ProjectConfig(
        name=name,
        language=str(project.get("language", "python")),
        source_root=str(project.get("source_root", "src")),
        test_root=str(project.get("test_root", "tests")),
        tdd=TDDConfig(
            prefix=str(tdd_data.get("prefix", "TDD")),
            max_workers=int(tdd_data.get("max_workers", 2)),
        ),
        git=GitConfig(
            base_branch=str(git_data.get("base_branch", "main")),
        ),
    )
    _validate_config(config)
    return config


def create_default_config(
    project_path: Path,
    *,
    name: str | None = None,
    language: str = "python",
    force: bool = False,
) -> ProjectConfig:
    """Create .tdd/ directory with config.toml, .gitignore, and empty DB.

    Args:
        project_path: Path to the project root directory.
        name: Project name. Defaults to directory basename.
        language: Project language. Defaults to "python".
        force: Overwrite existing .tdd/ configuration.

    Returns:
        The created ProjectConfig.

    Raises:
        FileExistsError: If .tdd/ exists and force=False.
    """
    tdd_dir = project_path / _TDD_DIR
    if tdd_dir.exists() and not force:
        msg = f"Project already initialized: {tdd_dir}"
        raise FileExistsError(msg)

    resolved_name = name or project_path.resolve().name

    config = ProjectConfig(
        name=resolved_name,
        language=language,
    )
    _validate_config(config)

    tdd_dir.mkdir(parents=True, exist_ok=True)

    config_file = tdd_dir / _CONFIG_FILE
    config_file.write_text(_generate_toml(config), encoding="utf-8")

    gitignore_file = tdd_dir / ".gitignore"
    gitignore_file.write_text(_GITIGNORE_CONTENT, encoding="utf-8")

    logger.info("Initialized project '%s' at %s", resolved_name, tdd_dir)
    return config


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from start to find nearest .tdd/ directory.

    Args:
        start: Starting directory. Defaults to cwd.

    Returns:
        The directory containing .tdd/, or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / _TDD_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


async def setup_project_context(project_root: Path) -> ProjectConfig:
    """Load project config and set DB singleton path.

    Integration hook for Phase 2B+ commands. Loads the project
    config and configures the database singleton to use the
    project-scoped database.

    Args:
        project_root: Path to the project root containing .tdd/.

    Returns:
        The loaded ProjectConfig.
    """
    from .database import set_db_path

    config = load_project_config(project_root)
    db_path = config.resolve_db_path(project_root)
    set_db_path(db_path)
    logger.info("Project context set: %s (db: %s)", config.name, db_path)
    return config


def resolve_db_for_cli(db_override: str | None = None) -> tuple[Path, ProjectConfig | None]:
    """Resolve database path for CLI commands with auto-discovery fallback.

    Args:
        db_override: Explicit --db path. If given, skips discovery.

    Returns:
        (db_path, config). config is None when db_override is used.

    Raises:
        FileNotFoundError: If no db_override and no .tdd/ found.
        ValueError: If .tdd/config.toml is corrupt or invalid.
    """
    if db_override is not None:
        return Path(db_override), None

    project_root = find_project_root()
    if project_root is None:
        msg = (
            "No .tdd/ directory found. "
            "Run 'tdd-orchestrator init' first or use --db."
        )
        raise FileNotFoundError(msg)

    config = load_project_config(project_root)
    db_path = config.resolve_db_path(project_root)
    return db_path, config


def _generate_toml(config: ProjectConfig) -> str:
    """Generate TOML string from a ProjectConfig.

    Handles Python→TOML type mapping: booleans as true/false,
    integers unquoted, strings quoted.
    """
    lines = [
        "[project]",
        f'name = "{_escape_toml_string(config.name)}"',
        f'language = "{_escape_toml_string(config.language)}"',
        f'source_root = "{_escape_toml_string(config.source_root)}"',
        f'test_root = "{_escape_toml_string(config.test_root)}"',
        "",
        "[tdd]",
        f'prefix = "{_escape_toml_string(config.tdd.prefix)}"',
        f"max_workers = {config.tdd.max_workers}",
        "",
        "[git]",
        f'base_branch = "{_escape_toml_string(config.git.base_branch)}"',
        "",
    ]
    return "\n".join(lines)


def _escape_toml_string(value: str) -> str:
    """Escape special characters for TOML string values."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _validate_config(config: ProjectConfig) -> None:
    """Validate config values.

    Raises:
        ValueError: On invalid configuration.
    """
    if not config.name or not config.name.strip():
        msg = "project.name must not be empty"
        raise ValueError(msg)
    if " " in config.name or "\t" in config.name:
        msg = f"project.name must not contain whitespace: '{config.name}'"
        raise ValueError(msg)

    if ".." in config.source_root:
        msg = f"source_root must not contain '..': '{config.source_root}'"
        raise ValueError(msg)
    if ".." in config.test_root:
        msg = f"test_root must not contain '..': '{config.test_root}'"
        raise ValueError(msg)

    if not config.tdd.prefix or not config.tdd.prefix.strip():
        msg = "tdd.prefix must not be empty"
        raise ValueError(msg)
    if " " in config.tdd.prefix or "\t" in config.tdd.prefix:
        msg = f"tdd.prefix must not contain whitespace: '{config.tdd.prefix}'"
        raise ValueError(msg)

    if config.tdd.max_workers < 1 or config.tdd.max_workers > 10:
        msg = f"tdd.max_workers must be 1-10, got {config.tdd.max_workers}"
        raise ValueError(msg)
