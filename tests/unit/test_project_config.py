"""Tests for project configuration module.

Tests config loading, creation, validation, find_project_root,
TOML round-trip fidelity, and error handling.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tdd_orchestrator.project_config import (
    GitConfig,
    ProjectConfig,
    TDDConfig,
    _generate_toml,
    _validate_config,
    create_default_config,
    find_project_root,
    load_project_config,
    setup_project_context,
)


class TestLoadProjectConfig:
    """Tests for load_project_config()."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Load a valid config.toml with all fields populated."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text(
            '[project]\n'
            'name = "my-project"\n'
            'language = "rust"\n'
            'source_root = "lib"\n'
            'test_root = "test"\n'
            "\n"
            "[tdd]\n"
            'prefix = "TSK"\n'
            "max_workers = 4\n"
            "\n"
            "[git]\n"
            'base_branch = "develop"\n',
            encoding="utf-8",
        )

        config = load_project_config(tmp_path)

        assert config.name == "my-project"
        assert config.language == "rust"
        assert config.source_root == "lib"
        assert config.test_root == "test"
        assert config.tdd.prefix == "TSK"
        assert config.tdd.max_workers == 4
        assert config.git.base_branch == "develop"

    def test_load_missing_optional_fields_uses_defaults(self, tmp_path: Path) -> None:
        """Missing optional fields get default values."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text(
            '[project]\nname = "minimal"\n',
            encoding="utf-8",
        )

        config = load_project_config(tmp_path)

        assert config.name == "minimal"
        assert config.language == "python"
        assert config.source_root == "src"
        assert config.test_root == "tests"
        assert config.tdd.prefix == "TDD"
        assert config.tdd.max_workers == 2
        assert config.git.base_branch == "main"

    def test_load_missing_config_raises_file_not_found(self, tmp_path: Path) -> None:
        """Missing .tdd/config.toml raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="config not found"):
            load_project_config(tmp_path)

    def test_load_corrupted_toml_raises_value_error(self, tmp_path: Path) -> None:
        """Corrupted TOML raises ValueError."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text("this is [not valid toml =", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid TOML"):
            load_project_config(tmp_path)

    def test_load_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        """Empty config file raises ValueError."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            load_project_config(tmp_path)

    def test_load_unknown_fields_silently_ignored(self, tmp_path: Path) -> None:
        """Unknown fields in TOML are silently ignored (forward compat)."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text(
            '[project]\n'
            'name = "proj"\n'
            'future_field = "ignored"\n'
            "\n"
            "[unknown_section]\n"
            'key = "value"\n',
            encoding="utf-8",
        )

        config = load_project_config(tmp_path)
        assert config.name == "proj"

    def test_load_missing_project_name_raises_value_error(self, tmp_path: Path) -> None:
        """Missing project.name raises ValueError."""
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()
        config_file = tdd_dir / "config.toml"
        config_file.write_text("[project]\nlanguage = \"python\"\n", encoding="utf-8")

        with pytest.raises(ValueError, match="name is required"):
            load_project_config(tmp_path)


class TestCreateDefaultConfig:
    """Tests for create_default_config()."""

    def test_creates_tdd_dir_and_config(self, tmp_path: Path) -> None:
        """Creates .tdd/ directory, config.toml, and .gitignore."""
        config = create_default_config(tmp_path, name="test-proj")

        assert (tmp_path / ".tdd").is_dir()
        assert (tmp_path / ".tdd" / "config.toml").is_file()
        assert (tmp_path / ".tdd" / ".gitignore").is_file()
        assert config.name == "test-proj"

    def test_existing_tdd_without_force_raises(self, tmp_path: Path) -> None:
        """Existing .tdd/ without force raises FileExistsError."""
        (tmp_path / ".tdd").mkdir()

        with pytest.raises(FileExistsError, match="already initialized"):
            create_default_config(tmp_path, name="proj")

    def test_existing_tdd_with_force_overwrites(self, tmp_path: Path) -> None:
        """Existing .tdd/ with force=True overwrites config."""
        create_default_config(tmp_path, name="original")

        config = create_default_config(tmp_path, name="updated", force=True)

        assert config.name == "updated"
        loaded = load_project_config(tmp_path)
        assert loaded.name == "updated"

    def test_name_defaults_to_directory_basename(self, tmp_path: Path) -> None:
        """Name defaults to the directory basename when not specified."""
        config = create_default_config(tmp_path)

        assert config.name == tmp_path.resolve().name

    def test_custom_language(self, tmp_path: Path) -> None:
        """Custom language is reflected in config."""
        config = create_default_config(tmp_path, name="proj", language="rust")
        assert config.language == "rust"

    def test_gitignore_content(self, tmp_path: Path) -> None:
        """Gitignore contains DB file exclusions."""
        create_default_config(tmp_path, name="proj")

        content = (tmp_path / ".tdd" / ".gitignore").read_text(encoding="utf-8")
        assert "orchestrator.db" in content
        assert "*.db-journal" in content
        assert "*.db-wal" in content
        assert "*.db-shm" in content


class TestGenerateToml:
    """Tests for _generate_toml() and TOML round-trip fidelity."""

    def test_round_trip_fidelity(self) -> None:
        """Write → load → compare produces identical config."""
        original = ProjectConfig(
            name="my-project",
            language="python",
            source_root="src",
            test_root="tests",
            tdd=TDDConfig(prefix="TDD", max_workers=3),
            git=GitConfig(base_branch="develop"),
        )

        toml_str = _generate_toml(original)
        data = tomllib.loads(toml_str)

        assert data["project"]["name"] == original.name
        assert data["project"]["language"] == original.language
        assert data["project"]["source_root"] == original.source_root
        assert data["project"]["test_root"] == original.test_root
        assert data["tdd"]["prefix"] == original.tdd.prefix
        assert data["tdd"]["max_workers"] == original.tdd.max_workers
        assert data["git"]["base_branch"] == original.git.base_branch

    def test_integers_unquoted(self) -> None:
        """Integers are serialized without quotes."""
        config = ProjectConfig(name="proj", tdd=TDDConfig(max_workers=5))
        toml_str = _generate_toml(config)
        assert "max_workers = 5" in toml_str

    def test_strings_quoted(self) -> None:
        """Strings are serialized with double quotes."""
        config = ProjectConfig(name="proj", language="python")
        toml_str = _generate_toml(config)
        assert 'language = "python"' in toml_str

    def test_special_chars_escaped(self) -> None:
        """Special characters in string values are escaped."""
        config = ProjectConfig(name='has\\"quote')
        toml_str = _generate_toml(config)
        # Verify the TOML is parseable
        data = tomllib.loads(toml_str)
        assert data["project"]["name"] == 'has\\"quote'


class TestValidateConfig:
    """Tests for _validate_config()."""

    def test_valid_config_passes(self) -> None:
        """Valid config passes validation without error."""
        config = ProjectConfig(name="valid-project")
        _validate_config(config)  # Should not raise

    def test_empty_name_raises(self) -> None:
        """Empty project name raises ValueError."""
        config = ProjectConfig(name="")
        with pytest.raises(ValueError, match="name must not be empty"):
            _validate_config(config)

    def test_whitespace_name_raises(self) -> None:
        """Name with whitespace raises ValueError."""
        config = ProjectConfig(name="has space")
        with pytest.raises(ValueError, match="whitespace"):
            _validate_config(config)

    def test_dotdot_in_source_root_raises(self) -> None:
        """Path traversal in source_root raises ValueError."""
        config = ProjectConfig(name="proj", source_root="../escape")
        with pytest.raises(ValueError, match="source_root.*\\.\\."):
            _validate_config(config)

    def test_dotdot_in_test_root_raises(self) -> None:
        """Path traversal in test_root raises ValueError."""
        config = ProjectConfig(name="proj", test_root="../../etc")
        with pytest.raises(ValueError, match="test_root.*\\.\\."):
            _validate_config(config)

    def test_max_workers_too_low_raises(self) -> None:
        """max_workers < 1 raises ValueError."""
        config = ProjectConfig(name="proj", tdd=TDDConfig(max_workers=0))
        with pytest.raises(ValueError, match="max_workers must be 1-10"):
            _validate_config(config)

    def test_max_workers_too_high_raises(self) -> None:
        """max_workers > 10 raises ValueError."""
        config = ProjectConfig(name="proj", tdd=TDDConfig(max_workers=11))
        with pytest.raises(ValueError, match="max_workers must be 1-10"):
            _validate_config(config)

    def test_empty_prefix_raises(self) -> None:
        """Empty tdd.prefix raises ValueError."""
        config = ProjectConfig(name="proj", tdd=TDDConfig(prefix=""))
        with pytest.raises(ValueError, match="prefix must not be empty"):
            _validate_config(config)

    def test_whitespace_prefix_raises(self) -> None:
        """Prefix with whitespace raises ValueError."""
        config = ProjectConfig(name="proj", tdd=TDDConfig(prefix="TD D"))
        with pytest.raises(ValueError, match="prefix.*whitespace"):
            _validate_config(config)


class TestFindProjectRoot:
    """Tests for find_project_root()."""

    def test_finds_tdd_in_current_dir(self, tmp_path: Path) -> None:
        """Finds .tdd/ in the given directory."""
        (tmp_path / ".tdd").mkdir()

        result = find_project_root(tmp_path)

        assert result == tmp_path.resolve()

    def test_finds_tdd_in_ancestor_dir(self, tmp_path: Path) -> None:
        """Finds .tdd/ in an ancestor directory."""
        (tmp_path / ".tdd").mkdir()
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)

        result = find_project_root(nested)

        assert result == tmp_path.resolve()

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Returns None when no .tdd/ exists in hierarchy."""
        result = find_project_root(tmp_path)

        assert result is None


class TestResolveDbPath:
    """Tests for ProjectConfig.resolve_db_path()."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """Returns absolute path to .tdd/orchestrator.db."""
        config = ProjectConfig(name="proj")
        db_path = config.resolve_db_path(tmp_path)

        expected = tmp_path.resolve() / ".tdd" / "orchestrator.db"
        assert db_path == expected


class TestSetupProjectContext:
    """Tests for setup_project_context()."""

    async def test_loads_config_and_sets_db_path(self, tmp_path: Path) -> None:
        """Loads config and configures DB singleton."""
        from tdd_orchestrator.database import reset_db

        create_default_config(tmp_path, name="ctx-test")

        try:
            config = await setup_project_context(tmp_path)
            assert config.name == "ctx-test"
        finally:
            await reset_db()

    async def test_raises_on_missing_config(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError if .tdd/config.toml missing."""
        with pytest.raises(FileNotFoundError):
            await setup_project_context(tmp_path)
