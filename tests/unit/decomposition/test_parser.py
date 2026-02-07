"""Tests for the spec parser module.

This module tests the SpecParser class and ParsedSpec dataclass,
verifying correct extraction of FR, NFR, AC, TDD cycles, and module structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.decomposition import ParsedSpec, SpecParseError, SpecParser

if TYPE_CHECKING:
    pass

# Inline test fixture content that matches original app_spec.txt structure
_FIXTURE_CONTENT = """\
SALESFORCE INTEGRATION SPECIFICATION
=====================================

FUNCTIONAL REQUIREMENTS
========================

FR-1: Authentication Setup
OAuth2 authentication with Salesforce API.
  FR-1.1: JWT Token Generation
  Generate JWT tokens for server-to-server auth.
  FR-1.2: Token Caching
  Cache tokens with TTL-based expiry.

FR-2: Data Upload
Upload commission data to Salesforce via REST API.

FR-3: Error Handling
Handle API errors with retries and circuit breakers.

FR-4: Rate Limiting
Implement rate limiting to respect Salesforce API limits.

FR-5: Batch Processing
Process records in configurable batch sizes.

FR-6: Field Mapping
Map internal fields to Salesforce object fields.

FR-7: Validation
Validate data before upload to Salesforce.

FR-8: Logging
Structured logging for audit trail.

FR-9: Configuration
External configuration for Salesforce connection settings.

NON-FUNCTIONAL REQUIREMENTS
============================

NFR-1: Performance
Response time under 200ms for single record operations.

NFR-2: Reliability
99.9% uptime with automatic failover.

NFR-3: Scalability
Handle up to 100k records per batch.

NFR-4: Security
All credentials encrypted at rest and in transit.

NFR-5: Observability
Prometheus metrics and structured JSON logging.

NFR-6: Maintainability
Code coverage above 90%.

ACCEPTANCE CRITERIA
====================

AC-1: Login Flow
GIVEN valid OAuth2 credentials
WHEN the client authenticates
THEN a valid access token is returned

AC-2: Token Refresh
GIVEN an expired token
WHEN a request is made
THEN the token is refreshed automatically

AC-3: Data Upload Success
GIVEN valid commission records
WHEN uploaded to Salesforce
THEN all records are created successfully

AC-4: Upload Error Handling
GIVEN an API error during upload
WHEN the error is transient
THEN the upload is retried up to 3 times

AC-5: Rate Limit Handling
GIVEN API rate limit is exceeded
WHEN a request fails with 429
THEN the client backs off exponentially

AC-6: Batch Processing
GIVEN 10000 records
WHEN batch processing is initiated
THEN records are processed in chunks of 200

AC-7: Field Mapping Validation
GIVEN a field mapping configuration
WHEN validation runs
THEN invalid mappings are reported

AC-8: Schema Validation
GIVEN incoming data
WHEN validated against schema
THEN invalid records are rejected with details

AC-9: Logging Format
GIVEN any operation
WHEN logged
THEN output is structured JSON

AC-10: Config Loading
GIVEN a configuration file
WHEN loaded
THEN all required fields are validated

AC-11: Connection Pooling
GIVEN multiple concurrent requests
WHEN connections are needed
THEN they are reused from the pool

AC-12: Metrics Export
GIVEN ongoing operations
WHEN metrics are scraped
THEN Prometheus format data is returned

AC-13: Graceful Shutdown
GIVEN a shutdown signal
WHEN in-flight requests exist
THEN they complete before exit

IMPLEMENTATION PLAN
====================

### Phase 0: Foundation

**TDD Cycle 1: Config Setup**
- ConfigLoader
- SettingsValidator
Tests: 8-10

**TDD Cycle 2: Auth Foundation**
- JWTGenerator
- TokenCache
Tests: 10-12

**TDD Cycle 3: HTTP Client**
- SalesforceHTTPClient
- RetryHandler
Tests: 8-10

