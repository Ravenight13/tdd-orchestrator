"""Spec Parser for extracting structured data from app_spec.txt files.

This module provides the SpecParser class which extracts functional requirements,
non-functional requirements, acceptance criteria, TDD cycles, and module structure
from specification documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import SpecParseError


@dataclass
class ParsedSpec:
    """Structured representation of a parsed specification document.

    Contains all extracted components from an app_spec.txt file including
    requirements, acceptance criteria, TDD cycles, and module structure.

    Attributes:
        functional_requirements: List of FR-N sections with id, title, content.
        non_functional_requirements: List of NFR-N sections with id, title, content.
        acceptance_criteria: List of AC-N sections with id, title, gherkin content.
        tdd_cycles: List of TDD cycle definitions with cycle number and components.
        module_structure: Dictionary containing base_path and files list.
        raw_content: The original unprocessed file content.
    """

    functional_requirements: list[dict[str, Any]] = field(default_factory=list)
    non_functional_requirements: list[dict[str, Any]] = field(default_factory=list)
    acceptance_criteria: list[dict[str, Any]] = field(default_factory=list)
    tdd_cycles: list[dict[str, Any]] = field(default_factory=list)
    module_structure: dict[str, Any] = field(default_factory=dict)
    module_api: dict[str, dict[str, Any]] = field(default_factory=dict)  # PLAN9
    raw_content: str = ""


class SpecParser:
    """Parser for extracting structured data from app_spec.txt files.

    Extracts functional requirements (FR-N), non-functional requirements (NFR-N),
    acceptance criteria (AC-N), TDD cycles, and module structure from specification
    documents.

    Example:
        >>> parser = SpecParser()
        >>> spec = parser.parse(Path("app_spec.txt"))
        >>> len(spec.functional_requirements)
        9
    """

    # Regex patterns for extraction
    # Support both numeric (FR-1) and alphanumeric (FR-HTMX-01) IDs
    FR_PATTERN = re.compile(r"^FR-([\w-]+?):\s*(.+?)$", re.MULTILINE)
    FR_SUBSECTION_PATTERN = re.compile(r"^\s+FR-([\w.-]+?):\s*(.+?)$", re.MULTILINE)
    NFR_PATTERN = re.compile(r"^NFR-([\w-]+?):\s*(.+?)$", re.MULTILINE)
    NFR_SUBSECTION_PATTERN = re.compile(r"^\s+NFR-([\w.-]+?):\s*(.+?)$", re.MULTILINE)
    AC_PATTERN = re.compile(r"^AC-([\w-]+?):\s*(.+?)$", re.MULTILINE)
    TDD_CYCLE_PATTERN = re.compile(
        r"\*\*TDD Cycle (\d+):\s*(.+?)\*\*\s*(.+?)(?=(?:\*\*TDD Cycle \d+:|\Z))",
        re.DOTALL,
    )
    # Fallback pattern for specs without ** markdown
    TDD_CYCLE_PATTERN_SIMPLE = re.compile(
        r"TDD Cycle (\d+):\s*(.+?)(?=(?:TDD Cycle \d+:|PHASE|$))",
        re.DOTALL,
    )
    # Pattern to find phase headers (### Phase N: Title)
    PHASE_HEADER_PATTERN = re.compile(
        r"###\s*Phase\s*(\d+):\s*(.+?)$",
        re.MULTILINE,
    )
    MODULE_STRUCTURE_PATTERN = re.compile(
        r"MODULE STRUCTURE\s*\n-+\s*\n(.+?)(?=\n\n[A-Z]|\Z)",
        re.DOTALL,
    )
    # PLAN9: Module API specification pattern
    MODULE_API_PATTERN = re.compile(
        r"MODULE API SPECIFICATION\s*\n=+\s*\n(.+?)(?=\n={20,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    def parse(self, spec_path: Path) -> ParsedSpec:
        """Parse a spec file and extract structured data.

        Args:
            spec_path: Path to the app_spec.txt file.

        Returns:
            ParsedSpec containing all extracted components.

        Raises:
            SpecParseError: If the file cannot be read or has invalid format.
        """
        if not spec_path.exists():
            raise SpecParseError(f"Spec file not found: {spec_path}")

        try:
            content = spec_path.read_text(encoding="utf-8")
        except OSError as e:
            raise SpecParseError(f"Failed to read spec file: {e}") from e

        if not content.strip():
            raise SpecParseError(f"Spec file is empty: {spec_path}")

        return ParsedSpec(
            functional_requirements=self._extract_fr(content),
            non_functional_requirements=self._extract_nfr(content),
            acceptance_criteria=self._extract_ac(content),
            tdd_cycles=self._extract_tdd_cycles(content),
            module_structure=self._extract_module_structure(content),
            module_api=self._extract_module_api(content),  # PLAN9
            raw_content=content,
        )

    def _extract_fr(self, content: str) -> list[dict[str, Any]]:
        """Extract FR-N: sections from content.

        Handles both top-level FR sections and nested subsections (FR-1.1, FR-1.2).

        Args:
            content: Raw spec file content.

        Returns:
            List of dictionaries with id, title, content, and subsections.
        """
        requirements: list[dict[str, Any]] = []

        # Find all top-level FR matches
        matches = list(self.FR_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            fr_id = f"FR-{match.group(1)}"
            title = match.group(2).strip()

            # Get content between this FR and the next
            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                # Look for next section marker (NFR, AC, or section header)
                next_section = re.search(r"\n(?:NFR-[\w-]+?:|AC-[\w-]+?:|={20,})", content[start:])
                if next_section:
                    end = start + next_section.start()
                else:
                    end = len(content)

            section_content = content[start:end].strip()

            # Extract subsections
            subsections = self._extract_subsections(section_content, self.FR_SUBSECTION_PATTERN)

            requirements.append(
                {
                    "id": fr_id,
                    "title": title,
                    "content": section_content,
                    "subsections": subsections,
                }
            )

        return requirements

    def _extract_nfr(self, content: str) -> list[dict[str, Any]]:
        """Extract NFR-N: sections from content.

        Args:
            content: Raw spec file content.

        Returns:
            List of dictionaries with id, title, and content.
        """
        requirements: list[dict[str, Any]] = []

        matches = list(self.NFR_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            nfr_id = f"NFR-{match.group(1)}"
            title = match.group(2).strip()

            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                # Look for next major section
                next_section = re.search(
                    r"\n(?:={20,}|TECHNICAL DESIGN|ACCEPTANCE CRITERIA)",
                    content[start:],
                )
                if next_section:
                    end = start + next_section.start()
                else:
                    end = len(content)

            section_content = content[start:end].strip()

            # Extract subsections
            subsections = self._extract_subsections(section_content, self.NFR_SUBSECTION_PATTERN)

            requirements.append(
                {
                    "id": nfr_id,
                    "title": title,
                    "content": section_content,
                    "subsections": subsections,
                }
            )

        return requirements

    def _extract_subsections(self, content: str, pattern: re.Pattern[str]) -> list[dict[str, str]]:
        """Extract subsections from a section's content.

        Args:
            content: Section content to search for subsections.
            pattern: Compiled regex pattern for subsection matching.

        Returns:
            List of dictionaries with id, title, and content for each subsection.
        """
        subsections: list[dict[str, str]] = []
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            sub_id = match.group(1)
            sub_title = match.group(2).strip()

            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)

            sub_content = content[start:end].strip()

            subsections.append(
                {
                    "id": sub_id,
                    "title": sub_title,
                    "content": sub_content,
                }
            )

        return subsections

    def _extract_ac(self, content: str) -> list[dict[str, Any]]:
        """Extract AC-N: sections from content.

        Parses acceptance criteria including Gherkin-style GIVEN/WHEN/THEN blocks.

        Args:
            content: Raw spec file content.

        Returns:
            List of dictionaries with id, title, and gherkin content.
        """
        criteria: list[dict[str, Any]] = []

        matches = list(self.AC_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            ac_id = f"AC-{match.group(1)}"
            title = match.group(2).strip()

            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                # Look for next major section
                next_section = re.search(r"\n(?:={20,}|IMPLEMENTATION PLAN)", content[start:])
                if next_section:
                    end = start + next_section.start()
                else:
                    end = len(content)

            section_content = content[start:end].strip()

            # Extract Gherkin content (GIVEN/WHEN/THEN)
            gherkin = self._extract_gherkin(section_content)

            criteria.append(
                {
                    "id": ac_id,
                    "title": title,
                    "content": section_content,
                    "gherkin": gherkin,
                }
            )

        return criteria

    def _extract_gherkin(self, content: str) -> str:
        """Extract Gherkin-style GIVEN/WHEN/THEN content.

        Args:
            content: AC section content.

        Returns:
            Extracted Gherkin content or empty string if not found.
        """
        # Extract lines starting with GIVEN, WHEN, THEN, AND (Gherkin keywords)
        gherkin_lines: list[str] = []
        in_gherkin = False

        for line in content.split("\n"):
            stripped = line.strip()
            upper = stripped.upper()

            # Check if line starts with a Gherkin keyword
            if upper.startswith(("GIVEN ", "WHEN ", "THEN ", "AND ")):
                in_gherkin = True
                gherkin_lines.append(stripped)
            elif in_gherkin and stripped and not stripped.startswith(("*", "-", "#")):
                # Continue capturing if it looks like a continuation
                # Stop if we hit a different section marker
                if any(stripped.startswith(kw) for kw in ("AC-", "FR-", "NFR-")):
                    break
                # Don't include section headers or empty lines
                if stripped and not stripped.startswith("="):
                    gherkin_lines.append(stripped)

        return "\n".join(gherkin_lines)

    def _extract_tdd_cycles(self, content: str) -> list[dict[str, Any]]:
        """Extract TDD Cycle N: sections from content.

        Supports both markdown format (**TDD Cycle N:**) and simple format.
        Extracts phase information from phase headers and module hints from cycle content.

        Args:
            content: Raw spec file content.

        Returns:
            List of dictionaries with cycle_number, title, phase, components,
            expected_tests, and module_hint.
        """
        cycles: list[dict[str, Any]] = []

        # First, extract phase headers to build phase map
        phase_map = self._build_phase_map(content)

        # Try markdown pattern first
        matches = list(self.TDD_CYCLE_PATTERN.finditer(content))

        if matches:
            # Markdown format: **TDD Cycle N: Title**
            for match in matches:
                cycle_num = int(match.group(1))
                title = match.group(2).strip()
                cycle_content = (
                    match.group(3).strip() if match.lastindex and match.lastindex >= 3 else ""
                )

                # Extract components (bulleted items)
                components = self._extract_components(cycle_content)

                # Extract expected test count
                expected_tests = self._extract_test_count(cycle_content)

                # Extract module hint
                module_hint = self._extract_module_hint(cycle_content)

                # Determine phase from position in content
                phase = self._find_phase_for_position(match.start(), phase_map)

                cycles.append(
                    {
                        "cycle_number": cycle_num,
                        "cycle_title": title,  # Use cycle_title for consistency with prompts
                        "title": title,
                        "phase": phase,
                        "content": cycle_content,
                        "components": components,
                        "expected_tests": expected_tests,
                        "module_hint": module_hint,
                    }
                )
        else:
            # Fallback to simple pattern
            matches = list(self.TDD_CYCLE_PATTERN_SIMPLE.finditer(content))

            for match in matches:
                cycle_num = int(match.group(1))
                cycle_content = match.group(2).strip()

                # Extract title (first line)
                lines = cycle_content.split("\n")
                title = lines[0].strip() if lines else ""

                # Extract components (bulleted items)
                components = self._extract_components(cycle_content)

                # Extract expected test count
                expected_tests = self._extract_test_count(cycle_content)

                # Extract module hint
                module_hint = self._extract_module_hint(cycle_content)

                # Determine phase from position
                phase = self._find_phase_for_position(match.start(), phase_map)

                cycles.append(
                    {
                        "cycle_number": cycle_num,
                        "cycle_title": title,
                        "title": title,
                        "phase": phase,
                        "content": cycle_content,
                        "components": components,
                        "expected_tests": expected_tests,
                        "module_hint": module_hint,
                    }
                )

        return cycles

    def _build_phase_map(self, content: str) -> list[tuple[int, str]]:
        """Build a map of phase positions and names.

        Args:
            content: Raw spec file content.

        Returns:
            List of tuples (position, phase_name) sorted by position.
        """
        phase_map: list[tuple[int, str]] = []

        for match in self.PHASE_HEADER_PATTERN.finditer(content):
            phase_num = match.group(1)
            phase_title = match.group(2).strip()
            phase_name = f"Phase {phase_num}: {phase_title}"
            phase_map.append((match.start(), phase_name))

        return sorted(phase_map)

    def _find_phase_for_position(self, pos: int, phase_map: list[tuple[int, str]]) -> str:
        """Find the phase name for a given position in content.

        Args:
            pos: Position in content.
            phase_map: List of (position, phase_name) tuples.

        Returns:
            Phase name or empty string if not found.
        """
        if not phase_map:
            return ""

        # Find the latest phase header before this position
        current_phase = ""
        for phase_pos, phase_name in phase_map:
            if phase_pos <= pos:
                current_phase = phase_name
            else:
                break

        return current_phase

    def _extract_module_hint(self, content: str) -> str:
        """Extract module hint from TDD cycle content.

        Args:
            content: TDD cycle section content.

        Returns:
            Module hint path or empty string if not found.
        """
        # Look for "Module Hint:" pattern
        module_match = re.search(
            r"Module\s+Hint:\s*(.+?)$",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
        if module_match:
            return module_match.group(1).strip()

        # Look for path patterns in the content
        path_match = re.search(
            r"(?:backend|src)/(?:[\w/]+)/?",
            content,
        )
        if path_match:
            return path_match.group(0)

        return ""

    def _extract_components(self, content: str) -> list[str]:
        """Extract component list from TDD cycle content.

        Args:
            content: TDD cycle section content.

        Returns:
            List of component names.
        """
        components: list[str] = []
        # Match lines starting with - or bullet points
        component_matches = re.findall(r"^\s*[-*]\s+(.+)$", content, re.MULTILINE)
        for comp in component_matches:
            # Clean up component name
            cleaned = comp.strip()
            if cleaned and not cleaned.startswith("Tests:"):
                components.append(cleaned)
        return components

    def _extract_test_count(self, content: str) -> str:
        """Extract expected test count from TDD cycle content.

        Args:
            content: TDD cycle section content.

        Returns:
            Test count string (e.g., "8-10") or empty string if not found.
        """
        # Look for "Tests: X-Y" or similar patterns
        test_match = re.search(r"Tests?:\s*(\d+(?:-\d+)?)", content, re.IGNORECASE)
        if test_match:
            return test_match.group(1)
        return ""

    def _extract_module_structure(self, content: str) -> dict[str, Any]:
        """Extract MODULE STRUCTURE section from content.

        Args:
            content: Raw spec file content.

        Returns:
            Dictionary with base_path and files list.
        """
        result: dict[str, Any] = {"base_path": "", "files": []}

        match = self.MODULE_STRUCTURE_PATTERN.search(content)
        if not match:
            return result

        structure_content = match.group(1).strip()
        lines = structure_content.split("\n")

        # First non-empty line should be the base path
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Check if it's a path (contains / or ends with /)
                if "/" in stripped:
                    result["base_path"] = stripped.rstrip("/")
                    break

        # Extract file names (lines with .py extension)
        for line in lines:
            stripped = line.strip()
            # Remove comment portion first
            if "#" in stripped:
                stripped = stripped.split("#")[0].strip()
            # Check if it's a .py file
            if stripped.endswith(".py"):
                # Extract just the filename (first word if multiple)
                filename = stripped.split()[0] if " " in stripped else stripped
                if filename:
                    result["files"].append(filename)

        return result

    def _extract_module_api(self, content: str) -> dict[str, dict[str, Any]]:
        """Extract MODULE_API_SPECIFICATION section from spec.

        PLAN9: Returns dict mapping module paths to their export specifications.
        Format:
            src/auth/jwt_generator.py:
              exports:
                - JWTGenerator (class): description
              import_pattern: direct
              test_import: from src.auth.jwt_generator import JWTGenerator

        Returns empty dict if section not found (backward compatibility).
        """
        match = self.MODULE_API_PATTERN.search(content)
        if not match:
            return {}

        section = match.group(1).strip()
        result: dict[str, dict[str, Any]] = {}

        current_module: str | None = None
        current_spec: dict[str, Any] = {}

        for line in section.split("\n"):
            line = line.rstrip()

            # Skip empty lines and separators
            if not line or line.startswith("-" * 10):
                continue

            # Module path line (ends with .py:)
            if line.endswith(".py:") and not line.startswith(" "):
                # Save previous module if exists
                if current_module:
                    result[current_module] = current_spec
                current_module = line.rstrip(":")
                current_spec = {"exports": [], "import_pattern": "direct", "test_import": ""}

            # Indented content for current module
            elif current_module and line.startswith("  "):
                stripped = line.strip()

                if stripped.startswith("exports:"):
                    continue  # Skip the exports: header
                elif stripped.startswith("- "):
                    # Export entry: "- ExportName (type): description"
                    export_line = stripped[2:]  # Remove "- "
                    # Extract just the name (before type in parentheses)
                    if " (" in export_line:
                        export_name = export_line.split(" (")[0].strip()
                    else:
                        export_name = export_line.split(":")[0].strip()

                    # Validate export name
                    if self._is_valid_export_name(export_name):
                        current_spec["exports"].append(export_name)

                elif stripped.startswith("import_pattern:"):
                    current_spec["import_pattern"] = stripped.split(":", 1)[1].strip()

                elif stripped.startswith("test_import:"):
                    current_spec["test_import"] = stripped.split(":", 1)[1].strip()

        # Save last module
        if current_module:
            result[current_module] = current_spec

        return result

    def _is_valid_export_name(self, name: str) -> bool:
        """Validate export name is a valid Python identifier.

        PLAN9 Security: Prevents prompt injection via malformed export names.
        """
        pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        if not name or not pattern.match(name):
            return False
        if len(name) > 255:
            return False
        return True
