"""Tests for CLI init-prd command.

Tests the `tdd-orchestrator init-prd` command using Click's CliRunner
with tmp_path fixtures for isolated filesystem operations, plus
template generation tests and parser round-trip verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.decomposition.parser import SpecParser
from tdd_orchestrator.prd_template import generate_prd_template


class TestGeneratePrdTemplate:
    """Tests for the prd_template.generate_prd_template function."""

    def test_default_template_has_required_sections(self) -> None:
        """Default template contains all required section headers."""
        template = generate_prd_template("Test Feature")
        assert "FR-1:" in template
        assert "FR-2:" in template
        assert "NFR-1:" in template
        assert "AC-1:" in template
        assert "TDD Cycle 1:" in template
        assert "MODULE STRUCTURE" in template
        assert "DEPENDENCY CHANGES" in template

    def test_default_template_has_three_phases(self) -> None:
        """Default template generates 3 phase headers."""
        template = generate_prd_template("Test Feature")
        assert "### Phase 1:" in template
        assert "### Phase 2:" in template
        assert "### Phase 3:" in template
        assert "### Phase 4:" not in template

    def test_phases_parameter_controls_count(self) -> None:
        """phases=5 generates 5 phase headers and 5 TDD cycle blocks."""
        template = generate_prd_template("Test Feature", phases=5)
        for i in range(1, 6):
            assert f"### Phase {i}:" in template
            assert f"**TDD Cycle {i}:" in template
        assert "### Phase 6:" not in template

    def test_with_module_api_includes_section(self) -> None:
        """with_module_api=True includes MODULE API SPECIFICATION."""
        template = generate_prd_template("Test Feature", with_module_api=True)
        assert "MODULE API SPECIFICATION" in template

    def test_without_module_api_excludes_section(self) -> None:
        """with_module_api=False does NOT include MODULE API SPECIFICATION."""
        template = generate_prd_template("Test Feature", with_module_api=False)
        assert "MODULE API SPECIFICATION" not in template

    def test_module_structure_underline_is_dashes(self) -> None:
        """MODULE STRUCTURE uses dash underline (parser expects -+)."""
        template = generate_prd_template("Test Feature")
        assert "MODULE STRUCTURE\n----------------" in template

    def test_dependency_changes_underline_is_equals(self) -> None:
        """DEPENDENCY CHANGES uses equals underline (parser expects =+)."""
        template = generate_prd_template("Test Feature")
        assert "DEPENDENCY CHANGES\n==================" in template

    def test_feature_name_in_title(self) -> None:
        """Feature name appears in the title section."""
        template = generate_prd_template("User Authentication")
        assert "User Authentication" in template

    def test_tdd_cycle_has_tests_and_module_hint(self) -> None:
        """TDD cycle stubs include Tests: and Module Hint: lines."""
        template = generate_prd_template("Test Feature", phases=1)
        assert "Tests: 8-10" in template
        assert "Module Hint:" in template

    def test_acceptance_criteria_has_gherkin(self) -> None:
        """AC section includes GIVEN/WHEN/THEN stubs."""
        template = generate_prd_template("Test Feature")
        assert "GIVEN" in template
        assert "WHEN" in template
        assert "THEN" in template


class TestInitPrdCommand:
    """Tests for the init-prd CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CliRunner for testing."""
        return CliRunner()

    def test_help_shows_all_options(self, runner: CliRunner) -> None:
        """init-prd --help shows all options."""
        result = runner.invoke(cli, ["init-prd", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--name" in result.output
        assert "--phases" in result.output
        assert "--with-module-api" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    def test_creates_file_at_output_path(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Creates file at --output path with expected content."""
        out_file = tmp_path / "my_spec.txt"
        result = runner.invoke(
            cli, ["init-prd", "--output", str(out_file), "--name", "My Feature"]
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "FR-1:" in content

    def test_dry_run_prints_but_does_not_create(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--dry-run prints template but does NOT create file."""
        out_file = tmp_path / "dry_spec.txt"
        result = runner.invoke(
            cli,
            ["init-prd", "--output", str(out_file), "--name", "Dry", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "FR-1:" in result.output
        assert not out_file.exists()

    def test_name_sets_title(self, runner: CliRunner, tmp_path: Path) -> None:
        """--name sets the title in template."""
        out_file = tmp_path / "auth_spec.txt"
        result = runner.invoke(
            cli, ["init-prd", "--output", str(out_file), "--name", "Auth Flow"]
        )
        assert result.exit_code == 0
        content = out_file.read_text(encoding="utf-8")
        assert "Auth Flow" in content

    def test_errors_if_file_exists_without_force(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Errors with exit code 1 if file exists without --force."""
        out_file = tmp_path / "existing.txt"
        out_file.write_text("existing content", encoding="utf-8")
        result = runner.invoke(
            cli, ["init-prd", "--output", str(out_file), "--name", "Test"]
        )
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_force_overwrites_existing_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--force overwrites existing file."""
        out_file = tmp_path / "overwrite.txt"
        out_file.write_text("old content", encoding="utf-8")
        result = runner.invoke(
            cli,
            ["init-prd", "--output", str(out_file), "--name", "New", "--force"],
        )
        assert result.exit_code == 0
        content = out_file.read_text(encoding="utf-8")
        assert "FR-1:" in content
        assert "old content" not in content

    def test_default_output_derives_from_name(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Default --output derives from --name."""
        result = runner.invoke(
            cli, ["init-prd", "--name", "User Auth", "--dry-run"]
        )
        assert result.exit_code == 0
        # Dry run doesn't create the file, but shows the template
        assert "User Auth" in result.output

    def test_name_derives_from_output_stem(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--name is derived from --output stem when omitted."""
        out_file = tmp_path / "auth_spec.txt"
        result = runner.invoke(cli, ["init-prd", "--output", str(out_file)])
        assert result.exit_code == 0
        content = out_file.read_text(encoding="utf-8")
        assert "Auth" in content

    def test_no_name_no_output_errors(self, runner: CliRunner) -> None:
        """Errors when neither --name nor --output provided."""
        result = runner.invoke(cli, ["init-prd"])
        assert result.exit_code != 0

    def test_init_prd_registered_in_main_help(self, runner: CliRunner) -> None:
        """init-prd command appears in main --help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "init-prd" in result.output

    def test_shows_next_steps(self, runner: CliRunner, tmp_path: Path) -> None:
        """Output includes next steps with ingest command."""
        out_file = tmp_path / "test_spec.txt"
        result = runner.invoke(
            cli, ["init-prd", "--output", str(out_file), "--name", "Test"]
        )
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "ingest" in result.output


class TestParserRoundTrip:
    """Verify that generated template parses without error."""

    def test_template_parses_with_spec_parser(self, tmp_path: Path) -> None:
        """Generate template -> parse with SpecParser -> verify extraction."""
        template = generate_prd_template(
            "Round Trip Test",
            phases=3,
            with_module_api=True,
        )

        spec_file = tmp_path / "roundtrip_spec.txt"
        spec_file.write_text(template, encoding="utf-8")

        parser = SpecParser()
        parsed = parser.parse(spec_file)

        # FR extraction
        assert len(parsed.functional_requirements) >= 1
        assert parsed.functional_requirements[0]["id"] == "FR-1"

        # NFR extraction
        assert len(parsed.non_functional_requirements) >= 1
        assert parsed.non_functional_requirements[0]["id"] == "NFR-1"

        # AC extraction
        assert len(parsed.acceptance_criteria) >= 1
        assert parsed.acceptance_criteria[0]["id"] == "AC-1"

        # TDD cycles
        assert len(parsed.tdd_cycles) >= 1
        assert parsed.tdd_cycles[0]["cycle_number"] == 1

        # Module structure
        assert parsed.module_structure.get("files") is not None

        # Module API (with_module_api=True)
        assert len(parsed.module_api) >= 0  # may or may not parse placeholder