### Phase 1: Core Features

**TDD Cycle 4: Data Uploader**
- SalesforceUploader
- BatchProcessor
Tests: 12-15

**TDD Cycle 5: Field Mapping**
- FieldMapper
- MappingValidator
Tests: 8-10

**TDD Cycle 6: Error Handling**
- CircuitBreaker
- ErrorClassifier
Tests: 10-12

### Phase 2: Integration

**TDD Cycle 7: Rate Limiter**
- RateLimiter
- BackoffStrategy
Tests: 8-10

**TDD Cycle 8: Validation Pipeline**
- SchemaValidator
- RecordValidator
Tests: 10-12

**TDD Cycle 9: Logging**
- StructuredLogger
- AuditTrail
Tests: 6-8

### Phase 3: Production Readiness

**TDD Cycle 10: Metrics**
- MetricsCollector
- PrometheusExporter
Tests: 8-10

**TDD Cycle 11: Connection Pool**
- ConnectionPool
- HealthChecker
Tests: 8-10

**TDD Cycle 12: Graceful Shutdown**
- ShutdownHandler
- RequestDrainer
Tests: 6-8

MODULE STRUCTURE
-----------------
backend/src/integrations/salesforce/
salesforce_uploader.py
config_loader.py
jwt_generator.py
field_mapper.py
rate_limiter.py
"""


class TestSpecParser:
    """Test class for SpecParser."""

    @pytest.fixture
    def parser(self) -> SpecParser:
        """Create a SpecParser instance."""
        return SpecParser()

    @pytest.fixture
    def fixture_path(self, tmp_path: Path) -> Path:
        """Create a temporary app_spec.txt file for testing."""
        spec_file = tmp_path / "app_spec.txt"
        spec_file.write_text(_FIXTURE_CONTENT)
        return spec_file

    @pytest.fixture
    def parsed_spec(self, parser: SpecParser, fixture_path: Path) -> ParsedSpec:
        """Parse the test fixture and return ParsedSpec."""
        return parser.parse(fixture_path)

    def test_parse_valid_app_spec_successfully(
        self, parser: SpecParser, parsed_spec: ParsedSpec
    ) -> None:
        """Test that parsing a valid app_spec.txt succeeds."""
        assert parsed_spec is not None
        assert parsed_spec.raw_content != ""
        assert len(parsed_spec.raw_content) > 0

    def test_extract_all_fr_sections(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of all FR-* sections (expect 9)."""
        fr_count = len(parsed_spec.functional_requirements)
        assert fr_count == 9, f"Expected 9 FR sections, got {fr_count}"

        # Verify FR IDs are correctly extracted
        fr_ids = [fr["id"] for fr in parsed_spec.functional_requirements]
        assert "FR-1" in fr_ids
        assert "FR-9" in fr_ids

    def test_extract_all_nfr_sections(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of all NFR-* sections (expect 6)."""
        nfr_count = len(parsed_spec.non_functional_requirements)
        assert nfr_count == 6, f"Expected 6 NFR sections, got {nfr_count}"

        # Verify NFR IDs are correctly extracted
        nfr_ids = [nfr["id"] for nfr in parsed_spec.non_functional_requirements]
        assert "NFR-1" in nfr_ids
        assert "NFR-6" in nfr_ids

    def test_extract_all_ac_sections(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of all AC-* sections (expect 13)."""
        ac_count = len(parsed_spec.acceptance_criteria)
        assert ac_count == 13, f"Expected 13 AC sections, got {ac_count}"

        # Verify AC IDs are correctly extracted
        ac_ids = [ac["id"] for ac in parsed_spec.acceptance_criteria]
        assert "AC-1" in ac_ids
        assert "AC-13" in ac_ids

    def test_extract_tdd_cycles(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of TDD cycles (expect 12+)."""
        tdd_count = len(parsed_spec.tdd_cycles)
        assert tdd_count >= 12, f"Expected at least 12 TDD cycles, got {tdd_count}"

        # Verify cycle numbers are correctly extracted
        cycle_numbers = [c["cycle_number"] for c in parsed_spec.tdd_cycles]
        assert 1 in cycle_numbers
        assert 12 in cycle_numbers

    def test_handle_missing_sections_gracefully(self, parser: SpecParser) -> None:
        """Test that missing sections result in empty lists, not errors."""
        # Create a minimal spec with only FR sections
        minimal_content = """
FR-1: Test Feature
This is a test feature description.
"""
        # Write to temp file
        temp_path = Path("/tmp/minimal_spec.txt")
        temp_path.write_text(minimal_content)

        try:
            result = parser.parse(temp_path)
            # Should have 1 FR but empty NFR, AC, and TDD cycles
            assert len(result.functional_requirements) == 1
            assert len(result.non_functional_requirements) == 0
            assert len(result.acceptance_criteria) == 0
            assert len(result.tdd_cycles) == 0
        finally:
            temp_path.unlink(missing_ok=True)

    def test_raise_spec_parse_error_for_nonexistent_file(self, parser: SpecParser) -> None:
        """Test that SpecParseError is raised for non-existent files."""
        with pytest.raises(SpecParseError) as exc_info:
            parser.parse(Path("/nonexistent/path/app_spec.txt"))
        assert "not found" in str(exc_info.value)

    def test_raise_spec_parse_error_for_empty_file(self, parser: SpecParser) -> None:
        """Test that SpecParseError is raised for empty files."""
        empty_path = Path("/tmp/empty_spec.txt")
        empty_path.write_text("")

        try:
            with pytest.raises(SpecParseError) as exc_info:
                parser.parse(empty_path)
            assert "empty" in str(exc_info.value)
        finally:
            empty_path.unlink(missing_ok=True)

    def test_extract_module_structure_paths(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of module structure with base path and files."""
        module = parsed_spec.module_structure
        assert module is not None

        # Check base path is extracted
        assert module.get("base_path") != ""
        assert "salesforce" in module.get("base_path", "").lower()

        # Check files list is populated
        files = module.get("files", [])
        assert len(files) > 0

        # Verify some expected files are present
        file_names = [f for f in files]
        assert any("uploader" in f.lower() for f in file_names)

    def test_handle_nested_subsections(self, parsed_spec: ParsedSpec) -> None:
        """Test extraction of nested subsections (FR-1.1, FR-1.2, etc.)."""
        # Find FR-1 which has subsections
        fr1 = next(
            (fr for fr in parsed_spec.functional_requirements if fr["id"] == "FR-1"),
            None,
        )
        assert fr1 is not None, "FR-1 not found"

        subsections = fr1.get("subsections", [])
        assert len(subsections) >= 2, f"Expected FR-1 subsections, got {len(subsections)}"

        # Verify subsection IDs
        sub_ids = [s["id"] for s in subsections]
        assert "1.1" in sub_ids or any("1.1" in sid for sid in sub_ids)

    def test_preserve_raw_content(self, parsed_spec: ParsedSpec) -> None:
        """Test that raw content is preserved in ParsedSpec."""
        assert parsed_spec.raw_content != ""
        # Verify it contains expected content markers
        assert "SALESFORCE" in parsed_spec.raw_content
        assert "FR-1" in parsed_spec.raw_content
        assert "NFR-1" in parsed_spec.raw_content
        assert "AC-1" in parsed_spec.raw_content

    def test_fr_contains_title_and_content(self, parsed_spec: ParsedSpec) -> None:
        """Test that FR sections contain both title and content."""
        for fr in parsed_spec.functional_requirements:
            assert "id" in fr, "FR missing 'id' field"
            assert "title" in fr, "FR missing 'title' field"
            assert "content" in fr, "FR missing 'content' field"
            assert fr["title"] != "", f"FR {fr['id']} has empty title"


class TestParsedSpec:
    """Test class for ParsedSpec dataclass."""

    def test_default_values_are_empty(self) -> None:
        """Test that ParsedSpec defaults to empty collections."""
        spec = ParsedSpec()
        assert spec.functional_requirements == []
        assert spec.non_functional_requirements == []
        assert spec.acceptance_criteria == []
        assert spec.tdd_cycles == []
        assert spec.module_structure == {}
        assert spec.raw_content == ""

    def test_parsed_spec_is_immutable_collections(self) -> None:
        """Test that ParsedSpec can be created with provided data."""
        spec = ParsedSpec(
            functional_requirements=[{"id": "FR-1", "title": "Test"}],
            non_functional_requirements=[{"id": "NFR-1", "title": "Perf"}],
            acceptance_criteria=[{"id": "AC-1", "title": "Basic"}],
            tdd_cycles=[{"cycle_number": 1, "title": "Config"}],
            module_structure={"base_path": "/test", "files": []},
            raw_content="test content",
        )
        assert len(spec.functional_requirements) == 1
        assert len(spec.non_functional_requirements) == 1
        assert len(spec.acceptance_criteria) == 1
        assert len(spec.tdd_cycles) == 1
        assert spec.module_structure["base_path"] == "/test"
        assert spec.raw_content == "test content"


class TestSpecParserEdgeCases:
    """Test edge cases for SpecParser."""

    @pytest.fixture
    def parser(self) -> SpecParser:
        """Create a SpecParser instance."""
        return SpecParser()

    def test_ac_extracts_gherkin_content(self, parser: SpecParser) -> None:
        """Test that AC sections extract Gherkin GIVEN/WHEN/THEN content."""
        content = """
AC-1: Test Acceptance Criteria
GIVEN a user is logged in
WHEN they click submit
THEN the form is saved
AND a confirmation is shown
"""
        temp_path = Path("/tmp/gherkin_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            assert len(result.acceptance_criteria) == 1
            ac = result.acceptance_criteria[0]
            assert "gherkin" in ac
            assert "GIVEN" in ac["gherkin"]
            assert "WHEN" in ac["gherkin"]
            assert "THEN" in ac["gherkin"]
        finally:
            temp_path.unlink(missing_ok=True)

    def test_tdd_cycle_extracts_test_count(self, parser: SpecParser) -> None:
        """Test that TDD cycles extract expected test counts."""
        content = """
TDD Cycle 1: Authentication
- JWT token generation
- Token caching
Tests: 8-10

TDD Cycle 2: Client API
- REST client
Tests: 12
"""
        temp_path = Path("/tmp/tdd_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            assert len(result.tdd_cycles) >= 2

            cycle1 = next((c for c in result.tdd_cycles if c["cycle_number"] == 1), None)
            assert cycle1 is not None
            assert cycle1["expected_tests"] == "8-10"

            cycle2 = next((c for c in result.tdd_cycles if c["cycle_number"] == 2), None)
            assert cycle2 is not None
            assert cycle2["expected_tests"] == "12"
        finally:
            temp_path.unlink(missing_ok=True)


class TestMalformedXMLHandling:
    """Test parser resilience to malformed or missing XML sections."""

    @pytest.fixture
    def parser(self) -> SpecParser:
        """Create a SpecParser instance."""
        return SpecParser()

    def test_missing_assumptions_section(self, parser: SpecParser) -> None:
        """Test that missing <assumptions> section doesn't break parsing."""
        content = """
FR-1: Test Feature
This is a test feature.

<dependencies>
- python >= 3.13
- pytest
</dependencies>
"""
        temp_path = Path("/tmp/no_assumptions_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse successfully with FR-1
            assert len(result.functional_requirements) == 1
            assert result.functional_requirements[0]["id"] == "FR-1"
        finally:
            temp_path.unlink(missing_ok=True)

    def test_missing_dependencies_section(self, parser: SpecParser) -> None:
        """Test that missing <dependencies> section doesn't break parsing."""
        content = """
FR-1: Test Feature
This is a test feature.

<assumptions>
- User is authenticated
- Database is available
</assumptions>
"""
        temp_path = Path("/tmp/no_dependencies_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse successfully
            assert len(result.functional_requirements) == 1
            assert result.functional_requirements[0]["id"] == "FR-1"
        finally:
            temp_path.unlink(missing_ok=True)

    def test_missing_error_catalog_section(self, parser: SpecParser) -> None:
        """Test that missing <error-catalog> section doesn't break parsing."""
        content = """
FR-1: Test Feature
This is a test feature with no error catalog.

NFR-1: Performance
Response time under 200ms.
"""
        temp_path = Path("/tmp/no_error_catalog_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse successfully with FR and NFR
            assert len(result.functional_requirements) == 1
            assert len(result.non_functional_requirements) == 1
        finally:
            temp_path.unlink(missing_ok=True)

    def test_unclosed_assumptions_tag(self, parser: SpecParser) -> None:
        """Test that unclosed <assumptions> tag is handled gracefully."""
        content = """
FR-1: Test Feature
This is a test feature.

<assumptions>
- User is authenticated
- Database is available

FR-2: Another Feature
This feature comes after the unclosed tag.
"""
        temp_path = Path("/tmp/unclosed_assumptions_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should still parse FRs (even if assumptions section is malformed)
            assert len(result.functional_requirements) >= 1
            # Verify we got at least FR-1
            fr_ids = [fr["id"] for fr in result.functional_requirements]
            assert "FR-1" in fr_ids
        finally:
            temp_path.unlink(missing_ok=True)

    def test_malformed_dependency_attributes(self, parser: SpecParser) -> None:
        """Test that malformed <dep> attributes don't crash parser."""
        content = """
FR-1: Test Feature
This is a test feature.

<dependencies>
<dep name="python" version>3.13</dep>
<dep name= version="1.0">pytest</dep>
<dep>no-attributes</dep>
</dependencies>

FR-2: Second Feature
Normal feature content.
"""
        temp_path = Path("/tmp/malformed_dep_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse FRs even with malformed dependency XML
            assert len(result.functional_requirements) >= 2
            fr_ids = [fr["id"] for fr in result.functional_requirements]
            assert "FR-1" in fr_ids
            assert "FR-2" in fr_ids
        finally:
            temp_path.unlink(missing_ok=True)

    def test_empty_error_catalog(self, parser: SpecParser) -> None:
        """Test that empty <error-catalog></error-catalog> is handled."""
        content = """
FR-1: Test Feature
This is a test feature.

<error-catalog></error-catalog>

NFR-1: Performance
Response time under 200ms.
"""
        temp_path = Path("/tmp/empty_error_catalog_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse successfully
            assert len(result.functional_requirements) == 1
            assert len(result.non_functional_requirements) == 1
        finally:
            temp_path.unlink(missing_ok=True)

    def test_nested_xml_in_content(self, parser: SpecParser) -> None:
        """Test that nested XML in content is preserved in raw_content."""
        content = """
FR-1: XML Processing Feature
This feature processes XML like <config><item>value</item></config>.

Example payload:
<payload>
  <data>test</data>
</payload>

FR-2: Another Feature
Normal content.
"""
        temp_path = Path("/tmp/nested_xml_spec.txt")
        temp_path.write_text(content)

        try:
            result = parser.parse(temp_path)
            # Should parse FRs correctly
            assert len(result.functional_requirements) == 2
            # Verify raw content preserves the nested XML
            assert "<config>" in result.raw_content
            assert "<item>value</item>" in result.raw_content
            assert "<payload>" in result.raw_content
            assert "<data>test</data>" in result.raw_content
        finally:
            temp_path.unlink(missing_ok=True)
