"""Tests for decomposition prompt templates."""

from __future__ import annotations

from tdd_orchestrator.decomposition.prompts import (
    _build_valid_prefixes,
    format_task_breakdown_prompt,
)


class TestBuildValidPrefixes:
    """Tests for _build_valid_prefixes helper."""

    def test_from_module_structure(self) -> None:
        """Extracts directory prefixes from module_structure files."""
        module_structure = {
            "files": [
                "src/tdd_orchestrator/api/routes.py",
                "src/tdd_orchestrator/api/middleware.py",
                "src/tdd_orchestrator/api/models.py",
            ]
        }
        result = _build_valid_prefixes("src/tdd_orchestrator/api/", module_structure)
        assert '"src/tdd_orchestrator/api/"' in result

    def test_uses_module_hint(self) -> None:
        """Module hint appears in output even without module_structure."""
        result = _build_valid_prefixes("src/myapp/core/", None)
        assert '"src/myapp/core/"' in result

    def test_fallback_to_src(self) -> None:
        """Falls back to src/ when no data available."""
        result = _build_valid_prefixes("", None)
        assert '"src/"' in result

    def test_deduplicates(self) -> None:
        """No duplicate prefixes when hint matches structure."""
        module_structure = {
            "files": [
                "src/api/routes.py",
                "src/api/models.py",
            ]
        }
        result = _build_valid_prefixes("src/api/", module_structure)
        # Should appear exactly once
        assert result.count('"src/api/"') == 1

    def test_module_hint_trailing_slash(self) -> None:
        """Module hint without trailing slash gets one added."""
        result = _build_valid_prefixes("src/myapp", None)
        assert '"src/myapp/"' in result

    def test_module_hint_no_slash_ignored(self) -> None:
        """Module hint without any slash is not treated as a path."""
        result = _build_valid_prefixes("mymodule", None)
        # Falls back to src/
        assert '"src/"' in result


class TestFormatTaskBreakdownPrompt:
    """Tests for format_task_breakdown_prompt with dynamic prefixes."""

    def test_includes_dynamic_prefixes(self) -> None:
        """Prompt includes dynamic VALID PATH PREFIXES section."""
        module_structure = {
            "files": ["src/tdd_orchestrator/api/routes.py"]
        }
        result = format_task_breakdown_prompt(
            cycle_number=1,
            cycle_title="Test Cycle",
            phase="Foundation",
            components=["Router"],
            expected_tests="5-10",
            module_hint="src/tdd_orchestrator/api/",
            context="Test context",
            module_structure=module_structure,
        )
        assert "VALID PATH PREFIXES" in result
        assert "src/tdd_orchestrator/api/" in result

    def test_no_htmx_fallback(self) -> None:
        """Prompt does NOT contain 'src/htmx/' as default fallback."""
        result = format_task_breakdown_prompt(
            cycle_number=1,
            cycle_title="Test Cycle",
            phase="Foundation",
            components=["Router"],
            expected_tests="5-10",
            module_hint="src/myapp/",
            context="Test context",
        )
        assert 'use "src/htmx/"' not in result
        assert "src/htmx/" not in result.split("VALID PATH PREFIXES")[1].split("INVALID")[0]

    def test_backward_compat_no_module_structure(self) -> None:
        """No module_structure -> prompt still valid with fallback prefixes."""
        result = format_task_breakdown_prompt(
            cycle_number=1,
            cycle_title="Test Cycle",
            phase="Foundation",
            components=["Config"],
            expected_tests="5-10",
            module_hint="src/config/",
            context="Test context",
        )
        assert "VALID PATH PREFIXES" in result
        assert "src/config/" in result

    def test_with_module_structure_files(self) -> None:
        """module_structure files appear as valid prefixes."""
        module_structure = {
            "files": [
                "src/tdd_orchestrator/api/routes.py",
                "src/tdd_orchestrator/api/middleware.py",
                "src/tdd_orchestrator/models/task.py",
            ]
        }
        result = format_task_breakdown_prompt(
            cycle_number=1,
            cycle_title="API Setup",
            phase="Foundation",
            components=["APIRouter"],
            expected_tests="8-10",
            module_hint="src/tdd_orchestrator/api/",
            context="API context",
            module_structure=module_structure,
        )
        assert "src/tdd_orchestrator/api/" in result
        assert "src/tdd_orchestrator/models/" in result
